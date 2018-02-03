from .AbstractDownloader import AbstractDownloader
import os
from user_agent import generate_user_agent
from .config import mediaDir, _DEBUG_, DATMUSIC_API_ENDPOINT, INLINE_QUERY_CACHE_TIME
import requests
import json
# logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                # level=logging.INFO)
# logger = logging.getLogger(__name__)

class BadReturnStatus(Exception):
    pass

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
            print("Got: " + str(data[0]))
        try:
            song = data[0]
        except (KeyError, IndexError) as e:
            return None
        song["headers"] = headers
        return song

    def schedule_link(self, song):
        downloaded = requests.get(song["download"], headers=song["headers"], stream=True)
        if downloaded.status_code != 200:
            raise BadReturnStatus(downloaded.status_code)
        file_path = os.path.join(os.getcwd(), mediaDir, song["artist"] + " - " + song["title"] + '.mp3')
        with open(file_path, 'wb') as f:
            f.write(downloaded.content)
        if _DEBUG_:
            print("Check file at path: "+ file_path)
        return file_path
            # downloaded.raw.decode_content = True
            # shutil.copyfileobj(downloaded.raw, f)
