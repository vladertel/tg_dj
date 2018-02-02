#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import datetime
from collections import namedtuple

class UserQuotaReached(Exception):
    pass

class UserRequestQuotaReached(UserQuotaReached):
    pass
   
Request = namedtuple("Request", ['user', 'url', 'time'])

class User():

    limits = {}
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
    frontends = []
    downloader = None
    backends = []
    request_callbacks = {}
    
    def __init__(self, frontend_list, downloader, backend_list):
        for frontend in frontend_list:
            self.frontends.append(frontend(self))
        self.downloader = downloader(self)
        for backend in backend_list:
            self.backends.append(backend(self))
    
    def add_request(self, user, url, callback):
        if user not in users:
            self.add_user(user)
        time = datetime.now()
        request = Request(user, url, time)
        try:
            self.users[user].add_request(request)
        except UserQuotaReached:
            raise
        
        self.request_calbcacks[request] = callback
        self.downloader.add_request(self, request, self.cb_done_downloading(request))
        
    def add_user(self, user):
        self.users[user] = User(user)
    
    def cb_done_downloading(self, request):
        return lambda: self.request_callbacks[request]()