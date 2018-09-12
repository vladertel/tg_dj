import sys
import atexit
import time

from brain.DJ_Brain import DJ_Brain
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
try:
    atexit.register(brain.cleanup)
except AttributeError:
        pass

print("Running infinite loop in main thread...")
try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    print("Caught SIGTERM. Exiting...")
    exit(0)
