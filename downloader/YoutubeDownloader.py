import AbstractDownloader
from pytube import YouTube
import os
from config import mediaDir, youtubePrefix

class YoutubeDownloader(AbstractDownloader):
	def schedule_link(self, url, callback):
		streams = YouTube('https://www.youtube.com/watch?v=dQw4w9WgXcQ').streams.filter(only_audio=True, progressive=True)

		streams.first().download(output_path = os.path.join(os.getcwd(), mediaDir), filename = youtubePrefix + "dQw4w9WgXcQ")