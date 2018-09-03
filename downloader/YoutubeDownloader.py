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
        self.yt_regex = re.compile(r"((?:https?://)?(?:www\.)?(?:m\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]{11})|((?:https?://)?(?:www\.)?(?:m\.)?youtu\.be/[a-zA-Z0-9_-]{11})", flags=re.IGNORECASE)

    def is_acceptable(self, task):
        if "text" in task:
            match = self.yt_regex.search(task["text"])
            if match:
                return match.group(0)
        return False

    def schedule_task(self, task):
        match = self.yt_regex.search(task["text"])
        if match:
            return self.schedule_link(match.group(0))
        raise UnappropriateArgument()

    def schedule_link(self, url):
        if _DEBUG_:
            print("Getting url: " + url)

        try:
            yt = YouTube(url)
            streams = yt.streams.filter(only_audio=True)
        except Exception:
            raise UrlOrNetworkProblem()
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
        searchUrl = "https://www.googleapis.com/youtube/v3/videos?id=" + video_id + \
            "&key=" + YT_API_KEY + "&part=contentDetails"
        try:
            response = urllib.request.urlopen(searchUrl).read()
        except Exception:
            raise UrlOrNetworkProblem("google")
        data = json.loads(response)
        duration = data['items'][0]['contentDetails']['duration']
        m = re.findall(r"\d+", duration)[::-1]
        multip = 1
        seconds = 0
        for match in m:
            seconds += (int(match) * multip)
            multip *= 60
        if seconds > MAXIMUM_DURATION:
            raise MediaIsTooLong()
        check_path = os.path.join(file_dir, unidecode(file_name)) + ".mp4"
        if self.is_in_cache(check_path):
            return (check_path, video_title, seconds)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
            if _DEBUG_:
                print("Media dir have been created: " + file_dir)
        streams.first().download(output_path=file_dir, filename=unidecode(file_name))
        file_name += ".mp4"
        file_name = unidecode(file_name)
        file_path = os.path.join(file_dir, file_name)
        self.touch_without_creation(file_path)
        filter_storage()
        if _DEBUG_:
            print("YT: check file at path - " + file_path)

        return (file_path, video_title, seconds)
