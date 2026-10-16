"""Find UPBGE, rebuild the scene when stale, and start the player.

Used by run_tankful.py (under the venv's Python) and tools/harness.py.
Nothing here runs inside the game engine.
"""

import collections
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time

from tankful.sim import species

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = os.path.join(ROOT, 'build', 'tankful.blend')
BUILD_SCRIPT = os.path.join(ROOT, 'tools', 'build_scene.py')


def species_sources(names=None):
  """Each present species' model builder and sim module
  (tankful.sim.species.present): the model takes its size from the sim,
  and may sit where the sim starts it.  A species whose modules are
  written later joins the sources then, newer than the scene, so the
  scene rebuilds."""
  out = []
  for name in species.present(names):
    out.append(species.model_path(name))
    out.append(species.sim_path(name))
  return tuple(out)


SCENE_SOURCES = (BUILD_SCRIPT,
                 os.path.join(ROOT, 'tools', 'scene_env.py'),
                 os.path.join(ROOT, 'tools', 'scene_fish.py'),
                 os.path.join(ROOT, 'tankful', 'sim', 'environment.py'),
                 os.path.join(ROOT, 'tankful', 'sim', 'bubbles.py'),
                 os.path.join(ROOT, 'tankful', 'sim', 'species',
                              '__init__.py'),
                 os.path.join(ROOT, 'tankful', 'sim', 'species', 'base.py'),
                 ) + species_sources()
WINDOW = (1280, 720)
# The player rejects windows smaller than its usage example's 320x200
MIN_WINDOW = (320, 200)

# Where and how big -w first makes the offscreen window.  The player
# rejects negative coordinates and macOS pulls titled windows back onto a
# screen, so the window starts tiny in a far corner, and the game then
# makes it borderless, moves it off the desktop and gives it its real
# size; see tankful/game/offscreen_*.py and docs/harness.md.
OFFSCREEN_POS = (20000, 20000)
OFFSCREEN_START_SIZE = (320, 200)

DOCKER_IMAGE = 'tankful-upbge'
DOCKER_ROOT = '/tankful'
# Image label holding dockerfile_digest(), so a changed Dockerfile rebuilds
DOCKER_LABEL = 'tankful.dockerfile'
# Mesa's shader cache, kept in the (git-ignored) build/ directory of the
# mounted project: compiling EEVEE's shaders on llvmpipe under emulation
# is most of the container's startup time
DOCKER_SHADER_CACHE = DOCKER_ROOT + '/build/docker-cache/mesa'

BACKENDS = ('window', 'offscreen', 'xvfb', 'docker')

Upbge = collections.namedtuple('Upbge', 'blender player')


class LaunchError(RuntimeError):
  pass


def window_size(env=None):
  """The game window size: $TANKFUL_WINDOW as WIDTHxHEIGHT, else WINDOW."""
  env = os.environ if env is None else env
  value = env.get('TANKFUL_WINDOW')
  if not value:
    return WINDOW
  try:
    w, h = (int(v) for v in value.lower().split('x'))
  except ValueError:
    raise LaunchError('TANKFUL_WINDOW=%s: expected WIDTHxHEIGHT, like 640x360'
                      % value)
  if w < MIN_WINDOW[0] or h < MIN_WINDOW[1]:
    raise LaunchError('TANKFUL_WINDOW=%s: the player needs at least %dx%d'
                      % ((value,) + MIN_WINDOW))
  return (w, h)


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


def player_command(upbge, backend, blend=BLEND, window=None, extra=()):
  """The argv that starts the player for one of BACKENDS (but docker)."""
  if backend == 'offscreen':
    geometry = OFFSCREEN_START_SIZE + OFFSCREEN_POS
  else:
    geometry = window or window_size()
  cmd = [upbge.player, '-w'] + [str(v) for v in geometry] + [blend]
  if extra:
    cmd += ['-'] + list(extra)
  return cmd


def game_env(base, root=ROOT, harness_port=None, harness_host=None,
             debug=False, offscreen=False, window=None):
  env = dict(base)
  env['TANKFUL_ROOT'] = root
  if offscreen:
    # The game moves its own window off the desktop and sizes it
    # (tankful.game.main)
    env['TANKFUL_OFFSCREEN'] = '%dx%d' % (window or window_size(base))
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


def start_xvfb(window=None):
  """Start Xvfb on a free display; return (process, DISPLAY value)."""
  xvfb = shutil.which('Xvfb')
  if not xvfb:
    raise LaunchError('Xvfb not found (install the xvfb package)')
  window = window or window_size()
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


def dockerfile_digest(root=ROOT):
  """sha256 of tools/docker/Dockerfile, kept as a label on the image."""
  with open(os.path.join(root, 'tools', 'docker', 'Dockerfile'), 'rb') as f:
    return hashlib.sha256(f.read()).hexdigest()


def ensure_docker_image(root=ROOT, image=DOCKER_IMAGE):
  """Build the container image unless it exists and was built from the
  current Dockerfile; return the exit code."""
  if not shutil.which('docker'):
    raise LaunchError('docker not found')
  digest = dockerfile_digest(root)
  have = subprocess.run(['docker', 'image', 'inspect', '--format',
                         '{{index .Config.Labels "%s"}}' % DOCKER_LABEL, image],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        text=True)
  if have.returncode == 0 and have.stdout.strip() == digest:
    return 0
  print('Building docker image %s' % image, flush=True)
  return subprocess.call(['docker', 'build', '--platform', 'linux/amd64',
                          '--label', '%s=%s' % (DOCKER_LABEL, digest),
                          '-t', image, os.path.join(root, 'tools', 'docker')])


def docker_command(root, argv, harness_port=None, image=DOCKER_IMAGE,
                   env=None):
  """docker run argv that runs run_tankful.py with the xvfb backend inside
  the Linux container, with the project mounted at DOCKER_ROOT."""
  env = os.environ if env is None else env
  cmd = ['docker', 'run', '--rm', '--platform', 'linux/amd64',
         '-v', '%s:%s' % (root, DOCKER_ROOT), '-w', DOCKER_ROOT,
         '-e', 'TANKFUL_HARNESS_HOST=0.0.0.0',
         '-e', 'MESA_SHADER_CACHE_DIR=' + DOCKER_SHADER_CACHE]
  if env.get('TANKFUL_WINDOW'):
    cmd += ['-e', 'TANKFUL_WINDOW=' + env['TANKFUL_WINDOW']]
  if harness_port is not None:
    cmd += ['-p', '127.0.0.1:%d:%d' % (harness_port, harness_port)]
  cmd += [image, 'python3', DOCKER_ROOT + '/run_tankful.py',
          '--backend', 'xvfb'] + list(argv)
  return cmd


def pick_port():
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(('127.0.0.1', 0))
    return s.getsockname()[1]
