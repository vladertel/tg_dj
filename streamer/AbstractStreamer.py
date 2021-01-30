import logging


class ShouldNotBeCalled(Exception):
    pass


class AbstractStreamer:
    def __init__(self, config):
        """
        :param configparser.ConfigParser config:
        """
        self.config = config
        self.logger = logging.getLogger("tg_dj.streamer.abstract")
        self.logger.setLevel(getattr(logging, self.config.get("streamer", "verbosity", fallback="warning").upper()))

    def bind_core(self, core):
        """
        :param brain.DJ_Brain.DjBrain core
        """
        raise ShouldNotBeCalled()

    def get_current_song(self):
        raise ShouldNotBeCalled()

    def get_song_progress(self):
        raise ShouldNotBeCalled()

    def stop(self):
        raise ShouldNotBeCalled()

    def switch_track(self, track):
        raise ShouldNotBeCalled()
