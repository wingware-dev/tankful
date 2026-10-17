"""The tank: the root of the simulation state."""

import random

from tankful.sim import daynight
from tankful.sim import fish as fish_mod
from tankful.sim import weather

# The steps the external factor's speed scale and depth shift are taken
# in (set_factor): each step is a new species for the fish, so an easing
# value settles instead of making a new one every frame
FACTOR_STEP = 0.01
# A depth band squeezed against the surface or the sand by a depth shift
# keeps at least this width (shift_band)
MIN_SHIFTED_WIDTH = 0.12
# On a full up shift the surface pushes a fish down only this near its
# swim box's top (m), so it can reach a band raised to the surface
# (factor_species)
MIN_SURFACE_MARGIN = 0.03
# How skittish fish swim at full skittishness: their flicks this many
# times as often, their wander this much wider, their turns this much
# quicker, and their hovering this many times as rare (factor_species)
SKITTISH_FLICKS = 6.0
SKITTISH_WANDER = 0.8
SKITTISH_TURN = 0.5
SKITTISH_HOVER = 3.0
# A startled fish darts at this fraction of its top speed, and one that
# flicks flicks for this long (s)
STARTLE_SPEED = 0.9
STARTLE_FLICK = 0.35


class Tank:
  """Holds everything that lives in the tank and advances it in time.

  Units are meters and seconds.  The origin is the center of the tank
  floor; x runs left to right as the viewer sees it, y front to back
  (away from the viewer) and z up.  The camera looks along +y.
  """

  def __init__(self, width=1.0, depth=0.4, height=0.5):
    self.width = width
    self.depth = depth
    self.height = height
    self.time = 0.0
    self.frame = 0
    self.fish = []
    # Groups of fish that swim together (tankful.sim.school); their
    # members are in fish too
    self.schools = []
    # The light switch and its fade between day and night
    self.light = daynight.Light()
    # The external factor's pull on the fish (tankful.factors.effects):
    # their speeds scaled, their depth bands shifted (set_factor)
    self.speed_scale = 1.0
    self.depth_shift = 0.0
    self.skittish = 0.0
    # The storm's lightning (tankful.sim.weather), as flicker says
    self.flicker = 0.0
    self.lightning = weather.Lightning()
    self.startles = 0
    self._rng = random.Random(23)
    # Each fish's and school's own species, while it swims a scaled one
    self._own_species = {}
    self._factor_species = {}

  @property
  def light_on(self):
    return self.light.on

  def set_factor(self, speed_scale=1.0, depth_shift=0.0, skittish=0.0,
                 flicker=0.0):
    """Scale the fish's speeds by speed_scale, shift their depth bands
    by depth_shift (-1 to the sand, 0 none, +1 to the surface) and make
    them skittish (0 to 1: twitchier, and startled by lightning), and
    strike lightning as often as flicker (0 to 1) says, as an external
    factor's Effects say, from the next step."""
    self.speed_scale = _step(speed_scale)
    self.depth_shift = _step(depth_shift)
    self.skittish = _step(skittish)
    self.flicker = flicker

  @property
  def _neutral(self):
    return (self.speed_scale == 1.0 and self.depth_shift == 0.0
            and self.skittish == 0.0)

  def _apply_factor(self):
    # Each fish and school swims as a copy of its species with the
    # factor in, shared by all of its kind (they tell each other apart by
    # species), and its own again once the factor is neutral
    neutral = self._neutral
    for swimmer in self.schools + self.fish:
      own = self._own_species.get(swimmer)
      if own is None:
        if neutral:
          continue
        own = self._own_species[swimmer] = swimmer.species
      if neutral:
        swimmer.species = own
        del self._own_species[swimmer]
        continue
      key = (own, self.speed_scale, self.depth_shift, self.skittish)
      species = self._factor_species.get(key)
      if species is None:
        species = factor_species(own, self.speed_scale, self.depth_shift,
                                 self.skittish)
        self._factor_species[key] = species
      swimmer.species = species

  def startle(self, chance):
    """Startle the fish, each with chance (0 to 1), as a lightning strike
    does: those that flick (guppies, tetras) flick, and the free
    swimmers dart.  The fish with ways of their own (on the glass or the
    sand, tankful.sim.species) and any the viewer steers are left be.
    How many startled."""
    count = 0
    for f in self.fish:
      if (getattr(f, 'state', None) is not None
          or getattr(f, 'steer', None) is not None
          or getattr(getattr(f, 'school', None), 'steer', None) is not None
          or self._rng.random() >= chance):
        continue
      if hasattr(f, 'flick_left'):
        f.flick_left = STARTLE_FLICK
        f.flick_turn = (self._rng.choice((-1, 1)) * f.species.flick_turn
                        * self._rng.uniform(0.6, 1.0))
      f.speed = max(f.speed, f.max_speed * STARTLE_SPEED)
      count += 1
    self.startles += 1
    return count

  def step(self, dt):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    self.time += dt
    self.frame += 1
    self.light.step(dt)
    if self._own_species or not self._neutral:
      self._apply_factor()
    if self.lightning.step(dt, self.flicker) and self.skittish > 0:
      self.startle(self.skittish)
    night = self.light.night
    for school in self.schools:
      school.night = night
    for fish in self.fish:
      fish.night = night
    for school in self.schools:
      school.step(dt)
    for fish in self.fish:
      fish.step(dt, self.fish)
    for school in self.schools:
      school.settle()

  def snapshot(self):
    """Return the state as plain JSON-able data, for harness assertions."""
    return {
      'time': round(self.time, 4),
      'frame': self.frame,
      'size': [self.width, self.depth, self.height],
      'light_on': self.light_on,
      'light': self.light.snapshot(),
      'factor': {'speed_scale': round(self.speed_scale, 3),
                 'depth_shift': round(self.depth_shift, 3),
                 'skittish': round(self.skittish, 3),
                 'flicker': round(self.flicker, 3),
                 'startles': self.startles},
      'lightning': self.lightning.snapshot(),
      'fish': [f.snapshot() for f in self.fish],
      'schools': [s.snapshot() for s in self.schools],
    }


def shift_band(band, shift):
  """A depth band (lo, hi, fractions from the sand to the surface) moved
  by shift: toward the surface for shift above 0 and toward the sand
  below 0.  Its center goes that fraction of the way from where it is to
  the surface or the sand, so a high band rises about as visibly as a
  low one sinks, and at 1 or -1 the center is at the end.  A band pushed
  past an end is squeezed against it, never narrower than
  MIN_SHIFTED_WIDTH (or its own width), so it never leaves 0 to 1: a band
  on the sand stays there on a down day."""
  lo, hi = band
  shift = min(1.0, max(-1.0, shift))
  if not shift:
    return (lo, hi)
  half = (hi - lo) / 2.0
  center = (lo + hi) / 2.0
  end = 1.0 if shift > 0 else 0.0
  center += abs(shift) * (end - center)
  lo, hi = max(0.0, center - half), min(1.0, center + half)
  width = min(MIN_SHIFTED_WIDTH, 2.0 * half)
  if hi - lo < width:
    if shift > 0:
      lo = hi - width
    else:
      hi = lo + width
  return (lo, hi)


def _step(value):
  return round(value / FACTOR_STEP) * FACTOR_STEP


def factor_species(species, speed_scale, depth_shift, skittish=0.0):
  """species (a tankful.sim.species.base.Species) with its speeds scaled,
  its depth bands, by day and by night, shifted, and as skittish as
  skittish (0 to 1) says: flicking more often, wandering wider, turning
  quicker and hovering less."""
  turn = 1.0 + SKITTISH_TURN * skittish
  changes = {'hover_speed': species.hover_speed * speed_scale,
             'cruise_speed': species.cruise_speed * speed_scale,
             'max_speed': species.max_speed * speed_scale,
             'depth_band': shift_band(species.depth_band, depth_shift),
             'flick_chance': species.flick_chance
             * (1.0 + SKITTISH_FLICKS * skittish),
             'wander_turn': species.wander_turn
             * (1.0 + SKITTISH_WANDER * skittish),
             'max_turn_rate': species.max_turn_rate * turn,
             'turn_accel': species.turn_accel * turn,
             'hover_chance': species.hover_chance
             / (1.0 + SKITTISH_HOVER * skittish)}
  if depth_shift > 0:
    changes['surface_margin'] = lift_margin(species.surface_margin,
                                            depth_shift)
  night = species.night
  if night is not None:
    night_changes = {}
    if night.depth_band is not None:
      night_changes['depth_band'] = shift_band(night.depth_band, depth_shift)
    if depth_shift > 0 and night.surface_margin is not None:
      night_changes['surface_margin'] = lift_margin(night.surface_margin,
                                                    depth_shift)
    if night_changes:
      changes['night'] = night._replace(**night_changes)
  return species._replace(**changes)


def lift_margin(margin, shift):
  """A species' surface_margin (None for the fish's default) eased
  toward MIN_SURFACE_MARGIN by an up shift (0 to 1): the surface's push
  starts within a band's reach of its top, and a margin already as small
  stays."""
  if margin is None:
    margin = fish_mod.MARGIN
  shift = min(1.0, max(0.0, shift))
  if margin <= MIN_SURFACE_MARGIN:
    return margin
  return margin + (MIN_SURFACE_MARGIN - margin) * shift
