#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import peewee
import json
import os
import asyncio

import datetime
import platform
import traceback
import logging

from prometheus_client import Gauge

from .scheduler import Scheduler
from .models import User, Request


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


class DjBrain:

    def __init__(self, config, frontend, downloader, backend):
        """
        :param configparser.ConfigParser config:
        :param frontend:
        :param downloader:
        :param backend:
        """
        self.config = config
        self.logger = logging.getLogger('tg_dj.core')
        self.logger.setLevel(getattr(logging, self.config.get("core", "verbosity", fallback="warning").upper()))

        self.isWindows = False
        if platform.system() == "Windows":
            self.isWindows = True
        self.frontend = frontend
        self.downloader = downloader
        self.backend = backend

        self.scheduler = Scheduler(config)

        self.loop = asyncio.get_event_loop()

        self.frontend.bind_core(self)
        self.downloader.bind_core(self)
        self.backend.bind_core(self)

        self.state_update_callbacks = []
        self.play_next_track()
        self.queue_rating_check_task = self.loop.create_task(self.watch_queue_rating())

        # noinspection PyArgumentList
        self.mon_active_users = Gauge('dj_active_users', 'Active users')
        self.mon_active_users.set_function(self.get_active_users_cnt)

    def cleanup(self):
        self.logger.debug("Cleaning up...")
        self.queue_rating_check_task.cancel()
        self.scheduler.play_next(self.backend.get_current_song())
        self.scheduler.cleanup()

    def user_init_action(self):
        u = User.create()
        self.logger.info('New user#%d with name %s' % (u.id, u.name))
        return u.id

    @staticmethod
    def set_user_name(uid, name):
        u = User.get(id=uid)
        u.name = name
        u.save()

    @staticmethod
    def get_user(uid):
        try:
            u = User.get(id=uid)
        except peewee.DoesNotExist:
            return None
        if u.banned:
            raise UserBanned
        return u

    @staticmethod
    def store_user_activity(user):
        user.last_activity = datetime.datetime.now()
        user.save()

    @staticmethod
    def get_active_users_cnt():
        active_users = User.filter(User.last_activity > datetime.datetime.now() - datetime.timedelta(minutes=60))
        return active_users.count()

    def check_requests_quota(self, user):
        interval = self.config.getint("core", "user_requests_limit_interval", fallback=600)
        limit = self.config.getint("core", "user_requests_limit", fallback=10)
        check_interval_start = datetime.datetime.now() - datetime.timedelta(
            seconds=interval)
        count = Request.select().where(Request.user == user, Request.time >= check_interval_start).count()
        if count >= limit:
            return False
        else:
            return True

    def check_song_rating(self, song):
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

    def check_song_rating_values(self, all_users, voted_users):
        rating_threshold = self.config.getfloat("core", "song_rating_threshold", fallback=0.3)
        rating_min_cnt = self.config.getint("core", "song_rating_cnt_min", fallback=3)
        return not (voted_users >= rating_min_cnt and voted_users / all_users >= rating_threshold)

    def add_state_update_callback(self, fn):
        self.state_update_callbacks.append(fn)

    async def download_action(self, user_id, text=None, result=None, file=None, progress_callback=None):
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

        song, position = self.scheduler.push_track(file_path, title, artist, duration, user_id)
        self.store_user_activity(user)

        if self.backend.now_playing is None:
            self.play_next_track()

        return song, position

    async def search_action(self, user_id, query, message_callback=None):
        user = self.get_user(user_id)
        message_callback = message_callback or (lambda _state: None)

        self.logger.debug("New search query \"%s\" from user#%d (%s)" % (query, user.id, user.name))
        return await self.downloader.search(query, message_callback)

    def play_next_track(self):
        active_users = User.filter(User.last_activity > datetime.datetime.now() - datetime.timedelta(minutes=60))
        active_users_cnt = active_users.count()

        while True:
            track = self.scheduler.pop_first_track()
            if track is None:
                return

            active_haters_cnt = active_users.filter(User.id << track.haters).count()
            if self.check_song_rating_values(active_users_cnt, active_haters_cnt):
                break

            self.logger.info("Song #%d (%s) have been skipped" % (track.id, track.full_title()))
            self.frontend.notify_user(
                track.user_id,
                "⚠️ Ваш трек удалён из очереди, так как он не нравится другим пользователям:\n%s"
                % track.full_title(),
            )

        self.logger.debug("New track rating: %d" % len(track.haters))

        next_track = self.scheduler.get_next_song()

        self.backend.switch_track(track)

        json_file_path = os.path.join(os.getcwd(), "web", "dynamic", "current_song_info.json")
        with open(json_file_path, 'w') as json_file:
            data_to_save = json.dumps(track.to_dict())
            json_file.write(data_to_save)

        user_curr_id = track.user_id
        user_next_id = None if next_track is None else next_track.user_id

        if user_curr_id is not None and user_next_id is not None and user_curr_id == user_next_id:
            self.frontend.notify_user(
                user_curr_id,
                "🎶 Запускаю ваш трек:\n%s\n\n🕓 Следующий тоже ваш:\n%s" % (track.full_title(), next_track.full_title()),
            )
        else:
            if user_next_id is not None:
                self.frontend.notify_user(user_next_id, "🕓 Следующий трек ваш:\n%s" % next_track.full_title())
            if user_curr_id is not None:
                self.frontend.notify_user(user_curr_id, "🎶 Запускаю ваш трек:\n%s" % track.full_title())

        for fn in self.state_update_callbacks:
            fn(track)

        return track, next_track

    def track_end_event(self):
        try:
            self.play_next_track()
        except:
            traceback.print_exc()

    def switch_track(self, user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        self.play_next_track()

    def delete_track(self, user_id, song_id):
        user = self.get_user(user_id)

        if not user.superuser:
            song, _ = self.scheduler.get_song(song_id)
            if user.id != song.user_id:
                raise PermissionDenied()

        position = self.scheduler.remove_from_queue(song_id)

        return position

    def raise_track(self, user_id, song_id):
        user = self.get_user(user_id)

        if not user.superuser:
            song, _ = self.scheduler.get_song(song_id)
            if user.id != song.user_id:
                raise PermissionDenied()

        self.scheduler.raise_track(song_id)

    def stop_playback(self, user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        self.scheduler.play_next(self.backend.get_current_song())
        self.backend.stop()

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
        current_song = self.backend.get_current_song()
        next_song = self.scheduler.get_next_song()
        return {
            "queue_len": self.scheduler.queue_length(),
            "current_song": current_song,
            "current_user": self.get_user(current_song.user_id) if current_song else None,
            "current_song_progress": self.backend.get_song_progress(),
            "next_song": next_song,
            "next_user": self.get_user(next_song.user_id) if next_song else None,
            "my_songs": {p: s for p, s in enumerate(self.scheduler.get_queue()) if s.user_id == user_id},
            "superuser": user.superuser,
        }
    # TODO: Limit my_songs length?

    def get_queue(self, _user_id, offset=0, limit=0):
        return {
            "list": self.scheduler.get_queue(offset, limit),
            "cnt": self.scheduler.get_queue_length(),
        }

    def get_song_info(self, user_id, song_id):
        user = self.get_user(user_id)

        (song, position) = self.scheduler.get_song(song_id)

        # TODO: Return superuser extra info

        return {
            "song": song,
            "hated": user_id in song.haters if song else False,
            "position": position,
            "superuser": user.superuser
        }

    def vote_song(self, user_id, sign, song_id):
        user = self.get_user(user_id)
        if sign == "up":
            self.scheduler.vote_up(user_id, song_id)
        elif sign == "down":
            self.scheduler.vote_down(user_id, song_id)
        else:
            raise ValueError("Sign value should be either 'up' or 'down'")

        self.store_user_activity(user)

    async def watch_queue_rating(self):
        while True:
            await asyncio.sleep(30)
            for song in self.scheduler.get_queue()[:]:
                if self.check_song_rating(song):
                    continue

                self.scheduler.remove_from_queue(song.id)
                self.logger.info("Song #%d (%s) have been removed from queue", song.id, song.full_title())
                self.frontend.notify_user(
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
            self.frontend.notify_user(user.id, "✉️ Сообщение от администратора\n\n%s" % message)

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

    def get_user_info(self, user_id, handled_user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        handled_user = self.get_user(handled_user_id)
        requests = Request.select().filter(Request.user == handled_user).order_by(-Request.time).limit(10)
        counter = Request.select().filter(Request.user == handled_user).count()

        return {
            "info": handled_user,
            "last_requests": [r for r in requests],
            "total_requests": counter,
        }
