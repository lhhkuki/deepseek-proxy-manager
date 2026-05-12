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
        self._lock = threading.Lock()
        self._shutdown_thread = None

    def start(self, port):
        # Wait for any in-progress shutdown to complete
        if self._shutdown_thread and self._shutdown_thread.is_alive():
            self._shutdown_thread.join(timeout=3)
        self._shutdown_thread = None
        from .config import is_already_running
        if is_already_running(port):
            raise RuntimeError(f"Port {port} is already in use")
        with self._lock:
            if self.running:
                return
            try:
                self.server = ThreadingHTTPServer(
                    ("127.0.0.1", port), self._handler_class)
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
                self.running = True
                LOG_QUEUE.put_nowait(f"Proxy started on port {port}")
            except Exception as e:
                LOG_QUEUE.put_nowait(f"ERROR: {e}")
                raise

    def _run(self):
        self.server.serve_forever()

    def stop(self):
        with self._lock:
            if not self.running:
                return
            self.running = False
            srv = self.server
            self.server = None
        if srv:
            def _shutdown():
                try:
                    srv.shutdown()
                except Exception:
                    pass
                try:
                    srv.server_close()
                except Exception:
                    pass
            self._shutdown_thread = threading.Thread(target=_shutdown, daemon=True)
            self._shutdown_thread.start()
        LOG_QUEUE.put_nowait("Proxy stopped")

    def is_running(self):
        return self.running
