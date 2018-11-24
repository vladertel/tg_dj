# Abstract Download
import os
import time
import requests
from .exceptions import UrlOrNetworkProblem, BadReturnStatus

class ShouldNotBeCalled(Exception):
    pass


class AbstractDownloader():
    """docstring for AbstractDownloader"""

    def __init__(self):
        pass

    def is_acceptable(self, kind, query):
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

    def get_file(self, url, file_path, percent_callback=lambda x: True, file_size=None):
        try:
            response = requests.get(url, allow_redirects=True, stream=True)
        except requests.exceptions.ConnectionError as e:
            raise UrlOrNetworkProblem(e)
        if response.status_code != 200:
            raise BadReturnStatus(response.status_code)

        if file_size is None:
            file_size = response.headers.get('content-length')

        print("INFO [AbstractDownloader]: Downloading file \"%s\" of size \"%s\"" % (file_path, file_size))

        last_update = time.time()
        with open(file_path, 'wb') as f:
            if file_size is None:
                f.write(response.content)
            else:
                done = 0
                content_length = int(file_size)
                for buf in response.iter_content(chunk_size=100000):
                    done += len(buf)
                    f.write(buf)

                    new_time = time.time()
                    if new_time > last_update + 3:
                        last_update = new_time
                        percent_callback(100 * done / content_length)