import logging
from typing import List, Optional

from brain.DJ_Brain import DjBrain
from frontend.AbstractFrontend import AbstractFrontend


# noinspection PyMissingConstructor
class MasterFrontend(AbstractFrontend):
    def __init__(self, config, *frontends):
        self.config = config
        self.logger = logging.getLogger("tg_dj.frontend.abstract")
        self.core: Optional[DjBrain] = None
        self.frontends: List[AbstractFrontend] = frontends

    def notify_user(self, core_user_id: int, text: str):
        for frontend in self.frontends:
            if frontend.accept_user(core_user_id):
                frontend.notify_user(core_user_id, text)

    def bind_core(self, core: DjBrain):
        self.core = core
        for frontend in self.frontends:
            frontend.bind_core(core)
