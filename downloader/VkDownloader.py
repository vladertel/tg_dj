import os
import requests
import json
from time import sleep

from unidecode import unidecode
from user_agent import generate_user_agent

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, DATMUSIC_API_ENDPOINT, MAXIMUM_FILE_SIZE
from .exceptions import *
from .storage_checker import filter_storage


class CaptchaNeeded(ApiError):
    pass


class VkDownloader(AbstractDownloader):
    name = "vk downloader"

    def __init__(self):
        super().__init__()

        self.songs_cache = {}

    def is_acceptable(self, task):
        return "query" in task

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

    def schedule_search(self, task):
        search_query = task["query"]

        if len(search_query.strip()) == 0:
            return []

        if _DEBUG_:
            print("Trying to get data from " + DATMUSIC_API_ENDPOINT + " with query " + search_query)
        headers = self.get_headers()
        songs = requests.get(DATMUSIC_API_ENDPOINT, params=self.get_payload(search_query), headers=headers)
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
            print("Payload has no data: %s" % songs.text)
            raise e
        if _DEBUG_:
            print("Got " + str(len(data)) + " results")

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

    def schedule_search_result(self, result_id, user_message=lambda msg: True):
        try:
            song = self.songs_cache[result_id]
        except KeyError:
            print("ERROR [VkDownloader]: No search cache entry for id " + result_id)
            # self.error(user, "Ошибка (запрошенная песня отсутствует в кэше поиска)")
            return

        file_name = unidecode(song["artist"] + " - " + song["title"] + '.mp3')
        file_path = os.path.join(os.getcwd(), mediaDir, file_name)

        if self.is_in_cache(file_path):
            print("INFO [VkDownloader]: File %s already in cache" % result_id)
            user_message("%s - %s в очереди" % (song['artist'], song['title']))
            return file_path, song["artist"] + " - " + song["title"], song["duration"]

        if not os.path.exists(os.path.join(os.getcwd(), mediaDir)):
            os.makedirs(os.path.join(os.getcwd(), mediaDir))
            if _DEBUG_:
                print("DEBUG [VkDownloader]: Media dir have been created: %s" % os.path.join(os.getcwd(), mediaDir))

        print("INFO [VkDownloader]: Downloading vk song #" + result_id)
        user_message("Скачиваем %s - %s ..." % (song['artist'], song['title']))

        response = requests.head(song["download"], headers=self.get_headers(), allow_redirects=True)
        if response.status_code != 200:
            raise BadReturnStatus(response.status_code)
        try:
            file_size = response.headers['content-length']
        except KeyError as e:
            print("ERROR [VkDownloader]: no such header: content-length. More information below\n" + str(e))
            raise ApiError
        if int(file_size) > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig(file_size)

        sleep(1)

        downloaded = requests.get(song["download"], headers=self.get_headers(), stream=True)
        if downloaded.status_code != 200:
            raise BadReturnStatus(downloaded.status_code)

        with open(file_path, 'wb') as f:
            f.write(downloaded.content)
        self.touch_without_creation(file_path)
        filter_storage()

        if _DEBUG_:
            print("DEBUG [VkDownloader]: File stored in path: " + file_path)

        user_message("%s - %s в очереди" % (song['artist'], song['title']))
        return file_path, song["artist"] + " - " + song["title"], song["duration"]
