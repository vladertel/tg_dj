import concurrent.futures
from collections import OrderedDict
import os


from .YoutubeDownloader import YoutubeDownloader
from .HtmlDownloader import HtmlDownloader
from .FileDownloader import FileDownloader
from .LinkDownloader import LinkDownloader
from .exceptions import *


class MasterDownloader:
    def __init__(self, config):
        """
        :param configparser.ConfigParser config:
        """
        self.config = config

        self.handlers = OrderedDict([
            ("yt", YoutubeDownloader(config)),
            ("file", FileDownloader(config)),
            ("html", HtmlDownloader(config)),
            ("link", LinkDownloader(config)),
        ])

        self.thread_pool = concurrent.futures.ThreadPoolExecutor()
        self.core = None

        media_dir = self.config.get("downloader", "media_dir", fallback="media")
        if not os.path.exists(media_dir):
            os.mkdir(media_dir)

    def bind_core(self, core):
        self.core = core

    def cleanup(self):
        pass
        # TODO: Delete incomplete downloads

    def _filter_storage(self):
        media_dir = self.config.get("downloader", "media_dir", fallback="media")
        files_storage_limit = self.config.getint("downloader", "files_storage_limit", fallback=60)

        files_dir = os.path.join(os.getcwd(), media_dir)

        files = [os.path.join(files_dir, f) for f in os.listdir(files_dir) if
                 os.path.isfile(os.path.join(files_dir, f)) and not f.startswith(".")]

        files.sort(key=lambda x: -os.path.getmtime(x))
        print("Number of files: " + str(len(files)))
        if len(files) <= files_storage_limit:
            print("filter_storage files < MAXIMUM_FILES_COUNT")
            return
        files_to_delete = files[files_storage_limit:]
        for file in files_to_delete:
            os.unlink(file)
            print("deleted: " + file)

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
                result = downloader.download(query, user_message=callback)
                self._filter_storage()
                return result
            except MediaIsTooLong as e:
                callback("Трек слишком длинный (" + str(e.args[0]) + " секунд)")
            except MediaIsTooBig as e:
                callback("Трек слишком много весит ( > " + ("%.2f" % (e.args[0] / 1000000)) + " MB)")
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
        results_limit = self.config.getint("downloader", "search_max_results", fallback=10)

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
                search_results = search_results[0:min(results_limit, len(search_results))]

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
