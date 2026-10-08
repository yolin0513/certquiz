#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生 App 圖示（PNG，只用標準函式庫）：深藍底、白色勾號。用法：python scripts/make_icons.py"""
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BG = (31, 78, 121)
FG = (255, 255, 255)


def png(size):
    rows = []
    r = size * 0.18                                  # 圓角半徑
    # 勾號：兩段線，用點到線段的距離畫粗線
    a, b, c = (0.27, 0.53), (0.43, 0.69), (0.74, 0.34)
    w = 0.075

    def seg_dist(px, py, p, q):
        ax, ay = p; bx, by = q
        dx, dy = bx - ax, by - ay
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5

    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            cx = min(max(x, r), size - 1 - r); cy = min(max(y, r), size - 1 - r)
            inside = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
            if not inside:
                row += bytes((0, 0, 0, 0)); continue
            u, v = (x + .5) / size, (y + .5) / size
            on = min(seg_dist(u, v, a, b), seg_dist(u, v, b, c)) <= w / 2
            row += bytes((*(FG if on else BG), 255))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


if __name__ == "__main__":
    out = ROOT / "icons"
    out.mkdir(exist_ok=True)
    for s in (192, 512):
        (out / f"icon-{s}.png").write_bytes(png(s))
        print(f"icons/icon-{s}.png")
