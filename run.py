import sys
import asyncio
import traceback

from brain.DJ_Brain import DjBrain
from streamer.VLCStreamer import VLCStreamer
from downloader.MasterDownloader import MasterDownloader
from frontend.telegram_bot import TgFrontend

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)
sys.stderr = sys.stdout

args = [TgFrontend(), MasterDownloader(), VLCStreamer()]
brain = DjBrain(*args)

loop = asyncio.get_event_loop()
try:
    loop.run_forever()
except (KeyboardInterrupt, SystemExit):
    pass
print("FATAL: Main event loop has ended")
print("DEBUG: Cleaning...")
for arg in args:
    try:
        arg.cleanup()
    except AttributeError:
        traceback.print_exc()
try:
    brain.cleanup()
except AttributeError:
    traceback.print_exc()

loop.close()
print("DEBUG: Exit")
