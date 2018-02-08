import os
import requests

from unidecode import unidecode
from mutagen.mp3 import MP3

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, MAXIMUM_DURATION, MAXIMUM_FILE_SIZE
from .exceptions import BadReturnStatus, MediaIsTooLong, UrlOrNetworkProblem, MediaIsTooBig

def get_mp3_title_and_duration(path):
    audio = MP3(path)
    title = "Not provided"
    if "artist" in audio and "title" in audio:
        title = info["artist"] + " - " + info["title"]
    return (title, audio.info.length)

class LinkDownloader(AbstractDownloader):

    def schedule_link(self, url):
        response = requests.head(url, allow_redirects=True)
        if response.status_code != 200:
            raise BadReturnStatus(response.status_code)
        try:
            file_size = response.headers['content-length']
        except KeyError as e:
            print("LinkDownloader: no such header: content-length")
            print(response.headers)
            raise e
        if file_size > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig()

        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = unidecode(url.split("/")[-1] + ".mp3")
        file_path = os.path.join(file_dir, file_name)

        if os.path.exists(file_path):
            title, duration = get_mp3_title_and_duration(file_path)
            return (file_path, title, duration)

        downloaded = requests.get(url, stream=True)
        if downloaded.status_code != 200:
            raise BadReturnStatus(downloaded.status_code)

        with open(file_path, 'wb') as f:
            f.write(downloaded.content)

        title, duration = get_mp3_title_and_duration(file_path)
        if duration > MAXIMUM_DURATION:
            os.unlink(file_path)
            raise MediaIsTooLong()

        self.touch_without_creation(file_path)
        sf.filter_storage()

        return (file_path, title, duration)