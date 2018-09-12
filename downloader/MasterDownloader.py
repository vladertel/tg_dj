import threading
from queue import Queue
from collections import OrderedDict

from .YoutubeDownloader import YoutubeDownloader
from .VkDownloader import VkDownloader
from .FileDownloader import FileDownloader
from .LinkDownloader import LinkDownloader
from .exceptions import *
from .config import MAXIMUM_FILE_SIZE, SEARCH_RESULTS_LIMIT


class MasterDownloader:
    def download_done(self, user_id, file_path, title, duration):
        self.output_queue.put({
            "action": "download_done",
            "path": file_path,
            "title": title,
            "user_id": user_id,
            "duration": duration
        })

    def error(self, user_id, message):
        self.output_queue.put({
            "action": "error",
            "user_id": user_id,
            "message": message
        })

    def send_user_message(self, user_id, text):
        self.output_queue.put({
            "action": "user_message",
            "user_id": user_id,
            "message": text
        })

    def edit_user_message(self, user_id, chat_id, message_id, new_text):
        self.output_queue.put({
            "action": "edit_user_message",
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "new_text": new_text
        })

    def thread_download(self, task):
        user_id = task["user_id"]

        # Use defined downloader if task has such info
        if "downloader" in task:
            dl_name = task["downloader"]
            downloaders = {dl_name: self.downloaders[dl_name]}
        else:
            downloaders = self.downloaders

        # Define callback for sending status updates to user
        if "message_id" in task and "chat_id" in task:
            def user_message(new_text):
                return self.edit_user_message(user_id, task["chat_id"], task["message_id"], new_text)
        else:
            def user_message(new_text):
                return self.send_user_message(user_id, new_text)

        accepted = False
        for dwnld_name in downloaders:
            downloader = downloaders[dwnld_name]
            arg = downloader.is_acceptable(task)
            if not arg:
                continue

            accepted = True
            try:
                file_path, title, seconds = downloader.download(
                    task,
                    user_message=user_message,
                )
            except MediaIsTooLong as e:
                user_message("Трек слишком длинный (" + str(e.args[0]) + " секунд)")
            except MediaIsTooBig:
                user_message("Трек слишком много весит ( > " + str(MAXIMUM_FILE_SIZE / 1000000) + " MB)")
            except MediaSizeUnspecified:
                user_message("Трек не будет загружен, так как не удаётся определить его размер")
            except BadReturnStatus as e:
                user_message("Сервер недоступен (код ответа: " + str(e.args[0]) + ")\nПопробуйте повторить позже")
            except ApiError:
                user_message("Сервер недоступен (ошибка API)\nПопробуйте повторить позже")
            except (UrlOrNetworkProblem, UrlProblem):
                user_message("Не удаётся выполнить запрос к серверу (ошибка сети или адреса)\n"
                             "Попробуйте повторить позже")
            except NothingFound:
                user_message("Ничего не нашел по этому запросу :(")
            except Exception as e:
                print("ERROR [MasterDownloader]: " + str(e))
                self.error(user_id, str(e))
            else:
                print("DEBUG [MasterDownloader]: Download done")
                self.download_done(user_id, file_path, title, seconds)
            break
        if not accepted:
            self.output_queue.put({
                "action": "no_dl_handler",
                "user_id": user_id,
                "text": task["text"] if "text" in task else "",
                "chat_id": task["chat_id"] if "chat_id" in task else None,
                "message_id": task["message_id"] if "message_id" in task else None,
            })

        self.input_queue.task_done()

    def thread_search(self, task):
        user_id = task["user_id"]

        # Define callback for sending status updates to user
        if "message_id" in task and "chat_id" in task:
            def user_message(new_text):
                return self.edit_user_message(user_id, task["chat_id"], task["message_id"], new_text)
        else:
            def user_message(new_text):
                return self.send_user_message(user_id, new_text)

        for dwnld_name in self.downloaders:
            downloader = self.downloaders[dwnld_name]
            arg = downloader.is_acceptable(task)
            if not arg:
                continue
            try:
                search_results = downloader.search(
                    task,
                    user_message=user_message,
                )
                search_results = search_results[0:min(SEARCH_RESULTS_LIMIT, len(search_results))]

                for r in search_results:
                    r["downloader"] = dwnld_name

                self.output_queue.put({
                    "action": "search_results",
                    "qid": task["qid"],
                    "user_id": user_id,
                    "results": search_results,
                })

            except BadReturnStatus as e:
                user_message("Сервер недоступен (код ответа: " + str(e.args[0]) + ")\nПопробуйте повторить позже")
            except ApiError:
                user_message("Сервер недоступен (ошибка API)\nПопробуйте повторить позже")
            except (UrlOrNetworkProblem, UrlProblem):
                user_message("Не удаётся выполнить запрос к серверу (ошибка сети или адреса)\n"
                             "Попробуйте повторить позже")
            except NothingFound:
                self.output_queue.put({
                    "action": "search_results",
                    "qid": task["qid"],
                    "user_id": user_id,
                    "results": []
                })
            except Exception as e:
                print("ERROR [MasterDownloader]: " + str(e))
                self.error(user_id, str(e))

        self.input_queue.task_done()

    def queue_listener(self):
        while True:
            task = self.input_queue.get()
            user_id = task["user_id"]

            if task["action"] == "download":
                print("INFO [MasterDownloader]: Download action")
                threading.Thread(daemon=True, target=self.thread_download, args=(task,)).start()
            elif task["action"] == "search":
                print("INFO [MasterDownloader]: Search action")
                threading.Thread(daemon=True, target=self.thread_search, args=(task,)).start()
            else:
                print("ERROR [MasterDownloader]: Unknown action: \"" + task["action"] + "\"")
                self.error(user_id, "Ошибка загрузчика: неизвестное действие \"" + task["action"] + "\"")

    def __init__(self):
        # https://youtu.be/qAeybdD5UoQ
        self.downloaders = OrderedDict([
            ("yt", YoutubeDownloader()),
            ("file", FileDownloader()),
            ("vk", VkDownloader()),
            ("link", LinkDownloader()),
        ])
        self.input_queue = Queue()
        self.output_queue = Queue()

        self.queue_thread_listener = threading.Thread(
            daemon=True, target=self.queue_listener)
        self.queue_thread_listener.start()
