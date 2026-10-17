"""Day and night: the tank's light switch, and how the fish take the dark.

Light is the switch and its transition.  Flipping it (toggle, or set)
starts a smooth fade over TRANSITION seconds, eased at both ends, from
day (level 1) to night (level 0) or back; flipping it again midway turns
the fade round from where it is.  The fade is slow on purpose: the
player's frame accumulation smears shading that changes fast, and the
caustics wash out (docs/harness.md).

Light.moon is how bright the moonlight is at night, from 0 (no moon,
starlight) to 1 (full moon).  The external factor's Effects.night_light
sets it (tankful.game.factor_hud), as the Time & Moon factor gives it
from the moon's phase; with none it is MOON_DEFAULT.

look(level, moon) is what the game shows for a light level: the lamp's
energy and color, the room, the back panel, the sheens on the front
glass, the caustics and god rays' strength, the bubbles' brightness,
how fast the airstone runs, and the moon's glint on the surface.

Each species says how its fish behave at full night with a Night (its
Species' night field; None changes nothing), and every modifier is
blended in by Light.night, 0 by day to 1 at full night, so the fish
change with the light as it fades.  The fish read it as their own night
attribute, which Tank.step sets (tankful.sim.fish.Fish.by_night).
"""

import collections

# How long a fade between day and night takes (s)
TRANSITION = 6.0
# The moon when nothing has said otherwise: about a half moon
MOON_DEFAULT = 0.5

# How a species behaves at full night.  Each is a factor on its day
# value (1 changes nothing) unless said otherwise:
#
# speed: its cruising and hovering speeds.
# depth_band: its preferred depth band at night (as Species.depth_band),
#   or None to keep the day's.
# hover: how often it stops to hover, and hover_time how long it stays.
# plants: how hard it is drawn toward the plants, from 0 (not at all);
#   it keeps about a body length off the nearest clump.
# activity: how busy a fish with a state machine of its own is (the
#   pleco, the corydoras, the shrimp): its timers run this much faster,
#   so it moves on sooner, and the quick moves (flicks, chases, hops)
#   come this much more often.  Below 1 is drowsy.
# loosen: a school's spacing (tankful.sim.school), wider above 1, and
#   its pull together, weaker.
# surface_margin: how near the surface the fish may rest (as
#   Species.surface_margin, m), or None to keep the day's.
Night = collections.namedtuple('Night', (
  'speed', 'depth_band', 'hover', 'hover_time', 'plants', 'activity',
  'loosen', 'surface_margin'),
  defaults=(1.0, None, 1.0, 1.0, 0.0, 1.0, 1.0, None))

DAY_NIGHT = Night()


def ease(t):
  """Smoothstep: 0 to 1, flat at both ends."""
  t = min(1.0, max(0.0, t))
  return t * t * (3 - 2 * t)


def blend(day, night, amount):
  """day's value toward night's by amount (0 to 1)."""
  return day + (night - day) * amount


def factor(species, name, night):
  """The factor species' Night gives for name (a Night field such as
  'speed'), blended in by night (0 to 1): 1 by day, or with no Night."""
  mod = species.night
  if mod is None or not night:
    return 1.0
  return blend(1.0, getattr(mod, name), night)


def depth_band(species, night):
  """species' preferred depth band, blended toward its night band by
  night (0 to 1)."""
  band = species.depth_band
  mod = species.night
  if mod is None or mod.depth_band is None or not night:
    return band
  return tuple(blend(d, n, night) for d, n in zip(band, mod.depth_band))


class Light:
  """The tank's light switch, and how far its fade has got."""

  def __init__(self, on=True, transition=TRANSITION, moon=MOON_DEFAULT):
    if transition <= 0:
      raise ValueError('transition must be positive: %r' % transition)
    self.on = bool(on)
    self.transition = transition
    # How far from night (0) to day (1), linearly; level eases it
    self.progress = 1.0 if self.on else 0.0
    self.moon = moon
    self.switches = 0

  @property
  def level(self):
    """The light, 0 at night to 1 by day, eased through the fade."""
    return ease(self.progress)

  @property
  def night(self):
    """How far into the night, 0 by day to 1: the behavior modifiers'
    weight."""
    return 1.0 - self.level

  @property
  def fading(self):
    return self.progress != (1.0 if self.on else 0.0)

  def set(self, on):
    """Turn the light on or off.  Whether that changed the switch."""
    on = bool(on)
    if on == self.on:
      return False
    self.on = on
    self.switches += 1
    return True

  def toggle(self):
    self.set(not self.on)
    return self.on

  def set_moon(self, moon):
    """The step 13 hook: the moon's brightness, 0 (none) to 1 (full)."""
    self.moon = min(1.0, max(0.0, float(moon)))

  def step(self, dt):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    goal = 1.0 if self.on else 0.0
    step = dt / self.transition
    self.progress += min(step, max(-step, goal - self.progress))

  def snapshot(self):
    return {'on': self.on, 'level': round(self.level, 4),
            'night': round(self.night, 4), 'fading': self.fading,
            'moon': round(self.moon, 3), 'switches': self.switches}


# What the tank looks like by day and at night.  The lamp's energy is in
# watts (tools/build_scene.py, setup_light), and the night lamp's goes
# from NIGHT_LAMP[0] with no moon to NIGHT_LAMP[1] at full moon
DAY_LAMP, NIGHT_LAMP = 20.0, (1.2, 3.6)
DAY_LAMP_COLOR, NIGHT_LAMP_COLOR = (1.0, 0.97, 0.9), (0.42, 0.58, 1.0)
# The room's background
DAY_ROOM, NIGHT_ROOM = (0.05, 0.06, 0.08), (0.006, 0.009, 0.02)
# A multiplier on the back panel's glow, and on the bubbles' and
# ripples' brightness
DAY_PANEL, NIGHT_PANEL = (1.0, 1.0, 1.0), (0.07, 0.10, 0.20)
DAY_BUBBLES, NIGHT_BUBBLES = (1.0, 1.0, 1.0), (0.22, 0.28, 0.42)
# A multiplier on the room's sheens on the front glass
DAY_SHEEN, NIGHT_SHEEN = (1.0, 1.0, 1.0), (0.05, 0.06, 0.1)
# The caustics' and god rays' strength, with no moon and at full moon.
# They glow of themselves (tools/scene_env.py, lit_surface), so for them
# to fall off as much as the lamp's light does, their strength goes as
# the lamp's energy, and a little lower: the moon's caustics are faint
NIGHT_CAUSTICS = (0.01, 0.045)
# The moon's glint on the surface (tankful.game.scenery, MoonGlint): none
# by day, and at night none for a moon of GLINT_FROM or less (a new moon
# gives tankful.factors.moon.NIGHT_LIGHT_NEW), full at full moon
GLINT_FROM = 0.15
# The glint's sparkle loops every GLINT_LOOP seconds (the shader's clock,
# glint_clock, goes 0 to 1 round it), changing at about the caustics'
# slow pace: the player's frame accumulation smears faster shading
GLINT_LOOP = 120.0
# Below this the glint is not drawn at all (MoonGlint is hidden)
GLINT_MIN = 0.01
# A factor on the airstone's bubbles per second (the
# tankful.sim.bubbles.BubblePool's rate): the pump runs low at night
NIGHT_BUBBLE_RATE = 0.35

Look = collections.namedtuple('Look', (
  'lamp', 'lamp_color', 'room', 'panel', 'sheen', 'caustics', 'bubbles',
  'bubble_rate', 'glint'))


def look(level, moon=MOON_DEFAULT):
  """The Look for a light level (0 night to 1 day) under a moon (0 to 1)."""
  level = min(1.0, max(0.0, level))
  moon = min(1.0, max(0.0, moon))

  def mix(day, night):
    if isinstance(day, tuple):
      return tuple(blend(n, d, level) for d, n in zip(day, night))
    return blend(night, day, level)
  night_lamp = blend(NIGHT_LAMP[0], NIGHT_LAMP[1], moon)
  night_caustics = blend(NIGHT_CAUSTICS[0], NIGHT_CAUSTICS[1], moon)
  return Look(lamp=mix(DAY_LAMP, night_lamp),
              lamp_color=mix(DAY_LAMP_COLOR, NIGHT_LAMP_COLOR),
              room=mix(DAY_ROOM, NIGHT_ROOM),
              panel=mix(DAY_PANEL, NIGHT_PANEL),
              sheen=mix(DAY_SHEEN, NIGHT_SHEEN),
              caustics=mix(1.0, night_caustics),
              bubbles=mix(DAY_BUBBLES, NIGHT_BUBBLES),
              bubble_rate=mix(1.0, NIGHT_BUBBLE_RATE),
              glint=mix(0.0, glint(moon)))


def glint_clock(time):
  """The glint shader's clock for game time (s): 0 to 1 round its loop."""
  return (time % GLINT_LOOP) / GLINT_LOOP


def glint(moon):
  """How bright the moon's glint is at full night under a moon (0 to
  1): 0 up to GLINT_FROM, then rising to 1 at a full moon."""
  return min(1.0, max(0.0, (moon - GLINT_FROM) / (1.0 - GLINT_FROM)))
