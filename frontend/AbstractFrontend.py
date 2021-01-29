import logging

from brain.DJ_Brain import DjBrain


class ShouldNotBeCalled(Exception):
    pass

class AbstractFrontend():
    def __init__(self, config):
        """
        :param configparser.ConfigParser config:
        """
        self.config = config
        self.logger = logging.getLogger("tg_dj.frontend.abstract")
        self.logger.setLevel(getattr(logging, self.config.get("frontend", "verbosity", fallback="warning").upper()))

    def notify_user(self, core_user_id: int, text: str):
        raise ShouldNotBeCalled()

    def accept_user(self, core_user_id: int) -> bool:
        raise ShouldNotBeCalled()

    def bind_core(self, core: DjBrain):
        raise ShouldNotBeCalled()
