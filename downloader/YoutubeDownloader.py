import urllib.request
import json
import re
import os
import time

from pytube import YouTube

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, _DEBUG_, MAXIMUM_DURATION, MAXIMUM_FILE_SIZE
from .private_config import YT_API_KEY
from .exceptions import *
from .storage_checker import filter_storage
from utils import sanitize_file_name


class YoutubeDownloader(AbstractDownloader):
    name = "YouTube downloader"

    def __init__(self):
        super().__init__()
        self.yt_regex = re.compile(r"((?:https?://)?(?:www\.)?(?:m\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]{11})|((?:https?://)?(?:www\.)?(?:m\.)?youtu\.be/[a-zA-Z0-9_-]{11})", flags=re.IGNORECASE)

        self.download_status = {}

    def is_acceptable(self, task):
        if "text" in task:
            match = self.yt_regex.search(task["text"])
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
            video = YouTube(url, on_progress_callback=self.video_download_progress)
            stream = video.streams.filter(only_audio=True).first()
        except Exception:
            raise ApiError()
        video_id = video.video_id
        video_title = video.title
        if video_id is None:
            raise UrlProblem()

        file_size = stream.filesize
        if int(file_size) > MAXIMUM_FILE_SIZE:
            raise MediaIsTooBig()

        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_name = sanitize_file_name("youtube-" + str(video_id))

        search_url = "https://www.googleapis.com/youtube/v3/videos?id=" + video_id + \
            "&key=" + YT_API_KEY + "&part=contentDetails"
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
        if seconds > MAXIMUM_DURATION:
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

        stream.download(output_path=file_dir, filename=file_name)
        self.touch_without_creation(file_path)
        filter_storage()

        if _DEBUG_:
            print("DEBUG [YoutubeDownloader]: File stored in path: " + file_path)

        user_message("Песня добавлена в очередь\n%s" % video_title)
        return file_path, video_title, seconds
