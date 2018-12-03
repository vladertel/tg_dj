import os
import json
import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncio


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
        print(self.request.remote_ip, 'connected')
        self.server.ws_clients.append(self)

    def on_close(self):
        print(self.request.remote_ip, 'closed')
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
            print(self.request.remote_ip, 'connection lost')
            self.on_close()


# noinspection PyAbstractClass,PyAttributeOutsideInit
class MainHandler(tornado.web.RequestHandler):

    def initialize(self, **kwargs):
        self.server = kwargs.get("server")

    def get(self):
        song, progress = self.server.get_current_state()
        self.render("index.html", song_info=song, song_progress=progress,
                    stream_url=self.server.stream_url, ws_url=self.server.ws_url)


class StatusWebServer:

    def __init__(self, config):
        self.config = config

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

        self.stream_url = self.config.get("web_server", "stream_url")
        self.ws_url = self.config.get("web_server", "ws_url", fallback="ws://localhost:8080/ws")

    def bind_core(self, core):
        self.core = core
        self.core.add_state_update_callback(self.update_state)

    def get_current_state(self):
        song = self.core.backend.get_current_song().to_dict()
        progress = self.core.backend.get_song_progress()
        return song, progress

    def update_state(self, track):
        self.broadcast_update(track.to_dict())

    def broadcast_update(self, data):
        for c in self.ws_clients:
            c.send("update", data)
