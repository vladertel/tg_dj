import threading
import re

from queue import Queue

from .YoutubeDownloader import YoutubeDownloader
from .VkDownloader import VkDownloader
from .exceptions import *


class MasterDownloader():
    def download_done(self, file_path, title, user):
        self.output_queue.put({
            "action": "download_done",
            "path": file_path,
            "title": title,
            "user": user
        })


    def error(self, user, message):
        self.output_queue.put({
            "action": "error",
            "user": user,
            "message": message
        })


    def ask_user(self, user, message, songs=None):
        response = {
            "action": "ask_user",
            "message": message,
            "user": user,
        }
        if songs is not None:
            response["songs"] = songs
        self.output_queue.put(response)


    def user_message(self, user, message):
        self.output_queue.put({
            "action": "user_message",
            "user": user,
            "message": message
        })

    def queue_listener(self):
        while True:
            task = self.input_queue.get(block=True)
            # process task???
            if task["action"] == "download":
                if "text" in task:
                    # YouTube
                    # decide whether it is youtube link or something else
                    text = task["text"]
                    # https://youtu.be/qAeybdD5UoQ
                    match = re.search(
                        r"((?:https?://www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_]{11})|(?:https?://)?youtu\.be/[a-zA-Z0-9_]{11}", text, flags=re.IGNORECASE)
                    if match:
                        self.user_message(task["user"], "Processing...")
                        try:
                            file_path, title, seconds = self.yt.schedule_link(match.group(0))
                        except (UrlOrNetworkProblem, UrlProblem) as e:
                            self.error(task["user"], "UrlOrNetworkProblem or UrlProblem")
                        except MediaIsTooLong as e:
                            self.user_message(task["user"], "Requested video is too long")
                        else:
                            self.download_done(file_path, title, task["user"])
                    else:
                        # VK
                        # try to find in datmusic service
                        try:
                            songs_obj, headers = self.vk.search_with_query(text)
                        except BadReturnStatus:
                            self.error(task["user"], "Error occured: BadReturnStatus form vk wrapper")
                        except NothingFound:
                            self.user_message(task["user"], "Nothing found. Try another query")
                        except OnlyOneFound as e:
                            args = e.args
                            self.user_message(task["user"], "Processing...")
                            file_path, title, seconds = self.vk.schedule_link(args[0], args[1])
                            self.download_done(file_path, title, task["user"])
                        else:
                            self.users_to_vk_songs[task["user"]] = songs_obj
                            self.users_to_vk_headers[task["user"]] = headers
                            self.ask_user(task["user"], "What you want exactly?", songs=songs_obj)
                elif "file" in task:
                    file = task["file"]
                    self.error(task["user"], "Error occured: Not Implemented")
                else:
                    self.error(task["user"], "Error occured: Unsupported")
            elif task["action"] == "user_confirmed":
                try:
                    songs = self.users_to_vk_songs.pop(task["user"])
                    headers = self.users_to_vk_headers.pop(task["user"])
                except KeyError:
                    self.error(task["user"], "UNEXISTENT USER IN users_to_vk_songs")
                else:
                    number = task["number"]
                    self.user_message(task["user"], "Processing...")
                    file_path, title, seconds = self.vk.schedule_link(songs[number], headers)
                    self.download_done(file_path, title, task["user"])
            else:
                self.error(task["user"], "Don't know what to do with this action: " + task["action"])

            self.input_queue.task_done()

    def __init__(self):
        self.users_to_vk_headers={}
        self.users_to_vk_songs={}
        self.vk = VkDownloader()
        self.yt = YoutubeDownloader()
        # self.file = FileDownloader()
        self.input_queue = Queue()
        self.output_queue = Queue()

        self.queue_thread_listener = threading.Thread(
            daemon=True, target=self.queue_listener)
        self.queue_thread_listener.start()
