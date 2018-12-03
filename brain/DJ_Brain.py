#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import peewee
import json
import os
import asyncio

import datetime
import platform
import traceback

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

    def __init__(self, frontend, downloader, backend):
        self.isWindows = False
        if platform.system() == "Windows":
            self.isWindows = True
        self.frontend = frontend
        self.downloader = downloader
        self.backend = backend

        self.scheduler = Scheduler()

        self.loop = asyncio.get_event_loop()

        self.frontend.bind_core(self)
        self.downloader.bind_core(self)
        self.backend.bind_core(self)

        self.state_update_callbacks = []

        self.play_next_track()

        self.queue_rating_check_task = self.loop.create_task(self.watch_queue_rating())

    def cleanup(self):
        print("DEBUG [Bot]: Cleaning up...")
        self.queue_rating_check_task.cancel()
        self.scheduler.play_next(self.backend.get_current_song())
        self.scheduler.cleanup()

    @staticmethod
    def user_init_action():
        u = User.create()
        print('INFO [Core]: New user#%d with name %s' % (u.id, u.name))
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

    def add_state_update_callback(self, fn):
        self.state_update_callbacks.append(fn)

    async def download_action(self, user_id, text=None, result=None, file=None, progress_callback=None):
        user = self.get_user(user_id)
        progress_callback = progress_callback or (lambda _state: None)

        if not user.check_requests_quota() and not user.superuser:
            print("DEBUG [Core]: Request quota reached by user#%d (%s)" % (user.id, user.name))
            raise UserRequestQuotaReached

        if text:
            print("DEBUG [Core]: New download (%s) from user#%d (%s)" % (text, user.id, user.name))
            response = await self.downloader.download("text", text, progress_callback)
        elif result:
            print("DEBUG [Core]: New download (%s) from user#%d (%s)" % (str(result), user.id, user.name))
            response = await self.downloader.download("search_result", result, progress_callback)
        elif file:
            print("DEBUG [Core]: New file #%s from user#%d (%s)" % (file["id"], user.id, user.name))
            response = await self.downloader.download("file", file, progress_callback)
        else:
            print("ERROR [Core]: No data for downloader (%s)" % (str(locals())))
            raise ValueError("No data for downloader")

        print("DEBUG [Core]: Response from downloader: (%s)" % str(response))
        if response is None:
            raise DownloadFailed()
        file_path, title, artist, duration = response

        if self.isWindows:
            file_path = file_path[2:]

        author = User.get(id=int(user_id))
        Request.create(user=author, text=(artist or "") + " - " + (title or ""))
        if not author.superuser and not author.check_requests_quota():
            raise UserRequestQuotaReached

        song, position = self.scheduler.push_track(file_path, title, artist, duration, user_id)
        self.store_user_activity(user)

        if self.backend.now_playing is None:
            self.play_next_track()

        return song, position

    async def search_action(self, user_id, query, message_callback=None):
        user = self.get_user(user_id)
        message_callback = message_callback or (lambda _state: None)

        print("DEBUG [Core]: New search query \"%s\" from user#%d (%s)" % (query, user.id, user.name))
        return await self.downloader.search(query, message_callback)

    def play_next_track(self):
        while True:
            track = self.scheduler.pop_first_track()
            if track is None:
                return
            if track.check_rating():
                break

            print("INFO [Core]: Song #%d (%s) have been skipped" % (track.id, track.full_title()))
            self.frontend.notify_user(
                "⚠️ Ваш трек удалён из очереди, так как он не нравится другим пользователям:\n%s"
                % track.full_title(),
                track.user_id
            )

        print("DEBUG [Core]: New track rating: %d" % len(track.haters))

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
                "🎶 Запускаю ваш трек:\n%s\n\n🕓 Следующий тоже ваш:\n%s" % (track.full_title(), next_track.full_title()),
                user_curr_id
            )
        else:
            if user_next_id is not None:
                self.frontend.notify_user("🕓 Следующий трек ваш:\n%s" % next_track.full_title(), user_next_id)
            if user_curr_id is not None:
                self.frontend.notify_user("🎶 Запускаю ваш трек:\n%s" % track.full_title(), user_curr_id)

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
            print("DEBUG [Core]: User banned")
        except KeyError:
            print("ERROR [Core]: User does not exists: can't ban user")
            raise KeyError("User does not exists: can't ban user")

    def unban_user(self, user_id, handled_user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        try:
            handled_user = User.get(id=handled_user_id)
            handled_user.banned = False
            handled_user.save()
            print("DEBUG [Core]: User unbanned")
        except KeyError:
            print("ERROR [Core]: User does not exists: can't unban user")
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
                if song.check_rating():
                    continue

                self.scheduler.remove_from_queue(song.id)
                print("INFO [Core]: Song #%d (%s) have been removed from queue" % (song.id, song.full_title()))
                self.frontend.notify_user(
                    "⚠️ Ваш трек удалён из очереди, так как он не нравится другим пользователям:\n%s"
                    % song.full_title(),
                    song.user_id
                )

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
