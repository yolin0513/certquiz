#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本機靜態伺服器（測試用）：只綁 127.0.0.1、多執行緒。
用法：python scripts/serve.py <根目錄> [port，0＝隨機]
啟動後第一行印出「SERVING <port>」給呼叫端讀。"""
import functools
import http.server
import sys


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
                      ".webmanifest": "application/manifest+json"}

    def log_message(self, fmt, *args):
        pass


def main():
    root = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=root))
    print(f"SERVING {srv.server_address[1]}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
