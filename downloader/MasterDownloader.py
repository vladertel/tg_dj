import concurrent.futures
from collections import OrderedDict
import os


from .YoutubeDownloader import YoutubeDownloader
from .HtmlDownloader import HtmlDownloader
from .FileDownloader import FileDownloader
from .LinkDownloader import LinkDownloader
from .exceptions import *
from .config import MAXIMUM_FILE_SIZE, SEARCH_RESULTS_LIMIT, mediaDir


class MasterDownloader:
    def __init__(self):
        # https://youtu.be/qAeybdD5UoQ
        self.handlers = OrderedDict([
            ("yt", YoutubeDownloader()),
            ("file", FileDownloader()),
            ("html", HtmlDownloader()),
            ("link", LinkDownloader()),
        ])

        self.thread_pool = concurrent.futures.ThreadPoolExecutor()
        self.core = None

        cache_dir = os.path.join(os.getcwd(), mediaDir)
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)

    def bind_core(self, core):
        self.core = core

    def thread_download(self, kind, query, callback):

        if kind == "search_result":
            dl_name = query["downloader"]
            handlers = {dl_name: self.handlers[dl_name]}
        else:
            handlers = self.handlers

        accepted = False
        for handler_name in handlers:
            downloader = handlers[handler_name]
            if not downloader.is_acceptable(kind, query):
                continue

            accepted = True
            try:
                return downloader.download(query, user_message=callback)
            except MediaIsTooLong as e:
                callback("Трек слишком длинный (" + str(e.args[0]) + " секунд)")
            except MediaIsTooBig:
                callback("Трек слишком много весит ( > " + str(MAXIMUM_FILE_SIZE / 1000000) + " MB)")
            except MediaSizeUnspecified:
                callback("Трек не будет загружен, так как не удаётся определить его размер")
            except BadReturnStatus as e:
                callback("Сервер недоступен (код ответа: " + str(e.args[0]) + ")\nПопробуйте повторить позже")
            except ApiError:
                callback("Сервер недоступен (ошибка API)\nПопробуйте повторить позже")
            except (UrlOrNetworkProblem, UrlProblem):
                callback("Не удаётся выполнить запрос к серверу (ошибка сети или адреса)\n"
                         "Попробуйте повторить позже")
            except NothingFound:
                callback("Ничего не нашел по этому запросу :(")
            except Exception as e:
                print("ERROR [MasterDownloader]: " + str(e))
                raise e
            break
        if not accepted:
            raise NotAccepted()

    def thread_search(self, query, callback):
        for dwnld_name in self.handlers:
            downloader = self.handlers[dwnld_name]
            arg = downloader.is_acceptable("search", query)
            if not arg:
                continue
            try:
                search_results = downloader.search(
                    query,
                    user_message=callback,
                )
                search_results = search_results[0:min(SEARCH_RESULTS_LIMIT, len(search_results))]

                for r in search_results:
                    r["downloader"] = dwnld_name

                return search_results

            except BadReturnStatus as e:
                callback("Сервер недоступен (код ответа: " + str(e.args[0]) + ")\nПопробуйте повторить позже")
            except ApiError:
                callback("Сервер недоступен (ошибка API)\nПопробуйте повторить позже")
            except (UrlOrNetworkProblem, UrlProblem):
                callback("Не удаётся выполнить запрос к серверу (ошибка сети или адреса)\nПопробуйте повторить позже")
            except NothingFound:
                return []
            except Exception as e:
                print("ERROR [MasterDownloader]: " + str(e))
                raise e

    async def download(self, kind, query, callback):
        print("INFO [MasterDownloader]: Download action")
        return await self.core.loop.run_in_executor(self.thread_pool, self.thread_download, kind, query, callback)

    async def search(self, query, callback):
        print("INFO [MasterDownloader]: Search action")
        return await self.core.loop.run_in_executor(self.thread_pool, self.thread_search, query, callback)
