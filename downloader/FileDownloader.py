import os
import requests

from .AbstractDownloader import AbstractDownloader
from frontend.private_config import token as bot_token
from .config import mediaDir, _DEBUG_, MAXIMUM_DURATION, MAXIMUM_FILE_SIZE
from .exceptions import *
from .storage_checker import filter_storage


class FileDownloader(AbstractDownloader):
    name = "file downloader"

    def is_acceptable(self, task):
        return "file" in task

    def schedule_task(self, task):
        file_id = task["file"]
        duration = task["duration"]
        file_size = task["file_size"]
        file_info = task["file_info"]

        artist = task["artist"].strip()
        if len(artist) == 0:
            artist = "TG_DJ"

        title = task["title"].strip()
        if len(title) == 0:
            title = "Music"

        title = artist + " - " + title

        if _DEBUG_:
            print("DEBUG [FileDownloader]: downloading song #" + str(file_id) + ": " + title)

        if duration > MAXIMUM_DURATION:
            raise MediaIsTooLong()

        if file_size > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig()

        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = file_id + ".mp3"
        file_path = os.path.join(file_dir, file_name)

        if self.is_in_cache(file_path):
            return file_path, title, duration

        response = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(bot_token, file_info.file_path))
        if response.status_code != 200:
            raise BadReturnStatus(response.status_code)
        with open(file_path, 'wb') as f:
            f.write(response.content)

        if _DEBUG_:
            print("DEBUG [FileDownloader]: Download complete #" + str(file_id))

        self.touch_without_creation(file_path)
        filter_storage()
        return file_path, title, duration
