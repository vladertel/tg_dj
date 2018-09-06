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

    def touch_without_creation(self, fname):
        try:
            os.utime(fname, None)
        except OSError:
            print("Touched unexistent path")

    def search(self, task, user_message=lambda text: True):
        raise ShouldNotBeCalled(
            "this method should not be called from abstract class")

    def download(self, task, user_message=lambda text: True):
        raise ShouldNotBeCalled(
            "this method should not be called from abstract class")

    def is_in_cache(self, file_path):
        return os.path.exists(file_path) and os.path.getsize(file_path) > 0
