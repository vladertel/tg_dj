import concurrent.futures
import logging
import os
import time
from collections import OrderedDict
from typing import Dict, List
from prometheus_client import Gauge, Summary

from core.AbstractDownloader import AbstractDownloader, DownloaderException, UrlOrNetworkProblem, UrlProblem, \
    MediaIsTooLong, MediaIsTooBig, MediaSizeUnspecified, BadReturnStatus, NothingFound, ApiError, NotAccepted

# noinspection PyArgumentList
mon_downloads_in_progress = Gauge('dj_downloads_in_progress', 'Downloads in progress')
# noinspection PyArgumentList
mon_searches_in_progress = Gauge('dj_searches_in_progress', 'Searches in progress')
mon_download_duration = Summary('dj_download_duration', 'Time spent in downloading', ['handler'])
mon_search_duration = Summary('dj_search_duration', 'Time spent in search', ['handler'])


class MasterDownloader:
    def __init__(self, config, downloaders: List[AbstractDownloader]):
        """
        :param configparser.ConfigParser config:
        """
        self.config = config
        self.logger = logging.getLogger("tg_dj.downloader.master")
        self.logger.setLevel(self.config.get("downloader", "verbosity", fallback="warning").upper())

        self.handlers = OrderedDict([(d.get_name(), d) for d in downloaders])

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
        self.logger.debug("Number of files: %d / %d", len(files), files_storage_limit)
        if len(files) <= files_storage_limit:
            self.logger.debug("File storage: OK")
            return
        files_to_delete = files[files_storage_limit:]
        for file in files_to_delete:
            os.unlink(file)
            self.logger.info("File have been deleted: " + file)

    @mon_downloads_in_progress.track_inprogress()
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
                self.logger.info(f"Downloading: {query}")
                start_time = time.time()
                result = downloader.download(query, user_message=callback)
                end_time = time.time()
                mon_download_duration.labels(handler_name).observe(end_time - start_time)
                self.logger.info(f"Downloaded: {query}")
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
            except DownloaderException as e:
                callback(str(e.args[0]))
            except Exception as e:
                self.logger.error(str(e))
                raise e
            break
        if not accepted:
            raise NotAccepted()

    @mon_searches_in_progress.track_inprogress()
    def thread_search(self, query, callback, limit):
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
                    limit=limit
                )
                start_time = time.time()
                search_results = search_results[0:min(results_limit, len(search_results))]
                end_time = time.time()
                mon_search_duration.labels(dwnld_name).observe(end_time - start_time)

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
                self.logger.error(str(e))
                raise e

    async def download(self, kind, query, callback):
        self.logger.info("Download action")
        return await self.core.loop.run_in_executor(self.thread_pool, self.thread_download, kind, query, callback)

    async def search(self, query, callback, limit):
        self.logger.info("Search action")
        return await self.core.loop.run_in_executor(self.thread_pool, self.thread_search, query, callback, limit)
