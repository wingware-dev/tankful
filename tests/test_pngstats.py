import os
import shutil
import struct
import tempfile
import unittest
import zlib

from tankful import pngstats


def write_png(path, width, height, pixel, channels=3, filters=(0,)):
  """Write an 8-bit PNG; pixel(x, y) gives a tuple of channel values.
  Rows cycle through filters, each encoded properly."""
  color = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
  raw, prev = b'', bytes(width * channels)
  for y in range(height):
    line = bytes(v for x in range(width) for v in pixel(x, y))
    ftype = filters[y % len(filters)]
    raw += bytes([ftype]) + _filter(ftype, line, prev, channels)
    prev = line

  def chunk(kind, body):
    return (struct.pack('>I', len(body)) + kind + body +
            struct.pack('>I', zlib.crc32(kind + body)))
  with open(path, 'wb') as f:
    f.write(b'\x89PNG\r\n\x1a\n')
    f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, color,
                                       0, 0, 0)))
    f.write(chunk(b'IDAT', zlib.compress(raw)))
    f.write(chunk(b'IEND', b''))


def _filter(ftype, line, prev, bpp):
  out = bytearray(len(line))
  for i, v in enumerate(line):
    a = line[i - bpp] if i >= bpp else 0
    b = prev[i]
    c = prev[i - bpp] if i >= bpp else 0
    if ftype == 0:
      pred = 0
    elif ftype == 1:
      pred = a
    elif ftype == 2:
      pred = b
    elif ftype == 3:
      pred = (a + b) >> 1
    else:
      p = a + b - c
      pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
      pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
    out[i] = (v - pred) & 0xff
  return bytes(out)


class PngStatsTests(unittest.TestCase):

  def setUp(self):
    self.dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.dir)

  def path(self, name):
    return os.path.join(self.dir, name)

  def test_all_filters_decode(self):
    def pixel(x, y):
      return ((x * 7 + y) % 256, (y * 13) % 256, (x * y) % 256, 255)
    p = self.path('f.png')
    write_png(p, 9, 10, pixel, channels=4, filters=(0, 1, 2, 3, 4))
    width, height, channels, rows = pngstats.read_png(p)
    self.assertEqual((width, height, channels), (9, 10, 4))
    for y in range(height):
      want = bytes(v for x in range(width) for v in pixel(x, y))
      self.assertEqual(rows[y], want, 'row %d' % y)

  def test_black_and_lit(self):
    black = self.path('black.png')
    write_png(black, 16, 16, lambda x, y: (0, 0, 0))
    summary = pngstats.stats(black, step=1)
    self.assertEqual(summary['max'], 0)
    self.assertTrue(pngstats.is_black(summary))

    lit = self.path('lit.png')
    write_png(lit, 16, 16, lambda x, y: (60, 70, 80) if x > 3 else (0, 0, 0))
    summary = pngstats.stats(lit, step=1)
    self.assertEqual(summary['width'], 16)
    self.assertEqual(summary['max'], 70)
    self.assertAlmostEqual(summary['lit_fraction'], 0.75)
    self.assertFalse(pngstats.is_black(summary))

  def test_gray(self):
    p = self.path('g.png')
    write_png(p, 4, 4, lambda x, y: (200,), channels=1)
    self.assertEqual(pngstats.stats(p, step=1)['mean'], 200)

  def test_not_a_png(self):
    p = self.path('x.png')
    with open(p, 'wb') as f:
      f.write(b'GIF89a')
    with self.assertRaises(pngstats.PngError):
      pngstats.read_png(p)


if __name__ == '__main__':
  unittest.main()
