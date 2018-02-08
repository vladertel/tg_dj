# Abstract Download
import os

class ShouldNotBeCalled(Exception):
    pass


class AbstractDownloader():
    """docstring for AbstractDownloader"""

    def __init__(self):
        pass

    def is_acceptable(self, task):
        raise ShouldNotBeCalled(
            "this method should not be called from abstract class")

    def schedule_link(self, url, callback):
        raise ShouldNotBeCalled(
            "this method should not be called from abstract class")

    def touch_without_creation(self, fname):
        try:
            os.utime(fname, None)
        except OSError:
            print("Touched unexistent path")

    def schedule_task(self, task):
        raise ShouldNotBeCalled(
            "this method should not be called from abstract class")
