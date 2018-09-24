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

    def handle_request(self, task, user=None, new_handler=None):

        if user is None:
            if "user_id" not in task:
                print('ERROR [Core]: Message with no user id:', str(task))
                return
            if user != 0:
                user = User.get(id=task["user_id"])

        if "action" in task:
            request_id = self.gen_cnt
            self.gen_cnt += 1
            gen = new_handler(task, user)
            self.requests[request_id] = gen
            new = True
        elif "request_id" in task:
            request_id = task["request_id"]
            gen = self.requests[request_id]
            new = False
        else:
            print('ERROR [Core]: Message has nor action nor request_id:', str(task))
            return

        try:
            response = gen.send(None if new else task)
            if response is None:
                return
            (target, new_task) = response
        except StopIteration:
            self.requests[request_id] = None
            return

        if new_task is None:
            new_task = {}

        new_task["request_id"] = request_id
        new_task["user_id"] = 0 if user is None else user.id
        target.input_queue.put(new_task)

    @staticmethod
    def reply(target, request, response):
        response["request_id"] = request["request_id"]
        response["user_id"] = request["user_id"]
        target.input_queue.put(response)

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

            self.handle_request(task, user, self.frontend_handler)
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
                yield from handlers[action](task, user)
        else:
            print('ERROR [Core]: Request not supported:', str(task))
            self.reply(self.frontend, task, {})

    def handler_download(self, task, user):
        if user.check_requests_quota() or user.superuser:
            yield (self.downloader, dict(task))

            while True:
                result = yield
                if result['state'] == 'download_done':
                    break
                self.reply(self.frontend, task, result)

            path = result['path']
            if self.isWindows:
                path = path[2:]

            Request.create(user=user, text=result['title'])
            if user.check_requests_quota() or user.superuser:
                self.scheduler.add_track_to_end_of_queue(path, result['title'], result['duration'], result["user_id"])
                if not self.backend.is_playing:
                    self.play_next_track()

            self.reply(self.frontend, task, result)
        else:
            self.reply(self.frontend, task,
                       {'action': 'user_message', 'message': 'Превышен лимит запросов. Попробуйте позже'})

    def handler_search(self, task, _user):
        result = yield (self.downloader, dict(task))
        self.reply(self.frontend, task, result)

    def handler_get_status(self, task, user):
        self.reply(self.frontend, task, {
            "entry": "main",
            "queue_len": self.scheduler.queue_length(),
            "now_playing": self.backend.now_playing,
            "next_in_queue": self.scheduler.get_next_song(),
            "superuser": user.superuser,
        })

    def handler_get_queue(self, task, _user):
        page = task["page"]
        songs_list, _, is_last_page = self.scheduler.get_queue_page(page)
        self.reply(self.frontend, task, {
            "page": page,
            "songs_list": songs_list,
            "is_last_page": is_last_page
        })

    def handler_get_song_info(self, task, user):
        song_id = task["song_id"]
        (song, position) = self.scheduler.get_song(song_id)
        if song is not None:
            self.reply(self.frontend, task, {
                "song_id": song_id,
                "title": song.title,
                "duration": song.duration,
                "rating": sum([song.votes[k] for k in song.votes]),
                "position": position,
                "page": position // PAGE_SIZE,
                "superuser": user.superuser,
            })
        else:
            self.reply(self.frontend, task, {
                "song_id": None,
                "page": position // PAGE_SIZE,
            })

    def handler_vote(self, task, user):
        sign = task["sign"]
        song_id = task["song_id"]

        print("DEBUG [Core]: User %d votes %s for song %d" % (user.id, sign, song_id))
        if sign == "+":
            self.scheduler.vote_up(user.id, song_id)
        else:
            self.scheduler.vote_down(user.id, song_id)
        self.reply(self.frontend, task, {})

    def handler_skip_song(self, task, user):
        if not user.superuser:
            self.reply(self.frontend, task, {})
            return

        self.play_next_track()
        self.reply(self.frontend, task, {})

    def handler_stop_playing(self, task, user):
        if not user.superuser:
            self.reply(self.frontend, task, {})
            return

        self.backend.input_queue.put({"action": "stop_playing"})
        self.reply(self.frontend, task, {})

    def handler_remove_song(self, task, user):
        if not user.superuser:
            self.reply(self.frontend, task, {})
            return

        song_id = task["song_id"]
        position = self.scheduler.remove_from_queue(song_id)
        self.reply(self.frontend, task, {"pos": position})

    def handler_get_users_list(self, task, user):
        if not user.superuser:
            self.reply(self.frontend, task, {})
            return

        page = task["page"]

        users_cnt = User.select().count()
        if users_cnt == 0:
            self.reply(self.frontend, task, {
                "page": 0,
                "users_list": [],
                "users_cnt": 0,
                "is_last_page": True,
            })

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

        self.reply(self.frontend, task, {
            "page": page,
            "users_list": users,
            "users_cnt": users_cnt,
            "is_last_page": end >= users_cnt,
        })

    def handler_get_user_info(self, task, user):
        if not user.superuser:
            self.reply(self.frontend, task, {})
            return

        handled_uid = task["handled_user_id"]
        try:
            handled_user = User.get(id=handled_uid)
            requests = Request.select().filter(Request.user == handled_user).order_by(-Request.time).limit(10)
            req_cnt = Request.select().count()

            self.reply(self.frontend, task, {
                "handled_user": handled_user,
                "requests": [r for r in requests],
                "req_cnt": req_cnt,
            })
        except KeyError:
            self.reply(self.frontend, task, {"handled_user": None})

    def handler_ban_user(self, task, user):
        if not user.superuser:
            self.reply(self.frontend, task, {})
            return

        handled_uid = task["handled_user_id"]
        try:
            handled_user = User.get(id=handled_uid)
            handled_user.banned = True
            handled_user.save()
        except KeyError:
            pass
        self.reply(self.frontend, task, {})

    def handler_unban_user(self, task, user):
        if not user.superuser:
            self.reply(self.frontend, task, {})
            return

        handled_uid = task["handled_user_id"]
        try:
            handled_user = User.get(id=handled_uid)
            handled_user.banned = False
            handled_user.save()
        except KeyError:
            pass
        self.reply(self.frontend, task, {})

# end handlers

    def downloader_listener(self):
        while True:
            task = self.downloader.output_queue.get()
            print("DEBUG [Core]: Task from downloader: %s" % str(task))
            self.handle_request(task)
            self.downloader.output_queue.task_done()

    def backend_listener(self):
        while True:
            task = self.backend.output_queue.get()
            print("DEBUG [Core]: Task from backend: %s" % str(task))
            self.handle_request(task, new_handler=self.backend_handler)
            self.backend.output_queue.task_done()

    def backend_handler(self, task, _user):
        action = task['action']

        if action == "song_finished":
            self.play_next_track()

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
