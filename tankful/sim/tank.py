"""The tank: the root of the simulation state."""

from tankful.sim import daynight


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

  @property
  def light_on(self):
    return self.light.on

  def step(self, dt):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    self.time += dt
    self.frame += 1
    self.light.step(dt)
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
      'fish': [f.snapshot() for f in self.fish],
      'schools': [s.snapshot() for s in self.schools],
    }
