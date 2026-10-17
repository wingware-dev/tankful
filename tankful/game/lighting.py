"""The light switch and the tank's lighting, day and night.

The switch (LightSwitch, tools/build_scene.py, build_switch) is on the
wall beside the tank.  Clicking it, or pressing L, flips the tank's
Light (tankful.sim.daynight), which fades between day and night; its
rocker tips to show which.  Each frame of the fade this sets what
tankful.sim.daynight.look says for the light's level:

- TankLight, the lamp: its energy and color, dim blue moonlight at
  night;
- the room (the world's background), which lights the tank faintly;
- BackPanel's glow, and the room's sheens on GlassFront, through their
  object colors.

The caustics, god rays, bubbles and ripples are the scenery's
(tankful.game.scenery.Scenery.set_look).

The lamp and the room are set through bpy, which costs frame time, so
only while the look changes: during a fade, not once it is done.  The
room costs most, about 3 ms a write, so it changes in small steps, not
every frame (room_due).
"""

import logging
import math

from tankful.sim import daynight
from tankful.sim import environment as env

log = logging.getLogger('tankful.lighting')

SWITCH = 'LightSwitch'
ROCKER = 'LightSwitch.Rocker'
LAMP = 'TankLight'
PANEL = 'BackPanel'
GLASS = 'GlassFront'
KEY = 'l'
# How far outside the plate (pixels) a click still flips the switch
CLICK_PAD = 6
# The room's color is written in steps of this much (of 0 to 1) in a
# channel: about 30 writes over a fade
ROOM_STEP = 0.002


class Lighting:

  def __init__(self, scene, light, world=None):
    objects = scene.objects
    self.scene = scene
    self.light = light
    self.lamp = objects.get(LAMP)
    self.panel = objects.get(PANEL)
    self.glass = objects.get(GLASS)
    self.switch = objects.get(SWITCH)
    self.rocker = objects.get(ROCKER)
    self.world = world
    for name, obj in ((LAMP, self.lamp), (PANEL, self.panel),
                      (GLASS, self.glass),
                      (SWITCH, self.switch), (ROCKER, self.rocker)):
      if obj is None:
        log.warning('no %s in the scene', name)
    self._applied = None
    self._room = None
    self._rocker_on = None
    self._window = None
    self.look = daynight.look(light.level, light.moon)

  # The switch

  def handle_input(self, state, window):
    """Flip the switch for the L key or a click on it this frame
    (state, a tankful.game.input.InputState; window, (width, height)).
    Whether it flipped."""
    self._window = window
    flip = state.was_pressed(KEY)
    if not flip and state.clicks():
      rect = self.switch_rect(window)
      flip = rect is not None and any(
        button == 'left' and in_rect(rect, x, y, CLICK_PAD)
        for x, y, button in state.clicks())
    if flip:
      self.light.toggle()
      log.info('light %s', 'on' if self.light.on else 'off')
    return flip

  def switch_rect(self, window):
    """The plate's (left, top, right, bottom) in window pixels, or None
    with no switch or camera."""
    camera = self.scene.active_camera
    if self.switch is None or camera is None:
      return None
    x, y, z = self.switch.worldPosition
    w, h = env.SWITCH_SIZE
    corners = [camera.getScreenPosition([x + dx, y, z + dz])
               for dx in (-w / 2, w / 2) for dz in (-h / 2, h / 2)]
    return screen_rect(corners, window)

  # Each frame

  def update(self):
    light = self.light
    self.look = daynight.look(light.level, light.moon)
    if light.on != self._rocker_on and self.rocker is not None:
      tilt = -env.SWITCH_TILT if light.on else env.SWITCH_TILT
      self.rocker.localOrientation = rotation_x(tilt)
      self._rocker_on = light.on
    if self.look != self._applied:
      self._apply(self.look)
      self._applied = self.look

  def _apply(self, look):
    if self.lamp is not None:
      data = self.lamp.blenderObject.data
      data.energy = look.lamp
      data.color = look.lamp_color
    if self.world is not None and room_due(self._room, look.room):
      # Each write of the world's color stalls the frame for about 3 ms
      # (docs/harness.md, "Frame budget"), so only in steps of ROOM_STEP
      self.world.inputs['Color'].default_value = look.room + (1.0,)
      self._room = look.room
    if self.panel is not None:
      self.panel.color = look.panel + (1.0,)
    if self.glass is not None:
      self.glass.color = look.sheen + (1.0,)

  def snapshot(self):
    look = self.look
    rect = self.switch_rect(self._window) if self._window else None
    return {
      'light': self.light.snapshot(),
      'switch_rect': [round(v) for v in rect] if rect else None,
      'lamp': round(look.lamp, 3),
      'lamp_color': [round(c, 3) for c in look.lamp_color],
      'caustics': round(look.caustics, 3),
      'bubble_rate': round(look.bubble_rate, 3),
    }


def room_due(written, room):
  """Whether the room's color room is far enough from the one last
  written (None for none yet) to write: by ROOM_STEP in any channel, or
  at either end of the fade, so it always ends exactly there."""
  if written is None:
    return True
  if room == written:
    return False
  if room in (daynight.DAY_ROOM, daynight.NIGHT_ROOM):
    return True
  return max(abs(a - b) for a, b in zip(room, written)) >= ROOM_STEP


def world_background():
  """The world's Background node, through bpy, or None."""
  import bpy
  world = bpy.context.scene.world
  if world is None or not world.use_nodes:
    return None
  return world.node_tree.nodes.get('Background')


def screen_rect(corners, window):
  """(left, top, right, bottom) in pixels round corners, points as
  KX_Camera.getScreenPosition gives them (0 to 1 from the top left), in
  a window of (width, height) pixels."""
  w, h = window
  xs = [c[0] * w for c in corners]
  ys = [c[1] * h for c in corners]
  return (min(xs), min(ys), max(xs), max(ys))


def in_rect(rect, x, y, pad=0):
  left, top, right, bottom = rect
  return left - pad <= x <= right + pad and top - pad <= y <= bottom + pad


def rotation_x(angle):
  """The 3x3 rotation (rows) by angle about x."""
  c, s = math.cos(angle), math.sin(angle)
  return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))
