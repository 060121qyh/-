# -*- coding: utf-8 -*-
"""生成 PWA 图标 PNG（纯标准库 zlib+struct，无第三方依赖）"""
import struct
import zlib
import math


def make_png(size):
    s = size / 512.0

    def S(v):
        return int(round(v * s))

    buf = bytearray(size * size * 4)

    def put(x, y, r, g, b, a=255):
        if 0 <= x < size and 0 <= y < size:
            i = (y * size + x) * 4
            da = a / 255.0
            buf[i] = int(r * da + buf[i] * (1 - da))
            buf[i + 1] = int(g * da + buf[i + 1] * (1 - da))
            buf[i + 2] = int(b * da + buf[i + 2] * (1 - da))
            buf[i + 3] = 255

    def dist2(x, y, cx, cy):
        return (x - cx) ** 2 + (y - cy) ** 2

    # 1) 背景：圆角矩形 + 对角渐变 (#0b1020 -> #1a2a5e)
    rad = S(96)
    c0 = (11, 16, 32)
    c1 = (26, 42, 94)
    for y in range(size):
        ty = y / size
        for x in range(size):
            if x < rad and y < rad and dist2(x, y, rad, rad) > rad * rad:
                continue
            if x >= size - rad and y < rad and dist2(x, y, size - rad - 1, rad) > rad * rad:
                continue
            if x < rad and y >= size - rad and dist2(x, y, rad, size - rad - 1) > rad * rad:
                continue
            if x >= size - rad and y >= size - rad and dist2(x, y, size - rad - 1, size - rad - 1) > rad * rad:
                continue
            blend = ((x / size) + ty) / 2
            r = int(c0[0] + (c1[0] - c0[0]) * blend)
            g = int(c0[1] + (c1[1] - c0[1]) * blend)
            b = int(c0[2] + (c1[2] - c0[2]) * blend)
            put(x, y, r, g, b)

    # 2) 蓝色圆环
    ccx, ccy, cr = S(256), S(205), S(128)
    for y in range(size):
        for x in range(size):
            d = math.sqrt(dist2(x, y, ccx, ccy))
            if abs(d - cr) <= S(8):
                put(x, y, 79, 124, 255, 217)

    # 3) "学"字简化笔画（白色）
    def dot(cx, cy, r):
        for y in range(size):
            for x in range(size):
                if dist2(x, y, S(cx), S(cy)) <= (S(r)) ** 2:
                    put(x, y, 245, 240, 232)

    def line(x1, y1, x2, y2, w):
        X1, Y1, X2, Y2 = S(x1), S(y1), S(x2), S(y2)
        ww = S(w)
        seg_len2 = (X2 - X1) ** 2 + (Y2 - Y1) ** 2
        if seg_len2 == 0:
            return
        for y in range(size):
            for x in range(size):
                t = ((x - X1) * (X2 - X1) + (y - Y1) * (Y2 - Y1)) / seg_len2
                t = max(0.0, min(1.0, t))
                px = X1 + t * (X2 - X1)
                py = Y1 + t * (Y2 - Y1)
                if (x - px) ** 2 + (y - py) ** 2 <= (ww / 2) ** 2:
                    put(x, y, 245, 240, 232)

    dot(150, 100, 15)
    dot(215, 88, 15)
    dot(282, 100, 15)
    line(155, 105, 268, 165, 16)   # 左撇
    line(140, 190, 372, 190, 20)   # 冖
    line(256, 200, 256, 300, 20)   # 竖钩
    line(256, 296, 292, 296, 18)   # 钩
    line(192, 250, 320, 250, 16)   # 横

    # 4) 朱砂弧线（下方半圆）
    acx, acy, ar = S(256), S(430), S(62)
    for y in range(size):
        for x in range(size):
            d = math.sqrt(dist2(x, y, acx, acy))
            if abs(d - ar) <= S(7) and y < acy:
                put(x, y, 192, 57, 43, 230)

    # PNG 编码
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(buf[y * size * 4:(y + 1) * size * 4]) for y in range(size))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    return png


if __name__ == "__main__":
    import glob
    for sz in (192, 512):
        p = make_png(sz)
        with open(f"static/icons/icon-{sz}.png", "wb") as f:
            f.write(p)
        print(f"icon-{sz}.png 生成 {len(p)} 字节")
    for f in glob.glob("static/icons/*.png"):
        with open(f, "rb") as fh:
            head = fh.read(8)
        assert head == b"\x89PNG\r\n\x1a\n", f
        print(f, "PNG 头校验通过")
