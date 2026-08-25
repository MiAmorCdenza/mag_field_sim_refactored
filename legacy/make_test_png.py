
import zlib, struct
W, H = 320, 160
def chunk(tag, data):
    c = struct.pack('>I', len(data)) + tag + data
    return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
rows = []
# top band: red-ish with diagonal white line; bottom: blue band; text-like blocks
import math
for y in range(H):
    row = bytearray()
    for x in range(W):
        if y < H // 2:
            r, g, b = 220, 30 + int(60 * x / W), 30
        else:
            r, g, b = 30, 30, 220
        if abs(x - y - 40) < 3 and y > 20 and y < 140:
            r, g, b = 255, 255, 255
        row += bytes((r, g, b))
    rows.append(bytes(row))
raw = b''.join(b'\x00' + r for r in rows)
png = (b'\x89PNG\r\n\x1a\n'
       + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
       + chunk(b'IDAT', zlib.compress(raw, 9))
       + chunk(b'IEND', b''))
open('test_vision.png', 'wb').write(png)
print('PNG written:', len(png), 'bytes')
