import os
import requests
import json

from unidecode import unidecode
from user_agent import generate_user_agent

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, DATMUSIC_API_ENDPOINT
from .exceptions import *
from .storage_checker import StorageFilter


sf = StorageFilter()

class VkDownloader(AbstractDownloader):
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
            "page":0
        }

    def search_with_query(self, search_query):
        if _DEBUG_:
            print("Trying to get data from "+ DATMUSIC_API_ENDPOINT + " with query " + search_query)
        headers = self.get_headers()
        songs = requests.get(DATMUSIC_API_ENDPOINT, params=self.get_payload(search_query), headers=headers)
        if songs.status_code != 200:
            raise BadReturnStatus(songs.status_code)
        try:
            data = json.loads(songs.text)["data"]
        except KeyError as e:
            print("seems like wrong result")
            print(songs.text)
            raise e
        if _DEBUG_:
            print("Got: " + str(data))
        # try:
        length = len(data)
        if length > 10:
            songs = data[0:10]
        elif length == 0:
            raise NothingFound()
        elif length == 1:
            raise OnlyOneFound(data[0], headers)
        else:
            songs = data[0:length]
        # except (KeyError, IndexError) as e:
        #     return None
        # song["headers"] = headers
        return (songs, headers)

    def schedule_link(self, song, headers):
        file_name = song["artist"] + " - " + song["title"] + '.mp3'
        file_name = unidecode(file_name)
        file_path = os.path.join(os.getcwd(), mediaDir, file_name)
        if os.path.exists(file_path):
            return (file_path, song["artist"] + " - " + song["title"], song["duration"])
        downloaded = requests.get(song["download"], headers=headers, stream=True)
        if downloaded.status_code != 200:
            raise BadReturnStatus(downloaded.status_code)
        with open(file_path, 'wb') as f:
            f.write(downloaded.content)
        self.touch_without_creation(file_path)
        sf.filter_storage()
        if _DEBUG_:
            print("Check file at path: "+ file_path)
        return (file_path, song["artist"] + " - " + song["title"], song["duration"])
            # downloaded.raw.decode_content = True
            # shutil.copyfileobj(downloaded.raw, f)
