#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import datetime
from collections import namedtuple
from threading import Thread
import platform
import json
import os

from .config import *
from .scheduler import Scheduler


class UserQuotaReached(Exception):
    pass


class UserRequestQuotaReached(UserQuotaReached):
    pass


Request = namedtuple("Request", ['user', 'text', 'time'])


class User():

    id = None
    past_requests = []
    recent_requests = []

    def __init__(self, id):
        self.id = id

    def add_request(self, request):
        self.expire_requests()
        if len(self.recent_requests) == user_max_request_number:
            raise UserRequestQuotaReached()
        self.recent_requests.append(request)

    def expire_requests(self):
        time = datetime.datetime.now()
        outdated = -1
        for i, request in enumerate(self.recent_requests):
            delta = time - request.time
            if delta.seconds > user_max_request_check_interval:
                outdated = i
            else:
                break
        self.past_requests += self.recent_requests[0:outdated + 1]
        self.recent_requests = self.recent_requests[outdated + 1:]

    def toJSON(self):
        json = {
            "past_requests": [],
            "recent_requests": []
        }
        for req in self.past_requests:
            json["past_requests"].append({
                "user": req.user,
                "text": req.text,
                "time": req.time.timestamp()
            })
        for req in self.recent_requests:
            json["recent_requests"].append({
                "user": req.user,
                "text": req.text,
                "time": req.time.timestamp()
            })
        return json

    def fromJSON(self, objecta):
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


class DJ_Brain():

    limits = {}
    users = {}

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

    def cleanup(self):
        self.scheduler.cleanup()
        out_users = {}
        for user in self.users:
            out_users[user] = self.users[user].toJSON()
        with open(os.path.join(saveDir, "users_save"), 'w') as f:
            f.write(json.dumps(out_users, ensure_ascii=False))
        print("Brain - state saved")

    def load(self):
        try:
            with open(os.path.join(saveDir, "users_save")) as f:
                users = json.loads(f.read())
            for user in users:
                self.add_user(user)
                self.users[user].fromJSON(users[user])
        except FileNotFoundError:
            print("save not found for brain")

    def frontend_listener(self):
        while True:
            task = self.frontend.output_queue.get()
            action = task['action']
            if action == 'download':
                if "text" in task:
                    text = task['text']
                elif "file" in task:
                    text = task['file']
                elif "downloader" in task and "result_id" in task:
                    text = task["downloader"] + "#" + task["result_id"]
                else:
                    text = "Unknown download type"
                user = task['user']
                if user in superusers or self.add_request(user, text):
                    print("pushed task to downloader: " + str(task))
                    self.downloader.input_queue.put(task)
                else:
                    self.frontend.input_queue.put({
                        'action': 'user_message',
                        'user': user,
                        'message': 'Превышен лимит запросов, попробуйте позже'
                    })
            elif action == "search":
                print("pushed task to downloader: " + str(task))
                self.downloader.input_queue.put(task)
            elif action == 'stop_playing':
                if task['user'] in superusers:
                    print("pushed task to backend: " + str(task))
                    self.backend.input_queue.put(task)
                else:
                    self.frontend.input_queue.put({
                        "action": "user_message",
                        "message": "You have no power here",
                        "user": task["user"]
                    })
            elif action == 'skip_song':
                if task['user'] in superusers:
                    # task['action'] = "stop_playing"
                    # print("pushed task to backend: " + str(task))
                    # self.backend.input_queue.put(task)
                    track = self.scheduler.get_first_track()
                    if track is not None:
                        new_task = {
                            "action": "play_song",
                            "uri": track.media,
                            "title": track.title
                        }
                        self.backend.input_queue.put(new_task)
                else:
                    self.frontend.input_queue.put({
                        "action": "user_message",
                        "message": "You have no power here",
                        "user": task["user"]
                    })
            elif action == 'delete':
                if task['user'] in superusers:
                    pos = self.scheduler.remove_from_queue(task['number'])
                    (lista, page, lastpage) = self.scheduler.get_queue_page(pos // 10)
                    self.frontend_menu_list(task["user"], page, lista, lastpage)
                else:
                    self.frontend.input_queue.put({
                        "action": "user_message",
                        "message": "You have no power here",
                        "user": task["user"]
                    })
            elif action == "vote_down":
                print("vote_down user: " + str(task["user"]) + ", sid: " + str(task["sid"]))
                song, pos = self.scheduler.vote_down(task["user"], task["sid"])
                (lista, page, lastpage) = self.scheduler.get_queue_page(pos // 10)
                self.frontend_menu_list(task["user"], page, lista, lastpage)
            elif action == "vote_up":
                print("vote_up user: " + str(task["user"]) + ", sid: " + str(task["sid"]))
                song, pos = self.scheduler.vote_up(task["user"], task["sid"])
                (lista, page, lastpage) = self.scheduler.get_queue_page(pos // 10)
                self.frontend_menu_list(task["user"], page, lista, lastpage)
            elif action == "menu":
                print("user " + str(task["user"]) + " requested menu")
                if task["entry"] == "main":
                    self.frontend_menu_main(task["user"], self.scheduler.queue_length(), self.backend.now_playing)
                elif task["entry"] == "list":
                    (lista, page, lastpage) = self.scheduler.get_queue_page(task["number"])
                    self.frontend_menu_list(task["user"], page, lista, lastpage)
                elif task["entry"] == "song":
                    (song, pos) = self.scheduler.get_song(task["number"])
                    if song is not None:
                        self.frontend_menu_song(task["user"], song, task["number"], pos)
                    else:
                        (lista, page, lastpage) = self.scheduler.get_queue_page(0)
                        self.frontend_menu_list(task["user"], page, lista, lastpage)
                else:
                    print('Menu not supported:', str(task["entry"]))
            elif action == "manual_start":
                self.manual_start()
            else:
                print('ERROR: Message not supported:', str(task))
            self.frontend.output_queue.task_done()

    def downloader_listener(self):
        while True:
            task = self.downloader.output_queue.get()
            action = task['action']
            if action == 'download_done':
                path = task['path']
                if self.isWindows:
                    path = path[2:]
                if self.backend.is_playing:
                    self.scheduler.add_track_to_end_of_queue(path, task['title'], task['duration'], task["user"])
                else:
                    print("pushed task to backend: { action: play_song, path: " + path + "}")
                    self.backend.input_queue.put({
                        'action': 'play_song',
                        'uri': path,
                        'title': task["title"]
                    })
                    self.frontend.input_queue.put({
                        "action": "user_message",
                        "message": "Играет один из ваших запросов!",
                        "user": task["user"]
                    })

            elif action == 'user_message' or action == 'edit_user_message' or action == 'confirmation_done':
                print("pushed task to frontend: " + str(task))
                self.frontend.input_queue.put(task)
            elif action == 'search_results':
                print("pushed task to frontend: " + str(task))
                self.frontend.input_queue.put(task)
            else:
                print('Message not supported: ', str(task))
            self.downloader.output_queue.task_done()

    def backend_listener(self):
        while True:
            task = self.backend.output_queue.get()
            action = task['action']
            if action == "song_finished":
                track = self.scheduler.get_first_track()
                if track is not None:
                    self.backend.input_queue.put({
                        "action": "play_song",
                        "uri": track.media,
                        "title": track.title
                    })
                    self.frontend.input_queue.put({
                        "action": "user_message",
                        "message": "Играет ваш заказ!\n" + track.title,
                        "user": track.user
                    })
                    next_track = self.scheduler.get_next_song()
                    if next_track is not None:
                        self.backend.input_queue.put({
                            "action": "user_message",
                            "message": "После текущего заказа будет играть ваш!\n" + next_track.title,
                            "user": next_track.user
                        })
            else:
                print('Message not supported:', str(task))
            self.backend.output_queue.task_done()

    def add_request(self, user, text):
        if user not in self.users:
            self.add_user(user)
        time = datetime.datetime.now()
        request = Request(user, text, time)
        try:
            self.users[user].add_request(request)
        except UserQuotaReached:
            return False
        return True

    def add_user(self, user):
        self.users[user] = User(user)

##### MESSAGING METHONDS ####
    def frontend_menu_list(self, user, number, lista, lastpage):
        self.frontend.input_queue.put({
            "action": "menu",
            "user": user,
            "entry": "list",
            "number": number,
            "lista": lista,
            "lastpage": lastpage
        })

    def frontend_menu_song(self, user, song, number, position):
        self.frontend.input_queue.put({
            "action": "menu",
            "user": user,
            "entry": "song",
            "number": number,
            "duration": song.duration,
            "rating": sum([song.votes[k] for k in song.votes]),
            "position": position,
            "title": song.title,
            "superuser": user in superusers
        })

    def frontend_menu_main(self, user, qlen, now_playing):
        self.frontend.input_queue.put({
            "action": "menu",
            "user": user,
            "entry": "main",
            "number": 0,
            "qlen": qlen,
            "now_playing": now_playing,
        })

#### MANUAL MANAGEMENT ####
    def manual_start(self):
        self.backend.vlc_song_finished("lolkek")
