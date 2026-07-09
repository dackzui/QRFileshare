import socket
import threading
import time
import urllib.error
import urllib.request

import webview

from config import BASE_URL, HOST, PORT
from server import create_app


def _local_url() -> str:
    # Match common Google OAuth redirect URI registration (localhost)
    return f"http://localhost:{PORT}"


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _wait_for_server(url: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    health_url = f"{url.rstrip('/')}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.15)
    return False


def start_background_server() -> threading.Thread:
    app = create_app()

    def _run() -> None:
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True, name="qrfileshare-server")
    thread.start()
    return thread


def run_desktop() -> int:
    if not _port_available("127.0.0.1", PORT):
        print(
            f"Port {PORT} is already in use. Stop the other QRFileshare instance "
            f"or change PORT in .env."
        )
        return 1

    start_background_server()
    app_url = _local_url()

    if not _wait_for_server(app_url):
        print("QRFileshare could not start the local server.")
        return 1

    window = webview.create_window(
        "QRFileshare",
        app_url,
        width=1200,
        height=820,
        min_size=(900, 640),
        text_select=True,
    )
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.start(debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_desktop())
