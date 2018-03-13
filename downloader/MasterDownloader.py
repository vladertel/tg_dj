import threading
# import re

from queue import Queue

from .YoutubeDownloader import YoutubeDownloader
from .VkDownloader import VkDownloader
from .FileDownloader import FileDownloader
from .LinkDownloader import LinkDownloader
from .exceptions import *
from .config import MAXIMUM_FILE_SIZE, MAXIMUM_DURATION


class MasterDownloader():
    def download_done(self, user, file_path, title, duration):
        self.output_queue.put({
            "action": "download_done",
            "path": file_path,
            "title": title,
            "user": user,
            "duration": duration
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

    def thread_download_function(self, downloader, task):
        try:
            file_path, title, seconds = downloader.schedule_task(task)
        except Exception as e:
            self.error(task["user"], "error happened: " + str(e))
        else:
            self.download_done(task["user"], file_path, title, seconds)

    def thread_download_confirmed(self, downloader, task):
        try:
            file_path, title, seconds = downloader.schedule_link(task["song"], task["headers"])
        except Exception as e:
            self.error(task["user"], "error happened: " + str(e))
        else:
            self.download_done(
                task["user"], file_path, title, seconds)

    def queue_listener(self):
        while True:
            task = self.input_queue.get()
            # process task???
            print("Downloader - task: " + str(task))
            if task["action"] == "download":
                print("Downloading something")
                for dwnld_name in self.downloaders:
                    downloader = self.downloaders[dwnld_name]
                    try:
                        arg = downloader.is_acceptable(task)
                        if arg:
                            self.user_message(task["user"], "Processing...")
                            threading.Thread(daemon=True, target=self.thread_download_function, args=(
                                downloader, task)).start()
                            break
                    except MediaIsTooLong:
                        self.user_message(task["user"],
                            "Requested media is too long (more than " + str(MAXIMUM_DURATION) + " seconds)")
                    except MediaIsTooBig:
                        self.user_message(task["user"], "Requested media is too large (more than " +
                                          str(MAXIMUM_FILE_SIZE / 1000000) + " MB)")
                    except (UrlOrNetworkProblem, UrlProblem, BadReturnStatus):
                        self.user_message(task["user"], "Seems like " + downloader.name +
                                          " is unavailable or bad link :(\nTry again, or tell this to admin")
                    except NothingFound:
                        self.user_message(
                            task["user"], "Nothing found with that query :(")
                    except AskUser as e:
                        songs, headers = e.args[0], e.args[1]
                        self.users_to_vk_songs[task["user"]] = songs
                        self.users_to_vk_headers[task["user"]] = headers
                        self.ask_user(
                            task["user"], "What you want exactly?", songs=songs)
                        break
                    except OnlyOneFound as e:
                        song, headers = e.args[0], e.args[1]
                        new_task = {
                            "user": task["user"],
                            "song": song,
                            "headers": headers
                        }
                        threading.Thread(daemon=True, target=self.thread_download_function, args=(
                            downloader, new_task)).start()
                        break
                self.input_queue.task_done()
                continue
            elif task["action"] == "user_confirmed":
                print("user_confirmed vk: " + str(task["number"]))
                try:
                    songs = self.users_to_vk_songs.pop(task["user"])
                    headers = self.users_to_vk_headers.pop(task["user"])
                except KeyError:
                    print("UNEXISTENT USER IN users_to_vk_songs")
                    self.error(
                        task["user"], "UNEXISTENT USER IN users_to_vk_songs")
                else:
                    number = task["number"]
                    try:
                        song = songs[number]
                    except (KeyError, IndexError):
                        self.user_message(task["user"], "No such music")
                        continue
                    self.user_message(task["user"], "Processing...")
                    self.output_queue.put({
                        "user": task["user"],
                        "action": "confirmation_done"
                    })
                    new_task = {
                        "action": "user_confirmed",
                        "song": song,
                        "headers": headers,
                        "user": task["user"]
                    }
                    threading.Thread(daemon=True, target=self.thread_download_confirmed, args=(
                        downloader, new_task)).start()
                    # file_path, title, seconds = self.downloaders["vk"].schedule_link(
                    #     songs[number], headers)

            else:
                self.error(
                    task["user"], "Don't know what to do with this action: " + task["action"])

    def __init__(self):
            # https://youtu.be/qAeybdD5UoQ
        self.downloaders = {
            "yt": YoutubeDownloader(),
            "link": LinkDownloader(),
            "file": FileDownloader(),
            "vk": VkDownloader()
        }
        self.users_to_vk_headers = {}
        self.users_to_vk_songs = {}
        self.input_queue = Queue()
        self.output_queue = Queue()

        self.queue_thread_listener = threading.Thread(
            daemon=True, target=self.queue_listener)
        self.queue_thread_listener.start()
