"""Per-frame entry from the scene's boot script (see tools/build_scene.py).

update(controller) runs once per logic tick.  The first call sets up the
App: the simulation, the input layer and, with TANKFUL_HARNESS_PORT set,
the harness channel.

Under the harness the sim steps with a fixed HARNESS_DT instead of real
frame time, and only while a wait command runs, so a script's waits
alone set the game time and its runs and shots repeat (docs/harness.md).
"""

import logging
import os
import sys
import time

from tankful.game import input as game_input
from tankful.game.fishes import Fishes
from tankful.game.scenery import Scenery
from tankful.sim import species
from tankful.sim.tank import Tank

log = logging.getLogger('tankful')

# The sim's step under the harness, in seconds
HARNESS_DT = 1.0 / 60

_app = None


def update(controller):
  global _app
  if _app is None:
    _app = App()
  _app.frame()


class App:

  def __init__(self):
    import bge
    self.bge = bge
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format='tankful: %(name)s: %(message)s')
    if os.environ.get('TANKFUL_DEBUG'):
      _start_debugger()
    self.root = os.environ.get('TANKFUL_ROOT') or os.getcwd()
    self.offscreen = None
    size = parse_size(os.environ.get('TANKFUL_OFFSCREEN', ''))
    if size:
      self.offscreen = _offscreen_module()
      if self.offscreen is not None:
        self.offscreen.hide_offscreen(size)
    self.tank = Tank()
    species.stock(self.tank)
    scene = bge.logic.getCurrentScene()
    self.scenery = Scenery(scene)
    self.fishes = Fishes(scene, self.tank.fish)
    self.input = game_input.InputState()
    self.channel = None
    self._last = time.monotonic()
    port = os.environ.get('TANKFUL_HARNESS_PORT')
    if port:
      self._start_harness(int(port))

  def _start_harness(self, port):
    from tankful.game import harness_channel
    processor = harness_channel.CommandProcessor(
      self.input, self.bge.render.makeScreenshot, self.state,
      self.bge.logic.endGame, self.root, frame_dt=HARNESS_DT)
    host = os.environ.get('TANKFUL_HARNESS_HOST', '127.0.0.1')
    self.channel = harness_channel.HarnessChannel(processor, port, host)
    log.info('harness listening on %s:%d', host, port)

  def frame(self):
    now = time.monotonic()
    dt, self._last = now - self._last, now
    bge = self.bge
    game_input.feed_from_bge(self.input, bge.logic, bge.events, bge.render)
    if self.channel is not None:
      self.channel.poll()
      dt = sim_step(self.channel.processor)
    if dt:
      self.tank.step(dt)
    self.scenery.update(self.tank.time, dt)
    self.fishes.update()
    self.input.end_frame()

  def state(self):
    render = self.bge.render
    scene = self.bge.logic.getCurrentScene()
    cam = scene.active_camera
    frames = self.offscreen.window_frames() if self.offscreen else None
    return {
      'window_frames': frames,
      'tank': self.tank.snapshot(),
      'scenery': self.scenery.snapshot(),
      'fishes': self.fishes.snapshot(),
      'input': self.input.snapshot(),
      'window': [render.getWindowWidth(), render.getWindowHeight()],
      'fps': round(self.bge.logic.getAverageFrameRate(), 1),
      'profile': profile(self.bge.logic),
      'scene': {'name': scene.name,
                'objects': len(scene.objects),
                'camera': cam.name if cam else None,
                'camera_pos': [round(v, 3) for v in cam.worldPosition]
                if cam else None},
    }


def sim_step(processor):
  """The sim's step this frame under the harness: HARNESS_DT while a
  wait runs, else 0, holding the sim still."""
  return HARNESS_DT if processor.waiting else 0.0


def profile(logic):
  """The player's frame time by category, in ms: {'Rasterizer': 15.4,
  ...}, for frame budgets (docs/harness.md)."""
  info = logic.getProfileInfo()
  return {name.rstrip(':'): round(times[0], 2) for name, times in info.items()}


def parse_size(text):
  """'1280x720' -> (1280, 720); None for '' or a malformed value."""
  w, sep, h = text.lower().partition('x')
  if not sep or not w.isdigit() or not h.isdigit():
    if text:
      log.warning('ignoring bad TANKFUL_OFFSCREEN size %r', text)
    return None
  return int(w), int(h)


def _offscreen_module():
  if sys.platform == 'darwin':
    from tankful.game import offscreen_macos as mod
  elif sys.platform.startswith('win'):
    from tankful.game import offscreen_windows as mod
  else:
    log.warning('TANKFUL_OFFSCREEN has no effect on %s; use the xvfb '
                'backend', sys.platform)
    return None
  return mod


def _start_debugger():
  try:
    import wingdbstub  # noqa: F401
  except ImportError:
    log.error('TANKFUL_DEBUG is set but wingdbstub is not importable: copy '
              'wingdbstub.py from the Wing install into the project root')
