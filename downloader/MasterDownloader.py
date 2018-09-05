import threading
from queue import Queue

from .YoutubeDownloader import YoutubeDownloader
from .VkDownloader import VkDownloader
from .FileDownloader import FileDownloader
from .LinkDownloader import LinkDownloader
from .exceptions import *
from .config import MAXIMUM_FILE_SIZE, MAXIMUM_DURATION


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

            print("DEBUG: Trying " + downloader.name)
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
                self.user_message(user, "Ничего не нашел по этому запросу :(")
            except Exception as e:
                self.error(task["user"], "ERROR [MasterDownloader]: " + str(e))
            else:
                self.download_done(task["user"], file_path, title, seconds)
                print("DEBUG: Download done")
                self.user_message(user, "Запрос обработан")
                break
        self.input_queue.task_done()

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

    def thread_search_function(self, task):
        user = task["user"]
        for dwnld_name in self.downloaders:
            downloader = self.downloaders[dwnld_name]
            arg = downloader.is_acceptable(task)
            if not arg:
                continue
            try:
                search_results = downloader.schedule_search(task)
                search_results = search_results[0:min(10, len(search_results))]

                for r in search_results:
                    r["downloader"] = dwnld_name

                self.output_queue.put({
                    "action": "user_inline_reply",
                    "qid": task["qid"],
                    "user": user,
                    "results": search_results,
                })

            except MediaIsTooLong:
                self.user_message(user, "Запрошенная песня слишком длинная")
            except MediaIsTooBig:
                self.user_message(user, "Запрошенная песня слишком много весит (Больше чем " +
                                  str(MAXIMUM_FILE_SIZE / 1000000) + " MB)")
            except (UrlOrNetworkProblem, UrlProblem, BadReturnStatus):
                self.user_message(user, "Похоже модуль " + downloader.name +
                                  " отвалился или плохой запрос :(\nПопробуйте позже или скажите админу")
            except NothingFound:
                if task["action"] == "text_message":
                    self.user_message(user, "Ничего не нашел по этому запросу :(")
                elif task["action"] == "search_inline":
                    self.output_queue.put({
                        "action": "user_inline_reply",
                        "qid": task["qid"],
                        "user": user,
                        "results": []
                    })
            except Exception as e:
                self.error(task["user"], "ERROR [MasterDownloader]: " + str(e))

        self.input_queue.task_done()

    def thread_search_result(self, downloader, task):
        user = task["user"]
        try:
            file_path, title, seconds = downloader.schedule_search_result(
                task["result_id"],
                user_message=lambda msg: self.user_message(user, msg)
            )
        except MediaIsTooLong:
            self.user_message(user, "Запрошенная песня слишком длинная")
        except MediaIsTooBig:
            self.user_message(user, "Запрошенная песня слишком много весит (Больше чем " +
                              str(MAXIMUM_FILE_SIZE / 1000000) + " MB)")
        except BadReturnStatus as e:
            self.user_message(user, "Не удаётся загрузить файл (код ответа: " + str(e.args[0]) + ")\n"
                                    "Попробуйте повторить позже")
        except ApiError:
            self.user_message(user, "Не удаётся загрузить файл (ошибка API)\n"
                                    "Попробуйте повторить позже")
        except (UrlOrNetworkProblem, UrlProblem):
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

            if task["action"] == "download":
                print("INFO: User downloading")
                threading.Thread(daemon=True, target=self.thread_download_function, args=(task,)).start()

            elif task["action"] == "search_inline":
                print("INFO: User searching: " + task["query"])
                threading.Thread(daemon=True, target=self.thread_search_function, args=(task,)).start()

            elif task["action"] == "search_result_selected":
                print("INFO: User selected result: " + task["downloader"] + "#" + str(task["result_id"]))

                downloader = self.downloaders[task["downloader"]]

                self.output_queue.put({
                    "user": user,
                    "action": "confirmation_done"
                })
                threading.Thread(
                    daemon=True,
                    target=self.thread_search_result,
                    args=(downloader, task)
                ).start()
            else:
                self.error(user, "ERROR: Don't know what to do with this action: " + task["action"])

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
