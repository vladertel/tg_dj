import threading
import json
from .config import queueDir
from os.path import join


class Song():
    ids = 1

    @classmethod
    def new(cls, path_to_media, title, duration, user):
        obj = cls()
        obj.title = title
        obj.duration = duration
        obj.media = path_to_media
        obj.user = user
        obj.votes = {}  # e.g. user: value
        obj.rating = 0
        obj.id = Song.ids
        Song.ids += 1
        return obj

    def __repr__(self):
        return "Song(Title: {}, id: {:d})".format(self.title, self.id)

    def __str__(self):
        return "Song(Title: {}, id: {:d})".format(self.title, self.id)

    @classmethod
    def deserialize(cls, objecta):
        obj = cls()
        obj.title = objecta["title"]
        obj.duration = objecta["duration"]
        obj.media = objecta["media"]
        obj.user = objecta["user"]
        obj.votes = objecta["votes"]
        obj.rating = objecta["rating"]
        obj.id = objecta["id"]
        return obj


class Scheduler():
    def __init__(self):
        self.is_media_playing = False
        self.playing_queue = []
        self.lock = threading.Lock()
        self.load_init()

    def load_init(self):
        try:
            with open(join(queueDir, "queue")) as f:
                dicts = json.loads(f.read())
                Song.ids = dicts["last_id"]
                queue = []
                if len(dicts) > 0:
                    for obj in dicts["songs"]:
                        queue.append(Song.deserialize(obj))
                    self.playing_queue = queue
                    self.sort_queue()
        except FileNotFoundError:
            pass

    def cleanup(self):
        output = [a.__dict__ for a in self.playing_queue]
        jsonya = {
            "last_id": Song.ids,
            "songs": output
        }
        with open(join(queueDir, "queue"), "w") as f:
            f.write(json.dumps(jsonya, ensure_ascii=False))


    def add_track_to_end_of_queue(self, path, title, duration, user):
        self.lock.acquire()
        self.playing_queue.append(Song.new(path, title, duration, user))
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
        k = 0
        for song in self.playing_queue:
            k += 1
            if sid == song.id:
                return (song, k)
        return (None, None)

    def get_queue(self):
        return list(self.playing_queue)

    def get_queue_page(self, page):
        queue = list(self.playing_queue)
        qlen = len(queue)
        if qlen == 0:
            return ([], 0, True)
        start = page * 10
        if start >= qlen:
            lendiv, lenmod = divmod(qlen, 10)
            return (queue[lendiv * 10:], lendiv, True)
        if start < 0:
            start = 0
        end = start + 10
        return (queue[start:end], page, qlen <= end)

    def get_queue_len(self):
        return len(self.playing_queue)

    def remove_from_queue(self, sid):
        self.lock.acquire()
        k = 0
        for song in self.playing_queue:
            k += 1
            if sid == song.id:
                try:
                    self.playing_queue.remove(song)
                    break
                except ValueError:
                    print("scheduler: TRIED TO REMOVE UNREMOVEABLE")
        self.lock.release()
        return k

    def queue_length(self):
        return len(self.playing_queue)

    def sort_queue(self):
        self.lock.acquire()
        self.playing_queue = sorted(self.playing_queue, key=lambda x: x.id - sum([x.votes[k] for k in x.votes]))
        self.lock.release()

    def vote_up(self, user, sid):
        found = False
        self.lock.acquire()
        k = 0
        for song in self.playing_queue:
            k += 1
            if sid == song.id:
                song.votes[user] = 1
                found = True
                break
        self.lock.release()
        if found:
            self.sort_queue()
            return (song, k)
        else:
            print("vote_down: song not found for sid: " + str(sid))
            return (None, None)

    def vote_down(self, user, sid):
        found = False
        self.lock.acquire()
        k = 0
        for song in self.playing_queue:
            k += 1
            if sid == song.id:
                song.votes[user] = -1
                found = True
                break
        self.lock.release()
        if found:
            self.sort_queue()
            return (song, k)
        else:
            print("vote_down: song not found for sid: " + str(sid))
            return (None, None)
