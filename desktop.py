from __future__ import annotations

import atexit
import socket
import threading
import time

import webview
from werkzeug.serving import make_server

from app import app


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LocalServer(threading.Thread):
    def __init__(self, port: int):
        super().__init__(daemon=True)
        # HTTPServer가 시작 중 로컬 IP의 역방향 DNS를 조회하며 오래 멈추는
        # macOS 환경이 있어, 서버를 만드는 짧은 구간에만 로컬 이름으로 고정한다.
        original_getfqdn = socket.getfqdn
        socket.getfqdn = lambda name="": name or "localhost"
        try:
            self.server = make_server("127.0.0.1", port, app, threaded=True)
        finally:
            socket.getfqdn = original_getfqdn

    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()


def wait_until_ready(port: int, timeout: float = 10) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.15)
    return False


def main():
    port = free_port()
    server = LocalServer(port)
    server.start()
    atexit.register(server.stop)
    if not wait_until_ready(port):
        raise RuntimeError("프로그램 화면을 시작하지 못했습니다.")

    try:
        webview.create_window(
            "주도픽 조건검색",
            f"http://127.0.0.1:{port}",
            width=1360,
            height=900,
            min_size=(1040, 720),
            text_select=True,
        )
        webview.start(debug=False)
    finally:
        server.stop()


if __name__ == "__main__":
    main()
