import os
import requests
import json
from time import sleep

from user_agent import generate_user_agent

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, DATMUSIC_API_ENDPOINT, MAXIMUM_FILE_SIZE
from .exceptions import *
from .storage_checker import filter_storage
from utils import sanitize_file_name


class CaptchaNeeded(ApiError):
    pass


class VkDownloader(AbstractDownloader):
    name = "vk downloader"

    def __init__(self):
        super().__init__()

        self.songs_cache = {}

    def is_acceptable(self, kind, query):
        return kind == "search" or kind == "search_result"

    @staticmethod
    def get_headers():
        return {
            "User-Agent": generate_user_agent(),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Pragma": "no-cache",
            "Origin": "https://datmusic.xyz",
            "Referer": "https://datmusic.xyz/",
            "Accept-Language": "en-us"
        }

    @staticmethod
    def get_payload(query):
        return {
            "q": query,
            "page": 0
        }

    def search(self, query, user_message=lambda text: True):
        if _DEBUG_:
            print("DEBUG [VkDownloader]: Search query: " + query)

        if len(query.strip()) == 0:
            return []

        if _DEBUG_:
            print("DEBUG [VkDownloader]: Getting data from " + DATMUSIC_API_ENDPOINT + " with query " + query)
        headers = self.get_headers()
        songs = requests.get(DATMUSIC_API_ENDPOINT, params=self.get_payload(query), headers=headers)
        if songs.status_code != 200:
            raise BadReturnStatus(songs.status_code)

        payload = json.loads(songs.text)
        if payload['status'] != "ok":
            if payload['error']['message'] == "Captcha needed":
                raise CaptchaNeeded()
            else:
                raise ApiError()

        try:
            data = payload["data"]
        except KeyError as e:
            print("ERROR [VkDownloader]: Payload has no data: %s" % songs.text)
            raise e
        if _DEBUG_:
            print("DEBUG [VkDownloader]: Got " + str(len(data)) + " results")

        length = len(data)
        if length == 0:
            raise NothingFound()

        songs = data
        for s in songs:
            self.songs_cache[s['source_id']] = s

        ret = []
        for s in songs:
            ret.append({
                "id": s["source_id"],
                "artist": s["artist"],
                "title": s["title"],
                "duration": s["duration"],
            })
        return ret

    def download(self, task, user_message=lambda text: True):
        result_id = task["result_id"]
        if _DEBUG_:
            print("DEBUG [VkDownloader]: Downloading result #" + str(result_id))

        try:
            song = self.songs_cache[result_id]
        except KeyError:
            print("ERROR [VkDownloader]: No search cache entry for id " + result_id)
            raise Exception("Внутренняя ошибка (запрошенная песня отсутствует в кэше поиска)")

        title = song["title"]
        artist = song["artist"]
        file_name = sanitize_file_name("vk-" + str(result_id) + '.mp3')
        file_path = os.path.join(os.getcwd(), mediaDir, file_name)

        if self.is_in_cache(file_path):
            print("INFO [VkDownloader]: File %s already in cache" % result_id)
            return file_path, title, artist, song["duration"]

        if not os.path.exists(os.path.join(os.getcwd(), mediaDir)):
            os.makedirs(os.path.join(os.getcwd(), mediaDir))
            if _DEBUG_:
                print("DEBUG [VkDownloader]: Media dir have been created: %s" % os.path.join(os.getcwd(), mediaDir))

        print("INFO [VkDownloader]: Downloading vk song #" + result_id)
        user_message("Скачиваем...\n%s" % title)

        response_head = requests.head(
            song["download"], headers=self.get_headers(),
            allow_redirects=True,
            stream=True,
        )
        if response_head.status_code != 200:
            raise BadReturnStatus(response_head.status_code)
        try:
            file_size = response_head.headers['content-length']
        except KeyError as e:
            print("ERROR [VkDownloader]: Тo such header: content-length. More information below\n" + str(e))
            raise ApiError
        if int(file_size) > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig(file_size)

        sleep(1)

        self.get_file(
            url=song["download"],
            file_path=file_path,
            file_size=file_size,
            percent_callback=lambda p: user_message("Скачиваем [%d%%]...\n%s" % (int(p), title)),
        )

        if _DEBUG_:
            print("DEBUG [VkDownloader]: Download complete #" + str(result_id))

        self.touch_without_creation(file_path)
        filter_storage()

        if _DEBUG_:
            print("DEBUG [VkDownloader]: File stored in path: " + file_path)

        return file_path, title, artist, song["duration"]
