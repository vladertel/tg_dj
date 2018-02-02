# Abstract Download


class ShouldNotBeCalled(Exception):
    pass


class AbstractDownloader():
    """docstring for AbstractDownloader"""

    def __init__(self):
        self.url = None

    def schedule_link(self, url, callback):
        raise ShouldNotBeCalled(
            "this method should not be called from abstract class")
