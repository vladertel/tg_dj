from .AbstractDownloader import AbstractDownloader
import os
from .config import mediaDir, _DEBUG_, DATMUSIC_API_ENDPOINT, INLINE_QUERY_CACHE_TIME

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                level=logging.INFO)
logger = logging.getLogger(__name__)

class VKDownloader(AbstractDownloader):
    def schedule_link(self, url, callback):
        pass
