import threading
import json
from os.path import join
import os
import random

from utils import get_mp3_title_and_duration

from .config import queueDir


def get_files_in_dir(directory):
    return [f for f in os.listdir(directory) if
            os.path.isfile(os.path.join(directory, f)) and not f.startswith(".")]


class Song:
    ids = 1

    title = ""
    id = None

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


class Scheduler:
    def __init__(self):
        self.is_media_playing = False
        self.playing_queue = []
        self.backlog = []
        self.backlog_played = []
        self.backlog_played_media = []
        self.backlog_initial_size = 0

        self.lock = threading.Lock()
        self.load_init()
        self.populate_backlog()

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
                try:
                    self.backlog_played_media = dicts["backlog_played_media"]
                except KeyError:
                    self.backlog_played_media = dicts["backlog_already_played"]
        except (FileNotFoundError, ValueError) as _:
            pass

    def populate_backlog(self):
        files = get_files_in_dir(os.path.join("brain", "backlog"))
        add_to_end = []
        for file in files:
            path = os.path.join(os.getcwd(), "brain", "backlog", file)
            title, duration = get_mp3_title_and_duration(path)
            if path in self.backlog_played_media:
                add_to_end.append(Song.new(path, title, duration, None))
            else:
                self.backlog.append(Song.new(path, title, duration, None))

        random.shuffle(self.backlog)
        random.shuffle(add_to_end)
        self.backlog += add_to_end

        print("INFO [Scheduler]: backlog capacity: " + str(len(self.backlog)))

    def cleanup(self):
        out_dict = {
            "last_id": Song.ids,
            "songs": [a.__dict__ for a in self.playing_queue],
            "backlog_played_media": [a.media for a in self.backlog_played]
        }
        with open(join(queueDir, "queue"), "w") as f:
            f.write(json.dumps(out_dict, ensure_ascii=False))
        print("Scheduler - saved queue")

    def add_track_to_end_of_queue(self, path, title, duration, user):
        self.lock.acquire()
        self.playing_queue.append(Song.new(path, title, duration, user))
        self.lock.release()
        return len(self.playing_queue)

    def pop_first_track(self):
        self.lock.acquire()
        try:
            song = self.playing_queue.pop(0)
            print("INFO [Scheduler]: Playing main queue: %s" % song.title)
        except IndexError:
            try:
                song = self.backlog.pop(0)
                print("INFO [Scheduler]: Playing backlog queue: %s" % song.title)
                self.backlog_played.append(song)

                if len(self.backlog) <= self.backlog_initial_size // 2:
                    i = random.randrange(len(self.backlog_played))
                    self.backlog.append(self.backlog_played.pop(i))

            except IndexError:
                print("INFO [Scheduler]: Nothing to play")
                song = None
        self.lock.release()
        return song

    def get_next_song(self):
        try:
            return self.playing_queue[0]
        except IndexError:
            try:
                return self.backlog[0]
            except IndexError:
                return None

    def get_song(self, sid):
        k = 0
        for song in self.playing_queue:
            k += 1
            if sid == song.id:
                return song, k
        return None, None

    def get_queue(self):
        return list(self.playing_queue)

    def get_queue_page(self, page):
        queue = list(self.playing_queue)
        queue_length = len(queue)
        if queue_length == 0:
            return [], 0, True
        start = page * 10
        if start >= queue_length:
            div, _ = divmod(queue_length, 10)
            return queue[div * 10:], div, True
        if start < 0:
            start = 0
        end = start + 10
        return queue[start:end], page, queue_length <= end

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
                    print("ERROR [Scheduler]: Have tried to remove unremovable")
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
        song = None
        for song in self.playing_queue:
            k += 1
            if sid == song.id:
                song.votes[user] = 1
                found = True
                break
        self.lock.release()
        if found:
            self.sort_queue()
            return song, k
        else:
            print("ERROR [Scheduler]: vote_up: song not found for sid: " + str(sid))
            return None, None

    def vote_down(self, user, sid):
        found = False
        self.lock.acquire()
        k = 0
        song = None
        for song in self.playing_queue:
            k += 1
            if sid == song.id:
                song.votes[user] = -1
                found = True
                break
        self.lock.release()
        if found:
            self.sort_queue()
            return song, k
        else:
            print("ERROR [Scheduler]: vote_down: song not found for sid: " + str(sid))
            return None, None
