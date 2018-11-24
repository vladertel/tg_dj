import os
import requests
from time import sleep
import lxml.html
import hashlib

from user_agent import generate_user_agent

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, MAXIMUM_FILE_SIZE
from .exceptions import *
from .storage_checker import filter_storage
from utils import sanitize_file_name

from .private_config import base_uri, html_search_uri, html_search_xpath, download_xpath


class HtmlDownloader(AbstractDownloader):
    name = "html downloader"

    def __init__(self):
        super().__init__()

        self.songs_cache = {}

    def is_acceptable(self, kind, query):
        return kind == "search" or kind == "search_result"

    @staticmethod
    def get_headers():
        return {
            "User-Agent": generate_user_agent(),
            "Pragma": "no-cache",
        }

    def search(self, query, user_message=lambda text: True):
        if _DEBUG_:
            print("DEBUG [HtmlDownloader]: Search query: " + query)

        if len(query.strip()) == 0:
            return []

        if _DEBUG_:
            print("DEBUG [HtmlDownloader]: Getting data from " + base_uri + " with query " + query)
        headers = self.get_headers()
        search_request = requests.get((base_uri + html_search_uri).format(query), headers=headers)
        if search_request.status_code != 200:
            raise BadReturnStatus(search_request.status_code)

        tree = lxml.html.fromstring(search_request.text)

        titles = tree.xpath(html_search_xpath["titles"])
        artists = tree.xpath(html_search_xpath["artists"])
        durations = tree.xpath(html_search_xpath["durations"])
        ratings = tree.xpath(html_search_xpath["ratings"])
        links = tree.xpath(html_search_xpath["links"])

        songs = []
        for el in zip(titles, artists, durations, ratings, links):
            songs.append(dict(zip(("title", "artist", "duration", "rating", "link"), el)))

        for s in songs:
            time_parts = s["duration"].split(":")
            t = 0
            for part in time_parts:
                t = t * 60 + int(part)
            s["duration"] = t

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
        return ret

    def download(self, query, user_message=lambda text: True):
        result_id = query["id"]
        if _DEBUG_:
            print("DEBUG [HtmlDownloader]: Downloading result #" + str(result_id))

        try:
            song = self.songs_cache[result_id]
        except KeyError:
            print("ERROR [HtmlDownloader]: No search cache entry for id " + result_id)
            raise Exception("Внутренняя ошибка (запрошенная песня отсутствует в кэше поиска)")

        headers = self.get_headers()
        search_request = requests.get((base_uri + song["link"]), headers=headers)
        if search_request.status_code != 200:
            raise BadReturnStatus(search_request.status_code)
        tree = lxml.html.fromstring(search_request.text)
        download_uri = base_uri + tree.xpath(download_xpath)[0]

        file_name = sanitize_file_name("html-" + str(result_id) + '.mp3')
        file_path = os.path.join(os.getcwd(), mediaDir, file_name)

        if self.is_in_cache(file_path):
            print("INFO [HtmlDownloader]: File %s already in cache" % result_id)
            return file_path, song["title"], song["artist"], song["duration"]

        if not os.path.exists(os.path.join(os.getcwd(), mediaDir)):
            os.makedirs(os.path.join(os.getcwd(), mediaDir))
            if _DEBUG_:
                print("DEBUG [HtmlDownloader]: Media dir have been created: %s" % os.path.join(os.getcwd(), mediaDir))

        print("INFO [HtmlDownloader]: Downloading song #" + result_id)
        user_message("Скачиваем...\n%s — %s" % (song["artist"], song["title"]))

        response_head = requests.head(
            download_uri, headers=self.get_headers(),
            allow_redirects=True,
            stream=True,
        )
        if response_head.status_code != 200:
            raise BadReturnStatus(response_head.status_code)
        try:
            file_size = response_head.headers['content-length']
        except KeyError as e:
            print("ERROR [HtmlDownloader]: Тo such header: content-length. More information below\n" + str(e))
            raise ApiError
        if int(file_size) > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig(file_size)

        sleep(1)

        self.get_file(
            url=download_uri,
            file_path=file_path,
            file_size=file_size,
            percent_callback=lambda p: user_message("Скачиваем [%d%%]...\n%s — %s"
                                                    % (int(p), song["artist"], song["title"])),
        )

        if _DEBUG_:
            print("DEBUG [HtmlDownloader]: Download complete #" + str(result_id))

        self.touch_without_creation(file_path)
        filter_storage()

        if _DEBUG_:
            print("DEBUG [HtmlDownloader]: File stored in path: " + file_path)

        return file_path, song["title"], song["artist"], song["duration"]
