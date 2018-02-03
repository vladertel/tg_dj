from brain.DJ_Brain import DJ_Brain
from streamer.LiquidStreamer import LiquidStreamer
from downloader.MasterDownloader import MasterDownloader
from frontend.telegram_bot import TgFrontend

brain = DJ_Brain(TgFrontend(), MasterDownloader(), LiquidStreamer())