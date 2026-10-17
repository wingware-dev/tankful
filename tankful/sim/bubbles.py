"""The airstone's bubble stream, as a fixed pool of bubbles.

The game makes one object per pool slot up front and only moves, scales
and hides them, so a stream never adds or frees objects at run time.  A
bubble is emitted into a free slot, rises with a helical wobble that
widens as it goes, grows a little as the pressure drops, and pops at the
surface: it swells for POP_TIME and frees its slot.  With every slot
busy, the emission waits for one.

Each pop is reported in BubblePool.pop_events, for a RipplePool: a fixed
pool of rings that spread on the surface from where bubbles popped, and
fade, so the pop reads at the tank's scale.
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

# A ripple spreads from where a bubble popped for RIPPLE_TIME, from
# RIPPLE_START of RIPPLE_RADIUS out to all of it, fading as it goes.  The
# pops are at the back of the tank, where the viewer sees the surface
# nearly edge on, so the rings spread wide to read at all.  The scene
# draws all RIPPLES of them on one object, through its color's red, green
# and blue (tools/scene_env.py, build_ripples, which repeats spread and
# strength below in its shader): a pop while all are busy makes no
# ripple, and with several pops a second, a few rings at a time read as
# well as one per pop
RIPPLE_TIME = 1.0
RIPPLE_RADIUS = 0.045
RIPPLE_START = 0.12
RIPPLES = 3

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
    # (x, y, radius) of each bubble that reached the surface during the
    # last step() call
    self.pop_events = []
    self._next_emit = 0.0

  @property
  def capacity(self):
    return len(self.bubbles)

  def active(self):
    return [b for b in self.bubbles if b.active]

  def step(self, dt):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    self.pop_events = []
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
      self.pop_events.append((b.x, b.y, b.base_radius))

  def snapshot(self):
    return {
      'active': sum(1 for b in self.bubbles if b.active),
      'capacity': self.capacity,
      'emitted': self.emitted,
      'popped': self.popped,
      'stalled': self.stalled,
    }


class Ripple:

  __slots__ = ('active', 'x', 'y', 'age')

  def __init__(self):
    self.active = False
    self.x = self.y = self.age = 0.0

  @property
  def progress(self):
    """0 to 1 through the ripple, and 1 when there is none."""
    return min(1.0, self.age / RIPPLE_TIME) if self.active else 1.0

  @property
  def spread(self):
    """The ring's radius as a fraction of RIPPLE_RADIUS: quick at first,
    slowing as it spreads."""
    ease = 1.0 - (1.0 - self.progress) ** 2
    return RIPPLE_START + (1.0 - RIPPLE_START) * ease

  @property
  def radius(self):
    return RIPPLE_RADIUS * self.spread

  @property
  def strength(self):
    """How bright the ring is, 1 fading to 0."""
    return (1.0 - self.progress) ** 1.5


class RipplePool:
  """Up to capacity ripples on the surface, one started per pop while
  a slot is free."""

  def __init__(self, capacity=RIPPLES):
    if capacity < 1:
      raise ValueError('capacity must be at least 1: %r' % capacity)
    self.ripples = [Ripple() for _ in range(capacity)]
    self.started = 0
    self.skipped = 0

  @property
  def capacity(self):
    return len(self.ripples)

  def start(self, x, y):
    """A ripple at (x, y), in a free slot; None, and none started, with
    every slot busy."""
    for r in self.ripples:
      if not r.active:
        break
    else:
      self.skipped += 1
      return None
    r.active = True
    r.x, r.y, r.age = x, y, 0.0
    self.started += 1
    return r

  def step(self, dt):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    for r in self.ripples:
      if r.active:
        r.age += dt
        if r.age >= RIPPLE_TIME:
          r.active = False

  def progresses(self):
    """Each slot's Ripple.progress, in slot order: 1 for a free one."""
    return tuple(r.progress for r in self.ripples)

  def snapshot(self):
    return {
      'active': sum(1 for r in self.ripples if r.active),
      'capacity': self.capacity,
      'started': self.started,
      'skipped': self.skipped,
    }
