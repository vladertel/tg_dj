import threading
import re

from queue import Queue

from .YoutubeDownloader import YoutubeDownloader, UrlOrNetworkProblem, UrlProblem
from .VkDownloader import VkDownloader, BadReturnStatus


class MasterDownloader():
    def queue_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            # process task???
            if task["action"] == "download":
                if "text" in task:
                    # decide whether it is youtube link or something else
                    text = task["text"]
                    match = re.search(
                        r"(https://www\.youtube\.com/watch\?v=[a-zA-Z0-9]{11})|http://youtu\.be/[a-zA-Z0-9]{11}", text, flags=re.IGNORECASE)
                    if match:
                        self.output_queue.put({
                            "action": "user_message",
                            "message": "Processing...",
                            "user": task["user"]
                        })
                        try:
                            file_path, title = self.yt.schedule_link(match.group(0))
                        except (UrlOrNetworkProblem, UrlProblem) as e:
                            self.output_queue.put({
                                "action": "error",
                                "user": task["user"],
                                "message": "Error occured"
                            })
                        else:
                            self.output_queue.put({
                                "action": "download_done",
                                "path": file_path,
                                "title": title,
                                "user": task["user"]
                            })
                    else:
                        # try to find in datmusic service
                        try:
                            song_obj = self.vk.search_with_query(text)
                        except BadReturnStatus as e:
                            self.output_queue.put({
                                "action": "error",
                                "user": task["user"],
                                "message": "Error occured: BadReturnStatus form vk wrapper"
                            })
                        else:
                            self.users_to_vk_songs[task["user"]] = song_obj
                            self.output_queue.put({
                                "action": "ask_user",
                                "message": "Is this what you want?\n"+ song_obj["artist"] + " - " + song_obj["title"],
                                "user": task["user"]
                            })


                elif "file" in task:
                    file = task["file"]
                    self.output_queue.put({
                        "action": "error",
                        "user": task["user"],
                        "message": "Not Implemented"
                    })
            elif task["action"] == "user_confirmed":
                if task["user"] in self.users_to_vk_songs:
                    song = self.users_to_vk_songs[task["user"]]
                    self.output_queue.put({
                        "action": "user_message",
                        "message": "Processing...",
                        "user": task["user"]
                    })
                    file_path = self.vk.schedule_link(song)
                    self.output_queue.put({
                        "action": "download_done",
                        "path": file_path,
                        "title": song["artist"] + " - " + song["title"],
                        "user": task["user"]
                    })
                else:
                    self.output_queue.put({
                        "action": "error",
                        "user": task["user"],
                        "message": "UNEXISTENT USER"
                    })
            else:
                self.output_queue.put({
                    "action": "error",
                    "user": task["user"],
                    "message": "Don't know what to do"
                })
            self.input_queue.task_done()

    def __init__(self):

        self.users_to_vk_songs={}
        self.vk = VkDownloader()
        self.yt = YoutubeDownloader()
        # self.file = FileDownloader()
        self.input_queue = Queue()
        self.output_queue = Queue()

        self.queue_thread_listener = threading.Thread(
            daemon=True, target=self.queue_listener)
        self.queue_thread_listener.start()
