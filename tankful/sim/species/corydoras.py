"""Corydoras: a small group of armored catfish that work the sand.

A Corydoras is a tankful.sim.fish.Fish that lives on the open sand in
front of the decor (Floor), apart from its trips up for air.  Its state
(Corydoras.state) is one of:

- SIFT: nose down, its mouth in the sand and its tail raised, it roots
  for food.  Its head works from side to side, its pectoral fins paddle,
  and each mouthful throws up a puff of sand (Corydoras.puffs) that
  rises, spreads and settles back.
- HOP: a short skip to the next spot: it lifts off the sand, levels out
  and beats its tail, then noses down again as it lands.  A spot is near
  the way it faces, toward the rest of the group when it strays, clear
  of the decor and of the others' spots.  Boxed in, it turns on the spot.
- REST: it lies level on the sand, propped on its fins, still.
- DASH: now and then (AIR_EVERY) it darts straight up to the surface,
  gulps air with its snout out of the water, and dives back down to the
  sand nearby.
- STEERED: the user steers it (Fish.steer, tankful.sim.steering): from
  whatever it was doing it levels out and swims as a fish does
  (tankful.sim.fish), where it is steered.  Let go, it dives back down
  to the sand nearby, as after a gulp of air.

On the sand (all but DASH) its height follows from how far it is tipped
nose down (Corydoras.tilt) and a hop's lift: the center is BELLY lengths
above the sand lying level, high enough to put the mouth on the sand
nose down, and never more than BAND lengths above it.  A dash rises
straight up from open sand and dives along a line over open sand, so no
part of it passes over the decor.

The group swims in no school (tankful.sim.school), but is drawn as one:
its members share one armature, Corydoras.Rig, as a school's members do
(Group; tools/species/corydoras.py), as fish that come in numbers must
for the frame budget (docs/harness.md).
"""

import math

from tankful.sim import environment as env
from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.daynight import Night
from tankful.sim.fish import CRUISE, MAX_STEP, Fish
from tankful.sim.noise import SmoothNoise
from tankful.sim.species.base import Resident, Species

# A panda corydoras: short, deep and armored, with a flat belly.  The
# speeds, pitch limits and gait are for its hops and dashes; it steers
# by the states above rather than by tankful.sim.fish, so the wander,
# hovering and depth band go unused
SPECIES = Species(
  name='corydoras',
  length=0.05, height=0.028,
  clear_side=0.015, clear_up=0.012, clear_front=0.015,
  hover_speed=0.0, cruise_speed=0.08, max_speed=0.55,
  thrust=1.5, glide_time=0.4,
  pivot_rate=2.0, turn_radius=0.03, max_turn_rate=4.0,
  max_pitch=math.radians(70), pitch_rate=math.radians(290),
  max_bank=math.radians(10),
  depth_band=(0.0, 0.1),
  wander_frequency=0.15, wander_turn=0.8,
  hover_chance=0.0, hover_time=(1.0, 2.0),
  beat_base=2.0, beat_per_speed=1.6,
  wave_min=0.08, wave_max=0.5,
  fin_beat=5.0, fin_swing=0.35,
  turn_accel=14.0, roll_rate=3.0,
  # Nocturnal: busier at night (Corydoras._span)
  night=Night(activity=2.2),
)

# The group's name, and so its armature's (Corydoras.Rig)
GROUP_NAME = 'Corydoras'

SIFT, HOP, REST, DASH, STEERED = 'sift', 'hop', 'rest', 'dash', 'steered'
# A dash's phases
RISE, GULP, DIVE = 'rise', 'gulp', 'dive'

# The center's height above its flat belly, and the mouth under the
# snout (x forward, z up from the center), in lengths: the model
# (tools/species/corydoras.py) is built to these
BELLY = 0.13
MOUTH = (0.46, -0.11)
# How far nose down it tips to sift (radians), and how long tipping
# down or levelling out takes (s)
SIFT_PITCH = math.radians(-32)
TILT_TIME = 0.3
# The most the center is ever above the sand off a dash, in lengths
BAND = 0.6
# How long it sifts, and rests, in one spot (s)
SIFT_TIME = (1.8, 4.5)
REST_TIME = (5.0, 12.0)
# How often a sift ends in a rest
REST_CHANCE = 0.05
# The head's working while it sifts: beats per second and swing (rad)
WORK_RATE = 3.2
WORK_SWING = 0.09
# A hop: how far (m), its lift (m) and nose-up (rad) at its height, and
# its time, from a base, by distance and by how far it turns (s, s/m,
# s/rad)
HOP_DIST = (0.025, 0.075)
HOP_LIFT = 0.006
HOP_PITCH = math.radians(8)
HOP_BASE, HOP_PER_M, HOP_PER_RAD = 0.35, 8.0, 0.25
# Hops keep each fish's spot this many lengths from the others', and
# lean toward the group when it is farther than GROUP (m) from their
# middle
SPACING = 1.4
GROUP = 0.10
# Sand puffs: slots per fish (the rig's Puff bones), how long one lasts
# (s), and how often a sift throws one up (s)
PUFFS = 2
PUFF_LIFE = 1.1
PUFF_EVERY = 0.8
# Between trips for air (s); the first comes sooner
AIR_EVERY = (90.0, 200.0)
FIRST_AIR = (15.0, 120.0)
# The dash: rising speed (m/s, at size 1), the drift forward on the way
# up (m), the center below the surface at the top (m), the nose-up held
# there and how long the gulp takes (s), and where it lands (m from the
# top) and how long the dive takes (s, at size 1)
RISE_SPEED = 0.22
RISE_DRIFT = 0.03
TOP_DEPTH = 0.016
GULP_PITCH = math.radians(40)
GULP_TIME = 0.7
LAND_DIST = (0.07, 0.16)
DIVE_TIME = 1.5
# The sand it works: from the glass by EDGE lengths, back to FLOOR_BACK
# (y, m), and clear of the decor's footprints by CLEAR_HARD lengths for
# wood and stone, CLEAR_SOFT for plants, which it noses among
EDGE = 0.6
FLOOR_BACK = 0.02
CLEAR_HARD = 0.6
CLEAR_SOFT = 0.3


def ease(t):
  t = vec.clamp(t, 0.0, 1.0)
  return t * t * (3 - 2 * t)


def lerp_angle(a, b, t):
  return vec.wrap_angle(a + vec.wrap_angle(b - a) * t)


def lerp2(a, b, t):
  return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def bezier(points, t):
  pts = list(points)
  while len(pts) > 1:
    pts = [vec.lerp(a, b, t) for a, b in zip(pts, pts[1:])]
  return pts[0]


def nose_height(length, pitch=SIFT_PITCH):
  """The center's height above the mouth, tipped nose down by pitch."""
  mx, mz = MOUTH
  return -length * (mx * math.sin(pitch) + mz * math.cos(pitch))


class Floor:
  """The open sand the group works: inside the glass by edge, in front
  of FLOOR_BACK, and clear of every obstacle's footprint (its capsule
  seen from above), so the water over it is clear of the decor too."""

  def __init__(self, length):
    edge = EDGE * length
    self.x = (-env.INNER_X + edge, env.INNER_X - edge)
    self.y = (-env.INNER_Y + edge, FLOOR_BACK)
    self._decor = [((o.a[0], o.a[1]), (o.b[0], o.b[1]),
                    o.radius + (CLEAR_SOFT if o.soft else CLEAR_HARD) * length)
                   for o in env.obstacles()]

  def gap(self, x, y):
    """How far x, y is inside the floor: from its edges and from each
    footprint.  Negative outside."""
    (x0, x1), (y0, y1) = self.x, self.y
    g = min(x - x0, x1 - x, y - y0, y1 - y)
    p = (x, y, 0.0)
    for a, b, clear in self._decor:
      c = vec.closest_on_segment(p, (a[0], a[1], 0.0), (b[0], b[1], 0.0))
      g = min(g, math.dist(p, c) - clear)
    return g

  def clear(self, a, b, step=0.01):
    """Whether the line from a to b (x, y) is on the floor all the way."""
    n = max(1, math.ceil(math.dist(a, b) / step))
    return all(self.gap(*lerp2(a, b, i / n)) > 0 for i in range(n + 1))


class Group:
  """The corydoras of one group, for the game's fish driver
  (tankful.game.fishes), which draws a fish whose school is set from
  that school's armature, <name>.Rig.  The members don't school: each
  minds the others as a Corydoras."""

  def __init__(self, name):
    self.name = name
    self.members = []

  def add(self, fish):
    self.members.append(fish)
    fish.school = self


class Corydoras(Fish):

  def __init__(self, name, species, size=1.0, seed=0,
               start=(0.0, -0.12, 0.0, 0.0)):
    # Set before Fish.__init__, which places the fish (_limit_position)
    self.state = None
    super().__init__(name, species, size, seed, (start[0], start[1], 0.0),
                     start[3])
    self.floor = Floor(self.length)
    self.state_time = 0.0
    self.state_len = self.rng.uniform(*SIFT_TIME)
    self.tilt = 1.0
    self.lift = 0.0
    self.work_phase = self.rng.uniform(0, 2 * math.pi)
    self.puffs = [None] * PUFFS
    self.next_puff = 0.0
    self.air_left = self.rng.uniform(*FIRST_AIR)
    self.dashes = 0
    self.hops = 0
    self.target = None
    self.phase = None
    self._hop = None
    self._dash = None
    self._next = None
    self._heading_noise = SmoothNoise(seed * 7 + 5, SPECIES.wander_frequency)
    self.speed = 0.0
    self.stroke = 0.0
    self.state = SIFT
    self._ground()

  # On the sand

  def ground_z(self, tilt=None, lift=None):
    """The center's height on the sand at x, y, tipped by tilt (0 level,
    1 nose down to sift) and raised by lift."""
    tilt = self.tilt if tilt is None else tilt
    lift = self.lift if lift is None else lift
    L = self.length
    level = env.sand_height(self.x, self.y) + BELLY * L
    # How far ahead of the center the mouth is, tipped nose down
    reach = L * (MOUTH[0] * math.cos(SIFT_PITCH)
                 - MOUTH[1] * math.sin(SIFT_PITCH))
    mx = self.x + math.cos(self.yaw) * reach
    my = self.y + math.sin(self.yaw) * reach
    nose = env.sand_height(mx, my) + nose_height(L)
    return level + (nose - level) * tilt + lift

  def above_sand(self):
    return self.z - env.sand_height(self.x, self.y)

  def _ground(self, pitch=0.0):
    self.z = self.ground_z()
    self.pitch = SIFT_PITCH * self.tilt + pitch
    self.roll = 0.0

  def _limit_position(self):
    # Its states keep it on the floor: nothing to do until they start,
    # but swimming free as it is steered
    if self.state == STEERED:
      super()._limit_position()

  @property
  def anchored(self):
    # Its states hold it on the sand, or on its dash, but for swimming as
    # it is steered
    return self.state != STEERED

  def _set_state(self, state, length=0.0):
    self.state = state
    self.state_time = 0.0
    self.state_len = length

  def _tilt_toward(self, goal, dt):
    step = dt / TILT_TIME
    self.tilt += vec.clamp(goal - self.tilt, -step, step)

  # The step

  def step(self, dt, others=()):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    dt = min(dt, MAX_STEP)
    if dt == 0:
      return
    if self.steer is not None and self.state != STEERED:
      self._take_steer()
    if self.state == STEERED:
      self._steered_step(dt, others)
      return
    self.time += dt
    self.state_time += dt
    self._age_puffs(dt)
    before = (self.x, self.y, self.z)
    yaw = self.yaw
    if self.state == DASH:
      self._dash_step(dt)
    else:
      self.air_left -= dt * self.by_night('activity')
      if self.state == SIFT:
        self._sift(dt, others)
      elif self.state == HOP:
        self._hop_step(dt, others)
      else:
        self._rest(dt, others)
    self.speed = math.dist(before, (self.x, self.y, self.z)) / dt
    self.yaw_rate = vec.wrap_angle(self.yaw - yaw) / dt
    self._gait(dt)

  def _sift(self, dt, others):
    self._tilt_toward(1.0, dt)
    self.lift = 0.0
    self.stroke = 0.0
    self._ground()
    self.work_phase = (self.work_phase
                       + 2 * math.pi * WORK_RATE * dt) % (2 * math.pi)
    # A puff for each mouthful once the snout is in, while one has time
    # to settle before the sift ends
    if (self.tilt > 0.95 and self.state_time >= self.next_puff
        and self.state_time + PUFF_LIFE <= self.state_len):
      self._puff()
      self.next_puff = self.state_time + PUFF_EVERY
    if self.state_time >= self.state_len and not self.active_puffs():
      self._next_state(others)

  def _rest(self, dt, others):
    self._tilt_toward(0.0, dt)
    self.lift = 0.0
    self.stroke = 0.0
    self._ground()
    if self.state_time >= self.state_len:
      self._next_state(others)

  def _next_state(self, others):
    if self.air_left <= 0:
      self._start_dash(others)
    elif self.state == SIFT and self.rng.random() < self._rest_chance():
      self._set_state(REST, self._span(REST_TIME))
    else:
      self._start_hop(others)

  # At night (tankful.sim.daynight) they are busier: shorter sifts and
  # rests, fewer rests and more trips for air

  def _span(self, span):
    """A sift's or rest's length from span, shorter the busier it is."""
    return self.rng.uniform(*span) / self.by_night('activity')

  def _rest_chance(self):
    return REST_CHANCE / self.by_night('activity')

  # Hops

  def _others(self, others):
    return [o for o in others if o is not self and isinstance(o, Corydoras)]

  def spot(self):
    """Where it will be on the sand: its hop's or dive's end, or here."""
    return self.target if self.target is not None else (self.x, self.y)

  def _free(self, p, mates):
    gap = SPACING * self.length
    return all(math.dist(p, m.spot()) >= gap for m in mates)

  def _choose_hop(self, others):
    """A spot to hop to (x, y), or None if boxed in."""
    mates = self._others(others)
    want = self.yaw + self._heading_noise(self.time) * SPECIES.wander_turn
    near = [m.spot() for m in mates if m.state != DASH]
    if near:
      cx = sum(p[0] for p in near) / len(near)
      cy = sum(p[1] for p in near) / len(near)
      d = math.dist((self.x, self.y), (cx, cy))
      if d > GROUP:
        # Toward the group, the more the farther it strays
        k = vec.clamp((d - GROUP) / GROUP, 0.0, 1.0)
        home = math.atan2(cy - self.y, cx - self.x)
        want = lerp_angle(want, home, 0.4 + 0.6 * k)
    here = (self.x, self.y)
    for i in range(18):
      # Fanning out from the way it wants to go, both sides in turn
      spread = (i + 1) // 2 * 0.35 * (1 if i % 2 else -1)
      a = want + spread + self.rng.uniform(-0.15, 0.15)
      d = self.rng.uniform(*HOP_DIST)
      p = (self.x + math.cos(a) * d, self.y + math.sin(a) * d)
      if self.floor.clear(here, p) and self._free(p, mates):
        return p
    return None

  def _start_hop(self, others):
    target = self._choose_hop(others)
    if target is None:
      # Boxed in: turn on the spot, toward the middle of the floor
      target = (self.x, self.y)
      yaw1 = lerp_angle(math.atan2(-0.1 - self.y, -self.x), self.yaw, 0.2)
    else:
      yaw1 = math.atan2(target[1] - self.y, target[0] - self.x)
    d = math.dist((self.x, self.y), target)
    self.target = target
    then = REST if self.rng.random() < self._rest_chance() * 0.5 else SIFT
    self._hop = ((self.x, self.y), target, self.yaw, yaw1, self.tilt,
                 1.0 if then == SIFT else 0.0, d > 1e-6)
    self._next = then
    self.hops += 1
    turn = abs(vec.wrap_angle(yaw1 - self.yaw))
    self._set_state(HOP, HOP_BASE + HOP_PER_M * d + HOP_PER_RAD * turn)

  def _hop_step(self, dt, others):
    p0, p1, yaw0, yaw1, tilt0, tilt1, moving = self._hop
    t = min(1.0, self.state_time / self.state_len)
    self.yaw = lerp_angle(yaw0, yaw1, ease(t / 0.6))
    self.x, self.y = lerp2(p0, p1, ease(t))
    # Level out lifting off, nose down again landing
    if t < 0.5:
      self.tilt = tilt0 * (1.0 - ease(t / 0.35))
    else:
      self.tilt = tilt1 * ease((t - 0.6) / 0.4)
    bump = math.sin(math.pi * t) if moving else 0.0
    self.lift = HOP_LIFT * bump
    self.stroke = 1.0 if moving and t < 0.8 else 0.0
    self._ground(HOP_PITCH * bump)
    if t >= 1.0:
      self.target = None
      self.lift = 0.0
      then = self._next
      if then == SIFT:
        self.next_puff = 0.0
        self._set_state(SIFT, self._span(SIFT_TIME))
      else:
        self._set_state(REST, self._span(REST_TIME))

  # Steered by the user

  def _take_steer(self):
    """Leave off whatever it was doing, to swim as it is steered."""
    self.target = None
    self.phase = None
    self._hop = None
    self._dash = None
    self.lift = 0.0
    self.mode = CRUISE
    self.speed = max(self.speed, 0.3 * self.cruise_speed)
    self.stroking, self.stroke = True, 1.0
    self._set_state(STEERED)

  def _steered_step(self, dt, others):
    self.state_time += dt
    self._age_puffs(dt)
    self._tilt_toward(0.0, dt)
    if self.steer is None:
      # Let go: back down to the sand near by
      here = (self.x, self.y)
      self._dash = {'start': (self.x, self.y, self.z),
                    'top': (self.x, self.y, self.z),
                    'land': self._choose_landing(here, others)}
      self.target = self._dash['land']
      self._set_state(DASH)
      self._start_dive()
      return
    Fish.step(self, dt, others)

  # Dashes for air

  def _start_dash(self, others):
    """Up from here, drifting forward if the sand ahead is clear."""
    here = (self.x, self.y)
    ahead = (self.x + math.cos(self.yaw) * RISE_DRIFT,
             self.y + math.sin(self.yaw) * RISE_DRIFT)
    top_xy = ahead if self.floor.clear(here, ahead) else here
    top = (top_xy[0], top_xy[1], env.WATER_LEVEL - TOP_DEPTH * self.size)
    land = self._choose_landing(top_xy, others)
    self.target = land
    # A bigger fish swims faster (tankful.sim.fish)
    rise_time = (top[2] - self.z) / (RISE_SPEED * self.size)
    self._dash = {'start': (self.x, self.y, self.z), 'top': top,
                  'land': land, 'rise_time': rise_time}
    self.air_left = self.rng.uniform(*AIR_EVERY)
    self.dashes += 1
    self.phase = RISE
    self._set_state(DASH)

  def _choose_landing(self, top_xy, others):
    mates = self._others(others)
    for _ in range(30):
      a = self.rng.uniform(-math.pi, math.pi)
      d = self.rng.uniform(*LAND_DIST)
      p = (top_xy[0] + math.cos(a) * d, top_xy[1] + math.sin(a) * d)
      if self.floor.clear(top_xy, p) and self._free(p, mates):
        return p
    # Nowhere clear: back down where it went up
    return top_xy

  def _pitch_toward(self, goal, dt):
    s = SPECIES
    goal = vec.clamp(goal, -s.max_pitch, s.max_pitch)
    step = s.pitch_rate * dt
    self.pitch += vec.clamp(goal - self.pitch, -step, step)

  def _dash_step(self, dt):
    d = self._dash
    self.tilt = 0.0
    self.lift = 0.0
    self.stroke = 1.0
    before = (self.x, self.y, self.z)
    if self.phase == RISE:
      t = min(1.0, self.state_time / d['rise_time'])
      start, top = d['start'], d['top']
      xy = lerp2(start, top, ease(t))
      # Off the sand fast, slowing into the surface
      z = start[2] + (top[2] - start[2]) * math.sin(math.pi / 2 * ease(
        min(1.0, t * 1.15)))
      self.x, self.y, self.z = xy[0], xy[1], z
      climb = math.atan2(self.z - before[2],
                         max(math.dist(xy, before[:2]), 1e-9))
      self._pitch_toward(max(climb, GULP_PITCH), dt)
      if t >= 1.0:
        self.phase = GULP
        self.state_time = 0.0
    elif self.phase == GULP:
      t = min(1.0, self.state_time / GULP_TIME)
      top, land = d['top'], d['land']
      # A bob at the surface as it gulps, turning toward where it lands
      self.z = top[2] + 0.003 * math.sin(math.pi * t)
      if math.dist(top[:2], land) > 1e-6:
        away = math.atan2(land[1] - top[1], land[0] - top[0])
        self.yaw = lerp_angle(d.setdefault('yaw0', self.yaw), away, ease(t))
      self._pitch_toward(GULP_PITCH, dt)
      if t >= 1.0:
        self._start_dive()
    else:
      t = min(1.0, self.state_time * self.size / DIVE_TIME)
      p = bezier(d['dive'], ease(t))
      self.x, self.y, self.z = p
      fall = math.atan2(self.z - before[2],
                        max(math.dist(p[:2], before[:2]), 1e-9))
      # Following the path down, but level by the time it reaches the
      # sand, as it lies there
      self.pitch = d['pitch']
      self._pitch_toward(fall, dt)
      d['pitch'] = self.pitch
      self.pitch *= 1.0 - ease((t - 0.7) / 0.3)
      if t >= 1.0:
        self.pitch = 0.0
        self.target = None
        self.phase = None
        self.next_puff = 0.0
        self._set_state(SIFT, self._span(SIFT_TIME))

  def _start_dive(self):
    d = self._dash
    top, land = d['top'], d['land']
    # Lying level on the sand where it lands, as _ground puts it
    x, y = self.x, self.y
    self.x, self.y = land
    end_z = self.ground_z(tilt=0.0, lift=0.0)
    self.x, self.y = x, y
    off = vec.sub((land[0], land[1], 0.0), (top[0], top[1], 0.0))
    run = vec.length(off)
    flat = vec.scale(off, 1.0 / run) if run > 1e-6 else (0.0, 0.0, 0.0)
    back = min(0.05, run * 0.6)
    # Down from the top, but not into the sand when it starts low
    d['dive'] = (top, (top[0], top[1], max(top[2] - 0.12, end_z + 0.015)),
                 (land[0] - flat[0] * back, land[1] - flat[1] * back,
                  end_z + 0.015),
                 (land[0], land[1], end_z))
    d['pitch'] = self.pitch
    self.phase = DIVE
    self.state_time = 0.0

  # Puffs

  def _puff(self):
    """Throw up a puff of sand, in the slot that is free or oldest."""
    k = min(range(PUFFS), key=lambda i: -math.inf if self.puffs[i] is None
            else -self.puffs[i])
    self.puffs[k] = 0.0

  def _age_puffs(self, dt):
    for i, age in enumerate(self.puffs):
      if age is not None:
        age += dt
        self.puffs[i] = None if age >= PUFF_LIFE else age

  def active_puffs(self):
    return sum(age is not None for age in self.puffs)

  def snapshot(self):
    snap = super().snapshot()
    snap.update({
      'state': self.state,
      'phase': self.phase,
      'above_sand': round(self.above_sand(), 4),
      'tilt': round(self.tilt, 3),
      'puffs': self.active_puffs(),
      'hops': self.hops,
      'dashes': self.dashes,
    })
    return snap


# The pose
#
# The rig (tools/species/corydoras.py) is the spine chain of
# tankful.sim.swim, the pectoral fins, which point back and out at rest
# (so bone x is the fish's left and z its back), and the sand puffs:
#
#   Root -> Head -> Spine.0 -> Spine.1 -> Spine.2 -> Tail
#   Head -> Pec.L, Pec.R
#   Root -> Puff.0, Puff.1
#
# Each Puff bone sits at the mouth pointing straight back, carrying its
# puff, a dome of sand grains on the sand, built at full size.  The bone
# turns the dome upright against the fish's tilt and scales it as the
# puff rises, spreads and settles: the bone's z is up, x across the fish
# and y along it.  A free slot's dome is scaled to nothing.

PUFF_BONES = tuple('Puff.%d' % i for i in range(PUFFS))
BONES = ('Head',) + swim.SPINE + ('Pec.L', 'Pec.R') + PUFF_BONES
# How far the pectorals fold back along the body when it swims (rad)
PEC_FOLD = 0.7
# A free puff's scale
HIDDEN = 1e-4


def puff_scale(age):
  """(sx, sy, sz) of a puff age seconds old (None: no puff): it bursts
  up, spreads, and settles flat onto the sand."""
  if age is None or age >= PUFF_LIFE:
    return (HIDDEN, HIDDEN, HIDDEN)
  u = age / PUFF_LIFE
  burst = ease(u / 0.2)
  spread = burst * (0.45 + 0.75 * u)
  rise = burst * (1.0 - ease((u - 0.4) / 0.6))
  return (spread, spread, max(HIDDEN, rise))


def pose(fish):
  """{bone: (rx, ry, rz)} for a Corydoras now."""
  angles = swim.spine_pose(fish)
  # Sifting, the head works the sand from side to side and the body
  # follows a little
  work = fish.tilt * WORK_SWING * math.sin(fish.work_phase)
  hx, hy, hz = angles['Head']
  angles['Head'] = (hx, hy, hz + work)
  sx, sy, sz = angles['Spine.0']
  angles['Spine.0'] = (sx, sy, sz - work * 0.6)
  # The pectorals paddle, and fold back as it swims fast
  fold = PEC_FOLD * vec.clamp(fish.speed / fish.cruise_speed - 0.5, 0.0, 1.0)
  flap = fish.fin_amp * math.sin(fish.fin_phase)
  angles['Pec.L'] = (flap, 0.0, fold)
  angles['Pec.R'] = (-flap, 0.0, -fold)
  # Upright in the world whatever the fish's tilt: the fish is pitched
  # by turning about its left, the Puff bones' x
  for bone in PUFF_BONES:
    angles[bone] = (fish.pitch, 0.0, 0.0)
  return angles


def scales(fish):
  """{bone: (sx, sy, sz)}: the puffs."""
  return {bone: puff_scale(age) for bone, age in zip(PUFF_BONES, fish.puffs)}


def residents():
  """The corydoras in the tank: a loose group on the open sand, right of
  the middle.  start's z is unused: each starts on the sand, sifting."""
  starts = ((-0.02, -0.12, 2.6), (0.09, -0.09, 0.4), (0.15, -0.15, 1.9),
            (0.06, -0.16, -0.6), (0.24, -0.13, 3.3))
  sizes = (1.05, 0.95, 1.0, 0.9, 1.1)
  return [Resident('Corydoras.%d' % i, SPECIES, size, 606 + i,
                   (x, y, 0.0, heading))
          for i, ((x, y, heading), size) in enumerate(zip(starts, sizes))]


def stock(tank):
  """Add the corydoras to tank, as one Group, and return them."""
  group = Group(GROUP_NAME)
  out = []
  for r in residents():
    fish = Corydoras(r.name, r.species, r.size, r.seed, r.start)
    group.add(fish)
    out.append(fish)
  tank.fish.extend(out)
  return out
