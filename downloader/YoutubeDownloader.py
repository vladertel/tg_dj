import urllib.request
import json
import re
import os
from pathlib import Path

from pytube import YouTube
from unidecode import unidecode

from .AbstractDownloader import AbstractDownloader
from .config import mediaDir, youtubePrefix, _DEBUG_, duplicates, MAXIMUM_DURATION
from .private_config import YT_API_KEY
from .exceptions import *
from .storage_checker import StorageFilter
if duplicates:
    import glob


sf = StorageFilter()

class YoutubeDownloader(AbstractDownloader):
    def schedule_link(self, url):
        if _DEBUG_:
            print("Getting url: " + url)

        try:
            yt = YouTube(url)
            streams = yt.streams.filter(only_audio=True)
        except Exception as e:
            raise UrlOrNetworkProblem()
        video_id = yt.video_id
        video_title = yt.title
        if video_id is None:
            raise UrlProblem()
        if _DEBUG_:
            for stream in streams.all():
                print(stream)
        # for stream in streams.all():
        # 	if stream.mime_type == "audio/mp4":
        # exit(1)
        file_dir = os.path.join(os.getcwd(), mediaDir)
        if duplicates:
            t = len(glob.glob(os.path.join(file_dir,video_title) + "*"))
            if t > 0:
                file_name = video_title + " (" + str(t) + ")"
            else:
                file_name = video_title
        else:
            file_name = video_title
        searchUrl = "https://www.googleapis.com/youtube/v3/videos?id="+video_id+"&key="+YT_API_KEY+"&part=contentDetails"
        try:
            response = urllib.request.urlopen(searchUrl).read()
        except Exception as e:
            raise UrlOrNetworkProblem()
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
        if os.path.exists(check_path):
            return (check_path, video_title , seconds)
        streams.first().download(output_path=file_dir, filename=file_name)
        file_name += ".mp4"
        file_name = unidecode(file_name)
        file_path = os.path.join(file_dir,file_name)
        Path(file_path).touch()
        sf.filter_storage()
        if _DEBUG_:
            print("check file at path - " + file_path)

        return (file_path, video_title, seconds)
