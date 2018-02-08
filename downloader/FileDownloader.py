import os
import requests

import mutagen
from unidecode import unidecode

from .AbstractDownloader import AbstractDownloader
from frontend.config import token as bot_token
from .config import mediaDir, _DEBUG_, MAXIMUM_DURATION
from .exceptions import *
from .storage_checker import StorageFilter

sf = StorageFilter()
        # self.output_queue.put({
        #     "user": message.from_user.id,
        #     "file": message.audio.file_id,
        #     "duration": message.audio.duration,
        #     "action": "download",
        #     "file_size": message.audio.file_size
        # })

class FileDownloader(AbstractDownloader):

    def is_acceptable(self, task):
        return "file" in task

    def schedule_link(self, user, file_id, duration, file_info, file_size=None):
        if duration > MAXIMUM_DURATION:
            raise MediaIsTooLong()
        downloaded = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(bot_token, file_info.file_path))
        if downloaded.status_code != 200:
            raise BadReturnStatus(songs.status_code)
        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = file_id + ".mp3"
        file_path = os.path.join(file_dir, file_name)
        with open(file_path, 'wb') as f:
            f.write(downloaded.content)
        # from mutagen.mp3 import MP3
        # audio = MP3("example.mp3")
        # print audio.info.length
        info = mutagen.File(file_path)
        title = "Not provided"
        if "artist" in info and "title" in info:
            title = info["artist"] + " - " + info["title"]
            file_name = title + ".mp3"
            new_file_path = unidecode(os.path.join(file_dir, file_name))
            os.rename(file_path, new_file_path)
            file_path = new_file_path
        self.touch_without_creation(file_path)
        sf.filter_storage()
        return (file_path, title, duration)


    def schedule_task(self, task):
        return self.schedule_link(task["user"], task["file"], task["duration"], task["file_info"], task["file_size"])

