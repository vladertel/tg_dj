#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import peewee
import time

import datetime
from threading import Thread
import platform

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

    # FRONTEND QUEUE
    def frontend_listener(self):
        while True:
            task = self.frontend.output_queue.get()

            if "user_id" not in task and task['action'] != "init_user":
                print('ERROR [Core]: Message from frontend with no user id:', str(task))
                continue

            if task['action'] == "init_user":
                u = User.create()
                self.frontend.input_queue.put({
                    "action": "user_init_done",
                    "user_id": u.id,
                    "frontend_user": task["frontend_user"],
                })
                print('INFO [Core]: User(id=%d) init done' % u.id)
                continue

            user = User.get(id=task["user_id"])
            if user.banned:
                self.frontend.input_queue.put({
                    "action": "access_denied",
                    "user_id": user.id,
                })
                continue

            print("DEBUG [Core]: Task from frontend: %s" % str(task))

            action = task['action']
            if action == 'download':
                self.download_action(task)
            elif action == "search":
                print("DEBUG [Core]: pushed search task to downloader: " + str(task))
                self.downloader.input_queue.put(task)
            elif action == "menu_event":
                self.menu_action(task)
            else:
                print('ERROR [Core]: Message not supported:', str(task))
            self.frontend.output_queue.task_done()

    def download_action(self, task):
        user_id = task["user_id"]
        user, _ = User.get_or_create(id=user_id)

        if user.check_requests_quota() or user.superuser:
            print("DEBUG [Core]: pushed task to downloader: " + str(task))
            self.downloader.input_queue.put(task)
        else:
            self.frontend.input_queue.put({
                'action': 'user_message',
                "user_id": user_id,
                'message': 'Превышен лимит запросов, попробуйте позже'
            })

    def menu_action(self, task):
        user_id = task["user_id"]
        user, _ = User.get_or_create(id=user_id)
        path = task["path"]
        print("DEBUG [Core]: menu action %s from user %s" % (path, user_id))

        if path[0] == "main":
            self.send_menu_main(user)
        elif path[0] == "queue":
            cur_page = int(path[1])
            songs_list, _, is_last_page = self.scheduler.get_queue_page(cur_page)
            self.send_menu_songs_queue(user, cur_page, songs_list, is_last_page)

        elif path[0] == "song":
            sel_song = int(path[1])
            (song, position) = self.scheduler.get_song(sel_song)
            if song is not None:
                self.send_menu_song_info(user, path[1], song, position, position // PAGE_SIZE)
            else:
                cur_page = 0
                songs_list, _, is_last_page = self.scheduler.get_queue_page(cur_page)
                self.send_menu_songs_queue(user, cur_page, songs_list, is_last_page)

        elif path[0] == "vote":
            sign = path[1]
            sid = int(path[2])
            print("DEBUG [Core]: User %d votes %s for song %d" % (user_id, sign, sid))
            if sign == "up":
                song, position = self.scheduler.vote_up(user_id, sid)
            else:
                song, position = self.scheduler.vote_down(user_id, sid)
            self.send_menu_song_info(user, path[2], song, position, position // PAGE_SIZE)

        elif path[0] == "admin" and user.superuser:
            path.pop(0)
            self.menu_admin_action(task)
        else:
            print('ERROR [Core]: Menu not supported:', str(path))

    def menu_admin_action(self, task):
        user_id = task["user_id"]
        user, _ = User.get_or_create(id=user_id)
        path = task["path"]

        if path[0] == "skip_song":
            track, next_track = self.play_next_track()
            self.send_menu_main(user, track, next_track)

        elif path[0] == "delete":
            pos = self.scheduler.remove_from_queue(int(path[1]))
            songs_list, page, is_last_page = self.scheduler.get_queue_page(pos // 10)
            self.send_menu_songs_queue(user, page, songs_list, is_last_page)

        elif path[0] == 'stop_playing':
            self.backend.input_queue.put({"action": "stop_playing"})
            self.send_menu_main(user)

        elif path[0] == "list_users":
            self.send_menu_users_list(user, int(path[1]))

        elif path[0] == "user_info":
            try:
                handled_user = User.get(id=int(path[1]))
                self.send_menu_user_info(user, handled_user)
            except KeyError:
                print("ERROR [Core]: User does not exists: can't obtain user info")

        elif path[0] == "ban_user" or path[0] == "unban_user":
            try:
                handled_user = User.get(id=int(path[1]))

                if path[0] == "ban_user":
                    handled_user.banned = True
                    print("DEBUG [Core]: User banned")
                if path[0] == "unban_user":
                    handled_user.banned = False
                    print("DEBUG [Core]: User unbanned")
                handled_user.save()

                self.send_menu_user_info(user, handled_user)
            except KeyError:
                print("ERROR [Core]: User does not exists: can't ban/unban user")

    # DOWNLOADER QUEUE
    def downloader_listener(self):
        while True:
            task = self.downloader.output_queue.get()
            action = task['action']
            if action == 'download_done':
                path = task['path']
                if self.isWindows:
                    path = path[2:]

                author = User.get(id=int(task["user_id"]))
                Request.create(user=author, text=task['title'])
                if author.check_requests_quota() or author.superuser:
                    self.scheduler.add_track_to_end_of_queue(path, task['title'], task['duration'], task["user_id"])
                    if not self.backend.is_playing:
                        self.play_next_track()

            elif action in ['user_message', 'edit_user_message', 'no_dl_handler', 'search_results', 'error']:
                print("DEBUG [Core]: pushed task to frontend: " + str(task))
                self.frontend.input_queue.put(task)
            else:
                print('ERROR [Core]: Message not supported: ', str(task))
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

    def send_menu_main(self, user, current_track=None, next_track=None):
        if current_track is not None:
            #  cruthcy conversions! YAAAY
            current_track = {
                "title": current_track.title,
                "duration": current_track.duration,
                "start_time": time.time(),
                "user_id": current_track.user,

            }
        self.frontend.input_queue.put({
            "action": "menu",
            "user_id": user.id,
            "entry": "main",
            "queue_len": self.scheduler.queue_length(),
            "now_playing": current_track or self.backend.now_playing,
            "next_in_queue": next_track or self.scheduler.get_next_song(),
            "superuser": user.superuser,
        })

    def send_menu_songs_queue(self, user, number, songs_list, is_last_page):
        self.frontend.input_queue.put({
            "action": "menu",
            "entry": "queue",
            "user_id": user.id,
            "page": number,
            "songs_list": songs_list,
            "is_last_page": is_last_page
        })

    def send_menu_song_info(self, user, number, song, position, page):
        self.frontend.input_queue.put({
            "action": "menu",
            "entry": "song_details",
            "user_id": user.id,
            "number": number,
            "duration": song.duration,
            "rating": sum([song.votes[k] for k in song.votes]),
            "position": position,
            "page": page,
            "title": song.title,
            "superuser": user.superuser
        })

    def send_menu_users_list(self, user, page):

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

        self.frontend.input_queue.put({
            "action": "menu",
            "entry": "admin_list_users",
            "user_id": user.id,
            "page": page,
            "users_list": users,
            "users_cnt": users_cnt,
            "is_last_page": end >= users_cnt
        })

    def send_menu_user_info(self, user, handled_user):

        requests = Request.select().filter(Request.user == handled_user).order_by(-Request.time).limit(10)
        req_cnt = Request.select().count()

        self.frontend.input_queue.put({
            "action": "menu",
            "entry": "admin_user",
            "user_id": user.id,
            "about_user": handled_user,
            "requests": [r for r in requests],
            "req_cnt": req_cnt,
        })
