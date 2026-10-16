"""Find UPBGE, rebuild the scene when stale, and start the player.

Used by run_tankful.py (under the venv's Python) and tools/harness.py.
Nothing here runs inside the game engine.
"""

import collections
import os
import shutil
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(ROOT, 'build', 'tankful.blend')
BUILD_SCRIPT = os.path.join(ROOT, 'tools', 'build_scene.py')
SCENE_SOURCES = (BUILD_SCRIPT,)
WINDOW = (1280, 720)

# Where and how big -w first makes the offscreen window.  The player
# rejects negative coordinates and macOS pulls titled windows back onto a
# screen, so the window starts tiny in a far corner, and the game then
# makes it borderless, moves it off the desktop and gives it its real
# size; see tankful/game/offscreen_*.py and docs/harness.md.
OFFSCREEN_POS = (20000, 20000)
OFFSCREEN_START_SIZE = (320, 200)

DOCKER_IMAGE = 'tankful-upbge'
DOCKER_ROOT = '/tankful'

BACKENDS = ('window', 'offscreen', 'xvfb', 'docker')

Upbge = collections.namedtuple('Upbge', 'blender player')


class LaunchError(RuntimeError):
  pass


def platform_key(platform=None):
  platform = platform or sys.platform
  if platform == 'darwin':
    return 'macos'
  if platform.startswith('win'):
    return 'windows'
  return 'linux'


def _layout(directory, plat, exists):
  """The Upbge in directory itself, laid out as plat ships it, or None."""
  if plat == 'macos':
    if directory.endswith('.app'):
      directory = os.path.dirname(directory)
    blender = os.path.join(directory, 'Blender.app', 'Contents', 'MacOS',
                           'Blender')
    player = os.path.join(directory, 'Blenderplayer.app', 'Contents',
                          'MacOS', 'Blenderplayer')
  elif plat == 'windows':
    blender = os.path.join(directory, 'blender.exe')
    player = os.path.join(directory, 'blenderplayer.exe')
  else:
    blender = os.path.join(directory, 'blender')
    player = os.path.join(directory, 'blenderplayer')
  if exists(player):
    return Upbge(blender if exists(blender) else None, player)
  return None


def _search(directory, plat, exists, listdir):
  """Look in directory and then each of its subdirectories."""
  found = _layout(directory, plat, exists)
  if found:
    return found
  try:
    names = sorted(listdir(directory))
  except OSError:
    return None
  for name in names:
    if name.endswith('.app'):
      continue
    found = _layout(os.path.join(directory, name), plat, exists)
    if found:
      return found
  return None


def candidate_dirs(env, root, plat):
  """Where to look for UPBGE, in order."""
  dirs = []
  override = env.get('TANKFUL_UPBGE')
  if override:
    # A binary as well as a directory is accepted
    if os.path.basename(override).lower() in (
        'blender', 'blender.exe', 'blenderplayer', 'blenderplayer.exe'):
      override = os.path.dirname(override)
    if plat == 'macos' and '.app' + os.sep in override + os.sep:
      override = override[:(override + os.sep).index('.app' + os.sep) + 4]
    dirs.append(override)
  dirs.append(os.path.join(root, 'vendor', 'upbge', plat))
  home = env.get('HOME') or env.get('USERPROFILE') or ''
  if plat == 'macos':
    dirs += ['/Applications/UPBGE', os.path.join(home, 'Applications', 'UPBGE')]
  elif plat == 'windows':
    for var in ('ProgramFiles', 'LOCALAPPDATA'):
      if env.get(var):
        dirs.append(os.path.join(env[var], 'UPBGE'))
  else:
    dirs += ['/opt/upbge', os.path.join(home, 'upbge')]
  return dirs


def find_upbge(env=None, root=ROOT, platform=None, exists=os.path.exists,
               listdir=os.listdir):
  """Return the Upbge to use; LaunchError if there is none.

  Looks at $TANKFUL_UPBGE first (an install directory, app bundle or
  binary), then vendor/upbge/<platform>/ as tools/fetch_upbge.py leaves
  it, then the usual install places.
  """
  env = os.environ if env is None else env
  plat = platform_key(platform)
  dirs = candidate_dirs(env, root, plat)
  for i, directory in enumerate(dirs):
    found = _search(directory, plat, exists, listdir)
    if found:
      return found
    if i == 0 and env.get('TANKFUL_UPBGE'):
      raise LaunchError('TANKFUL_UPBGE=%s has no UPBGE player'
                        % env['TANKFUL_UPBGE'])
  raise LaunchError('UPBGE not found; run "python tools/fetch_upbge.py" or '
                    'set TANKFUL_UPBGE.  Looked in:\n  ' + '\n  '.join(dirs))


def scene_is_stale(blend=BLEND, sources=SCENE_SOURCES, getmtime=os.path.getmtime):
  try:
    built = getmtime(blend)
  except OSError:
    return True
  return any(getmtime(src) > built for src in sources)


def build_scene_command(upbge, output=BLEND):
  if not upbge.blender:
    raise LaunchError('UPBGE install has no blender binary to build the scene')
  return [upbge.blender, '-b', '--factory-startup', '--python-exit-code', '1',
          '--python', BUILD_SCRIPT, '--', '--output', output]


def build_scene(upbge, force=False, output=BLEND):
  """Rebuild the scene if forced or stale; return the exit code."""
  if not force and not scene_is_stale(output):
    return 0
  print('Building %s' % os.path.relpath(output, ROOT), flush=True)
  return subprocess.call(build_scene_command(upbge, output))


def player_command(upbge, backend, blend=BLEND, window=WINDOW, extra=()):
  """The argv that starts the player for one of BACKENDS (but docker)."""
  if backend == 'offscreen':
    geometry = OFFSCREEN_START_SIZE + OFFSCREEN_POS
  else:
    geometry = (window[0], window[1])
  cmd = [upbge.player, '-w'] + [str(v) for v in geometry] + [blend]
  if extra:
    cmd += ['-'] + list(extra)
  return cmd


def game_env(base, root=ROOT, harness_port=None, harness_host=None,
             debug=False, offscreen=False, window=WINDOW):
  env = dict(base)
  env['TANKFUL_ROOT'] = root
  if offscreen:
    # The game moves its own window off the desktop and sizes it
    # (tankful.game.main)
    env['TANKFUL_OFFSCREEN'] = '%dx%d' % window
  if harness_port is not None:
    env['TANKFUL_HARNESS_PORT'] = str(harness_port)
  if harness_host:
    env['TANKFUL_HARNESS_HOST'] = harness_host
  if debug:
    env['TANKFUL_DEBUG'] = '1'
  return env


def free_display(exists=os.path.exists):
  for n in range(99, 200):
    if not exists('/tmp/.X11-unix/X%d' % n) and not exists('/tmp/.X%d-lock' % n):
      return n
  raise LaunchError('no free X display number')


def start_xvfb(window=WINDOW):
  """Start Xvfb on a free display; return (process, DISPLAY value)."""
  xvfb = shutil.which('Xvfb')
  if not xvfb:
    raise LaunchError('Xvfb not found (install the xvfb package)')
  n = free_display()
  proc = subprocess.Popen([xvfb, ':%d' % n, '-screen', '0',
                           '%dx%dx24' % (window[0], window[1]), '-nolisten',
                           'tcp'])
  for _ in range(50):
    if os.path.exists('/tmp/.X11-unix/X%d' % n):
      return proc, ':%d' % n
    if proc.poll() is not None:
      raise LaunchError('Xvfb exited with code %d' % proc.returncode)
    time.sleep(0.1)
  proc.kill()
  raise LaunchError('Xvfb did not start')


def ensure_docker_image(root=ROOT, image=DOCKER_IMAGE):
  """Build the container image unless it exists; return the exit code."""
  if not shutil.which('docker'):
    raise LaunchError('docker not found')
  have = subprocess.run(['docker', 'image', 'inspect', image],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  if have.returncode == 0:
    return 0
  print('Building docker image %s' % image, flush=True)
  return subprocess.call(['docker', 'build', '--platform', 'linux/amd64',
                          '-t', image, os.path.join(root, 'tools', 'docker')])


def docker_command(root, argv, harness_port=None, image=DOCKER_IMAGE):
  """docker run argv that runs run_tankful.py with the xvfb backend inside
  the Linux container, with the project mounted at DOCKER_ROOT."""
  cmd = ['docker', 'run', '--rm', '--platform', 'linux/amd64',
         '-v', '%s:%s' % (root, DOCKER_ROOT), '-w', DOCKER_ROOT,
         '-e', 'TANKFUL_HARNESS_HOST=0.0.0.0']
  if harness_port is not None:
    cmd += ['-p', '127.0.0.1:%d:%d' % (harness_port, harness_port)]
  cmd += [image, 'python3', DOCKER_ROOT + '/run_tankful.py',
          '--backend', 'xvfb'] + list(argv)
  return cmd


def pick_port():
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(('127.0.0.1', 0))
    return s.getsockname()[1]
