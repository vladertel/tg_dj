import sys
import asyncio
import traceback
import argparse

from brain.DJ_Brain import DjBrain
from streamer.VLCStreamer import VLCStreamer
from downloader.MasterDownloader import MasterDownloader
from frontend.telegram_bot import TgFrontend
from web.server import StatusWebServer

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)
sys.stderr = sys.stdout

parser = argparse.ArgumentParser()
parser.add_argument("-p", "--stat-port", type=int, default=8911)
parser.add_argument("-a", "--stat-address", type=str, default='127.0.0.1')
args = parser.parse_args()

modules = [TgFrontend(), MasterDownloader(), VLCStreamer()]
brain = DjBrain(*modules)

web = StatusWebServer(args.stat_address, args.stat_port)
web.bind_core(brain)

loop = asyncio.get_event_loop()
try:
    loop.run_forever()
except (KeyboardInterrupt, SystemExit):
    pass
print("FATAL: Main event loop has ended")
print("DEBUG: Cleaning...")
for module in modules:
    try:
        module.cleanup()
    except AttributeError:
        traceback.print_exc()
try:
    brain.cleanup()
except AttributeError:
    traceback.print_exc()

print("FATAL: Closing loop...")
loop.run_until_complete(asyncio.sleep(1))
loop.stop()
loop.close()
print("DEBUG: Exit")
