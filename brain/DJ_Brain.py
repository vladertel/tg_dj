#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import peewee
import json
import os
import asyncio

import datetime
from threading import Thread
import platform

from .config import *
from .scheduler import Scheduler

from utils import make_endless_unfailable


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


db = peewee.SqliteDatabase("db/dj_brain.db")


class BaseModel(peewee.Model):
    class Meta:
        database = db


class User(BaseModel):
    id = peewee.PrimaryKeyField()
    name = peewee.TextField(null=True)
    banned = peewee.BooleanField(default=False)
    superuser = peewee.BooleanField(default=False)

    def check_requests_quota(self):
        check_interval_start = datetime.datetime.now() - datetime.timedelta(seconds=USER_REQUESTS_THRESHOLD_INTERVAL)
        count = Request.select().where(Request.user == self, Request.time >= check_interval_start).count()
        if count >= USER_REQUESTS_THRESHOLD_VALUE:
            return False
        else:
            return True


class Request(BaseModel):
    user = peewee.ForeignKeyField(User)
    text = peewee.CharField()
    time = peewee.DateTimeField(default=datetime.datetime.now)


db.connect()


def users_from_json(self, objecta):
    for req in objecta['past_requests']:
        self.past_requests.append(
            Request(req['user'],
                    req['text'],
                    datetime.datetime.utcfromtimestamp(req['time']) + datetime.timedelta(hours=3))
        )
    for req in objecta['recent_requests']:
        self.recent_requests.append(
            Request(req['user'],
                    req['text'],
                    datetime.datetime.utcfromtimestamp(req['time']) + datetime.timedelta(hours=3))
        )


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

        self.downloader_thread = Thread(daemon=True, target=self.downloader_listener)
        self.backend_thread = Thread(daemon=True, target=self.backend_listener)

        self.downloader_thread.start()
        self.backend_thread.start()

        self.play_next_track()

        self.request_futures = {}
        self.request_counter = 0

        self.loop.run_forever()
        print("FATAL [Bot]: Polling loop ended")
        self.loop.close()

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

    async def download_action(self, user_id, text=None, result=None, file=None, progress_callback=None):
        user = self.get_user(user_id)

        if not user.check_requests_quota() and not user.superuser:
            print("DEBUG [Core]: Request quota reached by user#%d (%s)" % (user.id, user.name))
            raise UserRequestQuotaReached

        if text:
            print("DEBUG [Core]: New download (%s) from user#%d (%s)" % (text, user.id, user.name))
            response = await self.call_downloader({
                "action": "download",
                "text": text,
                "progress_callback": progress_callback or (lambda _state: None)
            })
        elif result:
            print("DEBUG [Core]: New download %s#%s from user#%d (%s)" % (result["downloader"], result["id"],
                                                                          user.id, user.name))
            response = await self.call_downloader({
                "action": "download",
                "downloader": result["downloader"],
                "result_id": result["id"],
                "progress_callback": progress_callback or (lambda _state: None)
            })
        elif file:
            print("DEBUG [Core]: New file #%s from user#%d (%s)" % (file["id"], user.id, user.name))
            response = await self.call_downloader({
                "action": "download",
                "file": file["id"],
                "duration": file["duration"],
                "file_size": file["size"],
                "file_info": file["info"],
                "artist": file["artist"],
                "title": file["title"],
                "progress_callback": progress_callback or (lambda _state: None)
            })
        else:
            print("ERROR [Core]: No data for downloader (%s)" % (str(locals())))
            raise ValueError("No data for downloader")

        print("DEBUG [Core]: Response from downloader: (%s)" % str(response))

        path = response['path']
        if self.isWindows:
            path = path[2:]

        author = User.get(id=int(user_id))
        Request.create(user=author, text=response['artist'] + " - " + response['title'])
        if author.check_requests_quota() or author.superuser:
            response["position"] = self.scheduler.push_track(
                path, response['title'], response['artist'], response['duration'], user_id
            )
        if not self.backend.is_playing:
            self.play_next_track()

        return response

    async def search_action(self, user_id, query):
        user = self.get_user(user_id)
        print("DEBUG [Core]: New search query \"%s\" from user#%d (%s)" % (query, user.id, user.name))
        return await self.call_downloader({
            "action": "search",
            "query": query,
        })

    def call_downloader(self, request):
        self.request_counter += 1
        request_id = self.request_counter
        request["request_id"] = request_id
        self.downloader.input_queue.put(request)

        loop = asyncio.get_event_loop()
        f = asyncio.Future(loop=loop)
        self.request_futures[request_id] = {
            "future": f,
            "loop": loop,
        }
        return f

    # DOWNLOADER QUEUE
    @make_endless_unfailable
    def downloader_listener(self):
        task = self.downloader.output_queue.get()

        if "request_id" in task:
            rid = task["request_id"]
            if rid not in self.request_futures:
                print('ERROR [Core]: Response to unknown request#%d: %s' % (task["request_id"], str(task)))
                return
            if task["state"] == "error":
                self.request_futures[rid]["loop"].call_soon_threadsafe(
                    self.send_exception_to_future, task, DownloadFailed(task["message"])
                )
            else:
                self.request_futures[rid]["loop"].call_soon_threadsafe(
                    self.send_result_to_future, task
                )

    def send_result_to_future(self, task):
        self.request_futures[task["request_id"]]["future"].set_result(task)
        del self.request_futures[task["request_id"]]

    def send_exception_to_future(self, task, exception):
        print('ERROR [Core]: Exception in future#%d: %s' % (task["request_id"], str(exception)))
        self.request_futures[task["request_id"]]["future"].set_exception(exception)
        del self.request_futures[task["request_id"]]

    @make_endless_unfailable
    def backend_listener(self):
        task = self.backend.output_queue.get()
        action = task['action']
        if action == "song_finished":
            self.play_next_track()
        else:
            print('ERROR [Core]: Message not supported:', str(task))
        self.backend.output_queue.task_done()

    def play_next_track(self):
        track = self.scheduler.pop_first_track()
        next_track = self.scheduler.get_next_song()
        if track is None:
            return

        next_track_task = {
            "action": "play_song",
            "song": track,
        }

        self.backend.input_queue.put(next_track_task)

        json_file_path = os.path.join(os.getcwd(), "web", "dynamic", "current_song_info.json")
        with open(json_file_path, 'w') as json_file:
            data_to_save = json.dumps(track.__dict__())
            json_file.write(data_to_save)

        user_curr_id = track.user_id
        user_next_id = None if next_track is None else next_track.user_id

        if user_curr_id is not None and user_next_id is not None and user_curr_id == user_next_id:
            self.frontend.notify_user(
                "Играет %s\n\nСледующий трек тоже ваш!\nБудет играть %s" % (track.full_title(), next_track.full_title()),
                user_curr_id
            )
        else:
            if user_next_id is not None:
                self.frontend.notify_user("Следующий трек ваш!\nБудет играть %s" % next_track.full_title(), user_next_id)
            if user_curr_id is not None:
                self.frontend.notify_user("Играет %s" % track.full_title(), user_curr_id)

        return track, next_track

    def switch_track(self, user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        self.play_next_track()

    def delete_track(self, user_id, song_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        position = self.scheduler.remove_from_queue(song_id)

        return position

    def stop_playback(self, user_id):
        user = self.get_user(user_id)

        if not user.superuser:
            raise PermissionDenied()

        self.backend.input_queue.put({"action": "stop_playing"})

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
            "superuser": user.superuser,
        }

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
            "position": position,
            "superuser": user.superuser
        }

    def vote_song(self, user_id, sign, song_id):
        if sign == "up":
            self.scheduler.vote_up(user_id, song_id)
        elif sign == "down":
            self.scheduler.vote_down(user_id, song_id)
        else:
            raise ValueError("Sign value should be either 'up' or 'down'")

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
