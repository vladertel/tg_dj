import re
import os
import time
import traceback
import logging
import html
from urllib.error import HTTPError

from pytube import YouTube

from core.AbstractDownloader import AbstractDownloader, UrlProblem, MediaIsTooLong, MediaIsTooBig, BadReturnStatus, \
    UnappropriateArgument, ApiError
from utils import sanitize_file_name, remove_links


class YoutubeDownloader(AbstractDownloader):
    name = "YouTube downloader"

    def __init__(self, config):
        super().__init__(config)
        self.logger = logging.getLogger("tg_dj.downloader.youtube")
        self.logger.setLevel(self.config.get("downloader_youtube", "verbosity", fallback="warning").upper())
        self.yt_regex = re.compile(r"((?:https?://)?(?:www\.)?(?:m\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]{11})|((?:https?://)?(?:www\.)?(?:m\.)?youtu\.be/[a-zA-Z0-9_-]{11})", flags=re.IGNORECASE)

        self.download_status = {}

    def get_name(self):
        return "yt"

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

        self.logger.info("Getting url: " + url)
        user_message("Загружаем информацию о видео...")

        media_dir = self.config.get("downloader", "media_dir", fallback="media")

        try:
            video = YouTube(url, on_progress_callback=self.video_download_progress)
            stream = video.streams.filter(only_audio=True).first()
        except Exception:
            traceback.print_exc()
            raise ApiError()
        video_id = video.video_id
        video_details = video.player_config_args.get('player_response', {}).get('videoDetails', {})
        if video_id is None:
            raise UrlProblem()
        try:
            video_title = html.unescape(video.title)
            self.logger.debug("Video title [using primary method]: " + video_title)
        except KeyError:
            video_title = html.unescape(video_details.get('title', 'Unknown YT video'))
            self.logger.debug("Video title [using fallback method]: " + video_title)

        video_title = remove_links(video_title)

        try:
            file_size = int(stream.filesize)
        except HTTPError as e:
            traceback.print_exc()
            raise BadReturnStatus(e.code)
        if file_size > 1000000 * self.config.getint("downloader", "max_file_size", fallback=self._default_max_size):
            raise MediaIsTooBig()

        file_dir = media_dir
        file_name = sanitize_file_name("youtube-" + str(video_id))

        seconds = video.length

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
            self.logger.debug("Loading from cache: " + file_path)
            return file_path, video_title, "", seconds

        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
            self.logger.debug("Media dir have been created: " + file_dir)

        self.logger.info("Downloading audio from video: " + video_id)
        user_message("Скачиваем...\n%s" % video_title)

        try:
            stream.download(output_path=file_dir, filename=file_name)
        except HTTPError as e:
            traceback.print_exc()
            raise BadReturnStatus(e.code)
        self.touch_without_creation(file_path)

        self.logger.debug("File stored in path: " + file_path)

        return file_path, video_title, "", seconds
