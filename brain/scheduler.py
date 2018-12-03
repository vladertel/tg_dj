import threading
import json
import os
import random

from utils import get_mp3_info

from .config import queueDir
from .models import Song


def get_files_in_dir(directory):
    return [f for f in os.listdir(directory) if
            os.path.isfile(os.path.join(directory, f)) and not f.startswith(".")]


class Scheduler:
    def __init__(self):
        self.is_media_playing = False
        self.playlist = []
        self.backlog = []
        self.backlog_played = []
        self.backlog_played_media = []
        self.backlog_initial_size = 0

        self.lock = threading.Lock()
        self.load_init()
        self.populate_backlog()

    def load_init(self):
        try:
            with open(os.path.join(queueDir, "queue")) as f:
                dicts = json.loads(f.read())
                Song.counter = dicts["last_id"]
                queue = []
                if len(dicts) > 0:
                    for d in dicts["songs"]:
                        queue.append(Song.from_dict(d))
                    self.playlist = queue
                try:
                    self.backlog_played_media = dicts["backlog_played_media"]
                except KeyError:
                    self.backlog_played_media = dicts["backlog_already_played"]
        except (FileNotFoundError, ValueError) as _:
            pass

    def populate_backlog(self):
        files = get_files_in_dir(os.path.join(os.getcwd(), "brain", "backlog"))
        add_to_end = []
        for file in files:
            path = os.path.join(os.getcwd(), "brain", "backlog", file)
            title, artist, duration = get_mp3_info(path)
            if path in self.backlog_played_media:
                add_to_end.append(Song(path, title, artist, duration, None))
            else:
                self.backlog.append(Song(path, title, artist, duration, None))

        random.shuffle(self.backlog)
        random.shuffle(add_to_end)
        self.backlog += add_to_end

        print("INFO [Scheduler - populate_backlog]: Fallback playlist length: %d " % len(self.backlog))

    def cleanup(self):
        out_dict = {
            "last_id": Song.counter,
            "songs": [a.to_dict() for a in self.playlist],
            "backlog_played_media": [a.media for a in self.backlog_played]
        }
        file_name = os.path.join(queueDir, "queue")
        with open(file_name, "w") as f:
            f.write(json.dumps(out_dict, ensure_ascii=False))
            print("INFO [Scheduler - cleanup]: Queue has been saved to file \"%s\"" % file_name)

    def push_track(self, path, title, artist, duration, user_id):
        self.lock.acquire()
        song = Song(path, title, artist, duration, user_id)
        self.playlist.append(song)
        self.lock.release()
        return song, len(self.playlist)

    def play_next(self, song):
        self.lock.acquire()
        self.playlist.insert(0, song)
        self.lock.release()
        return song, len(self.playlist)

    def pop_first_track(self):
        self.lock.acquire()
        if len(self.playlist) > 0:
            song = self.playlist.pop(0)
            print("INFO [Scheduler - pop]: Playing song from main playlist: %s" % song.title)
        else:
            try:
                song = self.backlog.pop(0)
                print("INFO [Scheduler - pop]: Playing song from fallback playlist: %s" % song.title)
                self.backlog_played.append(song)

                if len(self.backlog) <= self.backlog_initial_size // 2:
                    i = random.randrange(len(self.backlog_played))
                    self.backlog.append(self.backlog_played.pop(i))
            except IndexError:
                song = None
        self.lock.release()
        return song

    def get_next_song(self):
        if len(self.playlist) > 0:
            return self.playlist[0]
        else:
            try:
                return self.backlog[0]
            except IndexError:
                return None

    def get_song(self, sid):
        k = 0
        for song in self.playlist:
            k += 1
            if sid == song.id:
                return song, k
        return None, None

    def get_queue(self, offset=0, limit=0):
        if limit == 0:
            return list(self.playlist)[offset:]
        else:
            return list(self.playlist)[offset:offset + limit]

    def get_queue_length(self):
        return len(self.playlist)

    def remove_from_queue(self, sid):
        self.lock.acquire()
        try:
            song = next(s for s in self.playlist if s.id == sid)
            position = self.playlist.index(song)
            self.playlist.remove(song)
        except (ValueError, StopIteration):
            position = None
            print("WARNING [Scheduler - remove]: Unable to remove song #%d from the playlist")
        self.lock.release()
        return position

    def raise_track(self, sid):
        self.lock.acquire()
        try:
            song = next(s for s in self.playlist if s.id == sid)
            self.playlist.remove(song)
            self.playlist.insert(0, song)
        except (ValueError, StopIteration):
            print("WARNING [Scheduler - remove]: Unable to raise song #%d")
        self.lock.release()

    def queue_length(self):
        return len(self.playlist)

    def vote_up(self, user_id, song_id):
        self.lock.acquire()
        try:
            song = next(s for s in self.playlist if s.id == song_id)
            if user_id in song.haters:
                song.haters.remove(user_id)
        except (ValueError, StopIteration):
            print("WARNING [Scheduler - vote_up]: Unable to find song #%d in the playlist")
        self.lock.release()

    def vote_down(self, user_id, song_id):
        self.lock.acquire()
        try:
            song = next(s for s in self.playlist if s.id == song_id)
            if user_id not in song.haters:
                song.haters.append(user_id)
        except (ValueError, StopIteration):
            print("WARNING [Scheduler - vote_down]: Unable to find song #%d in the playlist")
        self.lock.release()
