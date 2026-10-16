"""Download UPBGE 0.50 into vendor/upbge/ and verify it.

Usage: python tools/fetch_upbge.py [--platform macos|linux|windows] [--force]

The default platform is the host's.  The archive is checked against the
size and sha256 GitHub publishes for the v0.50 release, then unpacked
into vendor/upbge/<platform>/.  On macOS the dmg is mounted read-only and
the app bundle is copied out.  vendor/ is git-ignored.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_DIR = os.path.join(ROOT, 'vendor', 'upbge')
DOWNLOAD_DIR = os.path.join(VENDOR_DIR, 'downloads')

VERSION = '0.50'
BASE_URL = 'https://github.com/UPBGE/upbge/releases/download/v0.50/'

# Sizes and digests as published on the GitHub release (2026-01-04)
ASSETS = {
  'macos': ('upbge-0.50-macos-arm64.dmg', 646710999,
            '4e505caf861a2408bdbdd54c8a6e35a2dcba7005aa44b0d75589fa7c45bdb18a'),
  'linux': ('upbge-0.50-linux-x64.tar.xz', 408374596,
            '21d535641cbab1751766737cd9958bae120cd161cf7f0c86f5d5df6dca868314'),
  'windows': ('upbge-0.50-windows-x64.7z', 293316768,
              'c59198cbe361afa9d78f515751d2a34f3df236f137393111fd8cc4b43e1dce71'),
}


def host_platform():
  if sys.platform == 'darwin':
    return 'macos'
  if sys.platform.startswith('win'):
    return 'windows'
  return 'linux'


def sha256_of(path):
  h = hashlib.sha256()
  with open(path, 'rb') as f:
    for chunk in iter(lambda: f.read(1 << 20), b''):
      h.update(chunk)
  return h.hexdigest()


def verify(path, size, digest):
  """Raise ValueError unless the file has the expected size and sha256."""
  actual = os.path.getsize(path)
  if actual != size:
    raise ValueError('%s: size %d, expected %d' % (path, actual, size))
  actual = sha256_of(path)
  if actual != digest:
    raise ValueError('%s: sha256 %s, expected %s' % (path, actual, digest))


def download(url, dest, size):
  part = dest + '.part'
  print('Downloading %s (%d MB)' % (url, size // 1000000))
  # Prefer curl, which uses the OS certificate store; python.org builds on
  # macOS often have no CA bundle until "Install Certificates" is run.  The
  # sha256 check afterwards guards the content either way.
  curl = shutil.which('curl')
  if curl:
    subprocess.run([curl, '-fL', '--retry', '3', '-o', part, url], check=True)
    os.replace(part, dest)
    return
  req =urllib.request.Request(url, headers={'User-Agent': 'tankful-fetch'})
  with urllib.request.urlopen(req) as resp, open(part, 'wb') as out:
    done = 0
    last = -1
    while True:
      chunk = resp.read(1 << 20)
      if not chunk:
        break
      out.write(chunk)
      done += len(chunk)
      pct = done * 100 // size
      if pct // 10 != last // 10:
        print('  %d%%' % pct, flush=True)
        last = pct
  os.replace(part, dest)


def extract_macos(archive, target):
  mount = tempfile.mkdtemp(prefix='upbge-dmg-')
  subprocess.run(['hdiutil', 'attach', '-nobrowse', '-readonly', '-noautoopen',
                  '-mountpoint', mount, archive], check=True,
                 stdout=subprocess.DEVNULL)
  try:
    apps = [n for n in os.listdir(mount) if n.endswith('.app')]
    if not apps:
      raise RuntimeError('No .app bundle in %s' % archive)
    os.makedirs(target, exist_ok=True)
    for app in apps:
      print('Copying %s' % app)
      # ditto keeps the bundle's symlinks, permissions and signature intact
      subprocess.run(['ditto', os.path.join(mount, app),
                      os.path.join(target, app)], check=True)
  finally:
    subprocess.run(['hdiutil', 'detach', mount], check=False,
                   stdout=subprocess.DEVNULL)
    os.rmdir(mount)


def extract_linux(archive, target):
  os.makedirs(target, exist_ok=True)
  with tarfile.open(archive) as tf:
    tf.extractall(target, filter='tar')


def extract_windows(archive, target):
  os.makedirs(target, exist_ok=True)
  seven = shutil.which('7z') or shutil.which('7za')
  if seven:
    cmd = [seven, 'x', '-y', '-o' + target, archive]
  else:
    # Windows 10+ tar.exe is bsdtar, which reads 7z
    cmd = ['tar', '-xf', archive, '-C', target]
  subprocess.run(cmd, check=True)


EXTRACTORS = {'macos': extract_macos, 'linux': extract_linux,
              'windows': extract_windows}


def fetch(platform, force=False):
  name, size, digest = ASSETS[platform]
  os.makedirs(DOWNLOAD_DIR, exist_ok=True)
  archive = os.path.join(DOWNLOAD_DIR, name)
  if os.path.exists(archive):
    try:
      verify(archive, size, digest)
      print('Already downloaded: %s' % archive)
    except ValueError as exc:
      print('Discarding bad download: %s' % exc)
      os.remove(archive)
  if not os.path.exists(archive):
    download(BASE_URL + name, archive, size)
    verify(archive, size, digest)
    print('Verified size and sha256')

  target = os.path.join(VENDOR_DIR, platform)
  if os.path.isdir(target):
    if not force:
      print('Already unpacked: %s (use --force to redo)' % target)
      return target
    shutil.rmtree(target)
  if os.path.isdir(target + '.tmp'):
    shutil.rmtree(target + '.tmp')
  EXTRACTORS[platform](archive, target + '.tmp')
  os.replace(target + '.tmp', target)
  print('Unpacked into %s' % target)
  return target


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument('--platform', choices=sorted(ASSETS),
                      default=host_platform())
  parser.add_argument('--force', action='store_true',
                      help='unpack again even if already unpacked')
  args = parser.parse_args(argv)
  fetch(args.platform, args.force)
  return 0


if __name__ == '__main__':
  sys.exit(main())
