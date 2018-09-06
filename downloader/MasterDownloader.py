import threading
from queue import Queue

from .YoutubeDownloader import YoutubeDownloader
from .VkDownloader import VkDownloader
from .FileDownloader import FileDownloader
from .LinkDownloader import LinkDownloader
from .exceptions import *
from .config import MAXIMUM_FILE_SIZE, SEARCH_RESULTS_LIMIT


class MasterDownloader:
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

    def send_user_message(self, user, text):
        self.output_queue.put({
            "action": "user_message",
            "user": user,
            "message": text
        })

    def edit_user_message(self, user, chat_id, message_id, new_text):
        self.output_queue.put({
            "action": "edit_user_message",
            "user": user,
            "chat_id": chat_id,
            "message_id": message_id,
            "new_text": new_text
        })

    def thread_download(self, task):
        user = task["user"]

        self.output_queue.put({
            "user": user,
            "action": "confirmation_done"
        })

        # Use defined downloader if task has such info
        if "downloader" in task:
            dl_name = task["downloader"]
            downloaders = {dl_name: self.downloaders[dl_name]}
        else:
            downloaders = self.downloaders

        # Define callback for sending status updates to user
        if "message_id" in task and "chat_id" in task:
            def user_message(new_text):
                return self.edit_user_message(user, task["chat_id"], task["message_id"], new_text)
        else:
            def user_message(new_text):
                return self.send_user_message(user, new_text)

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
                self.error(task["user"], "error happened: " + str(e))
            else:
                self.download_done(task["user"], file_path, title, seconds)
                accepted = True
                print("DEBUG: Download done")
                break
        if not accepted:
            user_message("Нет подходящего для вашего запроса обработчика.")

        self.input_queue.task_done()

    def thread_search(self, task):
        user = task["user"]

        # Define callback for sending status updates to user
        if "message_id" in task and "chat_id" in task:
            def user_message(new_text):
                return self.edit_user_message(user, task["chat_id"], task["message_id"], new_text)
        else:
            def user_message(new_text):
                return self.send_user_message(user, new_text)

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
                    "user": user,
                    "results": search_results,
                })

            except MediaIsTooLong:
                user_message("Трек слишком длинный")
            except MediaIsTooBig:
                user_message("Трек слишком много весит ( > " + str(MAXIMUM_FILE_SIZE / 1000000) + " MB)")
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
                    "user": user,
                    "results": []
                })
            except Exception as e:
                self.error(task["user"], "ERROR [MasterDownloader]: " + str(e))

        self.input_queue.task_done()

    def queue_listener(self):
        while True:
            task = self.input_queue.get()
            user = task["user"]

            if task["action"] == "download":
                print("INFO [MasterDownloader]: Download action")
                threading.Thread(daemon=True, target=self.thread_download, args=(task,)).start()
            elif task["action"] == "search":
                print("INFO [MasterDownloader]: Search action")
                threading.Thread(daemon=True, target=self.thread_search, args=(task,)).start()
            else:
                self.error(user, "WARNING [MasterDownloader]: Unknown action: \"" + task["action"] + "\"")

    def __init__(self):
        # https://youtu.be/qAeybdD5UoQ
        self.downloaders = {
            "yt": YoutubeDownloader(),
            "link": LinkDownloader(),
            "file": FileDownloader(),
            "vk": VkDownloader()
        }
        self.input_queue = Queue()
        self.output_queue = Queue()

        self.queue_thread_listener = threading.Thread(
            daemon=True, target=self.queue_listener)
        self.queue_thread_listener.start()
