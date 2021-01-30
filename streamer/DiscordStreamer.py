from typing import Optional

from brain.DJ_Brain import DjBrain
from frontend.DiscordFrontend import DiscordFrontend
from streamer.AbstractStreamer import AbstractStreamer


# noinspection PyMissingConstructor
class DiscordStreamer(AbstractStreamer):
    def __init__(self, config, discord_frontend: DiscordFrontend):
        """
        :param configparser.ConfigParser config:
        """
        self.config = config
        self.discord_frontend = discord_frontend
        self.core: Optional[DjBrain] = None

    def bind_core(self, core: DjBrain):
        self.core = core

    def stop(self):
        pass

    def switch_track(self, track):
        pass

    def get_current_song(self):
        pass

    def get_song_progress(self):
        pass
