"""Read a PNG with the standard library and summarize its pixels.

Enough for harness checks ("is this screenshot black?"): 8-bit
grayscale, RGB, gray+alpha and RGBA, not interlaced.
"""

import struct
import zlib

_CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
_SIGNATURE = b'\x89PNG\r\n\x1a\n'


class PngError(ValueError):
  pass


class PngTruncated(PngError):
  """The file ends early: perhaps it is still being written."""


def read_png(path):
  """Return (width, height, channels, rows), rows being bytes per row."""
  with open(path, 'rb') as f:
    data = f.read()
  if data[:8] != _SIGNATURE[:len(data)]:
    raise PngError('%s is not a PNG' % path)
  if len(data) < 8:
    raise PngTruncated('%s is too short for a PNG' % path)
  pos, idat, header, ended = 8, [], None, False
  while pos < len(data):
    if pos + 12 > len(data):
      break
    length, kind = struct.unpack('>I4s', data[pos:pos + 8])
    if pos + 12 + length > len(data):
      break
    body = data[pos + 8:pos + 8 + length]
    pos += 12 + length
    if kind == b'IHDR':
      header = struct.unpack('>IIBBBBB', body)
    elif kind == b'IDAT':
      idat.append(body)
    elif kind == b'IEND':
      ended = True
      break
  if not ended:
    raise PngTruncated('%s ends before its IEND chunk' % path)
  if header is None:
    raise PngError('%s has no IHDR' % path)
  width, height, depth, color, _, _, interlace = header
  if depth != 8 or color not in _CHANNELS or interlace:
    raise PngError('%s: unsupported PNG (depth %d, color type %d, '
                   'interlace %d)' % (path, depth, color, interlace))
  channels = _CHANNELS[color]
  raw = zlib.decompress(b''.join(idat))
  return width, height, channels, _unfilter(raw, width, height, channels)


def _unfilter(raw, width, height, bpp):
  stride = width * bpp
  rows, prev, pos = [], bytearray(stride), 0
  for _ in range(height):
    ftype = raw[pos]
    line = bytearray(raw[pos + 1:pos + 1 + stride])
    pos += 1 + stride
    if ftype == 1:
      for i in range(bpp, stride):
        line[i] = (line[i] + line[i - bpp]) & 0xff
    elif ftype == 2:
      for i in range(stride):
        line[i] = (line[i] + prev[i]) & 0xff
    elif ftype == 3:
      for i in range(stride):
        left = line[i - bpp] if i >= bpp else 0
        line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xff
    elif ftype == 4:
      for i in range(stride):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
        line[i] = (line[i] + pred) & 0xff
    elif ftype != 0:
      raise PngError('bad PNG filter type %d' % ftype)
    rows.append(bytes(line))
    prev = line
  return rows


def stats(path, step=4):
  """Summarize a PNG: size, mean and max brightness (0-255) over sampled
  pixels, and the fraction that are not near black."""
  width, height, channels, rows = read_png(path)
  color = 1 if channels < 3 else 3
  total = peak = lit = count = 0
  for y in range(0, height, step):
    row = rows[y]
    for x in range(0, width, step):
      px = row[x * channels:x * channels + color]
      value = sum(px) // color
      total += value
      peak = max(peak, value)
      lit += value > 16
      count += 1
  count = count or 1
  return {'width': width, 'height': height, 'mean': round(total / count, 1),
          'max': peak, 'lit_fraction': round(lit / count, 3)}


def is_black(summary):
  return summary['max'] <= 16 or summary['lit_fraction'] < 0.01
