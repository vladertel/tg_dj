from downloader import YoutubeDownloader
dwnld = YoutubeDownloader.YoutubeDownloader()
dwnld.schedule_link('https://www.youtube.com/watch?v=dQw4w9WgXcQ', lambda x: print(x))
