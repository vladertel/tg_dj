import urllib.request
import json
import re
import os
import time
import traceback

from pytube import YouTube

from .AbstractDownloader import AbstractDownloader
from .exceptions import *
from utils import sanitize_file_name


class YoutubeDownloader(AbstractDownloader):
    name = "YouTube downloader"

    def __init__(self, config):
        super().__init__(config)
        self.yt_regex = re.compile(r"((?:https?://)?(?:www\.)?(?:m\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]{11})|((?:https?://)?(?:www\.)?(?:m\.)?youtu\.be/[a-zA-Z0-9_-]{11})", flags=re.IGNORECASE)

        self.download_status = {}

    def is_acceptable(self, kind, query):
        if kind == "text":
            match = self.yt_regex.search(query)
            if match:
                return match.group(0)
        return False

    def video_download_progress(self, stream=None, _chunk=None, _file_handle=None, remaining=None):
        for video_id in self.download_status:
            stat = self.download_status[video_id]
            if stream != stat["stream"]:
                continue

            new_time = time.time()
            if new_time <= stat["last_update"] + 3:
                break

            stat["last_update"] = new_time
            file_size = stat["file_size"]
            percent = 100 * (file_size - remaining) / file_size
            stat["user_message"]("Скачиваем [%d%%]...\n%s" % (percent, stat["title"]))

    def download(self, query, user_message=lambda text: True):
        match = self.yt_regex.search(query)
        if match:
            url = match.group(0)
        else:
            raise UnappropriateArgument()

        print("INFO [YoutubeDownloader]: Getting url: " + url)
        user_message("Загружаем информацию о видео...")

        media_dir = self.config.get("downloader", "media_dir", fallback="media")
        api_key = self.config.get("downloader_youtube", "api_key")

        try:
            video = YouTube(url, on_progress_callback=self.video_download_progress)
            stream = video.streams.filter(only_audio=True).first()
        except Exception:
            traceback.print_exc()
            raise ApiError()
        video_id = video.video_id
        video_title = video.title
        if video_id is None:
            raise UrlProblem()

        file_size = int(stream.filesize)
        if file_size > 1000000 * self.config.getint("downloader", "max_file_size", fallback=self._default_max_size):
            raise MediaIsTooBig()

        file_dir = media_dir
        file_name = sanitize_file_name("youtube-" + str(video_id))

        search_url = "https://www.googleapis.com/youtube/v3/videos?id=" + video_id + \
            "&key=" + api_key + "&part=contentDetails"
        try:
            response = urllib.request.urlopen(search_url).read()
        except Exception:
            raise UrlOrNetworkProblem("google")

        data = json.loads(response.decode('utf-8'))
        duration = data['items'][0]['contentDetails']['duration']
        m = re.findall(r"\d+", duration)[::-1]
        multiplier = 1
        seconds = 0
        for match in m:
            seconds += (int(match) * multiplier)
            multiplier *= 60
        if seconds > self.config.getint("downloader", "max_duration", fallback=self._default_max_duration):
            raise MediaIsTooLong()

        self.download_status[str(video_id)] = {
            "start_time": time.time(),
            "last_update": time.time(),
            "file_size": file_size,
            "stream": stream,
            "title": video_title,
            "user_message": user_message,
        }

        file_path = os.path.join(file_dir, file_name) + ".mp4"
        if self.is_in_cache(file_path):
            print("DEBUG [YoutubeDownloader]: Loading from cache: " + file_path)
            return file_path, video_title, "", seconds

        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
            print("DEBUG [YoutubeDownloader]: Media dir have been created: " + file_dir)

        print("INFO [YoutubeDownloader]: Downloading audio from video: " + video_id)
        user_message("Скачиваем...\n%s" % video_title)

        stream.download(output_path=file_dir, filename=file_name)
        self.touch_without_creation(file_path)

        print("DEBUG [YoutubeDownloader]: File stored in path: " + file_path)

        return file_path, video_title, "", seconds
