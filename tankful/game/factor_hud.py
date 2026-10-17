"""The external factor picker and HUD, and the factor's hold on the tank.

A gear at the window's top left, or the F key, opens a menu of the
factors (tankful.factors.registry: None, Weather, Time & Moon, Battery,
Stock).  A click on one, or its number key, or the arrows and Enter,
picks it; F, the gear or a click elsewhere closes the menu (not
Escape, the player's exit key, tools/build_scene.py).  Beside the
gear a small label shows the factor and its live value, marked offline
when its source fails (tankful.factors.controller.FactorController.label).

Each frame the controller's eased Effects go to the tank (the fishes'
speed, depth band and skittishness, and the lightning,
tankful.sim.tank.Tank.set_factor), the lighting (the lamp's energy and
color, the panel's and glass's tint and the caustics' strength, through
Lighting.adjust, so the scenery's caustics follow too, with the
lightning's flashes, tankful.sim.weather), the rain on the surface
(Scenery.set_rain) and the moon (tankful.sim.daynight.Light.set_moon).
The Effects are taken in small steps (EFFECT_STEP), so once eased in
they stop changing and the lighting stops writing.

A factor that works the light switch (Time & Moon, its light_for) flips
it at dusk and dawn (AutoSwitch), unless the viewer has flipped it since,
and its light effects (level, tint, caustics) are for the lit tank: they
fade out as the light fades to night, and while the viewer's switch
overrides it (light_weighted).

The menu's state and layout are plain Python (FactorMenu); only draw()
needs UPBGE's blf and gpu, through the scene's post_draw.
"""

import contextlib
import dataclasses
import logging
import math

from tankful.factors import controller as controller_mod
from tankful.factors import effects as effects_mod
from tankful.factors import registry
from tankful.factors import standins
from tankful.sim import daynight

log = logging.getLogger('tankful.factor_hud')

KEY = 'f'
# The number keys as bge names them (tankful.game.input.normalize_key
# gives ONEKEY as 'one'); the harness sends '1'
DIGITS = ('one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
          'nine')
# Layout, in window pixels from the top left at a 720 pixel tall window,
# scaled with its height
MARGIN = 18
GEAR = 30
LABEL_GAP = 10
MENU_GAP = 8
MENU_WIDTH = 220
ROW = 32
TEXT = 15
TITLE = 'Tank mood'
# Colors (rgba)
PANEL_COLOR = (0.06, 0.08, 0.1, 0.82)
CURRENT_COLOR = (0.2, 0.45, 0.6, 0.9)
HOVER_COLOR = (1.0, 1.0, 1.0, 0.12)
TEXT_COLOR = (0.92, 0.95, 0.97, 1.0)
DIM_TEXT_COLOR = (0.65, 0.7, 0.75, 1.0)
OFFLINE_COLOR = (1.0, 0.72, 0.35, 1.0)
GEAR_COLOR = (0.9, 0.93, 0.95, 0.85)
# The step the Effects are taken in before they reach the tank
EFFECT_STEP = 0.005
# Caustics no stronger than this times the light's own
MAX_CAUSTICS = 1.5
# A full lightning flash: the lamp this many times brighter again, the
# back panel and the glass's sheens too, and the lamp's color
FLASH_LAMP = 3.0
FLASH_GLOW = 1.5
FLASH_COLOR = (0.85, 0.9, 1.0)
# The moon eases toward the factor's night light (or back to the
# default) over about this many seconds
MOON_TIME = 2.0


class FactorMenu:
  """The gear, the menu's rows and which is open, chosen or hovered."""

  def __init__(self, factors=registry.FACTORS):
    self.factors = list(factors)
    self.open = False
    # The row the arrows have moved to, or None
    self.cursor = None

  # Layout: rects are (left, top, right, bottom), window pixels

  def scale(self, window):
    return max(0.5, window[1] / 720.0)

  def gear_rect(self, window):
    s = self.scale(window)
    return (MARGIN * s, MARGIN * s, (MARGIN + GEAR) * s, (MARGIN + GEAR) * s)

  def label_pos(self, window):
    """Where the label's text starts: its left and its vertical center."""
    left, top, right, bottom = self.gear_rect(window)
    return (right + LABEL_GAP * self.scale(window), (top + bottom) / 2)

  def panel_rect(self, window):
    s = self.scale(window)
    left, _, _, bottom = self.gear_rect(window)
    top = bottom + MENU_GAP * s
    return (left, top, left + MENU_WIDTH * s,
            top + ROW * s * (len(self.factors) + 1))

  def row_rects(self, window):
    """Each factor's row, below the title row."""
    s = self.scale(window)
    left, top, right, _ = self.panel_rect(window)
    return [(left, top + ROW * s * (i + 1), right, top + ROW * s * (i + 2))
            for i in range(len(self.factors))]

  def row_at(self, window, x, y):
    for i, rect in enumerate(self.row_rects(window)):
      if in_rect(rect, x, y):
        return i
    return None

  def hit(self, window, x, y):
    """Whether x, y is on the gear or the open menu: a click there is the
    menu's, not the tank's."""
    return (in_rect(self.gear_rect(window), x, y)
            or (self.open and in_rect(self.panel_rect(window), x, y)))

  # Input

  def handle_input(self, state, window, current=None):
    """Act on this frame's input (state, a tankful.game.input.InputState)
    in a window of (width, height).  The key of the factor picked, or
    None.  current is the factor key now in use, where the arrows start."""
    picked = None
    if state.was_pressed(KEY):
      self.toggle()
    elif self.open:
      picked = self._keys(state, current)
    for x, y, button in state.clicks():
      if button != 'left':
        continue
      if in_rect(self.gear_rect(window), x, y):
        self.toggle()
      elif self.open:
        row = self.row_at(window, x, y)
        if row is not None:
          picked = self.factors[row].key
        elif not in_rect(self.panel_rect(window), x, y):
          self.close()
    if picked is not None:
      self.close()
    return picked

  def _keys(self, state, current):
    for i, factor in enumerate(self.factors):
      if i < len(DIGITS) and (state.was_pressed(str(i + 1))
                              or state.was_pressed(DIGITS[i])):
        return factor.key
    n = len(self.factors)
    for key, step in (('up', -1), ('down', 1)):
      if state.was_pressed(key):
        if self.cursor is None:
          self.cursor = self.index(current) or 0
        self.cursor = (self.cursor + step) % n
    if state.was_pressed('enter') and self.cursor is not None:
      return self.factors[self.cursor].key
    return None

  def index(self, key):
    for i, factor in enumerate(self.factors):
      if factor.key == key:
        return i
    return None

  def toggle(self):
    if self.open:
      self.close()
    else:
      self.open = True
      self.cursor = None

  def close(self):
    self.open = False
    self.cursor = None


class MoonFollower:
  """The moon the tank's light should have: the factor's night light
  while it gives one (above 0), else the default moon, eased over
  MOON_TIME so a change fades in with the Effects."""

  def __init__(self, moon=daynight.MOON_DEFAULT):
    self.moon = moon

  def update(self, night_light, dt):
    target = night_light if night_light > 0 else daynight.MOON_DEFAULT
    t = 1.0 - math.exp(-max(0.0, dt) / MOON_TIME)
    self.moon += (target - self.moon) * t
    if abs(self.moon - target) < EFFECT_STEP:
      self.moon = target
    return quantize_value(self.moon)


class AutoSwitch:
  """Works the tank's light switch (a tankful.sim.daynight.Light) for a
  factor that says when the light should be on.

  It flips the switch only when what the factor wants changes, as at
  dusk and dawn, so once the viewer has flipped it by hand it stays as
  they left it until the next one.  The factor's first reading after it
  is picked sets the switch at once.
  """

  def __init__(self, light):
    self.light = light
    # Whether the factor last wanted the light on; None for not yet
    self.wanted = None

  def reset(self):
    """Forget the last wish, for a newly picked factor."""
    self.wanted = None

  def update(self, wanted):
    """wanted: whether the factor wants the light on now, or None (it
    doesn't work the switch, or has no reading yet).  Whether this
    flipped the switch."""
    if wanted is None or wanted == self.wanted:
      return False
    self.wanted = wanted
    flipped = self.light.set(wanted)
    if flipped:
      log.info('light %s by the factor', 'on' if wanted else 'off')
    return flipped

  @property
  def active(self):
    """Whether a factor works the switch."""
    return self.wanted is not None

  @property
  def following(self):
    """Whether the switch is as the factor wants it."""
    return self.wanted is not None and self.light.on == self.wanted


def light_weighted(e, weight):
  """Effects e with its light fields (light_level, caustic_sharpness and
  tint) only weight (0 to 1) of the way from neutral; the rest as they
  are."""
  if weight >= 1.0:
    return e
  weight = max(0.0, weight)

  def toward(value):
    return 1.0 + (value - 1.0) * weight
  return e.replace(light_level=toward(e.light_level),
                   caustic_sharpness=toward(e.caustic_sharpness),
                   tint=tuple(toward(c) for c in e.tint))


def quantize_value(value, step=EFFECT_STEP):
  return round(round(value / step) * step, 6)


def quantize(e):
  """Effects e in steps of EFFECT_STEP, so an easing value settles."""
  changes = {name: quantize_value(getattr(e, name))
             for name in effects_mod.RANGES}
  changes['tint'] = tuple(quantize_value(c) for c in e.tint)
  return dataclasses.replace(e, **changes)


def adjust_look(look, e, flash=0.0):
  """look (a tankful.sim.daynight.Look) with Effects e in: the lamp's
  energy by e.light_level, its color, the back panel's glow and the
  glass's sheens by e.tint, and the caustics' strength by the light level
  and e.caustic_sharpness (none at 0).  flash (0 to 1) is a lightning
  flash (tankful.sim.weather.Lightning.level): the lamp, the panel, the
  sheens and the caustics brighten, and the lamp goes a cold white."""
  caustics = min(MAX_CAUSTICS, e.light_level * e.caustic_sharpness)
  lamp_color = tuple(c * t for c, t in zip(look.lamp_color, e.tint))
  bright = 1.0 + FLASH_GLOW * flash
  if flash:
    lamp_color = tuple(c + (f - c) * flash
                       for c, f in zip(lamp_color, FLASH_COLOR))
  return look._replace(
    lamp=look.lamp * e.light_level * (1.0 + FLASH_LAMP * flash),
    lamp_color=lamp_color,
    panel=tuple(c * t * bright for c, t in zip(look.panel, e.tint)),
    sheen=tuple(c * t * bright for c, t in zip(look.sheen, e.tint)),
    caustics=look.caustics * caustics * (1.0 + flash))


def in_rect(rect, x, y):
  left, top, right, bottom = rect
  return left <= x <= right and top <= y <= bottom


def gear_triangles(cx, cy, radius, teeth=8, steps=6):
  """A gear's outline around (cx, cy), as triangles (each three (x, y)
  points): a ring from half radius out to the teeth's tips at radius,
  the body between them at 0.78 radius."""
  inner = radius * 0.42
  points = teeth * steps
  out = []

  def outer(i):
    phase = (i % steps) / steps
    return radius if 0.2 <= phase < 0.6 else radius * 0.78

  for i in range(points):
    a0 = 2 * math.pi * i / points
    a1 = 2 * math.pi * (i + 1) / points
    r0 = outer(i)
    p = [(cx + inner * math.cos(a0), cy + inner * math.sin(a0)),
         (cx + r0 * math.cos(a0), cy + r0 * math.sin(a0)),
         (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1)),
         (cx + inner * math.cos(a1), cy + inner * math.sin(a1))]
    out.append((p[0], p[1], p[2]))
    out.append((p[0], p[2], p[3]))
  return out


def rect_triangles(rect):
  left, top, right, bottom = rect
  return [((left, top), (right, top), (right, bottom)),
          ((left, top), (right, bottom), (left, bottom))]


class FactorHud:
  """The picker, the HUD label and the factor's Effects, for the game.

  frame() once per frame; stop() on exit.  Draws itself through the
  scene's post_draw when given a scene.
  """

  def __init__(self, tank, lighting, controller=None, scene=None,
               window=None, scenery=None):
    """window: a function giving the window's (width, height), for
    draw().  scenery: the tankful.game.scenery.Scenery, for the rain."""
    if controller is None:
      controller = controller_mod.FactorController(
        make_source=standins.for_env())
    self.controller = controller
    self.tank = tank
    self.lighting = lighting
    self.scenery = scenery
    self.menu = FactorMenu()
    self.moon = MoonFollower(tank.light.moon)
    self.switch = AutoSwitch(tank.light)
    # How much of the factor's light effects the switch lets through,
    # eased: 1 unless a factor works the switch and the viewer has
    # overridden it (see light_weight)
    self._agree = 1.0
    self.effects = effects_mod.NEUTRAL
    self.label = ''
    self.offline = False
    self.mouse = (0, 0)
    self._window = window
    self._moon_set = None
    lighting.adjust = self.adjust_look
    self._draw_failed = False
    if scene is not None:
      scene.post_draw.append(self.draw)

  def adjust_look(self, look):
    e = light_weighted(self.effects, self.light_weight)
    return adjust_look(look, e, self.tank.lightning.level)

  @property
  def light_weight(self):
    """How much of the factor's light effects to show: all of them for a
    factor that leaves the switch alone; for one that works it, as much
    as the light is up while the switch is as it wants (so none at
    night), fading to none while the viewer's switch overrides it."""
    if not self.switch.active:
      return 1.0
    return quantize_value(self.tank.light.level * self._agree)

  def hit(self, window, x, y):
    return self.menu.hit(window, x, y)

  def frame(self, state, window, dt):
    """Handle input, then ease the Effects in by dt seconds and hand them
    to the tank and the lighting (before Lighting.update)."""
    self.mouse = state.mouse
    picked = self.menu.handle_input(state, window, self.controller.key)
    if picked is not None:
      factor = self.controller.select(picked)
      self.switch.reset()
      log.info('factor %s', factor.key)
    self.switch.update(self.controller.light_for())
    agree = 1.0 if self.switch.following or not self.switch.active else 0.0
    self._agree += (agree - self._agree) * (
      1.0 - math.exp(-max(0.0, dt) / MOON_TIME))
    if abs(self._agree - agree) < EFFECT_STEP:
      self._agree = agree
    self.effects = quantize(self.controller.update(dt))
    e = self.effects
    self.tank.set_factor(e.speed_scale, e.depth_shift, e.skittish, e.flicker)
    if self.scenery is not None:
      self.scenery.set_rain(e.surface_agitation)
    moon = self.moon.update(self.controller.target().night_light, dt)
    if moon != self._moon_set:
      self.tank.light.set_moon(moon)
      self._moon_set = moon
    self.label = self.controller.label
    self.offline = (self.controller.factor.module is not None
                    and (not self.controller.factor.available
                         or self.controller.status().offline))

  def stop(self):
    return self.controller.stop()

  def snapshot(self):
    e = self.effects
    return {
      'factor': self.controller.key,
      'label': self.label,
      'offline': self.offline,
      'menu_open': self.menu.open,
      'effects': {
        'speed_scale': e.speed_scale, 'depth_shift': e.depth_shift,
        'light_level': e.light_level,
        'caustic_sharpness': e.caustic_sharpness, 'tint': list(e.tint),
        'night_light': e.night_light},
      'moon': self._moon_set,
      'auto_light': self.switch.wanted,
      'light_weight': self.light_weight,
    }

  # Drawing, under UPBGE

  def draw(self):
    if self._draw_failed or self._window is None:
      return
    try:
      self._draw(self._window())
    except Exception:
      # Once only: a draw error every frame would flood the log
      self._draw_failed = True
      log.exception('factor HUD: draw failed, HUD off')

  def _draw(self, window):
    menu = self.menu
    s = menu.scale(window)
    with overlay(window, s) as paint:
      fill, text = paint.fill, paint.text
      left, top, right, bottom = menu.gear_rect(window)
      fill(gear_triangles((left + right) / 2, (top + bottom) / 2,
                          (right - left) / 2), GEAR_COLOR)
      if self.label:
        x, y = menu.label_pos(window)
        text(x, y, self.label, TEXT,
             OFFLINE_COLOR if self.offline else TEXT_COLOR)
      if menu.open:
        panel = menu.panel_rect(window)
        fill(rect_triangles(panel), PANEL_COLOR)
        pad = 12 * s
        text(panel[0] + pad, panel[1] + ROW * s / 2, TITLE, TEXT - 2,
             DIM_TEXT_COLOR)
        current = menu.index(self.controller.key)
        hover = menu.row_at(window, *self.mouse)
        for i, (factor, rect) in enumerate(zip(menu.factors,
                                               menu.row_rects(window))):
          if i == current:
            fill(rect_triangles(rect), CURRENT_COLOR)
          elif i == hover or i == menu.cursor:
            fill(rect_triangles(rect), HOVER_COLOR)
          y = (rect[1] + rect[3]) / 2
          text(rect[0] + pad, y, str(i + 1), TEXT, DIM_TEXT_COLOR)
          text(rect[0] + pad + 22 * s, y, factor.label, TEXT,
               TEXT_COLOR if factor.available else DIM_TEXT_COLOR)


class _Painter:
  """fill() and text() in window pixels from the top left, at scale s,
  for overlay()."""

  def __init__(self, h, s):
    import blf
    import gpu
    self._blf = blf
    self._h = h
    self.s = s
    self._shader = gpu.shader.from_builtin('UNIFORM_COLOR')

  def fill(self, triangles, color):
    from gpu_extras.batch import batch_for_shader
    # Our rects are from the top left; GL's from the bottom left
    h = self._h
    verts = [(x, h - y) for tri in triangles for x, y in tri]
    batch = batch_for_shader(self._shader, 'TRIS', {'pos': verts})
    self._shader.uniform_float('color', color)
    batch.draw(self._shader)

  def text_width(self, value, size):
    self._blf.size(0, size * self.s)
    return self._blf.dimensions(0, value)[0]

  def text(self, x, y_center, value, size, color):
    blf = self._blf
    blf.size(0, size * self.s)
    blf.color(0, *color)
    _, th = blf.dimensions(0, 'Ag')
    blf.position(0, x, self._h - y_center - th / 3, 0)
    blf.draw(0, value)


@contextlib.contextmanager
def overlay(window, s):
  """Draw over the scene in window pixels (UPBGE's gpu and blf, from a
  post_draw): yields a _Painter, at scale s."""
  import gpu
  from mathutils import Matrix
  w, h = window
  ortho = Matrix(((2.0 / w, 0, 0, -1), (0, 2.0 / h, 0, -1),
                  (0, 0, -1, 0), (0, 0, 0, 1)))
  gpu.state.blend_set('ALPHA')
  gpu.state.depth_test_set('NONE')
  try:
    with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
      gpu.matrix.load_matrix(Matrix.Identity(4))
      gpu.matrix.load_projection_matrix(ortho)
      yield _Painter(h, s)
  finally:
    gpu.state.blend_set('NONE')
