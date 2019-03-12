import time
from mpd import MPDClient
from mpd.base import CommandError as MPDCommandError
from prometheus_client import Gauge
import concurrent.futures
import asyncio
import traceback
import logging
import os


class MPDStreamer:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger('tg_dj.bot')
        self.logger.setLevel(getattr(logging, self.config.get("streamer_mpd", "verbosity", fallback="warning").upper()))

        self.is_playing = False
        self.now_playing = None
        self.song_start_time = 0
        self.core = None

        # noinspection PyArgumentList
        self.mon_is_playing = Gauge('dj_is_playing', 'Is something paying now')
        self.mon_is_playing.set_function(lambda: 1 if self.is_playing else 0)

        self.thread_pool = concurrent.futures.ThreadPoolExecutor()
        self.error_interval = .25
        self.interval = 0
        self.timeout = 20
        self.mpd_polling_task = None

        self.mpd_client = MPDClient()
        self.init_handlers()

    def bind_core(self, core):
        self.core = core
        self.mpd_polling_task = self.core.loop.create_task(self.mpd_status_polling())

    def init_handlers(self):
        self.mpd_client.timeout = 1
        self.mpd_client.connect("localhost", 6600)
        print(self.mpd_client.mpd_version)

        self.mpd_client.stop()
        self.mpd_client.clear()
        self.mpd_client.consume(1)
        self.mpd_client.single(0)
        self.mpd_client.addid("silence.mp3")

    async def mpd_status_polling(self):
        try:
            while True:
                # noinspection PyBroadException
                try:
                    await asyncio.sleep(self.interval)
                    await self.core.loop.run_in_executor(self.thread_pool, self.get_updates)
                except Exception as e:
                    self.logger.error("Polling exception: %s", str(e))
                    traceback.print_exc()
        except concurrent.futures.CancelledError:
            self.logger.info("Polling task have been canceled")

    def get_updates(self):
        try:
            updates = self.mpd_client.idle("playlist")
            print(updates)
            self.error_interval = .25
            if len(updates):
                self.logger.debug("Updates received: %s" % len(updates))
            self.updates_handler(updates)
        except Exception as e:
            self.logger.error("API Exception: %s", str(e))
            traceback.print_exc()
            self.logger.debug("Waiting for %d seconds until retry" % self.error_interval)
            time.sleep(self.error_interval)
            self.error_interval *= 2

    def updates_handler(self, updates):
        if "playlist" in updates:
            status = self.mpd_client.status()
            print(self.mpd_client.status())
            if status["playlistlength"] == "1":
                self.mpd_song_finished()

    def cleanup(self):
        try:
            self.mpd_client.noidle()
        except MPDCommandError:
            pass
        self.mpd_client.stop()

    def mpd_song_finished(self):
        self.is_playing = False
        self.now_playing = None
        self.core.loop.call_soon_threadsafe(self.core.track_end_event)

    def get_current_song(self):
        return self.now_playing

    def get_song_progress(self):
        return int(time.time() - self.song_start_time)

    def stop(self):
        try:
            self.mpd_client.noidle()
        except MPDCommandError:
            pass
        self.mpd_client.stop()
        self.is_playing = False
        self.now_playing = None

    def switch_track(self, track):
        uri = track.media[len("/home/vpolikarpov/code/tg_dj/"):]
        print(uri)
        try:
            self.mpd_client.noidle()
        except MPDCommandError:
            pass
        self.mpd_client.update("/")
        playlist_len = int(self.mpd_client.status()["playlistlength"])
        track_id = self.mpd_client.addid(uri, playlist_len)
        self.mpd_client.playid(track_id)
        self.is_playing = True
        self.now_playing = track
        self.song_start_time = time.time()
