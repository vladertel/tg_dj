import os
import requests
import re

from urllib import parse
from unidecode import unidecode
from mutagen.mp3 import MP3

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, MAXIMUM_DURATION, MAXIMUM_FILE_SIZE
from .exceptions import BadReturnStatus, MediaIsTooLong, MediaIsTooBig, UnappropriateArgument, UrlOrNetworkProblem
from .storage_checker import filter_storage


def get_mp3_title_and_duration(path):
    audio = MP3(path)

    try:
        artist = str(audio.tags.getall("TPE1")[0][0])
    except IndexError:
        artist = None
    try:
        title = str(audio.tags.getall("TIT2")[0][0])
    except IndexError:
        title = None

    if artist is not None and title is not None:
        ret = artist + " - " + title
    elif artist is not None:
        ret = artist
    elif title is not None:
        ret = title
    else:
        ret = os.path.splitext(os.path.basename(path[:-4]))[0]

    if _DEBUG_:
        print("DEBUG [LinkDownloader]: Media name: " + ret)

    return ret, audio.info.length


class LinkDownloader(AbstractDownloader):

    def __init__(self):
        super().__init__()
        self.mp3_dns_regex = re.compile(
            r"(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9_-]{3,30}\.)+[a-zA-Z]{2,4}\/.*\.mp3[a-zA-Z0-9_\?\&\=\-]*",
            flags=re.IGNORECASE)
        self.mp3_ip4_regex = re.compile(
            r"(?:https?://)?([0-9]{1,3}\.){3}([0-9]{1,3})\/.*\.mp3[a-zA-Z0-9_\?\&\=\-]*",
            flags=re.IGNORECASE)
        self.name = "links downloader"

    def is_acceptable(self, task):
        if "text" in task:
            match = self.mp3_dns_regex.search(task["text"])
            if match:
                return match.group(0)
            match = self.mp3_ip4_regex.search(task["text"])
            if match:
                return match.group(0)
        return False

    def download(self, task, user_message=lambda text: True):
        url = None
        match = self.mp3_dns_regex.search(task["text"])
        if match:
            url = match.group(0)
        match = self.mp3_ip4_regex.search(task["text"])
        if match:
            url = match.group(0)
        if url is None:
            raise UnappropriateArgument()

        if _DEBUG_:
            print("DEBUG [LinkDownloader]: Sending HEAD to url: " + url)

        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = unidecode(parse.unquote(url).split("/")[-1] + ".mp3")
        file_path = os.path.join(file_dir, file_name)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            title, duration = get_mp3_title_and_duration(file_path)
            user_message("Песня добавлена в очередь\n%s" % title)
            return file_path, title, duration

        user_message("Скачиваем...")

        try:
            response = requests.head(url, allow_redirects=True)
        except requests.exceptions.ConnectionError as e:
            raise UrlOrNetworkProblem(e)
        if response.status_code != 200:
            raise BadReturnStatus(response.status_code)
        try:
            file_size = response.headers['content-length']
        except KeyError as e:
            print("LinkDownloader: no such header: content-length")
            print(response.headers)
            raise e
        if int(file_size) > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig()

        try:
            response = requests.get(url, stream=True)
        except requests.exceptions.ConnectionError as e:
            raise UrlOrNetworkProblem(e)
        if response.status_code != 200:
            raise BadReturnStatus(response.status_code)

        with open(file_path, 'wb') as f:
            f.write(response.content)

        title, duration = get_mp3_title_and_duration(file_path)
        if duration > MAXIMUM_DURATION:
            os.unlink(file_path)
            raise MediaIsTooLong()

        self.touch_without_creation(file_path)
        filter_storage()

        user_message("Песня добавлена в очередь\n%s" % title)
        return file_path, title, duration
