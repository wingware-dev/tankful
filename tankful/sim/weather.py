"""The weather in the tank: raindrops on the surface, and lightning.

The Weather factor (tankful.factors.weather) says how hard it rains, as
Effects.surface_agitation, and how stormy it is, as Effects.flicker and
Effects.skittish.  The game shows them:

- Rain: drops land on the surface and spread rings.  They are drawn by
  one still object, RainRipples (tools/scene_env.py, build_rain), whose
  shader lays the surface out in cells of RAIN_CELL: in each a drop
  lands at a random spot once every 1 / RAIN_RATE seconds, at a random
  phase, and it shows only while a random draw is under the rain's
  strength, so the harder the rain, the more cells have drops.  Two
  such layers, the second offset by half a cell, keep the pattern from
  looking like a grid.  The game sets only the object's color: the rain
  clock (rain_clock), the strength and the brightness.  So rain costs
  one color write a frame, as the bubbles' ripples do.
- Lightning: Lightning strikes at random, more often the stormier, each
  strike a few quick flashes; the lamp brightens with Lightning.level
  (tankful.game.factor_hud), and the fish startle with each strike as
  skittish as the storm (tankful.sim.tank.Tank.startle).

All of it is plain Python, and Lightning is seeded, so a harness run
repeats.
"""

import random

# The rain's cells (m), how often a cell's drop lands (per s), and the
# cell layers drawn
RAIN_CELL = 0.1
RAIN_RATE = 0.7
RAIN_LAYERS = 2
# The rain clock wraps at this many seconds, to keep it precise as a
# float in the shader
RAIN_WRAP = 600.0
# A drop's ring: its radius at the start and the end of its cycle, as a
# fraction of RAIN_CELL, and the ring's half width
RAIN_RING = (0.04, 0.3, 0.035)
# Below this strength no rain is drawn at all (the object is hidden)
RAIN_MIN = 0.02

# Strikes per second at full flicker
STRIKE_RATE = 0.16
# The least time between strikes (s)
STRIKE_GAP = 2.5
# The flashes of a strike: (start, length, brightness), seconds from the
# strike
FLASHES = ((0.0, 0.08, 1.0), (0.14, 0.06, 0.55), (0.26, 0.12, 0.85))


def rain_clock(time):
  """The rain shader's clock for game time (s)."""
  return time % RAIN_WRAP


class Lightning:
  """Random strikes, each a few flashes, as often as flicker (0 to 1)
  says."""

  def __init__(self, seed=17):
    self.rng = random.Random(seed)
    # Time since the last strike began, or None before the first
    self.since = None
    self.strikes = 0
    # Whether a strike began in the last step
    self.struck = False

  def step(self, dt, flicker):
    """Advance by dt seconds at flicker (0 to 1); whether a strike began."""
    if self.since is not None:
      self.since += dt
    self.struck = False
    if flicker > 0 and (self.since is None or self.since >= STRIKE_GAP):
      if self.rng.random() < STRIKE_RATE * flicker * dt:
        self.since = 0.0
        self.strikes += 1
        self.struck = True
    return self.struck

  @property
  def level(self):
    """How bright the flash is now, 0 (none) to 1."""
    if self.since is None:
      return 0.0
    level = 0.0
    for start, length, brightness in FLASHES:
      t = (self.since - start) / length
      if 0.0 <= t < 1.0:
        # A sharp rise and a slower fall
        level = max(level, brightness * (t / 0.15 if t < 0.15
                                         else (1.0 - t) / 0.85))
    return level

  def snapshot(self):
    return {'strikes': self.strikes, 'level': round(self.level, 3)}
