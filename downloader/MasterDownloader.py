import threading
from queue import Queue
from collections import OrderedDict
import os


from .YoutubeDownloader import YoutubeDownloader
from .HtmlDownloader import HtmlDownloader
from .FileDownloader import FileDownloader
from .LinkDownloader import LinkDownloader
from .exceptions import *
from .config import MAXIMUM_FILE_SIZE, SEARCH_RESULTS_LIMIT, mediaDir

from utils import make_endless_unfailable


class MasterDownloader:
    def error(self, request_id, message):
        self.output_queue.put({
            "state": "error",
            "request_id": request_id,
            "message": message,
        })

    def thread_download(self, task):
        # Use defined downloader if task has such info
        if "downloader" in task:
            dl_name = task["downloader"]
            downloaders = {dl_name: self.downloaders[dl_name]}
        else:
            downloaders = self.downloaders

        # Define callback for sending status updates to user
        def user_message(new_text):
            task["progress_callback"](new_text)

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
                self.error(task["request_id"], str(e))
            else:
                print("DEBUG [MasterDownloader]: Download done")
                self.output_queue.put({
                    "state": "success",
                    "path": file_path,
                    "title": title,
                    "request_id": task["request_id"],
                    "duration": seconds,
                })
            break
        if not accepted:
            self.output_queue.put({
                "state": "error",
                "message": "Нет подходящего загрузчика",
                "request_id": task["request_id"],
                "text": task["text"] if "text" in task else "",
                "chat_id": task["chat_id"] if "chat_id" in task else None,
                "message_id": task["message_id"] if "message_id" in task else None,
            })

        self.input_queue.task_done()

    def thread_search(self, task):
        # Define callback for sending status updates to user
        def user_message(new_text):
            task["progress_callback"](new_text)

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
                    "state": "success",
                    "request_id": task["request_id"],
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
                    "state": "success",
                    "request_id": task["request_id"],
                    "results": [],
                })
            except Exception as e:
                print("ERROR [MasterDownloader]: " + str(e))
                self.error(task["request_id"], str(e))

        self.input_queue.task_done()

    @make_endless_unfailable
    def queue_listener(self):
        task = self.input_queue.get()

        if task["action"] == "download":
            print("INFO [MasterDownloader]: Download action")
            threading.Thread(daemon=True, target=self.thread_download, args=(task,)).start()
        elif task["action"] == "search":
            print("INFO [MasterDownloader]: Search action")
            threading.Thread(daemon=True, target=self.thread_search, args=(task,)).start()
        else:
            print("ERROR [MasterDownloader]: Unknown action: \"" + task["action"] + "\"")
            self.error(task["request_id"], "Ошибка загрузчика: неизвестное действие \"" + task["action"] + "\"")

    def __init__(self):
        # https://youtu.be/qAeybdD5UoQ
        self.downloaders = OrderedDict([
            ("yt", YoutubeDownloader()),
            ("file", FileDownloader()),
            ("html", HtmlDownloader()),
            ("link", LinkDownloader()),
        ])

        cacheDir = os.path.join(os.getcwd(), mediaDir)
        if not os.path.exists(cacheDir):
            os.mkdir(cacheDir)

        self.input_queue = Queue()
        self.output_queue = Queue()

        self.queue_thread_listener = threading.Thread(
            daemon=True, target=self.queue_listener)
        self.queue_thread_listener.start()
