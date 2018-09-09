import os
import time
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

    def download(self, task, user_message=lambda text: True):
        file_id = task["file"]
        duration = task["duration"]
        file_size = task["file_size"]
        file_info = task["file_info"]

        if _DEBUG_:
            print("DEBUG [FileDownloader]: Downloading song #" + str(file_id))

        artist = task["artist"].strip()
        title = task["title"].strip()
        if len(title) == 0:
            title = "Unknown"
        if len(artist) > 0:
            title = artist + " — " + title

        if _DEBUG_:
            print("DEBUG [FileDownloader]: Title for song #" + str(file_id) + ": " + title)

        if duration > MAXIMUM_DURATION:
            raise MediaIsTooLong(duration)

        if file_size > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig(file_size)

        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = file_id + ".mp3"
        file_path = os.path.join(file_dir, file_name)

        if self.is_in_cache(file_path):
            user_message("Песня добавлена в очередь\n%s" % title)
            return file_path, title, duration

        user_message("Скачиваем...\n%s" % title)
        if _DEBUG_:
            print("DEBUG [FileDownloader]: Querying Telegram API")

        self.get_file(
            url='https://api.telegram.org/file/bot{0}/{1}'.format(bot_token, file_info.file_path),
            file_path=file_path,
            file_size=file_size,
            percent_callback=lambda p: user_message("Скачиваем [%d%%]...\n%s" % (int(p), title)),
        )

        if _DEBUG_:
            print("DEBUG [FileDownloader]: Download complete #" + str(file_id))

        self.touch_without_creation(file_path)
        filter_storage()

        if _DEBUG_:
            print("DEBUG [FileDownloader]: File stored in path: " + file_path)

        user_message("Песня добавлена в очередь\n%s" % title)
        return file_path, title, duration
