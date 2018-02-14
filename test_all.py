import sys
import atexit

from brain.DJ_Brain import DJ_Brain
from streamer.LiquidStreamer import LiquidStreamer
from streamer.VLCStreamer import VLCStreamer
from downloader.MasterDownloader import MasterDownloader
from frontend.telegram_bot import TgFrontend

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)

args = [TgFrontend(), MasterDownloader(), VLCStreamer()]

for arg in args:
    try:
        atexit.register(arg.cleanup)
    except AttributeError:
        pass

brain = DJ_Brain(*args)
