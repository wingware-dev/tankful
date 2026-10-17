"""Tile the screenshots in docs/shots/ into one labeled contact sheet.

Usage: python tools/contact_sheet.py [--output docs/contact-sheet.png]
                                     [--columns 4] [--font FILE]
                                     [SHOT.png ...]

The default is every PNG in docs/shots/, in name order (so by step),
each scaled to 320x180 with its file name under it.  It runs
ImageMagick's montage (`magick montage`, or `montage` for ImageMagick
6), which must be on PATH; the game and the tests don't need it.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS_DIR = os.path.join(ROOT, 'docs', 'shots')
OUTPUT = os.path.join(ROOT, 'docs', 'contact-sheet.png')
TILE = '320x180'
# Label fonts tried in turn: ImageMagick often has no default font set up
FONTS = ('/System/Library/Fonts/Supplemental/Arial.ttf',
         '/System/Library/Fonts/Helvetica.ttc',
         '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
         '/usr/share/fonts/TTF/DejaVuSans.ttf',
         r'C:\Windows\Fonts\arial.ttf')


def find_font(fonts=FONTS, exists=os.path.exists):
  return next((f for f in fonts if exists(f)), None)


def montage_command():
  """The argv prefix that runs ImageMagick's montage, or None."""
  if shutil.which('magick'):
    return ['magick', 'montage']
  if shutil.which('montage'):
    return ['montage']
  return None


def sheet_command(montage, shots, output, columns, font=None):
  cmd = list(montage)
  if font:
    cmd += ['-font', font]
  for shot in shots:
    cmd += ['-label', os.path.splitext(os.path.basename(shot))[0], shot]
  return cmd + ['-tile', '%dx' % columns, '-geometry', TILE + '+6+6',
                '-background', '#1b1f24', '-fill', '#e6e6e6',
                '-pointsize', '14', '-depth', '8', output]


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument('shots', nargs='*')
  parser.add_argument('--output', default=OUTPUT)
  parser.add_argument('--columns', type=int, default=4)
  parser.add_argument('--font', help='label font file (default: the first '
                                     'of FONTS found)')
  args = parser.parse_args(argv)

  shots = args.shots or sorted(glob.glob(os.path.join(SHOTS_DIR, '*.png')))
  if not shots:
    print('contact_sheet: no shots in %s' % SHOTS_DIR, file=sys.stderr)
    return 1
  montage = montage_command()
  if montage is None:
    print('contact_sheet: ImageMagick (magick or montage) not found',
          file=sys.stderr)
    return 1
  code = subprocess.call(sheet_command(montage, shots, args.output,
                                       args.columns,
                                       args.font or find_font()))
  if code == 0:
    print('contact_sheet: %d shots in %s' % (len(shots), args.output))
  return code


if __name__ == '__main__':
  sys.exit(main())
