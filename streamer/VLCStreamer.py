from queue import Queue
from threading import Thread

import vlc

from .config import *

# options = 'sout=#duplicate{dst=rtp{access=udp,mux=ts,dst=224.0.0.1,port=1233},dst=display}'
# Load media with streaming options
# media = instance.media_new('test.mp3', options)
# The above snippet will stream to the multicast address 224.0.0.1, 
# allowing all devices on the network to consume the RTP stream, whilst also playing it locally.


class VLCStreamer():
    def __init__(self):
        self.input_queue = Queue()
        self.output_queue = Queue()
        self.queue_thread = Thread(daemon=True, target=self.queue_listener)
        self.queue_thread.start()
        self.vlc_instance = vlc.Instance()
        self.player = self.vlc_instance.media_player_new()

    def queue_listener(self):
        while True:
            task = self.input_queue.get()
            action = task['action']
            if action == 'play_song':
                uri = task['uri']
                media = self.vlc_instance.media_new(uri)
                self.player.set_media(media)
                self.player.play()
            elif action == 'skip_song':
                self.player.stop()
            elif action == 'stop_playback':
                self.player.stop()
            else:
                print('Message not found:', task)
            self.input_queue.task_done()
