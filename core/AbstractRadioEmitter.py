from core.AbstractComponent import AbstractComponent, ShouldNotBeCalled
from core.models import Song


class AbstractRadioEmitter(AbstractComponent):
    def bind_core(self, core):
        """
        :param core.DJ_Brain.DjBrain core
        """
        raise ShouldNotBeCalled()

    def get_current_song(self) -> Song:
        raise ShouldNotBeCalled()

    def get_song_progress(self) -> int:
        raise ShouldNotBeCalled()

    def stop(self):
        raise ShouldNotBeCalled()

    def switch_track(self, track: Song):
        raise ShouldNotBeCalled()
