from core.AbstractComponent import AbstractComponent, ShouldNotBeCalled
from core.models import Song


class AbstractRadioEmitter(AbstractComponent):
    def stop(self):
        raise ShouldNotBeCalled()

    def switch_track(self, track: Song):
        raise ShouldNotBeCalled()
