import os
import requests
import re

from urllib import parse

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, MAXIMUM_DURATION, MAXIMUM_FILE_SIZE
from .exceptions import *
from .storage_checker import filter_storage
from utils import get_mp3_info, sanitize_file_name


class LinkDownloader(AbstractDownloader):

    def __init__(self):
        super().__init__()
        self.mp3_dns_regex = re.compile(
            r"(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9_-]{3,30}\.)+[a-zA-Z]{2,4}\/.*[a-zA-Z0-9_\?\&\=\-]*",
            flags=re.IGNORECASE)
        self.mp3_ip4_regex = re.compile(
            r"(?:https?://)?([0-9]{1,3}\.){3}([0-9]{1,3})\/.*[a-zA-Z0-9_\?\&\=\-]*",
            flags=re.IGNORECASE)
        self.name = "links downloader"

    def is_acceptable(self, kind, query):
        if kind == "text":
            match = self.mp3_dns_regex.search(query)
            if match:
                return match.group(0)
            match = self.mp3_ip4_regex.search(query)
            if match:
                return match.group(0)
        return False

    def download(self, query, user_message=lambda text: True):
        url = None
        match = self.mp3_dns_regex.search(query)
        if match:
            url = match.group(0)
        match = self.mp3_ip4_regex.search(query)
        if match:
            url = match.group(0)
        if url is None:
            raise UnappropriateArgument()

        if _DEBUG_:
            print("DEBUG [LinkDownloader]: Sending HEAD to url: " + url)

        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = sanitize_file_name(parse.unquote(url).split("/")[-1] + ".mp3")
        file_path = os.path.join(file_dir, file_name)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            title, artist, duration = get_mp3_info(file_path)
            return file_path, title, artist, duration

        user_message("Скачиваем...")
        if _DEBUG_:
            print("DEBUG [LinkDownloader]: Querying URL")

        try:
            response_head = requests.head(url, allow_redirects=True)
        except requests.exceptions.ConnectionError as e:
            raise UrlOrNetworkProblem(e)
        if response_head.status_code != 200:
            raise BadReturnStatus(response_head.status_code)
        try:
            file_size = response_head.headers['content-length']
        except KeyError as e:
            print("ERROR [LinkDownloader]: No content-length header. See headers below:")
            print(str(response_head.headers))
            raise MediaSizeUnspecified()
        if int(file_size) > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig()

        self.get_file(
            url=url,
            file_path=file_path,
            file_size=file_size,
            percent_callback=lambda p: user_message("Скачиваем [%d%%]...\n" % int(p)),
        )

        title, artist, duration = get_mp3_info(file_path)
        if duration > MAXIMUM_DURATION:
            os.unlink(file_path)
            raise MediaIsTooLong()

        self.touch_without_creation(file_path)
        filter_storage()

        return file_path, title, artist, duration
