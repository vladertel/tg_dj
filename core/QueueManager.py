import threading
import json
import os
import random
import logging
from typing import Optional, List, Mapping, Dict, Tuple

from mutagen.mp3 import HeaderNotFoundError
from prometheus_client import Gauge

from utils import get_mp3_info, remove_links
from .models import Song


def get_files_in_dir(directory):
    return [f for f in os.listdir(directory) if
            os.path.isfile(os.path.join(directory, f)) and not f.startswith(".")]


UID = int


class QueueManager:
    def __init__(self, config):
        """
        :param configparser.ConfigParser config:
        """
        self.config = config
        self.logger = logging.getLogger("tg_dj.queueManager")
        self.logger.setLevel(getattr(logging, self.config.get("queue_manager", "verbosity", fallback="warning").upper()))

        self.is_media_playing = False
        self.playlists: Dict[UID, List[Song]] = {}
        self.queue: List[UID] = []
        self.backlog: List[Song] = []
        self.backlog_played: List[Song] = []
        self.backlog_played_media: List[str] = []

        self.playlists[-1] = []  # For tracks managed by admins

        # noinspection PyArgumentList
        self.mon_queue_len = Gauge('dj_queue_length', 'Queue length')
        self.mon_queue_len.set_function(lambda: len(self.queue))
        # noinspection PyArgumentList
        self.mon_playlist_len = Gauge('dj_playlist_length', 'Playlist length')
        self.mon_playlist_len.set_function(lambda: sum(len(self.playlists[i]) for i in self.playlists))
        # noinspection PyArgumentList
        self.mon_backlog_len = Gauge('dj_backlog_length', 'Backlog length')
        self.mon_backlog_len.set_function(lambda: len(self.backlog))

        self.lock = threading.Lock()
        self.load_init()
        self.populate_backlog()

    def load_init(self):
        try:
            queue_file = self.config.get("queue_manager", "queue_file", fallback="queue.json")
            with open(queue_file) as f:
                data = json.loads(f.read())
                self.queue = data["queue"]
                Song.counter = data["last_id"]

                for pl in data["playlists"]:
                    user_id = pl["user_id"]
                    self.playlists[user_id] = []
                    for d in pl["tracks"]:
                        track = Song.from_dict(d)
                        self.playlists[user_id].append(track)

                try:
                    self.backlog_played_media = data["backlog_played_media"]
                except KeyError:
                    self.backlog_played_media = data["backlog_already_played"]
        except (FileNotFoundError, ValueError) as _:
            pass

    def populate_backlog(self):
        path = os.path.abspath(self.config.get("queue_manager", "fallback_media_dir", fallback="media_fallback"))
        files = get_files_in_dir(path)
        add_to_end = []
        for file in files:
            file_path = os.path.join(path, file)
            try:
                title, artist, duration = get_mp3_info(file_path)
            except HeaderNotFoundError as e:
                self.logger.warning(f"Not loading {file} because it does not look like mp3")
                continue
            title = remove_links(title)
            artist = remove_links(artist)
            if file_path in self.backlog_played_media:
                add_to_end.append(Song(file_path, title, artist, duration, -1))
            else:
                self.backlog.append(Song(file_path, title, artist, duration, -1))

        random.shuffle(self.backlog)
        random.shuffle(add_to_end)
        self.backlog += add_to_end

        self.logger.info("Fallback playlist length: %d " % len(self.backlog))

    def cleanup(self):
        out_dict = {
            "last_id": Song.counter,
            "queue": self.queue,
            "playlists": [{
                "user_id": user_id,
                "tracks": [a.to_dict() for a in tracks],
            } for user_id, tracks in self.playlists.items()],
            "backlog_played_media": [a.media for a in self.backlog_played]
        }
        queue_file = self.config.get("queue_manager", "queue_file", fallback="queue.json")
        with open(queue_file, "w") as f:
            f.write(json.dumps(out_dict, ensure_ascii=False))
            self.logger.info("Queue has been saved to file \"%s\"" % queue_file)

    # Tracks manipulations

    def add_track(self, path: str, title: str, artist: str, duration: int, user_id: int) -> Song:
        with self.lock:
            track = Song(path, title, artist, duration, user_id)

            if user_id not in self.playlists:
                self.playlists[user_id] = []

            self.playlists[user_id].append(track)

            return track

    def remove_track(self, tid: int) -> int:
        with self.lock:
            track = self.get_track(tid)
            local_pos, global_pos = self.get_track_position(track)
            if track is not None:
                user_id = track.user_id
                self.playlists[user_id].remove(track)
                if len(self.playlists[user_id]) == 0:
                    self.queue.remove(user_id)
                self.logger.info("Playing track from main queue: %s", track.title)
            else:
                self.logger.warning("Unable to remove track #%d from the playlist" % tid)
            return global_pos

    def raise_track(self, tid: int):
        with self.lock:
            track = self.get_track(tid)
            user_id = track.user_id
            if track is not None:
                self.playlists[user_id].remove(track)
                self.playlists[user_id].insert(0, track)
            else:
                self.logger.warning("Unable to raise track #%d")

    def play_next(self, track: Song) -> Tuple[Song, int]:
        with self.lock:
            user_id = track.user_id
            if user_id is None:
                user_id = -1

            self.playlists[user_id].insert(0, track)

            try:
                self.queue.remove(user_id)
            except ValueError:
                pass
            self.queue.insert(0, user_id)

            return track, len(self.playlists[user_id])

    def get_track(self, tid: int) -> Optional[Song]:
        user_ids = (uid for uid in self.queue if uid in self.playlists.keys())
        for uid in user_ids:
            for t in self.playlists[uid]:
                if t.id == tid:
                    return t
        return None

    def get_track_position(self, track: Optional[Song]) -> Tuple[Optional[int], Optional[int]]:
        if track is None:
            return None, None

        user_ids = (uid for uid in self.queue if uid in self.playlists.keys())

        user_position = self.queue.index(track.user_id)
        user_ids_ahead = self.queue[:user_position + 1]

        loc = self.playlists[track.user_id].index(track) + 1
        glob = sum(map(lambda uid: min(len(self.playlists[uid]), loc - 1), user_ids)) + \
            sum(1 for uid in user_ids_ahead if len(self.playlists[uid]) >= loc)

        return loc, glob

    def get_all_tracks(self) -> List[Song]:
        res = []
        for uid in self.playlists:
            res += [track for track in self.playlists[uid]]
        return res

    def get_tracks_queue_length(self):
        return sum(len(p) for p in (self.playlists[uid] for uid in self.queue if uid in self.playlists))

    def get_user_tracks(self, user_id: int) -> List[Song]:
        if user_id not in self.playlists:
            return []
        return self.playlists[user_id]

    def get_queue_tracks(self, offset: int=0, limit: int=0) -> List[Song]:
        tracks = []
        queue = [uid for uid in self.queue if uid in self.playlists.keys()]

        i = 0
        while True:
            end = True
            for uid in queue:
                if len(self.playlists[uid]) <= i:
                    continue
                tracks.append(self.playlists[uid][i])
                end = False
            i += 1
            if end:
                break

        if limit == 0:
            return tracks[offset:]
        else:
            return tracks[offset:offset + limit]

    def pop_first_track(self) -> Optional[Song]:
        with self.lock:

            track = None
            for uid in self.queue:
                if len(self.playlists[uid]) == 0:
                    continue

                track = self.playlists[uid].pop(0)
                self.queue.remove(uid)
                if len(self.playlists[uid]) != 0:
                    self.queue.append(uid)

                if not os.path.isfile(track.media):
                    self.logger.warning("Media does not exist for track: %s", track.title)
                    track = None
                    continue

                self.logger.info("Playing track from main queue: %s", track.title)
                break

            while track is None:
                try:
                    track: Optional[Song] = self.backlog.pop(0)
                    if not os.path.isfile(track.media):
                        self.logger.warning("Media does not exist for fallback track: %s", track.title)
                        track = None
                        continue

                    self.logger.info("Playing track from fallback playlist: %s", track.title)
                    self.backlog_played.append(track)

                    if len(self.backlog) <= len(self.backlog_played):
                        i = random.randrange(len(self.backlog_played))
                        self.backlog.append(self.backlog_played.pop(i))
                except IndexError:
                    track = None
                    break

            return track

    def get_first_track(self) -> Optional[Song]:
        for uid in self.queue:
            if len(self.playlists[uid]) > 0:
                return self.playlists[uid][0]
        try:
            return self.backlog[0]
        except IndexError:
            return None

    # Queue manipulations
    #
    # def get_queue(self, offset=0, limit=0) -> List[UID]:
    #     if limit == 0:
    #         return list(self.queue)[offset:]
    #     else:
    #         return list(self.queue)[offset:offset + limit]

    def get_users_queue_length(self):
        return len(self.queue)

    def is_in_queue(self, user_id: int) -> bool:
        return user_id in self.queue

    def add_to_queue(self, user_id: int):
        with self.lock:
            if user_id in self.queue:
                position = self.queue.index(user_id)
            else:
                if len(self.playlists[user_id]) > 0:
                    self.queue.append(user_id)
                    position = len(self.queue)
                else:
                    position = None
                    self.logger.warning("User can't enter queue with empty playlist")
            return position

    def remove_from_queue(self, user_id: int):
        with self.lock:
            try:
                position = self.queue.index(user_id)
                self.queue.remove(user_id)
            except ValueError:
                position = None
                self.logger.warning("Unable to remove user #%d from the queue" % user_id)
            return position

    def raise_user_in_queue(self, user_id: int):
        with self.lock:
            try:
                self.queue.remove(user_id)
                self.queue.insert(0, user_id)
            except ValueError:
                self.logger.warning("Unable to raise user #%d in the queue" % user_id)

    # Voting

    def vote_up(self, user_id: int, track_id: int):
        with self.lock:
            tracks = self.get_all_tracks()
            try:
                track = next(t for t in tracks if t.id == track_id)
                if user_id in track.haters:
                    track.haters.remove(user_id)
            except (ValueError, StopIteration):
                self.logger.warning("Unable to find track #%d in the playlists" % track_id)

    def vote_down(self, user_id: int, track_id: int):
        with self.lock:
            tracks = self.get_all_tracks()
            try:
                track = next(t for t in tracks if t.id == track_id)
                if user_id not in track.haters:
                    track.haters.append(user_id)
            except (ValueError, StopIteration):
                self.logger.warning("Unable to find track #%d in the playlists" % track_id)
