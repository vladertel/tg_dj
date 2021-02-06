import logging
from typing import List, Optional

from brain.DJ_Brain import DjBrain
from frontend.AbstractFrontend import AbstractFrontend, FrontendUserInfo


# noinspection PyMissingConstructor
class MasterFrontend(AbstractFrontend):
    def __init__(self, config, *frontends):
        self.config = config
        self.logger = logging.getLogger("tg_dj.frontend.abstract")
        self.core: Optional[DjBrain] = None
        self.frontends: List[AbstractFrontend] = frontends
        for frontend in self.frontends:
            frontend.bind_master(self)

    def notify_user(self, core_user_id: int, text: str):
        for frontend in self.frontends:
            if frontend.accept_user(core_user_id):
                frontend.notify_user(core_user_id, text)

    def bind_core(self, core: DjBrain):
        self.core = core
        for frontend in self.frontends:
            frontend.bind_core(core)

    def get_user_infos(self, core_id: int) -> List[FrontendUserInfo]:
        user_infos = []
        for frontend in self.frontends:
            user_info = frontend.get_user_info(core_id)
            if user_info is not None:
                user_infos.append(user_info)
        return user_infos
