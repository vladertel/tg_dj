#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import datetime
from collections import namedtuple
from queue import Queue
from threading import Thread

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
        time = datetime.dateteme.now()
        outdated = -1
        for i, request in enumerate(recent_requests):
            delta = time - request.time
            if delta.seconds > user_max_request_check_interval:
                outdated = i
            else:
                break
        self.path_requests += self.recent_requests[0:outdated+1]
        self.recent_requests = self.recent_requests[outdated+1:]

class DJ_Brain():
    
    limits = {}
    users = {}
    
    def __init__(self, frontend, downloader, backend):
        self.frontend = frontend
        self.downloader = downloader
        self.backend = backend
        
        self.frontend_thread = Thread(daemon=True, action=frontend_listener)
        self.downloader_thread = Thread(daemon=True, action=downloader_listener)
        self.backend_thread = Thread(daemon=True, action=backend_listener)
        
        self.frontend_thread.start()
        self.downloader_thread.start()
        self.backend_thread.start()
    
    def frontend_listener(self):
        while True:
            task = self.frontend.output_queue.get()
            action = task['action']
            if action == 'download':
                text = task['text']
                user = task['user']
                if self.add_request(user, text):
                    self.downloader.input_queue.put(task)
                else:
                    self.frontent.input_queue.put({
                        'action': 'error',
                        'user': user,
                        'message': 'Request quota reached. Try again later'
                        })
            elif action == 'user_confirmed':
                self.downloader.input_queue.put(task)
    
    def downoader_listener(self):
        while True:
            task = self.downloader.output_queue.get()
            action = task['action']
            if action == 'download_done':
                path = task['path'][2:]
                self.backend.input_queue.put({
                    'action': 'add_song',
                    'uri': path
                    })
            elif action == 'user_message' or action == 'user_ask':
                self.frontend.input_queue.put(task)
    
    def backend_listener(self):
        while True:
            task = self.backend.output_queue.get()
            action = task['action']
    
    def add_request(self, user, text):
        if user not in users:
            self.add_user(user)
        time = datetime.now()
        request = Request(user, text, time)
        try:
            self.users[user].add_request(request)
        except UserQuotaReached:
            return False
        return True
        
    def add_user(self, user):
        self.users[user] = User(user)