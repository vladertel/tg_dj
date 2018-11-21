#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import peewee
import time
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

        self.frontend.bind_core(self)

        self.downloader_thread = Thread(daemon=True, target=self.downloader_listener)
        self.backend_thread = Thread(daemon=True, target=self.backend_listener)

        self.downloader_thread.start()
        self.backend_thread.start()

        self.play_next_track()

        self.request_callbacks = {}
        self.request_futures = {}
        self.request_counter = 0

    def add_request_callback(self, callback):
        self.request_counter += 1
        request_id = self.request_counter
        self.request_callbacks[request_id] = callback
        return request_id

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
        u = User.get(id=uid)
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
        Request.create(user=author, text=response['title'])
        if author.check_requests_quota() or author.superuser:
            self.scheduler.add_track_to_end_of_queue(path, response['title'], response['duration'], user_id)
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

    def menu_action(self, path, user_id):
        user = self.get_user(user_id)
        print("DEBUG [Core]: menu action %s from user %s" % (path, user_id))

        if path[0] == "main":
            return self.get_menu_main(user)
        elif path[0] == "queue":
            cur_page = int(path[1])
            songs_list, _, is_last_page = self.scheduler.get_queue_page(cur_page)
            return {
                "user_id": user.id,
                "page": cur_page,
                "songs_list": songs_list,
                "is_last_page": is_last_page
            }

        elif path[0] == "song":
            sel_song = int(path[1])
            (song, position) = self.scheduler.get_song(sel_song)
            if song is not None:
                return {
                    "user_id": user.id,
                    "number": path[1],
                    "duration": song.duration,
                    "rating": sum([song.votes[k] for k in song.votes]),
                    "position": position,
                    "page": position // PAGE_SIZE,
                    "title": song.title,
                    "superuser": user.superuser
                }
            else:
                cur_page = 0
                songs_list, _, is_last_page = self.scheduler.get_queue_page(cur_page)
                return {
                    "user_id": user.id,
                    "page": cur_page,
                    "songs_list": songs_list,
                    "is_last_page": is_last_page
                }

        elif path[0] == "vote":
            sign = path[1]
            sid = int(path[2])
            print("DEBUG [Core]: User %d votes %s for song %d" % (user_id, sign, sid))
            if sign == "up":
                song, position = self.scheduler.vote_up(user_id, sid)
            else:
                song, position = self.scheduler.vote_down(user_id, sid)
            return {
                "user_id": user.id,
                "number": path[2],
                "duration": song.duration,
                "rating": sum([song.votes[k] for k in song.votes]),
                "position": position,
                "page": position // PAGE_SIZE,
                "title": song.title,
                "superuser": user.superuser
            }

        elif path[0] == "admin" and user.superuser:
            return self.menu_admin_action(path, user_id)
        else:
            print('ERROR [Core]: Menu not supported:', str(path))

    def menu_admin_action(self, path, user_id):
        user = self.get_user(user_id)

        if path[1] == "skip_song":
            track, next_track = self.play_next_track()
            return self.get_menu_main(user, track, next_track)

        elif path[1] == "delete":
            pos = self.scheduler.remove_from_queue(int(path[2]))
            songs_list, page, is_last_page = self.scheduler.get_queue_page(pos // 10)
            return {
                "user_id": user.id,
                "page": page,
                "songs_list": songs_list,
                "is_last_page": is_last_page
            }

        elif path[1] == 'stop_playing':
            self.backend.input_queue.put({"action": "stop_playing"})
            return self.get_menu_main(user)

        elif path[1] == "list_users":
            return self.get_menu_users_list(user, int(path[2]))

        elif path[1] == "user_info":
            try:
                handled_user = User.get(id=int(path[2]))
                return self.get_menu_user_info(user, handled_user)
            except KeyError:
                print("ERROR [Core]: User does not exists: can't obtain user info")

        elif path[1] == "ban_user" or path[1] == "unban_user":
            try:
                handled_user = User.get(id=int(path[2]))

                if path[1] == "ban_user":
                    handled_user.banned = True
                    print("DEBUG [Core]: User banned")
                if path[1] == "unban_user":
                    handled_user.banned = False
                    print("DEBUG [Core]: User unbanned")
                handled_user.save()

                return self.get_menu_user_info(user, handled_user)
            except KeyError:
                print("ERROR [Core]: User does not exists: can't ban/unban user")

    # DOWNLOADER QUEUE
    @make_endless_unfailable
    def downloader_listener(self):
        task = self.downloader.output_queue.get()

        if "request_id" in task:
            rid = task["request_id"]
            if rid not in self.request_futures:
                print('ERROR [Core]: Response to unknown request#%d: %s' % (task["request_id"], str(task)))
                return
            print('ERROR [Core]: Response to request#%d: %s' % (task["request_id"], str(task)))
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
            "uri": track.media,
            "title": track.title,
            "duration": track.duration,
            "user_id": track.user,
        }

        self.backend.input_queue.put(next_track_task)

        json_file_path = os.path.join(os.getcwd(), "web", "dynamic", "current_song_info.json")
        with open(json_file_path, 'w') as json_file:
            data_to_save = json.dumps(next_track_task)
            json_file.write(data_to_save)

        user_curr = track.user
        user_next = None if next_track is None else next_track.user

        if user_curr is not None and user_next is not None and user_curr == user_next:
            self.frontend.input_queue.put({
                "action": "user_message",
                "message": "Играет " + track.title + "\n\nСледующий трек тоже ваш!\nБудет играть " + next_track.title,
                "user_id": next_track.user
            })
        else:
            if user_next is not None:
                self.frontend.input_queue.put({
                    "action": "user_message",
                    "message": "Следующий трек ваш!\nБудет играть " + next_track.title,
                    "user_id": next_track.user
                })
            if user_curr is not None:
                self.frontend.input_queue.put({
                    "action": "user_message",
                    "message": "Играет " + track.title,
                    "user_id": track.user
                })
        return track, next_track

    def get_menu_main(self, user, current_track=None, next_track=None):
        if current_track is not None:
            #  cruthcy conversions! YAAAY
            current_track = {
                "title": current_track.title,
                "duration": current_track.duration,
                "start_time": time.time(),
                "user_id": current_track.user,

            }
        return {
            "action": "menu",
            "user_id": user.id,
            "entry": "main",
            "queue_len": self.scheduler.queue_length(),
            "now_playing": current_track or self.backend.now_playing,
            "next_in_queue": next_track or self.scheduler.get_next_song(),
            "superuser": user.superuser,
        }

    def get_menu_users_list(self, user, page):

        users_cnt = User.select().count()
        if users_cnt == 0:
            return [], 0, True

        start = page * PAGE_SIZE
        if start >= users_cnt:
            div, mod = divmod(users_cnt, PAGE_SIZE)
            start = div * PAGE_SIZE
            page = div
        elif start < 0:
            start = 0
            page = 0
        end = start + PAGE_SIZE

        users = User.select().offset(start).limit(PAGE_SIZE)

        return {
            "action": "menu",
            "entry": "admin_list_users",
            "user_id": user.id,
            "page": page,
            "users_list": users,
            "users_cnt": users_cnt,
            "is_last_page": end >= users_cnt
        }

    def get_menu_user_info(self, user, handled_user):

        requests = Request.select().filter(Request.user == handled_user).order_by(-Request.time).limit(10)
        req_cnt = Request.select().count()

        return {
            "action": "menu",
            "entry": "admin_user",
            "user_id": user.id,
            "about_user": handled_user,
            "requests": [r for r in requests],
            "req_cnt": req_cnt,
        }
