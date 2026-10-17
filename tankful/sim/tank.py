"""The tank: the root of the simulation state."""

from tankful.sim import daynight

# The steps the external factor's speed scale and depth shift are taken
# in (set_factor): each step is a new species for the fish, so an easing
# value settles instead of making a new one every frame
FACTOR_STEP = 0.01


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
    # Each fish's and school's own species, while it swims a scaled one
    self._own_species = {}
    self._factor_species = {}

  @property
  def light_on(self):
    return self.light.on

  def set_factor(self, speed_scale=1.0, depth_shift=0.0):
    """Scale the fish's speeds by speed_scale and shift their depth bands
    by depth_shift (-1 to the sand, 0 none, +1 to the surface), as an
    external factor's Effects say, from the next step."""
    self.speed_scale = round(speed_scale / FACTOR_STEP) * FACTOR_STEP
    self.depth_shift = round(depth_shift / FACTOR_STEP) * FACTOR_STEP

  def _apply_factor(self):
    # Each fish and school swims as a copy of its species with the
    # factor in, shared by all of its kind (they tell each other apart by
    # species), and its own again once the factor is neutral
    neutral = self.speed_scale == 1.0 and self.depth_shift == 0.0
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
      key = (own, self.speed_scale, self.depth_shift)
      species = self._factor_species.get(key)
      if species is None:
        species = factor_species(own, self.speed_scale, self.depth_shift)
        self._factor_species[key] = species
      swimmer.species = species

  def step(self, dt):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    self.time += dt
    self.frame += 1
    self.light.step(dt)
    if self._own_species or self.speed_scale != 1.0 or self.depth_shift:
      self._apply_factor()
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
                 'depth_shift': round(self.depth_shift, 3)},
      'fish': [f.snapshot() for f in self.fish],
      'schools': [s.snapshot() for s in self.schools],
    }


def shift_band(band, shift):
  """A depth band (lo, hi, fractions from the sand to the surface) moved
  by shift: toward the surface for shift above 0, all the way up at 1,
  and toward the sand below 0, all the way down at -1.  Its width stays."""
  lo, hi = band
  shift = min(1.0, max(-1.0, shift))
  move = shift * (1.0 - hi) if shift > 0 else shift * lo
  return (lo + move, hi + move)


def factor_species(species, speed_scale, depth_shift):
  """species (a tankful.sim.species.base.Species) with its speeds scaled
  and its depth bands, by day and by night, shifted."""
  changes = {'hover_speed': species.hover_speed * speed_scale,
             'cruise_speed': species.cruise_speed * speed_scale,
             'max_speed': species.max_speed * speed_scale,
             'depth_band': shift_band(species.depth_band, depth_shift)}
  night = species.night
  if night is not None and night.depth_band is not None:
    changes['night'] = night._replace(
      depth_band=shift_band(night.depth_band, depth_shift))
  return species._replace(**changes)
