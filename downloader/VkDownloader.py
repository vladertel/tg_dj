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

    def is_acceptable(self, task):
        return "text" in task

    def schedule_task(self, task):
        if "song" in task:
            (song, headers) = (task["song"], task["headers"])
        else:
            (song, headers) = self.search_with_query(task["text"])
        return self.schedule_link(song, headers)

    def get_headers(self):
        return {
            "User-Agent": generate_user_agent(),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Pragma": "no-cache",
            "Origin": "https://datmusic.xyz",
            "Referer": "https://datmusic.xyz/",
            "Accept-Language": "en-us"
        }

    def get_payload(self, query):
        return {
            "q": query,
            "page": 0
        }

    def search_with_query(self, search_query):
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
        else:
            songs = data
            raise MultipleChoice(songs, headers)

    def schedule_link(self, song, headers):
        if _DEBUG_:
            print("Downloading song:" + str(song))
        response = requests.head(song["download"], headers=headers, allow_redirects=True)
        if response.status_code != 200:
            raise BadReturnStatus(response.status_code)
        try:
            file_size = response.headers['content-length']
        except KeyError as e:
            print("VkDownloader: no such header: content-length")
            print(e)
            raise e
        if int(file_size) > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig(file_size)
        file_name = song["artist"] + " - " + song["title"] + '.mp3'
        file_name = unidecode(file_name)
        file_path = os.path.join(os.getcwd(), mediaDir, file_name)
        if self.is_in_cache(file_path):
            return (file_path, song["artist"] + " - " + song["title"], song["duration"])
        if not os.path.exists(os.path.join(os.getcwd(), mediaDir)):
            os.makedirs(os.path.join(os.getcwd(), mediaDir))
            if _DEBUG_:
                print("Media dir have been created: " + os.path.join(os.getcwd(), mediaDir))
        sleep(1)
        downloaded = requests.get(song["download"], headers=headers, stream=True)
        if downloaded.status_code != 200:
            raise BadReturnStatus(downloaded.status_code)
        with open(file_path, 'wb') as f:
            f.write(downloaded.content)
        self.touch_without_creation(file_path)
        filter_storage()
        if _DEBUG_:
            print("VK: Check file at path: " + file_path)
        return (file_path, song["artist"] + " - " + song["title"], song["duration"])
        # downloaded.raw.decode_content = True
        # shutil.copyfileobj(downloaded.raw, f)
