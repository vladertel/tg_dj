from typing import Optional

from core.AbstractComponent import AbstractComponent, ShouldNotBeCalled


class FrontendUserInfo:
    def __init__(self, frontend_name: str, login: Optional[str], id: int):
        self.login = login  # aka username
        self.id = id
        self.frontend_name = frontend_name


class AbstractFrontend(AbstractComponent):
    def notify_user(self, core_user_id: int, text: str):
        raise ShouldNotBeCalled()

    def accept_user(self, core_user_id: int) -> bool:
        raise ShouldNotBeCalled()

    def bind_core(self, core):
        """
        :param core.DJ_Brain.DjBrain core:
        """
        raise ShouldNotBeCalled()

    def get_user_info(self, core_user_id: int) -> Optional[FrontendUserInfo]:
        raise ShouldNotBeCalled()
