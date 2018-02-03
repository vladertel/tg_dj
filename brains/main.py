#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import datetime
from collections import namedtuple
from queue import Queue
from threading import Thread

class UserQuotaReached(Exception):
    pass

class UserRequestQuotaReached(UserQuotaReached):
    pass
   
Request = namedtuple("Request", ['user', 'text', 'time'])

class User():

    limits = {
        'max_request_number': 10,
        'max_request_check_interval': 600,
        }
    id = None
    past_requests = []
    recent_requests = []
    
    def __init__(self, id):
        self.id = id
    
    def add_request(self, request):
        self.expire_requests()
        if len(self.recent_requests) == self.limits['max_request_number']:
            raise UserRequestQuotaReached()
        self.recent_requests.append(request)
        
    def expire_requests(self):
        time = datetime.dateteme.now()
        outdated = -1
        for i, request in enumerate(recent_requests):
            delta = time - request.time
            if delta.seconds > self.limits['max_request_check_interval']:
                outdated = i
            else:
                break
        self.path_requests += self.recent_requests[0:outdated+1]
        self.recent_requests = self.recent_requests[outdated+1:]

class DJ_Brain():
    
    limits = {}
    users = {}
    frontend = None
    downloader = None
    backend = None
    frontend_thread = None
    downloader_thread = None
    backend_thread = None
    
    def __init__(self, frontend, downloader, backend):
        self.frontend = frontend
        self.downloader = downloader(self)
        self.backend = backend
        
        self.frontend_thread = Thread(daemon=True, action=)
    
    def frontend_listener(self):
        while True:
            task = self.frontend.output_queue.get()
            action = task['action']
            if action == 'download':
                text = task['text']
                user = task['user']
                if self.add_request(user, text):
                    self.downloader.input_queue.put(task)
    
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