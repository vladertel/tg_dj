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

    def thread_download_function(self, task):
        user = task["user"]
        for dwnld_name in self.downloaders:
            downloader = self.downloaders[dwnld_name]
            arg = downloader.is_acceptable(task)
            if not arg:
                continue
            try:
                file_path, title, seconds = downloader.schedule_task(task)
            except MediaIsTooLong:
                self.user_message(user, "Запрошенная песня слишком длинная")
            except MediaIsTooBig:
                self.user_message(user, "Запрошенная песня слишком много весит (Больше чем " +
                                  str(MAXIMUM_FILE_SIZE / 1000000) + " MB)")
            except (UrlOrNetworkProblem, UrlProblem, BadReturnStatus):
                self.user_message(user, "Похоже модуль " + downloader.name +
                                  " отвалился или плохой запрос :(\nПопробуйте позже или скажите админу")
            except NothingFound:
                if task["action"] == "download":
                    self.user_message(user, "Ничего не нашел по этому запросу :(")
                elif task["action"] == "search_inline":
                    self.output_queue.put({
                        "action": "user_inline_reply",
                        "qid": task["qid"],
                        "user": user,
                        "results": []
                    })
            except MultipleChoice as e:
                if task["action"] == "download":
                    songs, headers = e.args[0], e.args[1]
                    songs = songs[0:min(10, len(songs))]
                    for s in songs:
                        self.vk_cache[s['source_id']] = s
                    self.users_to_vk_headers[user] = headers
                    self.ask_user(
                        user, "Что именно вы хотите?", songs=songs)
                    break
                elif task["action"] == "search_inline":
                    songs = e.args[0]
                    songs = songs[0:min(10, len(songs))]
                    for s in songs:
                        self.vk_cache[s['source_id']] = s
                    self.output_queue.put({
                        "action": "user_inline_reply",
                        "qid": task["qid"],
                        "user": user,
                        "results": songs
                    })
                    break
            except Exception as e:
                self.error(task["user"], "error happened: " + str(e))
            else:
                self.download_done(task["user"], file_path, title, seconds)
                break
            self.input_queue.task_done()
            continue

    def thread_download_confirmed(self, downloader, task):
        user = task["user"]
        try:
            file_path, title, seconds = downloader.schedule_link(task["song"], task["headers"])
        except MediaIsTooLong:
            self.user_message(user, "Запрошенная песня слишком длинная")
        except MediaIsTooBig:
            self.user_message(user, "Запрошенная песня слишком много весит (Больше чем " +
                              str(MAXIMUM_FILE_SIZE / 1000000) + " MB)")
        except (UrlOrNetworkProblem, UrlProblem, BadReturnStatus):
            self.user_message(user, "Похоже модуль " + downloader.name +
                              " отвалился или плохой запрос :(\nПопробуйте позже или скажите админу")
        except Exception as e:
            self.error(task["user"], "error happened: " + str(e))
        else:
            self.download_done(
                task["user"], file_path, title, seconds)

    def queue_listener(self):
        while True:
            task = self.input_queue.get()
            user = task["user"]
            print("Downloader - task: " + str(task))

            if task["action"] == "download" or task["action"] == "search_inline":
                threading.Thread( daemon=True, target=self.thread_download_function, args=(task,)).start()

            elif task["action"] == "user_confirmed" or task["action"] == "search_inline_select":
                print("user_confirmed vk: " + str(task["result_id"]))
                downloader = self.downloaders["vk"]
                try:
                    song = self.vk_cache[task["result_id"]]
                except KeyError:
                    print("ERROR: No search cache entry for id " + task["result_id"])
                    print("++ cache: " + str(self.vk_cache))
                    self.error(user, "Ошибка (запрошенная песня отсутствует в кэше поиска)")
                else:
                    try:
                        headers = self.users_to_vk_headers.pop(user)
                    except KeyError:
                        print("WARNING: Can't find user's headers")
                        headers = downloader.get_headers()

                    print("INFO: Downloading vk song #" + task["result_id"])
                    self.user_message(user, "Скачиваем %s - %s ..." % (song['artist'], song['title']))
                    self.output_queue.put({
                        "user": user,
                        "action": "confirmation_done"
                    })
                    new_task = {
                        "action": "user_confirmed",
                        "song": song,
                        "headers": headers,
                        "user": user
                    }
                    threading.Thread(
                        daemon=True,
                        target=self.thread_download_confirmed,
                        args=(downloader, new_task)
                    ).start()
            else:
                self.error(user, "Don't know what to do with this action: " + task["action"])

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

        self.vk_cache = {}

        self.queue_thread_listener = threading.Thread(
            daemon=True, target=self.queue_listener)
        self.queue_thread_listener.start()
