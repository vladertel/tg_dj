#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import datetime

class User():
    def __init__(self, id):
        self.id = id

class DJ_Brain():
    
    limits = {}
    users = {}
    frontends = []
    downloader = None
    backends = []
    requests = {}
    
    def __init__(self, frontend_list, downloader, backend_list):
        for frontend in frontend_list:
            self.frontends.append(frontend(self))
        self.downloader = downloader(self)
        for backend in backend_list:
            self.backends.append(backend(self))
    
    def add_request(self, user, request, callback):
        if user not in users:
            self.add_user(user)
        time = datetime.now()
        request_id = (user, request, time)
        self.requests[request_id] = callback
        self.downloader.add_request(self, request, self.cb_done_downloading(request_id))
        
    def add_user(self, user):
        self.users[user] = User(user)
    
    def cb_done_downloading(self, request_id):
        return lambda: self.requests[request_id]()