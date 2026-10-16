"""The fish agent: where a fish goes and how it holds itself on the way.

Each step a fish blends what it wants into one desired direction:

- wander: a heading offset that drifts with smooth noise;
- depth: a target height that wanders within the species' depth band;
- the glass, sand and surface: pushed off when a look-ahead point gets
  near them, hardest when nearest;
- decor (tankful.sim.environment.obstacles) the same way, gentler for
  the soft plants;
- the other fish: kept apart, and drawn together when far apart.

It then turns toward that direction within its limits: a heading rate
that grows with speed up to max_turn_rate (a fish pivots slowly on the
spot and turns tightest when swimming), and a pitch kept within
max_pitch.  It banks into turns, and swims in strokes and glides: it
strokes (and speeds up) when it is slower than it wants, and coasts,
slowing with drag, when faster.  Now and then it hovers: it stops nearly
still and holds itself with its fins.

Hard limits back the steering up: the center never leaves the swim box
or enters the decor, whatever a step's dt.

Coordinates as in tankful.sim.tank: x to the viewer's right, y away from
the viewer, z up.  yaw is the heading about z from +x, counterclockwise
seen from above; pitch is nose up; roll is about the fish's own forward
axis, positive rolling its back toward its right side.
"""

import math
import random

from tankful.sim import environment as env
from tankful.sim import vec
from tankful.sim.noise import SmoothNoise

CRUISE, HOVER = 'cruise', 'hover'

# The longest step taken at once, so a frame hitch cannot fling a fish
MAX_STEP = 0.1
# How far ahead of its walls and decor a fish starts to steer
MARGIN = 0.10
# Fish nearer than this many lengths (the longer one's) push apart;
# farther than COHESION meters they drift together
SEPARATION = 1.4
COHESION = 0.40
# Closer than this many lengths and fish are moved apart outright
MIN_GAP = 0.75
# At least this long cruising between hovers
MIN_CRUISE = 6.0


class Fish:

  # The tankful.sim.school.School the fish swims in, if any
  school = None

  def __init__(self, name, species, size=1.0, seed=0, position=(0, 0, 0.25),
               heading=0.0):
    self.name = name
    self.species = species
    self.size = size
    self.rng = random.Random(seed)
    self.x, self.y, self.z = position
    self.yaw = heading
    self.pitch = 0.0
    self.roll = 0.0
    self.speed = species.cruise_speed * 0.6
    self.yaw_rate = 0.0
    self.mode = CRUISE
    self.mode_time = 0.0
    self.hover_left = 0.0
    self.stroking = True
    self.stroke = 0.5
    self.time = 0.0
    self.danger = 0.0
    # Gait, read by tankful.sim.swim
    self.beat_phase = self.rng.uniform(0, 2 * math.pi)
    self.fin_phase = self.rng.uniform(0, 2 * math.pi)
    self.beat_freq = species.beat_base
    self.wave = species.wave_min
    self.fin_amp = 0.0
    self.hovering = 0.0
    self._reverse = 0
    self._wander = SmoothNoise(seed * 7 + 1, species.wander_frequency)
    self._depth = SmoothNoise(seed * 7 + 2, species.wander_frequency * 0.5)
    self._pace = SmoothNoise(seed * 7 + 3, species.wander_frequency * 1.3)
    self._obstacles = env.obstacles()
    # Each obstacle's bounding box, to pass over the far ones quickly
    self._boxes = [tuple((min(o.a[i], o.b[i]) - o.radius,
                          max(o.a[i], o.b[i]) + o.radius) for i in range(3))
                   for o in self._obstacles]
    self._limit_position()

  # Limits, scaled with the fish

  @property
  def length(self):
    return self.species.length * self.size

  @property
  def max_speed(self):
    return self.species.max_speed * self.size

  @property
  def cruise_speed(self):
    return self.species.cruise_speed * self.size

  def max_turn(self, speed=None):
    """The fastest heading change, in rad/s, at speed (default: now)."""
    s = self.species
    speed = self.speed if speed is None else speed
    return min(s.max_turn_rate,
               s.pivot_rate + speed / (s.turn_radius * self.size))

  def bounds(self, x=None, y=None):
    """((xmin, xmax), (ymin, ymax), (zmin, zmax)) for the center.

    The floor follows the sand under x, y (default: the fish's own)."""
    s = self.species
    x = self.x if x is None else x
    y = self.y if y is None else y
    bx = env.INNER_X - s.clear_front * self.size
    by = env.INNER_Y - s.clear_side * self.size
    up = s.clear_up * self.size
    floor = env.sand_height(vec.clamp(x, -bx, bx), vec.clamp(y, -by, by))
    return ((-bx, bx), (-by, by), (floor + up, env.WATER_LEVEL - up))

  def clearance(self, obstacle):
    """How near the center may come to an obstacle's axis."""
    pad = self.species.clear_side * self.size * (0.5 if obstacle.soft else 1.0)
    return obstacle.radius + pad

  def _obstacles_near(self, pos, pad):
    """The obstacles that may come within the fish's clearance plus pad
    of pos."""
    reach = pad + self.species.clear_side * self.size
    x, y, z = pos
    for obstacle, ((x0, x1), (y0, y1), (z0, z1)) in zip(self._obstacles,
                                                        self._boxes):
      if (x0 - reach < x < x1 + reach and y0 - reach < y < y1 + reach
          and z0 - reach < z < z1 + reach):
        yield obstacle

  # The step

  def step(self, dt, others=()):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    dt = min(dt, MAX_STEP)
    if dt == 0:
      return
    self.time += dt
    self.mode_time += dt
    self._update_mode(dt)
    want, z_want = self._desired(others)
    self._turn(dt, want)
    self._pitch(dt, want)
    self._swim(dt, want)
    fwd = self.forward()
    self.x += fwd[0] * self.speed * dt
    self.y += fwd[1] * self.speed * dt
    self.z += fwd[2] * self.speed * dt
    # Hovering, the fins hold the depth: a slow drift toward the target
    if self.mode == HOVER:
      self.z += vec.clamp(z_want - self.z, -1, 1) * 0.02 * dt
    self._keep_apart(others)
    self._limit_position()
    self._bank(dt)
    self._gait(dt)

  def _update_mode(self, dt):
    s = self.species
    if self.mode == HOVER:
      self.hover_left -= dt
      if self.hover_left <= 0 or self.danger > 0.8:
        self.mode, self.mode_time = CRUISE, 0.0
    elif (self.mode_time > MIN_CRUISE and self.danger < 0.5
          and self.rng.random() < s.hover_chance * dt):
      self.mode, self.mode_time = HOVER, 0.0
      self.hover_left = self.rng.uniform(*s.hover_time)

  def _desired(self, others):
    """The direction the fish wants to go (a unit vector), and its target
    height."""
    s = self.species
    wander = self._wander(self.time) * s.wander_turn
    if self.mode == HOVER:
      wander *= 0.4
    h = self.yaw + wander
    want = [math.cos(h), math.sin(h), 0.0]
    z_want = self._depth_target()
    want[2] = vec.clamp((z_want - self.z) / 0.08, -1.0, 1.0) * 0.45
    self.danger = self._steer_clear(want)
    self._mind_others(want, others)
    return vec.normalized(tuple(want), self.forward()), z_want

  def _depth_target(self):
    lo, hi = self.species.depth_band
    _, _, (z0, z1) = self.bounds()
    frac = lo + (hi - lo) * (0.5 + 0.5 * self._depth(self.time))
    return z0 + (z1 - z0) * frac

  def _steer_clear(self, want):
    """Add to want the pushes off the glass, sand, surface and decor near
    the fish or a look-ahead point; return how near the nearest is (0 to
    1, the danger)."""
    pos = (self.x, self.y, self.z)
    (x0, x1), (y0, y1), (z0, z1) = self.bounds()
    # Look ahead along the heading, further when faster
    look = 0.04 + self.speed * 1.2
    fwd = self.forward()
    ahead = (self.x + fwd[0] * look, self.y + fwd[1] * look,
             self.z + fwd[2] * look)
    danger = 0.0
    top = self.species.surface_margin
    if top is None:
      top = MARGIN
    for axis, (a, b) in enumerate(((x0, x1), (y0, y1), (z0, z1))):
      # The surface's margin is the species' own
      hi = top if axis == 2 else MARGIN
      for p in (pos[axis], ahead[axis]):
        near_lo = (a + MARGIN - p) / MARGIN
        near_hi = (p - (b - hi)) / hi
        for near, sign in ((near_lo, 1.0), (near_hi, -1.0)):
          if near > 0:
            w = min(near, 1.5) ** 2 * 2.0
            want[axis] += sign * w
            danger = max(danger, min(1.0, near))

    for obstacle in self._obstacles_near(pos, MARGIN + look):
      clear = self.clearance(obstacle)
      for p in (pos, ahead):
        c = vec.closest_on_segment(p, obstacle.a, obstacle.b)
        off = vec.sub(p, c)
        gap = vec.length(off) - clear
        if gap < MARGIN:
          near = 1.0 - gap / MARGIN
          w = min(near, 1.5) ** 2 * (0.9 if obstacle.soft else 1.8)
          away = vec.normalized(off, (-fwd[0], -fwd[1], 0.0))
          for axis in range(3):
            want[axis] += away[axis] * w
          danger = max(danger, min(1.0, near) * (0.5 if obstacle.soft else 1))
    return danger

  def _mind_others(self, want, others, skip=()):
    """Add to want the pull apart from fish too near, and, for fish of
    its own species, together when far apart.  A much smaller fish of
    another kind pushes less."""
    fwd = self.forward()
    for other in others:
      if other is self or other in skip:
        continue
      off = (self.x - other.x, self.y - other.y, self.z - other.z)
      d = vec.length(off)
      sep = SEPARATION * max(self.length, other.length)
      if d < sep:
        away = vec.normalized(off, (-fwd[0], -fwd[1], 0.0))
        w = (1.0 - d / sep) ** 2 * 3.0
        if other.species is not self.species:
          w *= min(1.0, other.length / self.length)
        for axis in range(3):
          want[axis] += away[axis] * w
      elif d > COHESION and other.species is self.species:
        toward = vec.scale(vec.normalized(off), -0.12)
        for axis in range(3):
          want[axis] += toward[axis]

  def _turn(self, dt, want):
    s = self.species
    flat = math.hypot(want[0], want[1])
    if flat < 1e-3:
      err = 0.0
    else:
      err = vec.wrap_angle(math.atan2(want[1], want[0]) - self.yaw)
    # Wanting to go nearly backward, the fish commits to one way round
    # instead of dithering between the two
    if abs(err) > 2.6:
      if not self._reverse:
        to_center = math.atan2(-self.y, -self.x)
        self._reverse = 1 if vec.wrap_angle(to_center - self.yaw) >= 0 else -1
      err = self._reverse * abs(err)
    elif abs(err) < 2.0:
      self._reverse = 0
    limit = self.max_turn()
    if self.mode == HOVER:
      limit = min(limit, s.pivot_rate * 0.5)
    target = vec.clamp(err * 1.4, -limit, limit)
    step = s.turn_accel * dt
    self.yaw_rate += vec.clamp(target - self.yaw_rate, -step, step)
    self.yaw_rate = vec.clamp(self.yaw_rate, -limit, limit)
    self.yaw = vec.wrap_angle(self.yaw + self.yaw_rate * dt)

  def _pitch(self, dt, want):
    s = self.species
    flat = math.hypot(want[0], want[1])
    target = math.atan2(want[2], max(flat, 1e-6))
    if self.mode == HOVER:
      target = 0.0
    # Slow fish climb by their fins rather than by tilting much
    target *= min(1.0, 0.35 + self.speed / self.cruise_speed)
    target = vec.clamp(target, -s.max_pitch, s.max_pitch)
    step = s.pitch_rate * dt
    self.pitch += vec.clamp(target - self.pitch, -step, step)
    self.pitch = vec.clamp(self.pitch, -s.max_pitch, s.max_pitch)

  def _swim(self, dt, want):
    s = self.species
    target, glide = self._target_speed(want)
    # Burst and glide: stroke up past the target, then coast down below it
    if self.speed < target * 0.8:
      self.stroking = True
    elif self.speed > target * 1.1:
      self.stroking = False
    rate = 2.5 if self.stroking else 1.2
    goal = 1.0 if self.stroking else 0.0
    self.stroke += vec.clamp(goal - self.stroke, -rate * dt, rate * dt)
    top = self.max_speed
    accel = (s.thrust * self.size * self.stroke * (1.0 - self.speed / top)
             - self.speed / glide)
    self.speed = vec.clamp(self.speed + accel * dt, 0.0, top)

  def _target_speed(self, want):
    """The speed the fish strokes toward, and its glide time."""
    s = self.species
    if self.mode == HOVER:
      return s.hover_speed * self.size, s.glide_time * 0.35
    pace = 0.8 + 0.35 * self._pace(self.time)
    fwd = self.forward()
    # Slow down to turn hard, and near walls and decor
    along = vec.dot(fwd, want)
    target = (self.cruise_speed * pace * (0.55 + 0.45 * max(0.0, along))
              * (1.0 - 0.45 * self.danger))
    return target, s.glide_time

  def _bank(self, dt):
    s = self.species
    # Into the turn: turning left (yaw_rate > 0), the back leans left
    lean = self.yaw_rate * self.speed / (0.8 * self.cruise_speed)
    target = -s.max_bank * vec.clamp(lean, -1.0, 1.0)
    step = s.roll_rate * dt
    self.roll += vec.clamp(target - self.roll, -step, step)
    self.roll = vec.clamp(self.roll, -s.max_bank, s.max_bank)

  def _gait(self, dt):
    s = self.species
    # Tail beats come faster with speed, and swing wider while stroking
    rel = self.speed / self.length
    self.beat_freq = s.beat_base + s.beat_per_speed * rel
    pace = vec.clamp(self.speed / self.cruise_speed, 0.0, 1.0)
    swing = s.wave_min + (s.wave_max - s.wave_min) * pace
    self.wave = swing * (0.12 + 0.88 * self.stroke)
    self.beat_phase = (self.beat_phase
                       + 2 * math.pi * self.beat_freq * dt) % (2 * math.pi)
    # The pectorals take over as the fish slows: fin-only hovering
    goal = 1.0 - pace
    self.hovering += vec.clamp(goal - self.hovering, -dt, dt)
    self.fin_amp = s.fin_swing * (0.2 + 0.8 * self.hovering)
    fin_freq = s.fin_beat * (0.6 + 0.4 * self.hovering)
    self.fin_phase = (self.fin_phase
                      + 2 * math.pi * fin_freq * dt) % (2 * math.pi)

  def _keep_apart(self, others):
    for other in others:
      if other is self:
        continue
      off = (self.x - other.x, self.y - other.y, self.z - other.z)
      d = vec.length(off)
      if other.species is self.species:
        gap = MIN_GAP * max(self.length, other.length)
        share = 0.5
      else:
        gap = MIN_GAP * 0.5 * (self.length + other.length)
        share = other.length / (self.length + other.length)
      if d < gap:
        # Each fish takes its share of the overlap on its own step: half,
        # or the smaller fish most of it
        away = vec.normalized(off, (0.0, 1.0 if self.y >= other.y else -1.0,
                                    0.0))
        push = vec.scale(away, (gap - d) * share)
        self.x, self.y, self.z = vec.add((self.x, self.y, self.z), push)

  def _limit_position(self):
    """Into the swim box and out of the decor.  The box wins: in a corner
    that a clump crowds, the fish may stay a little in the clump until it
    steers out."""
    for _ in range(4):
      self._clamp_to_bounds()
      pos = (self.x, self.y, self.z)
      moved = False
      for obstacle in self._obstacles_near(pos, 0.0):
        c = vec.closest_on_segment(pos, obstacle.a, obstacle.b)
        off = vec.sub(pos, c)
        clear = self.clearance(obstacle)
        if vec.length(off) < clear:
          # Out the nearest way; straight up from inside the axis
          away = vec.normalized(off, (0.0, 0.0, 1.0))
          pos = vec.add(c, vec.scale(away, clear))
          moved = True
      self.x, self.y, self.z = pos
      if not moved:
        return
    self._clamp_to_bounds()

  def _clamp_to_bounds(self):
    (x0, x1), (y0, y1), (z0, z1) = self.bounds()
    self.x = vec.clamp(self.x, x0, x1)
    self.y = vec.clamp(self.y, y0, y1)
    self.z = vec.clamp(self.z, z0, z1)

  # Pose

  def forward(self):
    cp = math.cos(self.pitch)
    return (cp * math.cos(self.yaw), cp * math.sin(self.yaw),
            math.sin(self.pitch))

  def orientation(self):
    """The 3x3 rotation (rows) from the fish's space to the world's.

    The fish's +x is forward, +y its left side and +z its back:
    Rz(yaw) Ry(-pitch) Rx(roll).
    """
    cy, sy = math.cos(self.yaw), math.sin(self.yaw)
    cp, sp = math.cos(self.pitch), math.sin(self.pitch)
    cr, sr = math.cos(self.roll), math.sin(self.roll)
    # Ry(-pitch) Rx(roll), then turned by the yaw
    m = ((cp, -sp * sr, -sp * cr),
         (0.0, cr, -sr),
         (sp, cp * sr, cp * cr))
    return (tuple(cy * m[0][j] - sy * m[1][j] for j in range(3)),
            tuple(sy * m[0][j] + cy * m[1][j] for j in range(3)),
            m[2])

  def snapshot(self):
    return {
      'name': self.name,
      'species': self.species.name,
      'position': [round(v, 4) for v in (self.x, self.y, self.z)],
      'yaw': round(self.yaw, 4),
      'pitch': round(self.pitch, 4),
      'roll': round(self.roll, 4),
      'speed': round(self.speed, 4),
      'mode': self.mode,
      'stroke': round(self.stroke, 3),
    }


def stock(tank, residents):
  """Add a Fish for each of residents (tankful.sim.species.base.Resident)
  to tank, and return them."""
  out = []
  for r in residents:
    x, y, z, heading = r.start
    out.append(Fish(r.name, r.species, r.size, r.seed, (x, y, z), heading))
  tank.fish.extend(out)
  return out
