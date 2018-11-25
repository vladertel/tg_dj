import os
import json
import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncio
from .config import stream_url


# noinspection PyAbstractClass
class WebSocketHandler(tornado.websocket.WebSocketHandler):

    def __init__(self, application, request, **kwargs):
        self.server = None
        super().__init__(application, request, **kwargs)

    def initialize(self, **kwargs):
        self.server = kwargs.get("server")
        loop = asyncio.get_event_loop()
        loop.create_task(self.keep_alive())

    def check_origin(self, _origin):
        return True

    def open(self):
        print(self.request.remote_ip, 'connected')
        self.server.ws_clients.append(self)

    def on_close(self):
        print(self.request.remote_ip, 'closed')
        self.server.ws_clients.remove(self)

    async def keep_alive(self):
        while True:
            await asyncio.sleep(self.server.KEEP_ALIVE_INTERVAL)
            self.send("keep_alive", {})

    def send(self, msg, data):
        line = json.dumps({msg: data})
        self.write_message(line)


# noinspection PyAbstractClass
class MainHandler(tornado.web.RequestHandler):

    def __init__(self, application, request, **kwargs):
        self.server = None
        super().__init__(application, request, **kwargs)

    def initialize(self, **kwargs):
        self.server = kwargs.get("server")

    def get(self):
        data = self.server.get_data()
        self.render("index.html", song_info=data, stream_url=stream_url)


class StatusWebServer:

    def __init__(self, core, bind_address, bind_port):
        self.core = core

        self.core.add_state_update_callback(self.update_state)

        settings = {
            "static_path": os.path.join(os.path.dirname(__file__), "static"),
            "debug": False,
        }

        app = tornado.web.Application([
            (r"/", MainHandler, dict(server=self)),
            (r'/ws', WebSocketHandler, dict(server=self)),
        ], **settings)

        app.listen(bind_port, address=bind_address)

        self.ws_clients = []
        self.KEEP_ALIVE_INTERVAL = 60

    def get_data(self):
        return self.core.backend.get_current_song().to_dict()

    def update_state(self, track):
        self.broadcast_update(track.to_dict())

    def broadcast_update(self, data):
        for c in self.ws_clients:
            c.send("update", data)
