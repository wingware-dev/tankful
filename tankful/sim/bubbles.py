"""The airstone's bubble stream, as a fixed pool of bubbles.

The game makes one object per pool slot up front and only moves, scales
and hides them, so a stream never adds or frees objects at run time.  A
bubble is emitted into a free slot, rises with a helical wobble that
widens as it goes, grows a little as the pressure drops, and pops at the
surface: it swells for POP_TIME and frees its slot.  With every slot
busy, the emission waits for one.
"""

import math
import random

FREE, RISING, POPPING = 'free', 'rising', 'popping'

# The longest step taken at once: a frame hitch (or the scene load before
# the first frame) must not launch a burst of bubbles at once
MAX_STEP = 0.1
POP_TIME = 0.12
POP_SWELL = 0.6
# The pool size the scene is built with: one bubble object per slot
CAPACITY = 48


class Bubble:

  __slots__ = ('state', 'x', 'y', 'z', 'radius', 'base_radius', 'age',
               'pop_age', 'origin', 'wobble', 'phase', 'freq', 'speed')

  def __init__(self):
    self.state = FREE
    self.x = self.y = self.z = 0.0
    self.radius = self.base_radius = 0.0
    self.age = self.pop_age = 0.0
    self.origin = (0.0, 0.0, 0.0)
    self.wobble = self.phase = self.freq = self.speed = 0.0

  @property
  def active(self):
    return self.state != FREE

  @property
  def pop_progress(self):
    """0 to 1 through the pop, 0 before it."""
    return min(1.0, self.pop_age / POP_TIME) if self.state == POPPING else 0.0


class BubblePool:
  """A stream of up to capacity bubbles from source up to surface_z.

  rate is bubbles per second; radius_range the radius at the source, in
  meters.  seed makes the stream repeatable.
  """

  def __init__(self, source, surface_z, capacity=CAPACITY, rate=18.0,
               radius_range=(0.0025, 0.006), seed=0):
    if capacity < 1:
      raise ValueError('capacity must be at least 1: %r' % capacity)
    if rate < 0:
      raise ValueError('rate must not be negative: %r' % rate)
    if surface_z <= source[2]:
      raise ValueError('the surface must be above the source')
    self.source = tuple(source)
    self.surface_z = surface_z
    self.rate = rate
    self.radius_range = radius_range
    self.bubbles = [Bubble() for _ in range(capacity)]
    self.rng = random.Random(seed)
    self.time = 0.0
    self.emitted = 0
    self.popped = 0
    self.stalled = 0
    self._next_emit = 0.0

  @property
  def capacity(self):
    return len(self.bubbles)

  def active(self):
    return [b for b in self.bubbles if b.active]

  def step(self, dt):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    while dt > 0:
      h = min(dt, MAX_STEP)
      self._step(h)
      dt -= h
      # Beyond one long step the rest is lost time, not simulated time
      if h == MAX_STEP:
        break

  def _step(self, dt):
    self.time += dt
    for b in self.bubbles:
      if b.state == RISING:
        self._rise(b, dt)
      elif b.state == POPPING:
        b.pop_age += dt
        b.radius = b.base_radius * (1 + POP_SWELL * b.pop_progress)
        if b.pop_age >= POP_TIME:
          b.state = FREE
          self.popped += 1
    if self.rate > 0:
      while self._next_emit <= self.time:
        if not self._emit():
          self.stalled += 1
          self._next_emit = self.time + 0.5 / self.rate
          break
        # Exponential gaps make the stream uneven, as a real one is
        self._next_emit += self.rng.expovariate(self.rate)

  def _emit(self):
    for b in self.bubbles:
      if b.state == FREE:
        break
    else:
      return False
    rng = self.rng
    lo, hi = self.radius_range
    # More small bubbles than big ones
    b.base_radius = lo + (hi - lo) * rng.random() ** 2
    b.radius = b.base_radius
    sx, sy, sz = self.source
    b.origin = (sx + rng.uniform(-0.006, 0.006),
                sy + rng.uniform(-0.003, 0.003), sz)
    b.x, b.y, b.z = b.origin
    b.age = b.pop_age = 0.0
    b.phase = rng.uniform(0, 2 * math.pi)
    b.freq = rng.uniform(2.5, 4.5)
    b.wobble = rng.uniform(0.6, 1.4)
    # Terminal speed of small bubbles grows with size: about 0.2 to 0.3 m/s
    b.speed = 0.17 + 20.0 * b.base_radius + rng.uniform(-0.01, 0.01)
    b.state = RISING
    self.emitted += 1
    return True

  def _rise(self, b, dt):
    b.age += dt
    b.z += b.speed * dt
    sz = self.source[2]
    risen = max(0.0, (b.z - sz) / (self.surface_z - sz))
    # The wobble starts small and widens as the bubble rises
    amp = b.wobble * (0.0015 + 0.006 * risen)
    angle = 2 * math.pi * b.freq * b.age + b.phase
    ox, oy, _ = b.origin
    b.x = ox + amp * math.sin(angle)
    b.y = oy + 0.7 * amp * math.cos(angle * 1.3)
    b.radius = b.base_radius * (1 + 0.15 * risen)
    if b.z + b.radius >= self.surface_z:
      b.z = self.surface_z - 0.4 * b.radius
      b.state = POPPING
      b.pop_age = 0.0

  def snapshot(self):
    return {
      'active': sum(1 for b in self.bubbles if b.active),
      'capacity': self.capacity,
      'emitted': self.emitted,
      'popped': self.popped,
      'stalled': self.stalled,
    }
