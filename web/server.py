import json
import time
from urllib.parse import urlparse

import tornado.ioloop
import tornado.web
import tornado.websocket
import asyncio
import logging
import os
import os.path
import tornado
import tornado.gen
import tornado.httpclient

ap = os.path.abspath
join = os.path.join

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
        self.set_header("Access-Control-Allow-Origin", "*")
        self.render(os.path.join(os.path.dirname(__file__), "index.html"), song_info=song, song_progress=progress,
                    stream_url=self.server.stream_url + '?ts=' + str(time.time()), ws_url=self.server.ws_url)


class StreamProxyHandler(tornado.web.RequestHandler):
    def initialize(self, proxy_url='/', **kwargs):
        super(StreamProxyHandler, self).initialize(**kwargs)
        self.proxy_url = proxy_url
        self.headers = []

    @tornado.gen.coroutine
    def get(self, url=None, ts=None):
        if ts is None:
            ts = time.time()
        url = url or self.proxy_url
        if url is None:
            if self.request.uri.startswith('/'):
                url = self.request.uri[1:]
            else:
                url = self.request.uri

        if "?ts=" not in url:
            url += "?ts=" + str(ts)

        client = tornado.httpclient.AsyncHTTPClient()


        if "?ts=" not in url:
            url += "?ts=" + str(self.request.query_arguments['ts'][0])

        self.add_header("Content-type", "application/octet-stream")
        self.add_header("Connection", "keep-alive")
        self.add_header("Cache-Control ", 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0')

        request = tornado.httpclient.HTTPRequest(
            url=url,
            # header_callback=self._handle_headers,
            streaming_callback=self._handle_chunk,
            # headers=
            # request_timeout=3600.0
        )

        try:
            yield client.fetch(request, raise_error=False)
        except:
            # self.set_status(response.code)
            self.finish()
    #
    # def _handle_headers(self, headers):
    #     self.headers.append(headers)
    #     try:
    #         self._start_line = tornado.httputil.parse_response_start_line(headers)
    #     except tornado.httputil.HTTPInputError:
    #         pass
    #
    def _handle_chunk(self, chunk):
        # print("handle_chunk: " + str(self._start_line.code))
        # if self._start_line.code == 200:
        self.write(chunk)
        self.flush()


class ProxyHandler(tornado.web.RequestHandler):
    def initialize(self, proxy_url="/", **kwargs):
        super(ProxyHandler, self).initialize(**kwargs)
        self.proxy_url = proxy_url

    @tornado.gen.coroutine
    def get(self, url=None):
        """Get the login page"""
        url = url or self.proxy_url
        if url is None:
            if self.request.uri.startswith("/"):
                url = self.request.uri[1:]
            else:
                url = self.request.uri

        req = tornado.httpclient.HTTPRequest(url)
        client = tornado.httpclient.AsyncHTTPClient()
        response = yield client.fetch(req, raise_error=False)

        # websocket upgrade
        if response.code == 599:
            self.set_status(200)  # switching protocols
            return

        self.set_status(response.code)
        if response.code != 200:
            self.finish()
        else:
            if response.body:
                for header in response.headers:
                    if header.lower() == "content-length":
                        self.set_header(
                            header,
                            str(
                                max(
                                    len(response.body),
                                    int(response.headers.get(header)),
                                )
                            ),
                        )
                    else:
                        if header.lower() != "transfer-encoding":
                            self.set_header(header, response.headers.get(header))

            self.write(response.body)
            self.finish()

class StatusWebServer:

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("tg_dj.web")
        self.logger.setLevel(getattr(logging, self.config.get("web_server", "verbosity", fallback="warning").upper()))

        settings = {
            "static_path": os.path.join(os.path.dirname(__file__), "static"),
            "debug": False,
        }

        self.stream_url = self.config.get("web_server", "stream_url", fallback='/stream')
        self.ws_url = self.config.get("web_server", "ws_url", fallback="auto")

        app = tornado.web.Application([
            (r"/", MainHandler, dict(server=self)),
            (r'/ws', WebSocketHandler, dict(server=self)),
            (self.stream_url, StreamProxyHandler, dict(proxy_url="http://127.0.0.1:1233/stream")),
            (r'/metrics', ProxyHandler, dict(proxy_url="http://127.0.0.1:8910/")),
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


def get_proxy(url):
    url_parsed = urlparse(url, scheme='http')
    proxy_key = '%s_proxy' % url_parsed.scheme
    return os.environ.get(proxy_key)


def parse_proxy(proxy):
    proxy_parsed = urlparse(proxy, scheme='http')
    return proxy_parsed.hostname, proxy_parsed.port


def fetch_request(url, callback, **kwargs):
    proxy = get_proxy(url)
    if proxy:
        logger.debug('Forward request via upstream proxy %s', proxy)
        tornado.httpclient.AsyncHTTPClient.configure(
            'tornado.curl_httpclient.CurlAsyncHTTPClient')
        host, port = parse_proxy(proxy)
        kwargs['proxy_host'] = host
        kwargs['proxy_port'] = port

    req = tornado.httpclient.HTTPRequest(url, **kwargs)
    client = tornado.httpclient.AsyncHTTPClient()
    client.fetch(req, callback, raise_error=False)


class ProxyHandler2(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'POST', 'CONNECT']

    def compute_etag(self):
        return None  # disable tornado Etag

    @tornado.web.asynchronous
    def get(self):
        logger.debug('Handle %s request to %s', self.request.method,
                     self.request.uri)

        def handle_response(response):
            if (response.error and not
            isinstance(response.error, tornado.httpclient.HTTPError)):
                self.set_status(500)
                self.write('Internal server error:\n' + str(response.error))
            else:
                self.set_status(response.code, response.reason)
                self._headers = tornado.httputil.HTTPHeaders()  # clear tornado default header

                for header, v in response.headers.get_all():
                    if header not in ('Content-Length', 'Transfer-Encoding', 'Content-Encoding', 'Connection'):
                        self.add_header(header, v)  # some header appear multiple times, eg 'Set-Cookie'

                if response.body:
                    self.set_header('Content-Length', len(response.body))
                    self.write(response.body)
            self.finish()

        body = self.request.body
        if not body:
            body = None
        try:
            if 'Proxy-Connection' in self.request.headers:
                del self.request.headers['Proxy-Connection']
            fetch_request(
                self.request.uri, handle_response,
                method=self.request.method, body=body,
                headers=self.request.headers, follow_redirects=False,
                allow_nonstandard_methods=True)
        except tornado.httpclient.HTTPError as e:
            if hasattr(e, 'response') and e.response:
                handle_response(e.response)
            else:
                self.set_status(500)
                self.write('Internal server error:\n' + str(e))
                self.finish()

    @tornado.web.asynchronous
    def post(self):
        return self.get()

    @tornado.web.asynchronous
    def connect(self):
        logger.debug('Start CONNECT to %s', self.request.uri)
        host, port = self.request.uri.split(':')
        client = self.request.connection.stream

        def read_from_client(data):
            upstream.write(data)

        def read_from_upstream(data):
            client.write(data)

        def client_close(data=None):
            if upstream.closed():
                return
            if data:
                upstream.write(data)
            upstream.close()

        def upstream_close(data=None):
            if client.closed():
                return
            if data:
                client.write(data)
            client.close()

        def start_tunnel():
            logger.debug('CONNECT tunnel established to %s', self.request.uri)
            client.read_until_close(client_close, read_from_client)
            upstream.read_until_close(upstream_close, read_from_upstream)
            client.write(b'HTTP/1.0 200 Connection established\r\n\r\n')

        def on_proxy_response(data=None):
            if data:
                first_line = data.splitlines()[0]
                http_v, status, text = first_line.split(None, 2)
                if int(status) == 200:
                    logger.debug('Connected to upstream proxy %s', proxy)
                    start_tunnel()
                    return

            self.set_status(500)
            self.finish()

        def start_proxy_tunnel():
            upstream.write('CONNECT %s HTTP/1.1\r\n' % self.request.uri)
            upstream.write('Host: %s\r\n' % self.request.uri)
            upstream.write('Proxy-Connection: Keep-Alive\r\n\r\n')
            upstream.read_until('\r\n\r\n', on_proxy_response)

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        upstream = tornado.iostream.IOStream(s)

        proxy = get_proxy(self.request.uri)
        if proxy:
            proxy_host, proxy_port = parse_proxy(proxy)
            upstream.connect((proxy_host, proxy_port), start_proxy_tunnel)
        else:
            upstream.connect((host, int(port)), start_tunnel)
