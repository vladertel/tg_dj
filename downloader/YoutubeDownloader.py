import urllib.request
import json
import re
import os

from pytube import YouTube
from unidecode import unidecode

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, MAXIMUM_DURATION
from .private_config import YT_API_KEY
from .exceptions import *
from .storage_checker import filter_storage


class YoutubeDownloader(AbstractDownloader):
    name = "YouTube downloader"

    def __init__(self):
        super().__init__()
        self.yt_regex = re.compile(r"((?:https?://)?(?:www\.)?(?:m\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]{11})|((?:https?://)?(?:www\.)?(?:m\.)?youtu\.be/[a-zA-Z0-9_-]{11})", flags=re.IGNORECASE)

    def is_acceptable(self, task):
        if "text" in task:
            match = self.yt_regex.search(task["text"])
            if match:
                return match.group(0)
        return False

    def download(self, task, user_message=lambda text: True):
        match = self.yt_regex.search(task["text"])
        if match:
            url = match.group(0)
        else:
            raise UnappropriateArgument()

        if _DEBUG_:
            print("INFO [YoutubeDownloader]: Getting url: " + url)
        user_message("Загружаем информацию о видео...")

        try:
            yt = YouTube(url)
            streams = yt.streams.filter(only_audio=True)
        except Exception:
            raise ApiError()
        video_id = yt.video_id
        video_title = yt.title
        if video_id is None:
            raise UrlProblem()
        # if _DEBUG_:
        #     for stream in streams.all():
        #         print(stream)
        # for stream in streams.all():
        # 	if stream.mime_type == "audio/mp4":
        # exit(1)

        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = video_title

        search_url = "https://www.googleapis.com/youtube/v3/videos?id=" + video_id + \
            "&key=" + YT_API_KEY + "&part=contentDetails"
        try:
            response = urllib.request.urlopen(search_url).read()
        except Exception:
            raise UrlOrNetworkProblem("google")

        data = json.loads(response.decode('utf-8'))
        duration = data['items'][0]['contentDetails']['duration']
        m = re.findall(r"\d+", duration)[::-1]
        multip = 1
        seconds = 0
        for match in m:
            seconds += (int(match) * multip)
            multip *= 60
        if seconds > MAXIMUM_DURATION:
            raise MediaIsTooLong()

        file_path = os.path.join(file_dir, unidecode(file_name)) + ".mp4"
        if self.is_in_cache(file_path):
            if _DEBUG_:
                print("DEBUG [YoutubeDownloader]: Loading from cache: " + file_path)
            user_message("Песня добавлена в очередь\n%s" % video_title)
            return file_path, video_title, seconds

        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
            if _DEBUG_:
                print("DEBUG [YoutubeDownloader]: Media dir have been created: " + file_dir)

        print("INFO [YoutubeDownloader]: Downloading audio from video: " + video_id)
        user_message("Скачиваем...\n%s" % video_title)

        streams.first().download(output_path=file_dir, filename=unidecode(file_name))
        self.touch_without_creation(file_path)
        filter_storage()

        if _DEBUG_:
            print("DEBUG [YoutubeDownloader]: File stored in path: " + file_path)

        user_message("Песня добавлена в очередь\n%s" % video_title)
        return file_path, video_title, seconds
