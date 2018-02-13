import threading


class Scheduler():
    def __init__(self):
        self.playing_queue = []
        self.lock = threading.Lock()

    def add_track_to_end_of_queue(self, song):
        self.lock.acquire()
        self.playing_queue.append(song)
        self.lock.release()

    def get_first_track(self):
        self.lock.acquire()
        song = self.playing_queue[0]
        self.playing_queue = self.playing_queue[1:]
        self.lock.release()
        return song
