import os
import json
import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado import gen


ws_clients = []


def broadcast_update(filename):
    f = open(filename, 'r')
    text = f.read()
    f.close()
    data = json.load(text)
    for c in ws_clients:
        c.send("update", data)


@gen.coroutine
def watch_file(filename):
    last_change = os.path.getmtime(filename)
    while True:
        yield gen.sleep(1)
        try:
            m_time = os.path.getmtime(filename)
        except FileNotFoundError:
            print("FileNotFoundError")
            continue
        if m_time > last_change:
            last_change = m_time
            broadcast_update(filename)


KEEP_ALIVE_INTERVAL = 60


class WSH(tornado.websocket.WebSocketHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tornado.ioloop.IOLoop.current().call_later(KEEP_ALIVE_INTERVAL, self.keep_alive)

    def check_origin(self, _origin):
        return True

    def open(self):
        print(self.request.remote_ip, 'connected')
        ws_clients.append(self)

    def on_close(self):
        print(self.request.remote_ip, 'closed')
        ws_clients.remove(self)

    @gen.coroutine
    def keep_alive(self):
        while True:
            self.send("keep_alive", {})
            yield gen.sleep(KEEP_ALIVE_INTERVAL)

    def send(self, msg, data):
        line = json.dumps({msg: data})
        self.write_message(line)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=8081)
    parser.add_argument("-a", "--address", type=str, default='127.0.0.1')
    parser.add_argument("file", type=str)
    args = parser.parse_args()

    settings = {
        "static_path": os.path.join(os.path.dirname(__file__), "static"),
        "debug": True,
    }

    app = tornado.web.Application([
        (r"/", MainHandler),
        (r'/ws', WSH),
    ], **settings)

    app.listen(args.port, address=args.address)

    file_path = os.path.realpath(args.file)

    tornado.ioloop.IOLoop.instance().add_callback(watch_file, file_path)
    tornado.ioloop.IOLoop.current().start()
