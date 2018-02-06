import sys

from brain.DJ_Brain import DJ_Brain
from streamer.LiquidStreamer import LiquidStreamer
from streamer.VLCStreamer import VLCStreamer
from downloader.MasterDownloader import MasterDownloader
from frontend.telegram_bot import TgFrontend

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)

brain = DJ_Brain(TgFrontend(), MasterDownloader(), VLCStreamer())