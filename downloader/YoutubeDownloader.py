from .AbstractDownloader import AbstractDownloader
from pytube import YouTube
import os
from .config import mediaDir, youtubePrefix, _DEBUG_
import re

class UrlOrNetworkProblem(Exception):
    pass

class UrlProblem(Exception):
    pass

class YoutubeDownloader(AbstractDownloader):
    def get_video_id(self, url):
        match = re.search(r'[a-zA-Z0-9]{11}', url)
        if match is not None:
            if _DEBUG_:
                print("Matched - id: {}, in url: {}".format(match.group(0), url))
            return match.group(0)
        return None

    def schedule_link(self, url, callback):
        if _DEBUG_:
            print("Getting url: " + url)
        video_id = self.get_video_id(url)
        if video_id is None:
            raise UrlProblem()
        try:
            streams = YouTube(url).streams.filter(only_audio=True)
        except Exception as e:
            raise UrlOrNetworkProblem()
        if _DEBUG_:
            for stream in streams.all():
                print(stream)
        # for stream in streams.all():
        # 	if stream.mime_type == "audio/mp4":
        # exit(1)
        file_dir = os.path.join(os.getcwd(), mediaDir)
        file_path = file_dir + youtubePrefix + video_id
        streams.first().download(output_path=, filename=youtubePrefix + video_id)
        if _DEBUG_:
            print("check file at path - " + os.path.join(os.getcwd(), mediaDir))
        callback(os.path.join(os.getcwd(), mediaDir))
