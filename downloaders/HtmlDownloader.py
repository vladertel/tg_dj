import os
import requests
from time import sleep
import lxml.html
import hashlib
import logging

from user_agent import generate_user_agent

from core.AbstractDownloader import AbstractDownloader, DownloaderException, MediaIsTooLong, MediaIsTooBig, \
    BadReturnStatus, NothingFound, ApiError
from utils import sanitize_file_name

# #DEBUG requests
# try:
#     import http.client as http_client
# except ImportError:
#     # Python 2
#     import httplib as http_client
# http_client.HTTPConnection.debuglevel = 1
#
# # You must initialize logging, otherwise you'll not see debug output.
# logging.basicConfig()
# logging.getLogger().setLevel(logging.DEBUG)
# requests_log = logging.getLogger("requests.packages.urllib3")
# requests_log.setLevel(logging.DEBUG)
# requests_log.propagate = True


class HtmlDownloader(AbstractDownloader):
    name = "html downloader"

    def __init__(self, config):
        super().__init__(config)
        self.logger = logging.getLogger("tg_dj.downloader.html")
        self.logger.setLevel(
            getattr(logging, self.config.get("downloader_html", "verbosity", fallback="warning").upper())
        )
        self.songs_cache = {}
        self.skip_head = self.config.get("downloader_html", "skip_head", fallback=True)

    def is_acceptable(self, kind, query):
        return kind == "search" or kind == "search_result"

    def get_name(self):
        return "html"

    @staticmethod
    def get_headers():
        ua = generate_user_agent()
        return {
            "User-Agent": ua,
            "Pragma": "no-cache"
        }

    def search(self, query, user_message=lambda text: True, limit=1000):
        self.logger.debug("Search query: " + query)

        if len(query.strip()) == 0:
            return []

        base_uri = self.config.get("downloader_html", "base_uri")
        search_uri = self.config.get("downloader_html", "search_page_uri")

        self.logger.debug("Getting data from " + base_uri + " with query " + query)
        headers = self.get_headers()
        search_request = requests.get((base_uri + search_uri).format(query), headers=headers)
        if search_request.status_code != 200:
            raise BadReturnStatus(search_request.status_code)

        tree = lxml.html.fromstring(search_request.text)

        titles = tree.xpath(self.config.get("downloader_html", "search_page_xpath_titles"))
        artists = tree.xpath(self.config.get("downloader_html", "search_page_xpath_artists"))
        durations = tree.xpath(self.config.get("downloader_html", "search_page_xpath_durations"))
        ratings = tree.xpath(self.config.get("downloader_html", "search_page_xpath_ratings"))
        links = tree.xpath(self.config.get("downloader_html", "search_page_xpath_page_links"))

        songs = []
        for el in zip(titles, artists, durations, ratings, links):
            songs.append(dict(zip(("title", "artist", "duration", "rating", "link"), el)))

        for s in songs:
            time_parts = s["duration"].split(":")
            t = 0
            for part in time_parts:
                t = t * 60 + int(part)
            s["duration"] = t
            s["rating"] = s["rating"].replace(",", "")
            if s["rating"].endswith("K"):
                s["rating"] = s["rating"].rstrip("K") + "000"

        songs.sort(key=lambda song: -int(song["rating"]))

        length = len(songs)
        if length == 0:
            raise NothingFound()

        ret = []
        for s in songs:
            song_id = hashlib.sha1(str(s["link"]).encode("utf-8")).hexdigest()
            self.songs_cache[song_id] = s

            ret.append({
                "id": song_id,
                "artist": s["artist"],
                "title": s["title"],
                "duration": s["duration"],
            })

            if len(ret) >= limit:
                break

        return ret

    def download(self, query, user_message=lambda text: True):
        result_id = query["id"]
        self.logger.debug("Downloading result #" + str(result_id))

        base_uri = self.config.get("downloader_html", "base_uri")
        download_xpath = self.config.get("downloader_html", "download_page_xpath")
        media_dir = self.config.get("downloader", "media_dir", fallback="media")

        try:
            song = self.songs_cache[result_id]
        except KeyError:
            self.logger.error("No search cache entry for id " + result_id)
            raise DownloaderException("Внутренняя ошибка (запрошенная песня отсутствует в кэше поиска)")

        if song["duration"] > self.config.getint("downloader", "max_duration", fallback=self._default_max_duration):
            raise MediaIsTooLong(song["duration"])

        headers = self.get_headers()
        search_request = requests.get((base_uri + song["link"]), headers=headers)
        if search_request.status_code != 200:
            raise BadReturnStatus(search_request.status_code)
        tree = lxml.html.fromstring(search_request.text)
        right_part: str = tree.xpath(download_xpath)[0]
        # if right_part.startswith("//"):
        #     right_part = right_part[1:]
        download_uri = base_uri + right_part

        file_name = sanitize_file_name("html-" + str(result_id) + '.mp3')
        file_path = os.path.join(os.getcwd(), media_dir, file_name)

        if self.is_in_cache(file_path):
            self.logger.info("File %s already in cache" % result_id)
            return file_path, song["title"], song["artist"], song["duration"]

        if not os.path.exists(os.path.join(os.getcwd(), media_dir)):
            os.makedirs(os.path.join(os.getcwd(), media_dir))
            self.logger.debug("Media dir have been created: %s" % os.path.join(os.getcwd(), media_dir))

        self.logger.info("Downloading song #" + result_id)
        user_message("Скачиваем...\n%s — %s" % (song["artist"], song["title"]))

        file_size = None

        if not self.skip_head:
            response_head = requests.head(
                download_uri,
                headers=self.get_headers(),
                allow_redirects=True,
                stream=True,
            )
            if response_head.status_code != 200:
                raise BadReturnStatus(response_head.status_code)
            try:
                file_size = int(response_head.headers['content-length'])
            except KeyError as e:
                self.logger.error("No header \"content-length\". More information below\n" + str(e))
                raise ApiError
            if file_size > 1000000 * self.config.getint("downloader", "max_file_size", fallback=self._default_max_size):
                raise MediaIsTooBig(file_size)

            sleep(1)

        self.get_file(
            url=download_uri,
            file_path=file_path,
            file_size=file_size,
            percent_callback=lambda p: user_message("Скачиваем [%d%%]...\n%s — %s"
                                                    % (int(p), song["artist"], song["title"])),
            headers=self.get_headers(),
        )

        self.logger.debug("Download completed #" + str(result_id))

        self.touch_without_creation(file_path)

        self.logger.debug("File stored in path: " + file_path)

        return file_path, song["title"], song["artist"], song["duration"]
