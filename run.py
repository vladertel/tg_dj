import sys
import asyncio
import traceback
import argparse
import configparser
import signal
import prometheus_client

from brain.DJ_Brain import DjBrain
from streamer.VLCStreamer import VLCStreamer
from downloader.MasterDownloader import MasterDownloader
from frontend.telegram_bot import TgFrontend
from web.server import StatusWebServer

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)
sys.stderr = sys.stdout

parser = argparse.ArgumentParser()
parser.add_argument("-f", "--config-file", type=str, default="config.ini")
args = parser.parse_args()

config = configparser.ConfigParser()
config.read(args.config_file)


def hup_handler(_signum, _frame):
    print("INFO: Caught sighup signal. Reloading configuration...")
    config.read(args.config_file)
    print("INFO: Config reloaded")


signal.signal(signal.SIGHUP, hup_handler)

modules = [TgFrontend(config), MasterDownloader(config), VLCStreamer(config)]
brain = DjBrain(config, *modules)

web = StatusWebServer(config)
web.bind_core(brain)

prometheus_client.start_http_server(8910)

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
