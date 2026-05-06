"""Proxy server that runs in a background thread."""

import threading
from http.server import HTTPServer
from socketserver import ThreadingMixIn

from .config import LOG_QUEUE


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class ProxyServer:
    def __init__(self, handler_class):
        self.server = None
        self.thread = None
        self.running = False
        self._handler_class = handler_class

    def start(self, port):
        if self.running:
            return
        try:
            self.server = ThreadingHTTPServer(
                ("127.0.0.1", port), self._handler_class)
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            self.running = True
            LOG_QUEUE.put(f"Proxy started on port {port}")
        except Exception as e:
            LOG_QUEUE.put(f"ERROR: {e}")
            raise

    def _run(self):
        self.server.serve_forever()

    def stop(self):
        if not self.running:
            return
        self.running = False
        srv = self.server

        def _shutdown():
            try:
                srv.shutdown()
            except Exception:
                pass
        threading.Thread(target=_shutdown, daemon=True).start()
        LOG_QUEUE.put("Proxy stopped")

    def is_running(self):
        return self.running
