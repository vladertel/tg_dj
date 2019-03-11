import asyncio
import traceback
import argparse
import configparser
import logging
import signal
import prometheus_client

from brain.DJ_Brain import DjBrain
from streamer.MPDStreamer import MPDStreamer
from downloader.MasterDownloader import MasterDownloader
from frontend.telegram_bot import TgFrontend
from web.server import StatusWebServer

# Parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("-f", "--config-file", type=str, default="config.ini")
args = parser.parse_args()

config = configparser.ConfigParser()
config.read(args.config_file)


# Reload config on sighup signal
def hup_handler(_signum, _frame):
    logging.info("Caught sighup signal. Reloading configuration...")
    config.read(args.config_file)
    logging.info("Config reloaded")


signal.signal(signal.SIGHUP, hup_handler)

# Setup logging
logging.basicConfig(format='%(asctime)s %(levelname)s [%(name)s - %(funcName)s]: %(message)s')

# Start modules
modules = [TgFrontend(config), MasterDownloader(config), MPDStreamer(config)]
brain = DjBrain(config, *modules)
web = StatusWebServer(config)
web.bind_core(brain)

# Start prometheus server
prometheus_client.start_http_server(8910)

# Run event loop
loop = asyncio.get_event_loop()
try:
    loop.run_forever()
except (KeyboardInterrupt, SystemExit):
    pass
logging.info("Main event loop has ended")
logging.debug("Cleaning...")
for module in modules:
    try:
        module.cleanup()
    except AttributeError:
        traceback.print_exc()
try:
    brain.cleanup()
except AttributeError:
    traceback.print_exc()

logging.info("Closing loop...")
loop.run_until_complete(asyncio.sleep(1))
loop.stop()
loop.close()
logging.debug("Exit")
