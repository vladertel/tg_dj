import os
import json
import time
import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncio
import logging
from prometheus_client import Gauge

from brain.models import Song


# noinspection PyAbstractClass,PyAttributeOutsideInit
class WebSocketHandler(tornado.websocket.WebSocketHandler):

    def initialize(self, **kwargs):
        self.server = kwargs.get("server")
        loop = asyncio.get_event_loop()
        loop.create_task(self.keep_alive())
        self.active = True

    def check_origin(self, _origin):
        return True

    def open(self):
        self.server.logger.info('Websocket connected: %s', str(self.request.connection.context.address))
        self.server.ws_clients.append(self)

        track_dict, progress = self.server.get_current_state()
        self.send("update", track_dict)
        self.send("progress", progress)

    def on_close(self):
        self.server.logger.info('Websocket disconnected: %s', str(self.request.connection.context.address))
        self.active = False
        try:
            self.server.ws_clients.remove(self)
        except ValueError:
            pass

    async def keep_alive(self):
        while self.active:
            await asyncio.sleep(self.server.KEEP_ALIVE_INTERVAL)
            self.send("keep_alive", {})

    def send(self, msg, data):
        line = json.dumps({msg: data})
        try:
            self.write_message(line)
        except tornado.websocket.WebSocketClosedError:
            self.server.logger.info('Lost websocket %s', str(self.request.connection.context.address))
            self.on_close()


# noinspection PyAbstractClass,PyAttributeOutsideInit
class MainHandler(tornado.web.RequestHandler):

    def initialize(self, **kwargs):
        self.server = kwargs.get("server")

    def get(self):
        song, progress = self.server.get_current_state()
        self.render(os.path.join(os.path.dirname(__file__), "index.html"), song_info=song, song_progress=progress,
                    stream_url=self.server.stream_url + '?ts=' + str(time.time()), ws_url=self.server.ws_url)


class StatusWebServer:

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("tg_dj.web")
        self.logger.setLevel(getattr(logging, self.config.get("web_server", "verbosity", fallback="warning").upper()))

        settings = {
            "static_path": os.path.join(os.path.dirname(__file__), "static"),
            "debug": False,
        }

        app = tornado.web.Application([
            (r"/", MainHandler, dict(server=self)),
            (r'/ws', WebSocketHandler, dict(server=self)),
        ], **settings)

        app.listen(
            port=self.config.getint("web_server", "listen_port", fallback=8080),
            address=self.config.get("web_server", "listen_addr", fallback="127.0.0.1"),
        )

        self.core = None
        self.ws_clients = []
        self.KEEP_ALIVE_INTERVAL = 60

        # noinspection PyArgumentList
        self.mon_web_ws_clients = Gauge('dj_web_ws_clients', 'Number of websocket connections')
        self.mon_web_ws_clients.set_function(lambda: len(self.ws_clients))

        self.stream_url = self.config.get("web_server", "stream_url", fallback="/stream")
        self.ws_url = self.config.get("web_server", "ws_url", fallback="auto")

    def bind_core(self, core):
        self.core = core
        self.core.add_state_update_callback(self.update_state)

    def get_current_state(self):
        track = self.core.backend.get_current_song()
        track_dict = Song.to_dict(track)

        progress = self.core.backend.get_song_progress()
        return track_dict, progress

    def update_state(self, track):
        if track is not None:
            self.broadcast_update(track.to_dict())
        else:
            self.broadcast_stop()

    def broadcast_update(self, data):
        for c in self.ws_clients:
            c.send("update", data)

    def broadcast_stop(self):
        for c in self.ws_clients:
            c.send("stop_playback", {})
