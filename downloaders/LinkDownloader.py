import os
import requests
import re
import logging

from urllib import parse

from core.AbstractDownloader import AbstractDownloader, UrlOrNetworkProblem, MediaIsTooLong, MediaIsTooBig, \
    MediaSizeUnspecified, BadReturnStatus, UnappropriateArgument
from utils import get_mp3_info, sanitize_file_name, remove_links


class LinkDownloader(AbstractDownloader):

    def __init__(self, config):
        super().__init__(config)
        self.logger = logging.getLogger("tg_dj.downloader.link")
        self.logger.setLevel(
            getattr(logging, self.config.get("downloader_link", "verbosity", fallback="warning").upper())
        )
        self.mp3_dns_regex = re.compile(
            r"(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9_-]{3,30}\.)+[a-zA-Z]{2,4}\/.*[a-zA-Z0-9_\?\&\=\-]*",
            flags=re.IGNORECASE)
        self.mp3_ip4_regex = re.compile(
            r"(?:https?://)?([0-9]{1,3}\.){3}([0-9]{1,3})\/.*[a-zA-Z0-9_\?\&\=\-]*",
            flags=re.IGNORECASE)
        self.name = "links downloader"

    def get_name(self):
        return "link"

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

        self.logger.debug("Sending HEAD to url: " + url)

        media_dir = self.config.get("downloader", "media_dir", fallback="media")

        file_dir = os.path.join(os.getcwd(), media_dir)
        file_name = sanitize_file_name(parse.unquote(url).split("/")[-1] + ".mp3")
        file_path = os.path.join(file_dir, file_name)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            title, artist, duration = get_mp3_info(file_path)
            title = remove_links(title)
            artist = remove_links(artist)
            return file_path, title, artist, duration

        user_message("Скачиваем...")
        self.logger.debug("Querying URL")

        try:
            response_head = requests.head(url, allow_redirects=True)
        except requests.exceptions.ConnectionError as e:
            raise UrlOrNetworkProblem(e)
        if response_head.status_code != 200:
            raise BadReturnStatus(response_head.status_code)
        try:
            file_size = int(response_head.headers['content-length'])
        except KeyError:
            self.logger.error("No content-length header. Headers: %s", str(response_head.headers))
            raise MediaSizeUnspecified()
        if file_size > 1000000 * self.config.getint("downloader", "max_file_size", fallback=self._default_max_size):
            raise MediaIsTooBig()

        self.get_file(
            url=url,
            file_path=file_path,
            file_size=file_size,
            percent_callback=lambda p: user_message("Скачиваем [%d%%]...\n" % int(p)),
        )

        title, artist, duration = get_mp3_info(file_path)
        title = remove_links(title)
        artist = remove_links(artist)
        if duration > self.config.getint("downloader", "max_duration", fallback=self._default_max_duration):
            os.unlink(file_path)
            raise MediaIsTooLong()

        self.touch_without_creation(file_path)

        return file_path, title, artist, duration
