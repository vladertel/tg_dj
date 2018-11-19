import sys
import atexit
import time

from brain.DJ_Brain import DjBrain
from streamer.VLCStreamer import VLCStreamer
from downloader.MasterDownloader import MasterDownloader
from frontend.telegram_bot import TgFrontend

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)
sys.stderr = sys.stdout

args = [TgFrontend(), MasterDownloader(), VLCStreamer()]

for arg in args:
    try:
        atexit.register(arg.cleanup)
    except AttributeError:
        pass

brain = DjBrain(*args)

print("Running infinite loop in main thread...")
try:
    while True:
        time.sleep(60)
except KeyboardInterrupt:
    print("Caught SIGTERM. Exiting...")
    exit(0)
