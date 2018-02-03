from .AbstractDownloader import AbstractDownloader
from pytube import YouTube
import os
from .config import mediaDir, youtubePrefix, _DEBUG_, duplicates
if duplicates:
    import glob
class UrlOrNetworkProblem(Exception):
    pass

class UrlProblem(Exception):
    pass

class YoutubeDownloader(AbstractDownloader):
    def schedule_link(self, url, callback):
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
        file_path = os.path.join(file_dir,file_name)
        streams.first().download(output_path=file_dir, filename=file_name)
        if _DEBUG_:
            print("check file at path - " + file_path)
        callback(file_path)
