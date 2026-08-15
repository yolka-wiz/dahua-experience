#!/usr/bin/env python3
"""Minimal CDP client over websocket with a single reader thread + queue.

Usage:
    from cdp import CDP
    c = CDP("ws://127.0.0.1:9222/devtools/page/<TARGET>")
    c.cmd("Runtime.evaluate", {"expression": "1+1", "returnByValue": True})
    c.wait_event("Network.requestWillBeSent", timeout=10)
"""
import json
import queue
import threading
from websocket import create_connection


class CDP:
    def __init__(self, url, timeout=10):
        self.ws = create_connection(url, timeout=timeout, origin="http://localhost:9222")
        self._id = 0
        self._pending = {}
        self._events = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        while True:
            try:
                msg = json.loads(self.ws.recv())
            except Exception:
                return
            if "id" in msg:
                if msg["id"] in self._pending:
                    self._pending[msg["id"]].put(msg)
            else:
                self._events.put(msg)

    def cmd(self, method, params=None, timeout=15):
        self._id += 1
        mid = self._id
        q = queue.Queue()
        self._pending[mid] = q
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        try:
            msg = q.get(timeout=timeout)
        finally:
            self._pending.pop(mid, None)
        if "error" in msg:
            raise RuntimeError(f"CDP error {msg['error']}")
        return msg.get("result", {})

    def eval(self, expression, timeout=15):
        r = self.cmd("Runtime.evaluate", {"expression": expression, "returnByValue": True}, timeout=timeout)
        return r.get("result", {}).get("value")

    def wait_event(self, method, timeout=15):
        return self._events.get(timeout=timeout)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else None
    if not url:
        import urllib.request
        targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json"))
        url = "ws://127.0.0.1:9222/devtools/page/" + next(
            t["id"] for t in targets if t["type"] == "page"
        )
    c = CDP(url)
    print("title:", c.eval("document.title"))
    c.close()
