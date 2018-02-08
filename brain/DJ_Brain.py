#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import datetime
from collections import namedtuple
from queue import Queue
from threading import Thread
import platform

from .config import *

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
        self.past_requests += self.recent_requests[0:outdated+1]
        self.recent_requests = self.recent_requests[outdated+1:]

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
        
        self.frontend_thread = Thread(daemon=True, target=self.frontend_listener)
        self.downloader_thread = Thread(daemon=True, target=self.downloader_listener)
        self.backend_thread = Thread(daemon=True, target=self.backend_listener)
        
        self.frontend_thread.start()
        self.downloader_thread.start()
        self.backend_thread.start()
    
    def frontend_listener(self):
        while True:
            task = self.frontend.output_queue.get()
            action = task['action']
            if action == 'download':
                if "text" in task:
                    text = task['text']
                elif "file" in task:
                    text = task['file']
                user = task['user']
                if self.add_request(user, text):
                    print("pushed task to downloader: " + str(task))
                    self.downloader.input_queue.put(task)
                else:
                    self.frontend.input_queue.put({
                        'action': 'user_message',
                        'user': user,
                        'message': 'Request quota reached. Try again later'
                        })
            elif action == 'user_confirmed':
                print("pushed task to downloader: " + str(task))
                self.downloader.input_queue.put(task)
            else:
                print('Message not found:', task)
            self.frontend.output_queue.task_done()
    
    def downloader_listener(self):
        while True:
            task = self.downloader.output_queue.get()
            action = task['action']
            if action == 'download_done':
                path = task['path']
                if self.isWindows:
                    path = path[2:]
                print("pushed task to backend: { action: play_song, path: " + path + "}")
                self.backend.input_queue.put({
                    'action': 'play_song',
                    'uri': path
                    })
                self.frontend.input_queue.put({
                        "action": "user_message",
                        "message": "Your query is playing now",
                        "user": task["user"]
                    })
            elif action == 'user_message' or action == 'ask_user':
                print("pushed task to frontend: " + str(task))
                self.frontend.input_queue.put(task)
            else:
                print('Message not found:', task)
            self.downloader.output_queue.task_done()
    
    def backend_listener(self):
        while True:
            task = self.backend.output_queue.get()
            action = task['action']
            if False:
                ...
            else:
                print('Message not found:', task)
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