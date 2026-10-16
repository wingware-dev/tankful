"""Cherry shrimp: a few small red shrimp that pick at the moss and the
sand.

A Shrimp is a tankful.sim.fish.Fish that spends most of its time on a
surface, standing on its legs: the open sand in front of the decor, or
the top of a moss clump (tankful.sim.environment.plants).  Its state
(Shrimp.state) runs round

  PICKING -> LIFTING -> SWIMMING -> LANDING -> PICKING

- PICKING: on the surface, it picks at it with its claws, one and then
  the other (pick_phase), and now and then walks a little way, its
  heading wandering and turning back from the surface's edges and from
  the other shrimp.  After a while (PICK_TIME) it lifts off, or sooner
  if a fish of another kind crowds it.
- LIFTING: it rises off the surface along its normal, turning to face
  the next spot (Shrimp.target, chosen by choose_spot), most often one
  near by (HOP).
- SWIMMING: it swims there as a fish does, slowly, by its swimmerets
  (the speeds and turns of SPECIES), steering round the decor, until it
  is within ARRIVE of the point just above the spot.  If it hasn't got
  there in SWIM_TIMEOUT, or another fish is on the spot, it picks
  another.
- LANDING: it settles onto the spot, its legs to it, and picks.

LIFTING and LANDING follow a set path in a set time rather than
steering, so the shrimp always ends exactly on its legs.  lift() lifts
off early.  On a surface its frame is its own (Shrimp.forward and
orientation): forward along the surface, its back along the normal.

The shrimp are one Colony, which the model builds as one object
(tools/species/cherry_shrimp.py) and the game's fish driver poses as a
school (tankful.game.fishes): small animals that come in numbers cost
less that way (docs/harness.md, "Frame budget").  A Colony doesn't steer
its members, as a School does: each shrimp goes its own way.
"""

import math

from tankful.sim import environment as env
from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.fish import MAX_STEP, MIN_GAP, Fish
from tankful.sim.noise import SmoothNoise
from tankful.sim.species.base import Resident, Species
from tankful.sim.surfaces import (Sand, Spot, ease, signed_angle, tangent,
                                  turned)

# A cherry shrimp (Neocaridina): the speeds and turns are for its short
# swims between spots, and its tail beats are its swimmerets'.  It has
# no body wave, and the depth band, hovering and wander go unused
SPECIES = Species(
  name='cherry_shrimp',
  length=0.028, height=0.0105,
  clear_side=0.008, clear_up=0.006, clear_front=0.008,
  hover_speed=0.0, cruise_speed=0.055, max_speed=0.12,
  thrust=0.5, glide_time=0.4,
  pivot_rate=2.0, turn_radius=0.02, max_turn_rate=3.0,
  max_pitch=math.radians(40), pitch_rate=math.radians(90),
  max_bank=math.radians(10),
  depth_band=(0.0, 0.2),
  wander_frequency=0.3, wander_turn=0.2,
  hover_chance=0.0, hover_time=(1.0, 2.0),
  beat_base=5.0, beat_per_speed=1.5,
  wave_min=0.0, wave_max=0.0,
  fin_beat=1.2, fin_swing=0.2,
  turn_accel=10.0, roll_rate=3.0,
)

PICKING, LIFTING, SWIMMING, LANDING = (
  'picking', 'lifting', 'swimming', 'landing')

# The center's height above the surface it stands on, in lengths: the
# model's legs (tools/species/cherry_shrimp.py) reach this far below it
STAND = 0.2
# How long it picks at a spot (s), by the kind of surface
PICK_TIME = {'sand': (8.0, 20.0), 'moss': (12.0, 30.0)}
# Claw strokes per second, each claw in turn
PICK_RATE = 1.4
# Walking: its speed (m/s per length), how much of the time it walks, how
# fast its heading wanders (rad/s), and how fast it turns back from an
# edge (rad/s) and how near an edge (m) it starts to
WALK_SPEED = 0.6
WALKING = 0.3
HEADING_WANDER = 0.9
EDGE_TURN = 2.0
EDGE_ZONE = 0.012
# Steps per second of its legs at WALK_SPEED
STEP_RATE = 3.0
# The other shrimp: it turns away from one nearer than KEEP_OFF lengths
# while picking, and lands no nearer one than LAND_OFF lengths
KEEP_OFF = 2.0
LAND_OFF = 2.5
# Lifting off: how far it rises (m), and how long that and landing take
# (s)
LIFT = 0.012
LIFT_TIME = 0.5
LAND_TIME = 0.6
# How far above the spot the swim aims (m), how near that it must come,
# and how long it may take (s)
APPROACH = 0.015
ARRIVE = 0.01
SWIM_TIMEOUT = 8.0
# How far a hop goes (m), mostly
HOP = (0.04, 0.22)
# How far from the edge of the open sand it keeps (m)
SAND_EDGE = 0.015
# The open sand it uses: in front of this y
SAND_BACK = 0.0
# The moss clumps it uses: in front of this y, where the viewer sees them
MOSS_BACK = 0.05
# How often it picks each kind of spot
SPOT_WEIGHTS = (('sand', 0.55), ('moss', 0.45))

# Surfaces

class MossTop:
  """The top of a moss clump: a low dome over the sand.

  The clump (tools/scene_env.py, plant_leaves) is a cushion of tufts
  about RADIUS across, tallest in the middle; a shrimp walks within
  WALK of its middle, and keeps off the rocks and wood (a clump may
  grow against them, or under the driftwood): its spots are clear
  enough of them to swim down to."""

  kind = 'moss'
  still = False
  RADIUS = 0.05
  WALK = 0.028
  # How far the spot itself, and the point a swim aims for above it,
  # keep from the hard decor's surface (m)
  CLEAR = 0.004
  APPROACH_CLEAR = 0.012

  def __init__(self, plant):
    self.name = plant.name + '.Top'
    self.obstacle = plant.name
    self.center = (plant.x, plant.y)
    self.height = plant.height
    reach = self.RADIUS + 0.1
    self._hard = [o for o in env.obstacles() if not o.soft and math.dist(
      self.center, vec.closest_on_segment(
        (plant.x, plant.y, 0.0), (o.a[0], o.a[1], 0.0),
        (o.b[0], o.b[1], 0.0))[:2]) < reach + o.radius]

  def top(self, x, y):
    d2 = (x - self.center[0]) ** 2 + (y - self.center[1]) ** 2
    dome = 0.8 - 0.2 * d2 / self.RADIUS ** 2
    return env.sand_height(x, y) + self.height * dome

  def contact(self, p):
    x, y = p[0], p[1]
    h = 1e-3
    dx = (self.top(x + h, y) - self.top(x - h, y)) / (2 * h)
    dy = (self.top(x, y + h) - self.top(x, y - h)) / (2 * h)
    return (x, y, self.top(x, y)), vec.normalized((-dx, -dy, 1.0))

  def _off(self, c):
    return (c[0] - self.center[0], c[1] - self.center[1], 0.0)

  def _decor(self, c, clear=CLEAR):
    """[(gap, away)] from each hard obstacle near: the gap past clear
    from its surface, and the way away from it over the sand."""
    out = []
    for o in self._hard:
      off = vec.sub(c, vec.closest_on_segment(c, o.a, o.b))
      away = vec.normalized((off[0], off[1], 0.0), (0.0, -1.0, 0.0))
      out.append((vec.length(off) - o.radius - clear, away))
    return out

  def open(self, point):
    """Whether point is a spot to land on: clear of the hard decor, and
    so is the water above it."""
    above = (point[0], point[1], point[2] + APPROACH)
    return (all(gap > 0 for gap, _ in self._decor(point)) and
            all(gap > 0 for gap, _ in self._decor(above,
                                                   self.APPROACH_CLEAR)))

  def edges(self, c):
    off = self._off(c)
    d = vec.length(off)
    return [(self.WALK - d, vec.normalized(vec.scale(off, -1.0),
                                           (1.0, 0.0, 0.0)))] + self._decor(c)

  def clamp(self, c):
    x, y = c[0], c[1]
    for _ in range(3):
      off = self._off((x, y, 0.0))
      d = vec.length(off)
      if d > self.WALK:
        off = vec.scale(off, self.WALK / d)
      x, y = self.center[0] + off[0], self.center[1] + off[1]
      p = self.contact((x, y, 0.0))[0]
      for gap, away in self._decor(p):
        if gap < 0:
          x, y = x - away[0] * gap, y - away[1] * gap
    return self.contact((x, y, 0.0))[0]

  def random_point(self, rng):
    """A point within WALK of the middle that is open, or None if none
    comes up."""
    for _ in range(30):
      a = rng.uniform(-math.pi, math.pi)
      r = self.WALK * 0.8 * math.sqrt(rng.random())
      p = self.contact((self.center[0] + r * math.cos(a),
                        self.center[1] + r * math.sin(a), 0.0))[0]
      if self.open(p):
        return p
    return None

  def heading(self, angle):
    return (math.cos(angle), math.sin(angle), 0.0)


def surfaces():
  """The surfaces a shrimp picks at, by kind of spot."""
  return {
    'sand': [Sand(SAND_EDGE, SAND_BACK)],
    'moss': [MossTop(p) for p in env.plants()
             if p.kind == 'moss' and p.y < MOSS_BACK],
  }


def choose_spot(rng, by_kind, here, avoid=()):
  """A spot to go to: a surface by SPOT_WEIGHTS, a point on it a HOP
  from here (the point it is leaving) if one comes up, and no nearer
  any of avoid (points) than LAND_OFF lengths, and a heading."""
  total = sum(w for _, w in SPOT_WEIGHTS)
  near = LAND_OFF * SPECIES.length
  fallback = None
  for _ in range(60):
    r = rng.uniform(0, total)
    for kind, w in SPOT_WEIGHTS:
      r -= w
      if r <= 0:
        break
    surface = rng.choice(by_kind[kind])
    point = surface.random_point(rng)
    if point is None or any(math.dist(point, p) < near for p in avoid):
      continue
    _, normal = surface.contact(point)
    heading = tangent(surface.heading(rng.uniform(-math.pi, math.pi)),
                      normal)
    spot = Spot(surface, point, normal, heading)
    hop = math.dist(point, here)
    if HOP[0] <= hop <= HOP[1]:
      return spot
    if fallback is None and hop >= HOP[0]:
      fallback = spot
  if fallback is not None:
    return fallback
  # Nowhere else came up: the middle of the front sand
  surface = by_kind['sand'][0]
  point = surface.clamp((0.0, -0.12, 0.0))
  _, normal = surface.contact(point)
  return Spot(surface, point, normal, (1.0, 0.0, 0.0))


# The colony

class Colony:
  """The shrimp of the tank as one group, which the model builds as one
  object and selecting a shrimp selects (tankful.sim.school.group_of).
  Unlike a School it has no goal: it doesn't step."""

  def __init__(self, name, species):
    self.name = name
    self.species = species
    self.members = []

  def add(self, fish):
    fish.school = self
    self.members.append(fish)

  def __contains__(self, fish):
    return fish in self.members

  def centroid(self):
    n = len(self.members)
    if not n:
      return (0.0, 0.0, 0.0)
    return tuple(sum(getattr(f, a) for f in self.members) / n
                 for a in 'xyz')


# The shrimp

class Shrimp(Fish):

  def __init__(self, name, species, size=1.0, seed=0,
               start=(0.0, -0.12, 0.04, 0.0)):
    # Set before Fish.__init__, which places the fish (_limit_position)
    self.state = PICKING
    self._frame = None
    super().__init__(name, species, size, seed, start[:3], 0.0)
    self.surfaces = surfaces()
    self.state_time = 0.0
    self.pick_left = 0.0
    self.pick_phase = self.rng.uniform(0, 2 * math.pi)
    self.step_phase = self.rng.uniform(0, 2 * math.pi)
    self.feel_phase = self.rng.uniform(0, 2 * math.pi)
    # How much it swims (1) rather than stands (0), and walks (1) rather
    # than stands still picking (0), for the pose
    self.swimming = 0.0
    self.walking = 0.0
    self.target = None
    self.hops = 0
    self.surface = None
    self.contact = None
    self.normal = None
    self.heading = None
    self._path = None
    self._skip = ()
    self._depart = None
    self._heading_noise = SmoothNoise(seed * 7 + 5, 0.15)
    self._walk_noise = SmoothNoise(seed * 7 + 6, 0.12)
    # Stand on the surface nearest the start
    p = start[:3]
    surface = min((s for group in self.surfaces.values() for s in group),
                  key=lambda s: math.dist(p, s.clamp(p)))
    point = surface.clamp(p)
    _, normal = surface.contact(point)
    heading = tangent(surface.heading(start[3]), normal) or (1.0, 0.0, 0.0)
    self._stand_on(surface, point, normal, heading)

  # The frame

  def forward(self):
    if self._frame is None:
      return super().forward()
    m = self._frame
    return (m[0][0], m[1][0], m[2][0])

  def orientation(self):
    if self._frame is None:
      return super().orientation()
    return self._frame

  def _swim_frame(self, direction):
    """Set yaw, pitch and roll to swim along direction; return that
    orientation."""
    s = self.species
    self.yaw = math.atan2(direction[1], direction[0])
    self.pitch = vec.clamp(math.atan2(direction[2], math.hypot(
      direction[0], direction[1])), -s.max_pitch, s.max_pitch)
    self.roll = 0.0
    self.yaw_rate = 0.0
    return Fish.orientation(self)

  # The state machine

  def _set_state(self, state):
    self.state = state
    self.state_time = 0.0

  def _stand_on(self, surface, point, normal, heading):
    self.surface = surface
    self.contact = point
    self.normal = normal
    self.heading = heading
    self.pick_left = self.rng.uniform(*PICK_TIME[surface.kind])
    self.target = None
    self.speed = 0.0
    self._place()
    self._set_state(PICKING)

  def _place(self):
    """Put the center and frame where the contact, normal and heading say."""
    c = vec.add(self.contact, vec.scale(self.normal, STAND * self.length))
    self.x, self.y, self.z = c
    self._frame = vec.frame(self.heading, self.normal)
    h = self.heading
    self.yaw = math.atan2(h[1], h[0])
    self.pitch = math.asin(vec.clamp(h[2], -1.0, 1.0))
    self.roll = 0.0

  def lift(self, others=()):
    """Lift off the surface for a new spot, away from the other shrimp
    of others.  Whether it was on one."""
    if self.state != PICKING:
      return False
    self.target = choose_spot(self.rng, self.surfaces, self.contact,
                              self._mates(others))
    start = (self.x, self.y, self.z)
    end = vec.add(start, vec.scale(self.normal, LIFT))
    turn = self._swim_frame(vec.normalized(vec.sub(self._approach(), end),
                                           self.normal))
    self._path = (start, vec.quaternion(self._frame), end,
                  vec.quaternion(turn), LIFT_TIME)
    self._depart = (self.contact, getattr(self.surface, 'obstacle', None))
    self.surface = None
    self._set_state(LIFTING)
    return True

  def _mates(self, others):
    """Where the other shrimp in others are, or are going."""
    out = []
    for f in others:
      if f is self or f.species is not self.species:
        continue
      out.append(f.target.point if getattr(f, 'target', None)
                 else (f.x, f.y, f.z))
    return out

  def _approach(self):
    t = self.target
    return vec.add(t.point, vec.scale(t.normal, APPROACH))

  def _land(self):
    """Start onto the target from where the swim left off."""
    t = self.target
    heading = tangent(self.forward(), t.normal) or t.heading
    self.contact, self.normal, self.heading = t.point, t.normal, heading
    start = (self.x, self.y, self.z)
    start_q = vec.quaternion(self.orientation())
    end = vec.add(t.point, vec.scale(t.normal, STAND * self.length))
    end_q = vec.quaternion(vec.frame(heading, t.normal))
    self._path = (start, start_q, end, end_q, LAND_TIME)
    self._frame = self.orientation()
    self._set_state(LANDING)

  def _retarget(self, others):
    self.target = choose_spot(self.rng, self.surfaces,
                              (self.x, self.y, self.z), self._mates(others))
    self.state_time = 0.0

  # The step

  def step(self, dt, others=()):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    dt = min(dt, MAX_STEP)
    if dt == 0:
      return
    self.state_time += dt
    self.feel_phase = (self.feel_phase + 2 * math.pi * 0.35 * dt) % (
      2 * math.pi)
    if self.state == SWIMMING:
      self._swim_to(dt, others)
      return
    self.time += dt
    if self.state == PICKING:
      self._pick(dt, others)
    else:
      self._follow_path(dt)
    self._gait(dt)

  def _pick(self, dt, others):
    self.swimming = max(0.0, self.swimming - dt / LAND_TIME)
    surface = self.surface
    n = self.normal
    turn = self._heading_noise(self.time) * HEADING_WANDER
    # Turn back from the nearest edge, harder the nearer
    depth, inward = min(surface.edges(self.contact), key=lambda e: e[0])
    inward = tangent(inward, n)
    if depth < EDGE_ZONE and inward is not None:
      err = signed_angle(self.heading, inward, n)
      near = 1.0 - max(0.0, depth) / EDGE_ZONE
      turn += vec.clamp(err * 2.0, -1.0, 1.0) * EDGE_TURN * near
    # and from the other shrimp
    for f in others:
      if f is self or f.species is not self.species:
        continue
      off = tangent(vec.sub((self.x, self.y, self.z), (f.x, f.y, f.z)), n)
      d = math.dist((self.x, self.y, self.z), (f.x, f.y, f.z))
      keep = KEEP_OFF * max(self.length, f.length)
      if off is not None and d < keep:
        err = signed_angle(self.heading, off, n)
        turn += vec.clamp(err * 2.0, -1.0, 1.0) * EDGE_TURN * (1 - d / keep)
    self.heading = turned(self.heading, n, turn * dt)
    # Walk now and then; pick while still, and slower while walking
    goal = 1.0 if self._walk_noise(self.time) > 1.0 - 2 * WALKING else 0.0
    self.walking += vec.clamp(goal - self.walking, -3 * dt, 3 * dt)
    self.speed = WALK_SPEED * self.length * self.walking
    self.step_phase = (self.step_phase + 2 * math.pi * STEP_RATE
                       * self.walking * dt) % (2 * math.pi)
    self.pick_phase = (self.pick_phase + 2 * math.pi * PICK_RATE
                       * (1.0 - 0.6 * self.walking) * dt) % (2 * math.pi)
    moved = vec.add(self.contact, vec.scale(self.heading, self.speed * dt))
    self.contact, self.normal = surface.contact(surface.clamp(moved))
    self.heading = tangent(self.heading, self.normal) or self.heading
    self._place()
    self.pick_left -= dt
    # It hops off when its time is up, or when another kind of fish
    # crowds it
    if self.pick_left <= 0 or self._crowded(others):
      self.lift(others)

  def _crowded(self, others):
    pos = (self.x, self.y, self.z)
    for f in others:
      if f is not self and f.species is not self.species and math.dist(
          pos, (f.x, f.y, f.z)) < MIN_GAP * 0.5 * (self.length + f.length):
        return True
    return False

  def _follow_path(self, dt):
    start, start_q, end, end_q, duration = self._path
    t = ease(self.state_time / duration)
    before = (self.x, self.y, self.z)
    self.x, self.y, self.z = vec.lerp(start, end, t)
    self._frame = vec.rotation(vec.slerp(start_q, end_q, t))
    self.speed = math.dist(before, (self.x, self.y, self.z)) / dt
    self.walking = max(0.0, self.walking - 3 * dt)
    if self.state == LIFTING:
      self.swimming = t
      if self.state_time >= duration:
        # Off the surface: swim from here, facing the way it turned
        self._frame = None
        self.speed = self.cruise_speed * 0.5
        self.stroking, self.stroke = True, 1.0
        self.hops += 1
        self._set_state(SWIMMING)
    else:
      self.swimming = 1.0 - t
      if self.state_time >= duration:
        t = self.target
        self._stand_on(t.surface, t.point, t.normal, self.heading)

  def _swim_to(self, dt, others):
    self.swimming = 1.0
    target_obstacle = getattr(self.target.surface, 'obstacle', None)
    point, depart_obstacle = self._depart
    self._skip = {target_obstacle}
    if math.dist(point, (self.x, self.y, self.z)) < 2 * APPROACH:
      self._skip.add(depart_obstacle)
    Fish.step(self, dt, others)
    if math.dist((self.x, self.y, self.z), self._approach()) < ARRIVE:
      self._land()
    elif self.state_time > SWIM_TIMEOUT or self._taken(others):
      self._retarget(others)

  def _taken(self, others):
    """Whether another fish of others is on the spot it swims to, too
    near for it to land (tankful.sim.fish keeps fish MIN_GAP apart)."""
    spot = self.target.point
    for f in others:
      if f is self:
        continue
      if f.species is self.species:
        gap = MIN_GAP * max(self.length, f.length)
      else:
        gap = MIN_GAP * 0.5 * (self.length + f.length)
      if math.dist(spot, (f.x, f.y, f.z)) < gap + STAND * self.length:
        return True
    return False

  # Fish steering, while swimming

  def _update_mode(self, dt):
    pass

  def _desired(self, others):
    goal = self._approach()
    pos = (self.x, self.y, self.z)
    off = vec.sub(goal, pos)
    d = vec.length(off)
    toward = vec.normalized(off, self.forward())
    # The sand and decor push it off less the nearer it is to the spot,
    # which is on one of them
    clear = [0.0, 0.0, 0.0]
    danger = self._steer_clear(clear)
    k = vec.clamp((d - 0.02) / 0.15, 0.0, 1.0)
    want = [toward[i] * 2.5 + clear[i] * k for i in range(3)]
    self.danger = danger * k
    self._mind_others(want, others)
    return vec.normalized(tuple(want), self.forward()), goal[2]

  def _target_speed(self, want):
    d = math.dist((self.x, self.y, self.z), self._approach())
    along = vec.dot(self.forward(), want)
    target = (self.cruise_speed * vec.clamp(d / 0.06, 0.3, 1.0)
              * (0.5 + 0.5 * max(0.0, along)))
    return target, self.species.glide_time

  def _obstacles_near(self, pos, pad):
    for obstacle in super()._obstacles_near(pos, pad):
      if obstacle.name not in self._skip:
        yield obstacle

  def _limit_position(self):
    # On a surface, or on its way on or off, the path holds it
    if self.state == SWIMMING:
      super()._limit_position()

  def snapshot(self):
    snap = super().snapshot()
    snap.update({
      'state': self.state,
      'surface': self.surface.name if self.surface else None,
      'contact': [round(v, 4) for v in self.contact],
      'target': self.target.surface.name if self.target else None,
      'pick_left': round(self.pick_left, 2),
      'hops': self.hops,
      'colony': self.school.name if self.school else None,
    })
    return snap


# The pose
#
# The rig (tools/species/cherry_shrimp.py) is the spine chain of
# tankful.sim.swim: the Head is the carapace, Spine.0 to Spine.2 the
# abdomen and Tail the tail fan.  The limbs' bones all point straight
# back at rest, as the pleco's fins do, so bone x is the shrimp's left
# and z its back, and a positive x rotation swings what hangs below a
# bone back and what reaches ahead of it down:
#
#   Head -> Spine.0 -> Spine.1 -> Spine.2 -> Tail
#   Head -> Antenna.L, Antenna.R, Claw.L, Claw.R, Legs.L, Legs.R
#   Spine.0 -> Swim.0; Spine.1 -> Swim.1; Spine.2 -> Swim.2
#
# The model rests standing: the legs down to the surface, the claws
# reaching ahead and down, the antennae forward and out.

SPINE = swim.SPINE
BONES = ('Head',) + SPINE + ('Antenna.L', 'Antenna.R', 'Claw.L', 'Claw.R',
                             'Legs.L', 'Legs.R', 'Swim.0', 'Swim.1',
                             'Swim.2')
# How far each claw reaches down to the surface, and lifts back to the
# mouth, from rest (radians)
CLAW_REACH = 0.45
CLAW_LIFT = 0.5
# The legs' swing walking, and how far they fold back swimming (radians)
LEG_SWING = 0.35
LEG_FOLD = 0.7
# The swimmerets' beat standing (fanning water over the eggs and gills)
# and swimming (radians)
SWIM_REST = 0.25
SWIM_BEAT = 0.7
# The abdomen's slow bob standing, and how much it straightens swimming
# (radians per segment)
BOB = 0.03
STRETCH = -0.06
# How much a turn bends the abdomen aside, per rad/s
BEND = 0.04


def pose(fish):
  """{bone: (rx, ry, rz)} for a Shrimp now."""
  sw = fish.swimming
  rest = 1.0 - sw
  angles = {'Head': (0.0, 0.0, 0.0)}
  bend = vec.clamp(fish.yaw_rate, -2.0, 2.0) * BEND
  for k, name in enumerate(SPINE):
    bob = BOB * math.sin(fish.feel_phase * 2 - 0.7 * k)
    angles[name] = (rest * bob + sw * STRETCH, 0.0, -bend)
  # The claws pick in turn, less while walking, and are held ahead
  # swimming
  picking = rest * (1.0 - 0.6 * fish.walking)
  for name, phase in (('Claw.L', 0.0), ('Claw.R', math.pi)):
    s = math.sin(fish.pick_phase + phase)
    reach = CLAW_REACH * max(0.0, s) - CLAW_LIFT * max(0.0, -s)
    angles[name] = (picking * reach - sw * 0.3, 0.0, 0.0)
  # The legs step left and right in turn, and fold back swimming
  for name, phase in (('Legs.L', 0.0), ('Legs.R', math.pi)):
    stride = LEG_SWING * fish.walking * math.sin(fish.step_phase + phase)
    angles[name] = (rest * stride + sw * LEG_FOLD, 0.0, 0.0)
  # The antennae feel about, out to each side, and sweep back swimming
  f = fish.feel_phase
  for name, side in (('Antenna.L', 1.0), ('Antenna.R', -1.0)):
    sweep = 0.18 * math.sin(f + side) + 0.08 * math.sin(2.3 * f + 2 * side)
    angles[name] = (0.12 * math.sin(1.3 * f + side) - sw * 0.2, 0.0,
                    side * (sweep - sw * 0.35))
  # The swimmerets beat as a wave from back to front
  amp = SWIM_REST * rest + SWIM_BEAT * sw
  for k in range(3):
    angles['Swim.%d' % k] = (amp * math.sin(fish.beat_phase + 0.8 * k),
                             0.0, 0.0)
  return angles


def scales(fish):
  """{bone: (sx, sy, sz)}: no bone scales."""
  return {}


# Who lives in the tank

COLONY = 'CherryShrimp'


def shrimps():
  """The shrimp in the tank.  start is a point near the surface each
  starts on (the sand in front, or a moss clump's top), and its heading
  there."""
  name = COLONY + '.%d'
  return [
    Resident(name % 0, SPECIES, 1.05, 701, (-0.17, -0.13, 0.03, 0.4)),
    Resident(name % 1, SPECIES, 0.9, 702, (-0.05, -0.04, 0.09, 2.6)),
    Resident(name % 2, SPECIES, 1.0, 703, (0.08, -0.14, 0.03, 2.9)),
    Resident(name % 3, SPECIES, 0.85, 704, (0.20, -0.05, 0.09, -1.2)),
  ]


def stock(tank):
  """Add the shrimp to tank, as one Colony, and return them."""
  colony = Colony(COLONY, SPECIES)
  out = []
  for r in shrimps():
    shrimp = Shrimp(r.name, r.species, r.size, r.seed, r.start)
    colony.add(shrimp)
    out.append(shrimp)
  tank.fish.extend(out)
  return out
