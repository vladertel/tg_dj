#!/usr/bin/python3
# -*- coding: UTF-8 -*-
import asyncio
import datetime
import logging
import platform
import time
import traceback
from itertools import chain
from typing import Optional, Callable, List, Tuple, NoReturn, Union

import peewee
from prometheus_client import Gauge

from core.AbstractFrontend import AbstractFrontend, FrontendUserInfo
from core.AbstractRadioEmitter import AbstractRadioEmitter
from downloaders.MasterDownloader import MasterDownloader
from .AbstractComponent import AbstractComponent
from .AbstractDownloader import AbstractDownloader
from .QueueManager import QueueManager
from .models import User, Request, Song, UserInfoMinimal, UserInfo


class UserQuotaReached(Exception):
    pass


class UserRequestQuotaReached(UserQuotaReached):
    pass


class UserBanned(Exception):
    pass


class PermissionDenied(Exception):
    pass


class DownloadFailed(Exception):
    pass


class Core:

    def __init__(self, config, components: List[Union[AbstractComponent]], downloader: MasterDownloader, loop=asyncio.get_event_loop()):
        """
        :param configparser.ConfigParser config:
        :param MasterDownloader downloader:
        :param asyncio.AbstractEventLoop loop:
        """
        self.config = config
        self.logger = logging.getLogger('tg_dj.core')
        self.logger.setLevel(getattr(logging, self.config.get("core", "verbosity", fallback="warning").upper()))

        self.isWindows = False
        if platform.system() == "Windows":
            self.isWindows = True

        # noinspection PyTypeChecker
        self.frontends: List[AbstractFrontend] = []
        self.downloader: MasterDownloader = downloader
        self.downloader.bind_core(self)
        # noinspection PyTypeChecker
        self.backend: AbstractRadioEmitter = None

        self.loop = loop
        self.current_track: Optional[Song] = None
        self.state_update_callbacks: List[Callable] = []

        self.queueManager = QueueManager(config)
        self.song_start_time = time.time()
        for component in components:
            component_added = False
            if issubclass(type(component), AbstractFrontend):
                # noinspection PyTypeChecker
                self.frontends.append(component)
                component_added = True

            if issubclass(type(component), AbstractRadioEmitter):
                if self.backend is not None:
                    raise ValueError("Currently I don't support multiple steamer")
                # noinspection PyTypeChecker
                self.backend: AbstractRadioEmitter = component
                component_added = True

            if issubclass(type(component), AbstractDownloader):
                raise ValueError("Currently I don't support downloaders passed with components, use MasterDownloader")

            if not component_added:
                self.logger.warning(f"Type of component ({component.__repr__()}) is not specified. You might want to subclass one")

            component.bind_core(self)

        if self.downloader is None:
            raise ValueError("MasterDownloader was not passed in")

        self.wait_task = None
        self.play_next_track()
        self.queue_rating_check_task = self.loop.create_task(self.watch_queue_rating())

        # noinspection PyArgumentList
        self.mon_active_users = Gauge('dj_active_users', 'Active users')
        self.mon_active_users.set_function(self.get_active_users_cnt)

        self.stud_board_user = User(id=-1, name=config.get("core", "fallback_user_name", fallback="Студсовет"))

    def update_config(self, config):
        # todo: IMPLEMENT ME
        pass

    def _notify_user(self, core_user_id: int, text: str):
        for frontend in self.frontends:
            if frontend.accept_user(core_user_id):
                frontend.notify_user(core_user_id, text)

    def get_user_infos(self, core_id: int) -> List[FrontendUserInfo]:
        user_infos = []
        for frontend in self.frontends:
            user_info = frontend.get_user_info(core_id)
            if user_info is not None:
                user_infos.append(user_info)
        return user_infos

    def cleanup(self):
        self.logger.debug("Cleaning up...")
        self.queue_rating_check_task.cancel()
        if self.current_track is not None:
            self.queueManager.play_next(self.current_track)
        self.queueManager.cleanup()
        # noinspection PyTypeChecker
        for module in self.frontends + [self.downloader, self.backend]:
            try:
                module.cleanup()
            except AttributeError:
                traceback.print_exc()

    def user_init_action(self):
        u = User.create()
        self.logger.info('New user#%d with name %s' % (u.id, u.name))
        return u.id

    @staticmethod
    def set_user_name(uid: int, name: str):
        u = User.get(id=uid)
        u.name = name
        u.save()

    def get_user(self, uid: int) -> Optional[User]:
        if uid == -1:
            return self.stud_board_user
        try:
            u = User.get(id=uid)
        except peewee.DoesNotExist:
            return None
        if u.banned:
            raise UserBanned
        return u

    @staticmethod
    def store_user_activity(user: User):
        user.last_activity = datetime.datetime.now()
        user.save()

    @staticmethod
    def get_active_users_cnt() -> int:
        active_users = User.filter(User.last_activity > datetime.datetime.now() - datetime.timedelta(minutes=60))
        return active_users.count()

    def check_requests_quota(self, user: User) -> bool:
        """
        returns: true -> user has quota
                 true -> user does not have quota
        """
        interval = self.config.getint("core", "user_requests_limit_interval", fallback=600)
        limit = self.config.getint("core", "user_requests_limit", fallback=10)
        check_interval_start = datetime.datetime.now() - datetime.timedelta(
            seconds=interval)
        count = Request.select().where(Request.user == user, Request.time >= check_interval_start).count()
        if count >= limit:
            return False
        else:
            return True

    def check_song_rating(self, song: Song) -> bool:
        active_users_cnt = self.get_active_users_cnt()
        active_haters_cnt = User\
            .filter(User.id << song.haters)\
            .filter(User.last_activity > datetime.datetime.now() - datetime.timedelta(minutes=60))\
            .count()

        if self.check_song_rating_values(active_users_cnt, active_haters_cnt):
            return True

        self.logger.info("Song #%d (%s) has bad rating (haters: %d, active: %d)",
                         song.id, song.full_title(), active_haters_cnt, active_users_cnt)
        return False

    def check_song_rating_values(self, all_users: int, voted_users: int):
        rating_threshold = self.config.getfloat("core", "song_rating_threshold", fallback=0.3)
        rating_min_cnt = self.config.getint("core", "song_rating_cnt_min", fallback=3)
        return not (voted_users >= rating_min_cnt and voted_users / all_users >= rating_threshold)

    def add_state_update_callback(self, fn: Callable):
        self.state_update_callbacks.append(fn)

    async def download_action(self, user_id: int, text=None, result=None, file=None, progress_callback=None) -> Tuple[Song, int, int]:
        user = self.get_user(user_id)
        progress_callback = progress_callback or (lambda _state: None)

        if not self.check_requests_quota(user) and not user.superuser:
            self.logger.debug("Request quota reached by user#%d (%s)" % (user.id, user.name))
            raise UserRequestQuotaReached

        if text:
            self.logger.debug("New download (%s) from user#%d (%s)" % (text, user.id, user.name))
            response = await self.downloader.download("text", text, progress_callback)
        elif result:
            self.logger.debug("New download (%s) from user#%d (%s)" % (str(result), user.id, user.name))
            response = await self.downloader.download("search_result", result, progress_callback)
        elif file:
            self.logger.debug("New file #%s from user#%d (%s)" % (file["id"], user.id, user.name))
            response = await self.downloader.download("file", file, progress_callback)
        else:
            self.logger.debug("No data for downloader (%s)" % (str(locals())))
            raise ValueError("No data for downloader")

        self.logger.debug("Response from downloader: (%s)" % str(response))
        if response is None:
            raise DownloadFailed()
        file_path, title, artist, duration = response

        if self.isWindows:
            file_path = file_path[2:]

        author = User.get(id=int(user_id))
        Request.create(user=author, text=(artist or "") + " - " + (title or ""))
        if not author.superuser and not self.check_requests_quota(author):
            raise UserRequestQuotaReached

        track = self.queueManager.add_track(file_path, title, artist, duration, user_id)
        self.store_user_activity(user)

        if not self.queueManager.is_in_queue(user_id):
            self.queueManager.add_to_queue(user_id)

        local_position, global_position = self.queueManager.get_track_position(track)

        return track, local_position, global_position

    async def search_action(self, user_id: int, query: str, message_callback: Optional[Callable[[str], NoReturn]]=None, limit: int=1000):
        user = self.get_user(user_id)
        message_callback = message_callback or (lambda _state: None)

        self.logger.debug("New search query \"%s\" from user#%d (%s)" % (query, user.id, user.name))
        return await self.downloader.search(query, message_callback, limit)

    async def wait_until_track_end(self, track: Song):
        # fixme: magic number?!
        await asyncio.sleep(track.duration - 0.3)
        self.play_next_track()

    def get_song_progress(self) -> int:
        return int(time.time() - self.song_start_time)

    def get_current_song(self) -> Song:
        return self.current_track

    def play_next_track(self):
        if self.wait_task is not None:
            self.wait_task.cancel()

        active_users = User.filter(User.last_activity > datetime.datetime.now() - datetime.timedelta(minutes=60))
        active_users_cnt = active_users.count()

        while True:
            track = self.queueManager.pop_first_track()
            if track is None:
                self.backend.stop()
                return

            active_haters_cnt = active_users.filter(User.id << track.haters).count()
            if self.check_song_rating_values(active_users_cnt, active_haters_cnt):
                break

            self.logger.info("Song #%d (%s) have been skipped" % (track.id, track.full_title()))
            self._notify_user(
                track.user_id,
                "⚠️ Ваш трек удалён из очереди, так как он не нравится другим пользователям:\n%s"
                % track.full_title(),
            )

        self.logger.debug("New track rating: %d" % len(track.haters))

        next_track = self.queueManager.get_first_track()

        self.backend.switch_track(track)

        self.current_track = track
        self.song_start_time = time.time()

        user_curr_id = track.user_id
        if user_curr_id == -1:
            user_curr_id = None

        user_next_id = None if next_track is None else next_track.user_id
        if user_next_id == -1:
            user_next_id = None

        if user_curr_id is not None and user_next_id is not None and user_curr_id == user_next_id:
            self._notify_user(
                user_curr_id,
                "🎶 Запускаю ваш трек:\n%s\n\n🕓 Следующий тоже ваш:\n%s" % (track.full_title(), next_track.full_title()),
            )
        else:
            if user_next_id is not None:
                self._notify_user(user_next_id, "🕓 Следующий трек ваш:\n%s" % next_track.full_title())
            if user_curr_id is not None:
                self._notify_user(user_curr_id, "🎶 Запускаю ваш трек:\n%s" % track.full_title())

        for fn in self.state_update_callbacks:
            fn(track)

        track.fetch_lyrics()

        self.wait_task = self.loop.create_task(self.wait_until_track_end(track))

        return track, next_track

    # def track_end_event(self):
    #     # noinspection PyBroadException
    #     try:
    #         self.play_next_track()
    #     except Exception:
    #         traceback.print_exc()

    def switch_track(self, user_id):
        user = self.get_user(user_id)
        current_song = self.current_track

        if not user.superuser and not (current_song is not None and user_id == current_song.user_id):
            raise PermissionDenied()

        self.play_next_track()

    def delete_track(self, user_id, song_id):
        user = self.get_user(user_id)

        if not user.superuser:
            song = self.queueManager.get_track(song_id)
            if user.id != song.user_id:
                raise PermissionDenied()

        position = self.queueManager.remove_track(song_id)

        return position

    def raise_track(self, user_id, track_id):
        user = self.get_user(user_id)

        if not user.superuser:
            track = self.queueManager.get_track(track_id)
            if user.id != track.user_id:
                raise PermissionDenied()

        self.queueManager.raise_track(track_id)

    def raise_user(self, user_id: int, handled_user_id: int):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        self.queueManager.raise_user_in_queue(handled_user_id)

    def stop_playback(self, user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        self.queueManager.play_next(self.current_track)
        self.backend.stop()

        for fn in self.state_update_callbacks:
            fn(None)

    def ban_user(self, user_id, handled_user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        try:
            handled_user = User.get(id=handled_user_id)
            handled_user.banned = True
            handled_user.save()
            self.logger.debug("User banned")
        except KeyError:
            self.logger.error("User does not exists: can't ban user")
            raise KeyError("User does not exists: can't ban user")

    def unban_user(self, user_id, handled_user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        try:
            handled_user = User.get(id=handled_user_id)
            handled_user.banned = False
            handled_user.save()
            self.logger.debug("User unbanned")
        except KeyError:
            self.logger.error("User does not exists: can't unban user")
            raise KeyError("User does not exists: can't unban user")

    def get_state(self, user_id):
        user = self.get_user(user_id)
        current_song = self.current_track
        next_song = self.queueManager.get_first_track()
        user_tracks = self.queueManager.get_user_tracks(user_id)
        return {
            "queue_len": self.queueManager.get_users_queue_length(),
            "current_song": current_song,
            "current_user": self.get_user(current_song.user_id) if current_song else None,
            "current_song_progress": self.get_song_progress(),
            "next_song": next_song,
            "next_user": self.get_user(next_song.user_id) if next_song else None,
            "my_songs": {self.queueManager.get_track_position(t)[1]: t for t in user_tracks},
            "superuser": user.superuser,
            "me": user,
        }

    def get_queue(self, user_id, offset=0, limit=0):
        users_cnt = self.queueManager.get_users_queue_length()

        tracks = self.queueManager.get_queue_tracks(offset, limit)
        first_tracks = self.queueManager.get_queue_tracks(0, users_cnt)
        for track in chain(tracks, first_tracks):
            track.author = self.get_user_info_minimal(track.user_id).info

        return {
            "first_tracks": first_tracks,
            "list": tracks,
            "users_cnt": users_cnt,
            "tracks_cnt": self.queueManager.get_tracks_queue_length(),
            "is_own_tracks": any(track.user_id == user_id for track in tracks)
        }

    def get_song_info(self, user_id, song_id):
        user = self.get_user(user_id)

        track = self.queueManager.get_track(song_id)
        local_position, global_position = self.queueManager.get_track_position(track)

        # TODO: Return extra info for superuser

        return {
            "song": track,
            "hated": user_id in track.haters if track else False,
            "local_position": local_position,
            "global_position": global_position,
            "superuser": user.superuser
        }

    def enqueue(self, user_id):
        position = self.queueManager.add_to_queue(user_id)
        if position is None:
            self._notify_user(
                user_id, "Прежде, чем вставать в очередь, нужно добавить в плейлист хотя бы один трек"
            )
        else:
            self._notify_user(
                user_id, "Ваша позиция в очереди: %d" % position
            )
        return position

    def vote_song(self, user_id, sign, song_id):
        user = self.get_user(user_id)
        if sign == "up":
            self.queueManager.vote_up(user_id, song_id)
        elif sign == "down":
            self.queueManager.vote_down(user_id, song_id)
        else:
            raise ValueError("Sign value should be either 'up' or 'down'")

        self.store_user_activity(user)

    async def watch_queue_rating(self):
        while True:
            await asyncio.sleep(30)
            for song in self.queueManager.get_queue_tracks():
                if self.check_song_rating(song):
                    continue

                self.queueManager.remove_from_queue(song.id)
                self.logger.info("Song #%d (%s) have been removed from queue", song.id, song.full_title())
                self._notify_user(
                    song.user_id,
                    "⚠️ Ваш трек удалён из очереди, так как он не нравится другим пользователям:\n%s"
                    % song.full_title(),
                )

    def broadcast_message(self, author_id, message):
        author = self.get_user(author_id)

        if not author.superuser:
            raise PermissionDenied()

        users = User.select()
        for user in users:
            self._notify_user(user.id, "✉️ Сообщение от администратора\n\n%s" % message)

    def get_users(self, user_id, offset=0, limit=0):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        users_cnt = User.select().count()
        if users_cnt == 0:
            return {"list": [], "cnt": 0}

        if limit == 0:
            users = User.select().offset(offset)
        else:
            users = User.select().offset(offset).limit(limit)

        return {
            "list": users,
            "cnt": users_cnt,
        }

    def get_user_info(self, user_id: int, handled_user_id: int) -> UserInfo:
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        if handled_user_id == -1:
            handled_user = self.stud_board_user
            requests = []
            counter = 0
        else:
            handled_user = User.get(id=handled_user_id)
            requests = Request.select().filter(Request.user == handled_user).order_by(-Request.time).limit(10)
            counter = Request.select().filter(Request.user == handled_user).count()

        tracks = self.queueManager.get_user_tracks(handled_user_id)
        return UserInfo(handled_user, {self.queueManager.get_track_position(t)[1]: t for t in tracks}, counter, [r for r in requests])

    def get_user_info_minimal(self, handled_user_id: int) -> UserInfoMinimal:
        if handled_user_id == -1:
            handled_user: User = self.stud_board_user
        else:
            handled_user: User = User.get(id=handled_user_id)

        tracks = self.queueManager.get_user_tracks(handled_user_id)
        return UserInfoMinimal(handled_user, {self.queueManager.get_track_position(t)[1]: t for t in tracks})
