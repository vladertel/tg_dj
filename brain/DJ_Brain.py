#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import peewee

import datetime
from threading import Thread
import platform
import types

from .config import *
from .scheduler import Scheduler


class UserQuotaReached(Exception):
    pass


class UserRequestQuotaReached(UserQuotaReached):
    pass


db = peewee.SqliteDatabase("db/dj_brain.db")


class BaseModel(peewee.Model):
    class Meta:
        database = db


class User(BaseModel):
    id = peewee.PrimaryKeyField()
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


class DJ_Brain:

    def __init__(self, frontend, downloader, backend):
        self.isWindows = False
        if platform.system() == "Windows":
            self.isWindows = True
        self.frontend = frontend
        self.downloader = downloader
        self.backend = backend

        self.scheduler = Scheduler()
        self.load()

        self.frontend_thread = Thread(daemon=True, target=self.frontend_listener)
        self.downloader_thread = Thread(daemon=True, target=self.downloader_listener)
        self.backend_thread = Thread(daemon=True, target=self.backend_listener)

        self.frontend_thread.start()
        self.downloader_thread.start()
        self.backend_thread.start()

        self.play_next_track()

        self.requests = {}
        self.gen_cnt = 0

    def cleanup(self):
        self.scheduler.cleanup()
        # out_users = {}
        # for user in self.users:
        #     out_users[user] = self.users[user].toJSON()
        # with open(os.path.join(saveDir, "users_save"), 'w') as f:
        #     f.write(json.dumps(out_users, ensure_ascii=False))
        print("INFO [Core]: Brain - state saved")

    def load(self):
        try:
            pass
            # with open(os.path.join(saveDir, "users_save")) as f:
            #     users = json.loads(f.read())
            # for user in users:
            #     self.add_user(user)
            #     self.users[user].fromJSON(users[user])
        except FileNotFoundError:
            print("WARNING [Core]: save not found for brain")

    def handle_request(self, request_id, user_id, task=None):
        gen = self.requests[request_id]["handler"]

        try:
            response = gen.send(task)
            if response is None:
                return
            (target, new_task) = response
        except StopIteration as e:
            new_task = e.value
            request = self.requests[request_id]
            target = request["from"]
            source_id = request["source_id"]
            self.requests[request_id] = None
            request_id = source_id

        if new_task is None:
            new_task = {}

        new_task["request_id"] = request_id
        new_task["user_id"] = user_id
        target.input_queue.put(new_task)

    # FRONTEND QUEUE
    def frontend_listener(self):
        while True:
            task = self.frontend.output_queue.get()
            source_id = task["request_id"]

            if task['action'] == "init_user":
                u = User.create()
                self.frontend.input_queue.put({
                    "request_id": source_id,
                    "user_id": u.id,
                    "frontend_user": task["frontend_user"],
                })
                print('INFO [Core]: User(id=%d) init done' % u.id)
                continue

            if "user_id" not in task:
                print('ERROR [Core]: Message from frontend with no user id:', str(task))
                continue

            user = User.get(id=task["user_id"])
            if user.banned:
                self.frontend.input_queue.put({
                    "request_id": source_id,
                    "user_id": user.id,
                    "action": "access_denied",
                })
                continue

            print("DEBUG [Core]: Task from frontend: %s" % str(task))

            request_id = self.gen_cnt
            self.gen_cnt += 1
            self.requests[request_id] = {
                "handler": self.frontend_handler(task, user),
                "from": self.frontend,
                "source_id": source_id,
            }
            self.handle_request(request_id, user.id)
            self.frontend.output_queue.task_done()

    def frontend_handler(self, task, user):
        action = task['action']

        handlers = {
            "download": self.handler_download,
            "search": self.handler_search,
            "get_status": self.handler_get_status,
            "get_queue": self.handler_get_queue,
            "get_song_info": self.handler_get_song_info,
            "vote": self.handler_vote,
            "skip_song": self.handler_skip_song,
            "stop_playing": self.handler_stop_playing,
            "remove_song": self.handler_remove_song,
            "get_users_list": self.handler_get_users_list,
            "get_user_info": self.handler_get_user_info,
            "ban_user": self.handler_ban_user,
            "unban_user": self.handler_unban_user,
        }

        if action in handlers:
            g = handlers[action](task, user)
            if isinstance(g, types.GeneratorType):
                result = yield from handlers[action](task, user)
                return result
            else:
                return g
        else:
            print('ERROR [Core]: Request not supported:', str(task))
            return {}

    def handler_download(self, task, user):
        if user.check_requests_quota() or user.superuser:
            result = yield (self.downloader, task)

            while result['state'] != 'download_done':
                result = yield

            path = result['path']
            if self.isWindows:
                path = path[2:]

            Request.create(user=user, text=result['title'])
            if user.check_requests_quota() or user.superuser:
                self.scheduler.add_track_to_end_of_queue(path, result['title'], result['duration'], result["user_id"])
                if not self.backend.is_playing:
                    self.play_next_track()

            return result
        else:
            return {'action': 'user_message', 'message': 'Превышен лимит запросов. Попробуйте позже'}

    def handler_search(self, task, _user):
        result = yield (self.downloader, task)
        return result

    def handler_get_status(self, _task, user):
        return {
            "entry": "main",
            "queue_len": self.scheduler.queue_length(),
            "now_playing": self.backend.now_playing,
            "next_in_queue": self.scheduler.get_next_song(),
            "superuser": user.superuser,
        }

    def handler_get_queue(self, task, _user):
        page = task["page"]
        songs_list, _, is_last_page = self.scheduler.get_queue_page(page)
        return {
            "page": page,
            "songs_list": songs_list,
            "is_last_page": is_last_page
        }

    def handler_get_song_info(self, task, user):
        song_id = task["song_id"]
        (song, position) = self.scheduler.get_song(song_id)
        if song is not None:
            return {
                "song_id": song_id,
                "title": song.title,
                "duration": song.duration,
                "rating": sum([song.votes[k] for k in song.votes]),
                "position": position,
                "page": position // PAGE_SIZE,
                "superuser": user.superuser,
            }
        else:
            return {
                "song_id": None,
                "page": position // PAGE_SIZE,
            }

    def handler_vote(self, task, user):
        sign = task["sign"]
        song_id = task["song_id"]

        print("DEBUG [Core]: User %d votes %s for song %d" % (user.id, sign, song_id))
        if sign == "+":
            self.scheduler.vote_up(user.id, song_id)
        else:
            self.scheduler.vote_down(user.id, song_id)
        return {}

    def handler_skip_song(self, _task, user):
        if user.superuser:
            self.play_next_track()
        return {}

    def handler_stop_playing(self, _task, user):
        if user.superuser:
            self.backend.input_queue.put({"action": "stop_playing"})
        return {}

    def handler_remove_song(self, task, user):
        if user.superuser:
            song_id = task["song_id"]
            position = self.scheduler.remove_from_queue(song_id)
            return {"pos": position}
        return {}

    def handler_get_users_list(self, task, user):
        if user.superuser:
            page = task["page"]

            users_cnt = User.select().count()
            if users_cnt == 0:
                return {
                    "page": 0,
                    "users_list": [],
                    "users_cnt": 0,
                    "is_last_page": True,
                }

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
                "page": page,
                "users_list": users,
                "users_cnt": users_cnt,
                "is_last_page": end >= users_cnt,
            }
        return {}

    def handler_get_user_info(self, task, user):
        if user.superuser:
            handled_uid = task["handled_user_id"]
            try:
                handled_user = User.get(id=handled_uid)
                requests = Request.select().filter(Request.user == handled_user).order_by(-Request.time).limit(10)
                req_cnt = Request.select().count()

                return {
                    "handled_user": handled_user,
                    "requests": [r for r in requests],
                    "req_cnt": req_cnt,
                }
            except KeyError:
                return {"handled_user": None}
        return {}

    def handler_ban_user(self, task, user):
        if user.superuser:
            handled_uid = task["handled_user_id"]
            try:
                handled_user = User.get(id=handled_uid)
                handled_user.banned = True
                handled_user.save()
            except KeyError:
                pass
        return {}

    def handler_unban_user(self, task, user):
        if user.superuser:
            handled_uid = task["handled_user_id"]
            try:
                handled_user = User.get(id=handled_uid)
                handled_user.banned = False
                handled_user.save()
            except KeyError:
                pass
        return {}

# end handlers

    def downloader_listener(self):
        while True:
            task = self.downloader.output_queue.get()

            print("DEBUG [Core]: Task from downloader: %s" % str(task))

            if "request_id" in task:
                self.handle_request(task["request_id"], task["user_id"], task)
            else:
                print('ERROR [Core]: Bad response from downloader: ', str(task))

            self.downloader.output_queue.task_done()

    def backend_listener(self):
        while True:
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

        self.backend.input_queue.put({
            "action": "play_song",
            "uri": track.media,
            "title": track.title,
            "duration": track.duration,
            "user_id": track.user,
        })

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
