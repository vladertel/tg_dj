#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import subprocess
import atexit
from queue import Queue
from threading import Thread
from telnetlib import Telnet

from .config import *

class TelnetWrapper(Telnet):
    def readwrite(self, data):
        self.write(data.encode())
        return self.read_eager()

class LiquidStreamer():
    def __init__(self):
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.queue_thread = Thread(daemon=True, target=self.queue_listener)
        self.queue_thread.start()
        self.init_liquid()
        self.init_telnet()
        
    def init_liquid(self):
        self.liquidsoap = subprocess.Popen(
            [liquidsoap_exe_path, liquidsoap_config_path],
            stdout=subprocess.PIPE)
        atexit.register(self.kill_liquid)
        self.liquid_thread = Thread(daemon=True, target=self.liquidsoap_reader)
        self.liquid_thread.start()
        
    def init_telnet(self):
        self.telnet = TelnetWrapper('localhost', 1234)
    
    def kill_liquid(self):
        self.liquidsoap.kill()
        
    def queue_listener(self):
        while True:
            task = self.input_queue.get()
            action = task['action']
            if action == 'add_song':
                uri = task['uri']
                self.telnet.readwrite(''.join(['queue.push ', uri, '\n']))
            elif action == 'skip_song':
                self.telnet.readwrite('ao.skip\n')
            else:
                print('Message not found:', task)
            self.input_queue.task_done()
     
    def liquidsoap_reader(self):
        for line in self.liquidsoap.stdout:
            print(line)