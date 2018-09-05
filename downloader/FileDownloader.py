import os
import requests

import mutagen
from unidecode import unidecode

from .AbstractDownloader import AbstractDownloader
from frontend.private_config import token as bot_token
from .config import mediaDir, _DEBUG_, MAXIMUM_DURATION
from .exceptions import *
from .storage_checker import filter_storage

        # self.output_queue.put({
        #     "user": message.from_user.id,
        #     "file": message.audio.file_id,
        #     "duration": message.audio.duration,
        #     "action": "download",
        #     "file_size": message.audio.file_size
        # })

class FileDownloader(AbstractDownloader):
    name = "file downloader"

    def is_acceptable(self, task):
        return "file" in task

    def get_title(self, file_path):
        info = mutagen.File(file_path)
        title = "Not provided"
        if "artist" in info and "title" in info:
            title = info["artist"] + " - " + info["title"]
        return title

    def schedule_link(self, user, file_id, duration, file_info, file_size=None):
        if duration > MAXIMUM_DURATION:
            raise MediaIsTooLong()

        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = file_id + ".mp3"
        file_path = os.path.join(file_dir, file_name)

        if self.is_in_cache(file_path):
            return (file_path, self.get_title(file_path), duration)

        downloaded = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(bot_token, file_info.file_path))
        if downloaded.status_code != 200:
            raise BadReturnStatus(songs.status_code)
        with open(file_path, 'wb') as f:
            f.write(downloaded.content)

        info = mutagen.File(file_path)
        self.touch_without_creation(file_path)
        filter_storage()
        return (file_path, self.get_title(file_path), duration)

    def schedule_task(self, task):
        return self.schedule_link(task["user"], task["file"], task["duration"], task["file_info"], task["file_size"])

