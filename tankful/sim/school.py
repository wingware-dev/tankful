"""Schools: small fish that swim as one group, such as the neon tetras.

A School is a group object in its own right: it has a name and its
members, and it is what the user will select when they pick any one of
them (step 9).  It leads its members with a goal, a point that wanders
the open water like a fish of its own: it drifts with smooth noise,
keeps to the species' depth band, turns away from the glass and the
decor in good time (it keeps a school's width clear of them), and now
and then swings round hard, so that the school turns as a group behind
it.

Each member (Member, a tankful.sim.fish.Fish) blends the boids rules
with the goal:

- separation: away from schoolmates nearer than SPACING lengths;
- alignment: toward the heading of the mates it can see (within VIEW);
- cohesion: toward their center;
- the goal: toward it, harder the farther off it is, swimming faster
  when it is ahead and easing off when it is behind;

then, as any fish, the pushes off the glass, sand, surface and decor,
and away from fish outside the school.  Now and then a member flicks: a
quick dart aside at a burst of speed, after which the rules draw it
back in.  The members' bodies (capsules along their spines) never
overlap: whatever the steering does, each step ends by pushing apart
any that touch (School.settle).
"""

import collections
import math
import random

from tankful.sim import environment as env
from tankful.sim import vec
from tankful.sim.fish import MAX_STEP, Fish
from tankful.sim.noise import SmoothNoise
from tankful.sim.species.base import Resident

# A school: its name, its species, how many, a seed for their sizes and
# places, and where it starts (x, y, z, heading)
SchoolSpec = collections.namedtuple('SchoolSpec',
                                    'name species count seed start')

# Boids, in body lengths: members keep SPACING apart, and heed the mates
# within VIEW
SPACING = 1.7
VIEW = 4.5
W_SEPARATION = 2.6
W_ALIGNMENT = 0.8
W_COHESION = 0.55
W_GOAL = 1.0
# How much of its own heading, and of its own wander, a member keeps
W_INERTIA = 0.5
# The body capsule, in lengths: from BODY_FRONT ahead of the center to
# BODY_BACK behind it, BODY_RADIUS round; the tail fin bends and is left
# out
BODY_FRONT, BODY_BACK, BODY_RADIUS = 0.42, 0.30, 0.09
# How long a flick lasts (s)
FLICK_TIME = 0.35
# The goal: its speed as a fraction of the members' cruise, its turn
# rate, and its rate when swinging round (rad/s)
GOAL_SPEED = 0.75
GOAL_TURN = 0.6
GOAL_SWING_TURN = 1.3
# How far from the walls and decor (beyond the school's radius) the goal
# starts to turn away (m)
GOAL_MARGIN = 0.10
# How often (per s) the goal swings round, and by how much (rad)
SWING_CHANCE = 1 / 15.0
SWING = (1.4, 2.6)
# The goal keeps in front of this y: the back of the tank is planted, and
# a school in open water is one the viewer sees
OPEN_BACK = 0.04


class School:

  def __init__(self, name, species, seed=0, start=(0.0, 0.0, 0.25, 0.0)):
    self.name = name
    self.species = species
    self.members = []
    self._member_set = set()
    x, y, z, heading = start
    self.goal = (x, y, z)
    self.yaw = heading
    self.speed = species.cruise_speed * GOAL_SPEED
    self.time = 0.0
    self.danger = 0.0
    self.swing = 0.0
    self.rng = random.Random(seed)
    self._wander = SmoothNoise(seed * 7 + 4, 0.05)
    self._depth = SmoothNoise(seed * 7 + 5, 0.03)
    self._obstacles = env.obstacles()

  def add(self, fish):
    fish.school = self
    self.members.append(fish)
    self._member_set.add(fish)

  def __contains__(self, fish):
    return fish in self._member_set

  @property
  def radius(self):
    """About how far the members spread from the school's center."""
    n = max(1, len(self.members))
    return 0.5 * SPACING * self.species.length * n ** (1 / 3.0)

  def centroid(self):
    n = len(self.members)
    if not n:
      return self.goal
    return tuple(sum(getattr(f, a) for f in self.members) / n
                 for a in 'xyz')

  def spread(self):
    """The members' mean distance from the centroid."""
    if not self.members:
      return 0.0
    c = self.centroid()
    return (sum(math.dist((f.x, f.y, f.z), c) for f in self.members)
            / len(self.members))

  def bounds(self):
    """((xmin, xmax), (ymin, ymax), (zmin, zmax)) for the goal: the
    members' swim box, less some of the school's width, and in front of
    the planted back (OPEN_BACK)."""
    s = self.species
    r = self.radius
    bx = env.INNER_X - s.clear_front - r
    by = env.INNER_Y - s.clear_side - 0.6 * r
    x, y, _ = self.goal
    floor = env.sand_height(vec.clamp(x, -bx, bx), vec.clamp(y, -by, by))
    return ((-bx, bx), (-by, min(by, OPEN_BACK)),
            (floor + s.clear_up + 0.5 * r, env.WATER_LEVEL - s.clear_up - r))

  # The step

  def step(self, dt):
    """Move the goal.  The tank steps the members after this."""
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    dt = min(dt, MAX_STEP)
    if dt == 0:
      return
    self.time += dt
    if not self.swing and self.rng.random() < SWING_CHANCE * dt:
      self.swing = self.rng.choice((-1, 1)) * self.rng.uniform(*SWING)
    want = self._goal_want()
    if self.swing:
      turn = math.copysign(min(abs(self.swing), GOAL_SWING_TURN * dt),
                           self.swing)
      self.swing -= turn
      if abs(self.swing) < 1e-6:
        self.swing = 0.0
    else:
      err = vec.wrap_angle(math.atan2(want[1], want[0]) - self.yaw)
      turn = vec.clamp(err * 1.5, -GOAL_TURN, GOAL_TURN) * dt
    self.yaw = vec.wrap_angle(self.yaw + turn)
    self.speed = (self.species.cruise_speed * GOAL_SPEED
                  * (1.0 - 0.5 * self.danger))
    x, y, z = self.goal
    x += math.cos(self.yaw) * self.speed * dt
    y += math.sin(self.yaw) * self.speed * dt
    z += vec.clamp(self._depth_target() - z, -1.0, 1.0) * 0.4 * dt
    self.goal = (x, y, z)
    self._limit_goal()

  def _depth_target(self):
    lo, hi = self.species.depth_band
    _, _, (z0, z1) = self.bounds()
    return z0 + (z1 - z0) * (lo + (hi - lo) * (0.5 + 0.5 *
                                               self._depth(self.time)))

  def _goal_want(self):
    """Where the goal wants to head, flat: its wander, turned away from
    the glass and decor near it or ahead."""
    h = self.yaw + self._wander(self.time) * 0.8
    want = [math.cos(h), math.sin(h)]
    x, y, z = self.goal
    look = 0.08
    ahead = (x + math.cos(self.yaw) * look, y + math.sin(self.yaw) * look)
    (x0, x1), (y0, y1), _ = self.bounds()
    m = GOAL_MARGIN
    danger = 0.0
    for axis, (a, b) in enumerate(((x0, x1), (y0, y1))):
      for p in ((x, y)[axis], ahead[axis]):
        for near, sign in (((a + m - p) / m, 1.0), ((p - (b - m)) / m, -1.0)):
          if near > 0:
            want[axis] += sign * min(near, 1.5) ** 2 * 2.0
            danger = max(danger, min(1.0, near))
    pad = self._decor_pad()
    for obstacle in self._obstacles:
      if obstacle.b[2] < z - self.radius:
        continue
      for p in ((x, y), ahead):
        c = vec.closest_on_segment((p[0], p[1], z), obstacle.a, obstacle.b)
        off = (p[0] - c[0], p[1] - c[1])
        gap = math.hypot(*off) - obstacle.radius - pad
        if gap < m:
          near = 1.0 - gap / m
          w = min(near, 1.5) ** 2 * 1.5
          away = vec.normalized((off[0], off[1], 0.0),
                                (-math.cos(self.yaw), -math.sin(self.yaw), 0))
          want[0] += away[0] * w
          want[1] += away[1] * w
          danger = max(danger, min(1.0, near))
    self.danger = danger
    return want

  def _decor_pad(self):
    # A school's width from the decor: any less and the members on its
    # flank catch on the driftwood and fall behind
    return self.species.clear_side + self.radius

  def _limit_goal(self):
    pad = self._decor_pad()
    for _ in range(3):
      (x0, x1), (y0, y1), (z0, z1) = self.bounds()
      x, y, z = self.goal
      x, y, z = vec.clamp(x, x0, x1), vec.clamp(y, y0, y1), vec.clamp(z, z0,
                                                                      z1)
      moved = False
      for obstacle in self._obstacles:
        c = vec.closest_on_segment((x, y, z), obstacle.a, obstacle.b)
        off = (x - c[0], y - c[1], z - c[2])
        clear = obstacle.radius + pad
        if vec.length(off) < clear:
          away = vec.normalized(off, (0.0, 0.0, 1.0))
          x, y, z = vec.add(c, vec.scale(away, clear))
          moved = True
      self.goal = (x, y, z)
      if not moved:
        break
    (x0, x1), (y0, y1), (z0, z1) = self.bounds()
    x, y, z = self.goal
    self.goal = (vec.clamp(x, x0, x1), vec.clamp(y, y0, y1),
                 vec.clamp(z, z0, z1))

  def settle(self):
    """Push apart members whose bodies touch, after they have all moved
    this step."""
    moved = set()
    for _ in range(4):
      again = False
      for i, a in enumerate(self.members):
        for b in self.members[i + 1:]:
          if a.part_from(b, 0.5):
            moved.update((a, b))
            again = True
      if not again:
        break
    for f in moved:
      f._limit_position()

  def snapshot(self):
    return {
      'name': self.name,
      'species': self.species.name,
      'members': [f.name for f in self.members],
      'goal': [round(v, 4) for v in self.goal],
      'yaw': round(self.yaw, 4),
      'swinging': bool(self.swing),
      'centroid': [round(v, 4) for v in self.centroid()],
      'spread': round(self.spread(), 4),
    }


class Member(Fish):
  """A fish in a school."""

  def __init__(self, name, species, school, size=1.0, seed=0,
               position=(0, 0, 0.25), heading=0.0):
    self.flick_left = 0.0
    self.flick_turn = 0.0
    self._catch = 1.0
    super().__init__(name, species, size, seed, position, heading)
    school.add(self)

  @property
  def flicking(self):
    return self.flick_left > 0

  def body(self):
    """The body capsule: (front, back, radius)."""
    f = self.forward()
    p = (self.x, self.y, self.z)
    length = self.length
    return (vec.add(p, vec.scale(f, BODY_FRONT * length)),
            vec.sub(p, vec.scale(f, BODY_BACK * length)),
            BODY_RADIUS * length)

  def part_from(self, other, share):
    """Move self away from other until their bodies no longer touch,
    by share of the overlap.  Whether it moved."""
    reach = (BODY_FRONT + BODY_RADIUS) * (self.length + other.length)
    dx, dy, dz = self.x - other.x, self.y - other.y, self.z - other.z
    if dx * dx + dy * dy + dz * dz >= reach * reach:
      return False
    a0, a1, ra = self.body()
    b0, b1, rb = other.body()
    p, q = vec.closest_between_segments(a0, a1, b0, b1)
    off = vec.sub(p, q)
    d = vec.length(off)
    gap = ra + rb
    if d >= gap:
      return False
    # Coincident axes: apart sideways, the same way every time
    away = vec.normalized(off, vec.normalized(
      (self.x - other.x, self.y - other.y, self.z - other.z),
      (0.0, 1.0 if self.y >= other.y else -1.0, 0.0)))
    # A little more than the overlap, so float rounding leaves a gap
    push = (gap - d) * 1.001 + 1e-9
    self.x += away[0] * push * share
    self.y += away[1] * push * share
    self.z += away[2] * push * share
    if share < 1.0:
      other.x -= away[0] * push * (1 - share)
      other.y -= away[1] * push * (1 - share)
      other.z -= away[2] * push * (1 - share)
    return True

  # The step, as for any fish but for these parts

  def _update_mode(self, dt):
    # Members never hover; now and then one flicks
    s = self.species
    if self.flick_left > 0:
      self.flick_left = max(0.0, self.flick_left - dt)
    elif self.danger < 0.3 and self.rng.random() < s.flick_chance * dt:
      self.flick_left = FLICK_TIME
      self.flick_turn = (self.rng.choice((-1, 1)) * s.flick_turn
                         * self.rng.uniform(0.6, 1.0))
      self.stroking = True
      self.stroke = 1.0

  def _desired(self, others):
    s = self.species
    school = self.school
    length = self.length
    fwd = self.forward()
    sep_r, view = SPACING * length, VIEW * length
    sep = [0.0, 0.0, 0.0]
    align = [0.0, 0.0, 0.0]
    center = [0.0, 0.0, 0.0]
    n = 0
    for m in school.members:
      if m is self:
        continue
      off = (self.x - m.x, self.y - m.y, self.z - m.z)
      d = vec.length(off)
      if d > view:
        continue
      n += 1
      mf = m.forward()
      for axis in range(3):
        align[axis] += mf[axis]
      center[0] += m.x
      center[1] += m.y
      center[2] += m.z
      if d < sep_r:
        away = vec.normalized(off, (-fwd[1], fwd[0], 0.0))
        w = (1.0 - d / sep_r) ** 2
        for axis in range(3):
          sep[axis] += away[axis] * w

    h = self.yaw + self._wander(self.time) * s.wander_turn
    want = [math.cos(h) * W_INERTIA, math.sin(h) * W_INERTIA,
            fwd[2] * W_INERTIA]
    if n:
      a = vec.normalized(tuple(align), fwd)
      c = vec.sub(tuple(v / n for v in center), (self.x, self.y, self.z))
      pull = min(1.0, vec.length(c) / (0.5 * view))
      c = vec.normalized(c, fwd)
      for axis in range(3):
        want[axis] += (a[axis] * W_ALIGNMENT + c[axis] * W_COHESION * pull
                       + sep[axis] * W_SEPARATION)
    off = vec.sub(school.goal, (self.x, self.y, self.z))
    d = vec.length(off)
    radius = max(school.radius, 1e-6)
    pull = W_GOAL * min(1.5, d / radius)
    toward = vec.normalized(off, fwd)
    for axis in range(3):
      want[axis] += toward[axis] * pull
    # Ahead of the school, ease off; behind it, catch up
    self._catch = vec.clamp(1.0 + 0.5 * vec.dot(off, fwd) / radius, 0.6, 1.7)
    if self.flicking:
      h = self.yaw + self.flick_turn
      want[0] += math.cos(h) * 4.0
      want[1] += math.sin(h) * 4.0
    # Climbing steeply is no use: the goal's depth comes about slowly
    want[2] = vec.clamp(want[2], -0.6, 0.6)
    self.danger = self._steer_clear(want)
    self._mind_others(want, others, skip=school)
    return vec.normalized(tuple(want), fwd), school.goal[2]

  def _target_speed(self, want):
    s = self.species
    if self.flicking:
      return self.max_speed * 0.6, s.glide_time
    target, glide = super()._target_speed(want)
    return target * self._catch, glide

  def snapshot(self):
    snap = super().snapshot()
    snap['school'] = self.school.name
    snap['flicking'] = self.flicking
    return snap


def group_of(fish):
  """What selecting fish selects: its school, or the fish itself."""
  return fish.school or fish


def school_members(spec):
  """Each member of the school spec (a SchoolSpec) as a
  tankful.sim.species.base.Resident, around its start.

  The members are spread over a loose ball facing the school's heading,
  with sizes from 0.88 to 1.1 of the species' length.
  """
  rng = random.Random(spec.seed)
  x, y, z, heading = spec.start
  length = spec.species.length
  out = []
  for i in range(spec.count):
    # A spiral of points over a flattened ball, jittered
    a = i * 2.39996
    r = length * 1.4 * math.sqrt(i + 0.5)
    px = x + r * math.cos(a) + rng.uniform(-0.3, 0.3) * length
    py = y + 0.5 * r * math.sin(a) + rng.uniform(-0.3, 0.3) * length
    pz = z + rng.uniform(-1.2, 1.2) * length
    out.append(Resident('%s.%02d' % (spec.species.name.title().replace('_', ''),
                                     i),
                        spec.species, rng.uniform(0.88, 1.1),
                        spec.seed * 100 + i,
                        (px, py, pz, heading + rng.uniform(-0.3, 0.3))))
  return out


def stock(tank, specs):
  """Add the schools specs (SchoolSpecs) to tank, and return them."""
  out = []
  for spec in specs:
    school = School(spec.name, spec.species, spec.seed, spec.start)
    for r in school_members(spec):
      x, y, z, heading = r.start
      tank.fish.append(Member(r.name, r.species, school, r.size, r.seed,
                              (x, y, z), heading))
    out.append(school)
  tank.schools.extend(out)
  return out
