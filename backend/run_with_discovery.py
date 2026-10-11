"""LeafLens FastAPI launcher + zero-dependency LAN auto-discovery.

Run in the existing backend directory:
    python run_with_discovery.py

This adds a UDP discovery responder and runs the EXISTING app.py unchanged.
The IoT data POST, AI model, Supabase logic and web UI are untouched.
"""
from __future__ import annotations

import logging
import socket
import threading
from pathlib import Path

DISCOVERY_PORT = 42177
API_PORT = 8000
PREFIX_REQUEST = "LEAFLENS_FIND_V1|"
PREFIX_RESPONSE = "LEAFLENS_HERE_V1|"
LOG = logging.getLogger("leaflens.discovery")


class DiscoveryResponder:
    def __init__(self, host: str = "0.0.0.0", port: int = DISCOVERY_PORT):
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.host, self.port))
            sock.settimeout(0.4)
        except Exception:
            sock.close()
            raise
        self._sock = sock
        self._stopped.clear()
        self._thread = threading.Thread(target=self._serve, name="leaflens-udp-discovery", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stopped.is_set():
            try:
                payload, sender = self._sock.recvfrom(128)
                message = payload.decode("ascii", errors="ignore")
                if not message.startswith(PREFIX_REQUEST):
                    continue
                nonce = message[len(PREFIX_REQUEST):]
                if not nonce or len(nonce) > 16 or not all(c in "0123456789abcdefABCDEF" for c in nonce):
                    continue
                response = f"{PREFIX_RESPONSE}{nonce}|{API_PORT}".encode("ascii")
                self._sock.sendto(response, sender)
                LOG.info("Found by ESP32 from %s", sender[0])
            except socket.timeout:
                continue
            except OSError:
                if not self._stopped.is_set():
                    LOG.exception("UDP discovery socket error")
                break
            except Exception:
                LOG.exception("Unexpected UDP discovery issue")

    def stop(self) -> None:
        self._stopped.set()
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None


def main() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    # Same backend environment and import path as: uvicorn app:app
    backend_dir = Path(__file__).resolve().parent
    import os
    os.chdir(backend_dir)

    responder = DiscoveryResponder()
    try:
        responder.start()
    except OSError as exc:
        print(f"[LeafLens] UDP discovery port {DISCOVERY_PORT} unavailable: {exc}")
        print("[LeafLens] Backend will still start. ESP32 can use local subnet search fallback.")
    else:
        print(f"[LeafLens] UDP auto-discovery ready on port {DISCOVERY_PORT} (IPv4)", flush=True)

    print(f"[LeafLens] Starting existing FastAPI app at 0.0.0.0:{API_PORT}", flush=True)
    print("[LeafLens] Keep this terminal open while using the dashboard.", flush=True)
    try:
        uvicorn.run("app:app", host="0.0.0.0", port=API_PORT, workers=1, reload=False)
    finally:
        responder.stop()


if __name__ == "__main__":
    main()
