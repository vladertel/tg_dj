import logging
from typing import Optional


class ShouldNotBeCalled(Exception):
    pass


class FrontendUserInfo:
    def __init__(self, frontend_name: str, login: Optional[str], id: int):
        self.login = login # aka username
        self.id = id
        self.frontend_name = frontend_name

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

    def bind_core(self, core):
        """
        :param brain.DJ_Brain.DjBrain core:
        """
        raise ShouldNotBeCalled()

    def bind_master(self, master):
        """
        :param frontend.MasterFrontend.MasterFrontend master:
        """
        raise ShouldNotBeCalled()

    def get_user_info(self, core_user_id: int) -> Optional[FrontendUserInfo]:
        raise ShouldNotBeCalled()
