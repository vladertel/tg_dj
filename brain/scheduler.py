import threading


class Song():
    ids = 1

    def __init__(self, path_to_media, title, duration, user):
        self.title = title
        self.duration = duration
        self.media = path_to_media
        self.user = user
        self.votes = {}  # e.g. user: value
        self.rating = 0
        self.id = Song.ids
        Song.ids += 1


class Scheduler():
    def __init__(self):
        self.is_media_playing = False
        self.playing_queue = []
        self.lock = threading.Lock()

    def add_track_to_end_of_queue(self, path, title, duration, user):
        self.lock.acquire()
        self.playing_queue.append(Song(path, title, duration, user))
        self.lock.release()

    def get_first_track(self):
        self.lock.acquire()
        try:
            song = self.playing_queue.pop(0)
        except IndexError:
            print("Scheduler: Nothing to pop")
            song = None
        self.lock.release()
        return song

    def get_song(self, sid):
        for song in self.playing_queue:
            if sid == song.id:
                return song
        return None

    def get_queue(self):
        return list(self.playing_queue)

    def remove_from_queue(self, index):
        self.lock.acquire()
        try:
            self.playing_queue.pop(index)
        except IndexError:
            print("Nothing to remove")
        self.lock.release()

    def queue_length(self):
        return len(self.playing_queue)

    def sort_queue(self):
        self.lock.acquire()
        self.playing_queue = sorted(self.playing_queue, key=lambda x: x.id - sum([x.votes[k] for k in x.votes]))
        self.lock.release()

    def vote_up(self, user, sid):
        found = False
        self.lock.acquire()
        for song in self.playing_queue:
            if sid == song.id:
                song.votes[user] = 1
                found = True
                break
        self.lock.release()
        if found:
            self.sort_queue()
        else:
            print("vote_up: song not found for sid: " + str(sid))

    def vote_down(self, user, sid):
        found = False
        self.lock.acquire()
        for song in self.playing_queue:
            if sid == song.id:
                song.votes[user] = -1
                found = True
                break
        self.lock.release()
        if found:
            self.sort_queue()
        else:
            print("vote_down: song not found for sid: " + str(sid))
