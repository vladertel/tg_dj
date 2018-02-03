from downloader.VkDownloader import VkDownloader
dwnld = VkDownloader()
song = dwnld.search_with_query("sad trombone")
print(dwnld.schedule_link(song))

