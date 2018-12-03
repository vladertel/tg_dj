import os

from .AbstractDownloader import AbstractDownloader
from .exceptions import *


class FileDownloader(AbstractDownloader):
    name = "file downloader"

    def is_acceptable(self, kind, query):
        return kind == "file"

    def download(self, query, user_message=lambda text: True):
        file_id = query["id"]
        duration = query["duration"]
        file_size = query["size"]
        file_info = query["info"]

        print("DEBUG [FileDownloader]: Downloading song #" + str(file_id))

        artist = query["artist"].strip()
        title = query["title"].strip()

        print("DEBUG [FileDownloader]: Title for song #" + str(file_id) + ": " + title)

        if duration > self.config.getint("downloader", "max_duration", fallback=self._default_max_duration):
            raise MediaIsTooLong(duration)

        if file_size > 1000000 * self.config.getint("downloader", "max_file_size", fallback=self._default_max_size):
            raise MediaIsTooBig(file_size)

        file_dir = self.config.get("downloader", "media_dir", fallback="media")
        file_name = file_id + ".mp3"
        file_path = os.path.join(file_dir, file_name)

        if self.is_in_cache(file_path):
            return file_path, title, artist, duration

        user_message("Скачиваем...\n%s" % title)
        print("DEBUG [FileDownloader]: Querying Telegram API")
        tg_api_url = self.config.get("telegram", "api_url", fallback="https://api.telegram.org/")
        bot_token = self.config.get("telegram", "token")

        self.get_file(
            url=tg_api_url + 'file/bot{0}/{1}'.format(bot_token, file_info.file_path),
            file_path=file_path,
            file_size=file_size,
            percent_callback=lambda p: user_message("Скачиваем [%d%%]...\n%s" % (int(p), title)),
        )

        print("DEBUG [FileDownloader]: Download complete #" + str(file_id))

        self.touch_without_creation(file_path)

        print("DEBUG [FileDownloader]: File stored in path: " + file_path)

        return file_path, title, artist, duration
