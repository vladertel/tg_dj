import os
import json
import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncio
from .config import stream_url


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
        data = self.server.get_current_song()
        self.render("index.html", song_info=data, stream_url=stream_url)


class StatusWebServer:

    def __init__(self, address, port):

        settings = {
            "static_path": os.path.join(os.path.dirname(__file__), "static"),
            "debug": False,
        }

        app = tornado.web.Application([
            (r"/", MainHandler, dict(server=self)),
            (r'/ws', WebSocketHandler, dict(server=self)),
        ], **settings)

        app.listen(port, address=address)

        self.core = None
        self.ws_clients = []
        self.KEEP_ALIVE_INTERVAL = 60

    def bind_core(self, core):
        self.core = core
        self.core.add_state_update_callback(self.update_state)

    def get_current_song(self):
        return self.core.backend.get_current_song().to_dict()

    def update_state(self, track):
        self.broadcast_update(track.to_dict())

    def broadcast_update(self, data):
        for c in self.ws_clients:
            c.send("update", data)
