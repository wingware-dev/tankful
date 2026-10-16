"""The tank: the root of the simulation state."""


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
    self.light_on = True

  def step(self, dt):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    self.time += dt
    self.frame += 1
    for fish in self.fish:
      fish.step(dt, self.fish)

  def snapshot(self):
    """Return the state as plain JSON-able data, for harness assertions."""
    return {
      'time': round(self.time, 4),
      'frame': self.frame,
      'size': [self.width, self.depth, self.height],
      'light_on': self.light_on,
      'fish': [f.snapshot() for f in self.fish],
    }
