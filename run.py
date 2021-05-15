import asyncio
import traceback
import argparse
import configparser
import logging
import signal

import discord
import prometheus_client
import os

from core.Core import Core
from downloaders.FileDownloader import FileDownloader
from downloaders.HtmlDownloader import HtmlDownloader
from downloaders.LinkDownloader import LinkDownloader
from downloaders.YoutubeDownloader import YoutubeDownloader
from VLC.VLCRadioEmitter import VLCStreamer
from downloaders.MasterDownloader import MasterDownloader
from telegram.TelegramFrontend import TgFrontend
from discord_.DiscordComponent import DiscordComponent
from web.server import StatusWebServer


def read_config_and_environment(file_path) -> configparser.ConfigParser:
    config = configparser.ConfigParser()
    config.read(file_path)

    for name in os.environ:
        if name[:3] != "DJ_":
            continue

        value = os.environ[name]
        name = name[3:]

        section = None
        for s in config.sections() + [config.default_section]:
            if s == name[:len(s)]:
                section = s
        if section is None:
            continue

        key = name[len(section) + 1:]

        config.set(section, key, value)

    return config


if __name__ == '__main__':

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--config-file", type=str, default="config.ini")
    args = parser.parse_args()

    config = read_config_and_environment(args.config_file)

    # Setup logging
    logging.basicConfig(format='%(asctime)s %(levelname)s [%(name)s - %(funcName)s]: %(message)s')
    logger = logging.getLogger('tg_dj')
    logger.setLevel(config.get(config.default_section, "verbosity", fallback="warning").upper())

    # Start modules
    main_loop = asyncio.get_event_loop()

    downloader = MasterDownloader(config, [
        YoutubeDownloader(config),
        FileDownloader(config),
        HtmlDownloader(config),
        LinkDownloader(config),
    ])
    # modules = [DiscordComponent(config, discord.Client(loop=main_loop)), TgFrontend(config)]
    modules = [DiscordComponent(config, discord.Client(loop=main_loop)), StatusWebServer(config)]
    # modules = [VLCStreamer(config), TgFrontend(config)]

    core = Core(config, components=modules, downloader=downloader, loop=main_loop)

    # Reload config on sighup signal
    def hup_handler(_signum, _frame):
        logging.info("Caught sighup signal. Reloading configuration...")
        config.read(args.config_file)
        core.update_config(config)
        logging.info("Config reloaded")

    signal.signal(signal.SIGHUP, hup_handler)

    # Start prometheus server
    prometheus_client.start_http_server(8910)

    # Run event loop
    try:
        main_loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    logger.info("Main event loop has ended")
    logger.debug("Cleaning...")
    try:
        core.cleanup()
    except AttributeError:
        traceback.print_exc()

    logger.info("Closing loop...")
    main_loop.run_until_complete(asyncio.sleep(1))
    main_loop.stop()
    main_loop.close()
    logger.debug("Exit")
