"""The fish agent: where a fish goes and how it holds itself on the way.

Each step a fish blends what it wants into one desired direction:

- wander: a heading offset that drifts with smooth noise;
- depth: a target height that wanders within the species' depth band;
- the glass, sand and surface: pushed off when a look-ahead point gets
  near them, hardest when nearest;
- decor (tankful.sim.environment.obstacles) the same way, gentler for
  the soft plants;
- the other fish: kept apart, and drawn together when far apart;
- at night, the plants, for the species whose Night says so.

When its body (a capsule along its spine, Fish.body) touches another
fish's, it is startled: it gets a kick of speed and darts away for a
moment, then is not startled again for a while (Fish._bump).  Fish of
one group (a school, shoal or colony) keep apart by separation instead,
and a fish the user steers is never startled: only the fish it bumps
into flees, and gives way to it (Fish._keep_apart).  A pleco on the
glass or a shrimp on the sand (anchored) holds on, and the fish that
bumps into it darts off; bumping into a shrimp startles no fish, but a
swimming shrimp darts off itself.

At night (Fish.night, tankful.sim.daynight) the species' Night also
changes its speed, depth band, hovering and how near the surface it may
rest (by_night).

It then turns toward that direction within its limits: a heading rate
that grows with speed up to max_turn_rate (a fish pivots slowly on the
spot and turns tightest when swimming), and a pitch kept within
max_pitch.  It banks into turns, and swims in strokes and glides: it
strokes (and speeds up) when it is slower than it wants, and coasts,
slowing with drag, when faster.  Now and then it hovers: it stops nearly
still and holds itself with its fins.

Hard limits back the steering up: the center never leaves the swim box
or enters the decor, whatever a step's dt.

The user may steer a fish (tankful.sim.steering): while Fish.steer is
set, its weight blends the direction the arrow keys ask for, in the
screen plane at the depth (y) the fish had when it was taken, into what
the fish wants, and the fish cruises rather than hovers.  It turns,
pitches and banks toward that as it does toward its own wants, so it
faces the way it goes.  A species with states of its own takes the
steer up in them (the pleco lets go of the glass first).

Coordinates as in tankful.sim.tank: x to the viewer's right, y away from
the viewer, z up.  yaw is the heading about z from +x, counterclockwise
seen from above; pitch is nose up; roll is about the fish's own forward
axis, positive rolling its back toward its right side.
"""

import math
import random

from tankful.sim import daynight
from tankful.sim import environment as env
from tankful.sim import vec
from tankful.sim.noise import SmoothNoise

CRUISE, HOVER = 'cruise', 'hover'

# The longest step taken at once, so a frame hitch cannot fling a fish
MAX_STEP = 0.1
# How far ahead of its walls and decor a fish starts to steer
MARGIN = 0.10
# The sand's and surface's pushes each reach at most this share of the
# swim box's height, so a tall fish's short box keeps room to swim in
VERTICAL_MARGIN_SHARE = 0.25
# Fish nearer than this many lengths (the longer one's) push apart;
# farther than COHESION meters they drift together
SEPARATION = 1.4
COHESION = 0.40
# Closer than this many lengths and fish are moved apart outright
MIN_GAP = 0.75
# At least this long cruising between hovers
MIN_CRUISE = 6.0
# At night, a fish drawn to the plants keeps within this many of its
# lengths of their leaves, and hovers more once within PLANT_NEAR (m) of
# there
PLANT_KEEP = 0.5
PLANT_NEAR = 0.03
# Steered (tankful.sim.steering): how hard a fish holds its depth, and
# within how far of it (m) it eases off, and how much it moves across
# the screen when asked only to climb or dive
STEER_HOLD = 0.7
STEER_HOLD_NEAR = 0.03
STEER_CLIMB_RUN = 0.6
# The body capsule (Fish.body), in lengths: from BODY_FRONT ahead of the
# center to BODY_BACK behind it, BODY_RADIUS round.  The tail fin bends
# and is left out, and the capsule is as thick as the body is from side
# to side: as deep as an angelfish is, fish swimming side by side would
# touch all the time
BODY_FRONT, BODY_BACK, BODY_RADIUS = 0.42, 0.30, 0.09
# How far a body reaches from the center, in lengths
BODY_REACH = BODY_FRONT + BODY_RADIUS
# Collisions (Fish._bump): bumped, a fish darts away for STARTLE_TIME
# (s), its speed kicked up by STARTLE_KICK of its cruise and held up to
# STARTLE_SPEED of its most, steering away with W_STARTLE; it is not
# startled again until STARTLE_CALM (s) after the bump
STARTLE_TIME = 0.8
STARTLE_CALM = 2.5
STARTLE_KICK = 0.8
STARTLE_SPEED = 0.7
W_STARTLE = 4.0


class Fish:

  # The tankful.sim.school.School the fish swims in, if any
  school = None
  # How far into the night it is, 0 by day to 1 (tankful.sim.daynight):
  # the tank sets it each step
  night = 0.0
  # How far it is from where it keeps by the plants at night (m), or None
  # (Fish._seek_plants)
  plant_gap = None
  # The user's tankful.sim.steering.Steer while it is steered, and the
  # depth (y) it keeps meanwhile
  steer = None
  _steer_y = None
  # Whether bumping into it startles the other fish (Fish._bump): the
  # little shrimp get out of the way themselves
  startles_others = True
  # How long a bump startles it (s)
  startle_time = STARTLE_TIME
  # When a bump last startled it (its own time), the way it darts off,
  # and how many times one has
  _startled_at = None
  _startle_away = None
  _kick = False
  bumps = 0

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
    # The plant clumps, which some fish keep near at night
    self._plants = [o for o in self._obstacles if o.soft]
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
    """The species' cruising speed for this fish, by day: the pose and
    gait measure pace against it.  swim_speed is what it cruises at
    now."""
    return self.species.cruise_speed * self.size

  # Night (tankful.sim.daynight)

  def by_night(self, name):
    """The factor the species' Night gives for name (a Night field such
    as 'speed'), blended in by how far into the night it is: 1 by day."""
    return daynight.factor(self.species, name, self.night)

  @property
  def swim_speed(self):
    """The speed it cruises at now: slower or faster at night."""
    return self.cruise_speed * self.by_night('speed')

  def depth_band(self):
    """The preferred depth band now (as Species.depth_band)."""
    return daynight.depth_band(self.species, self.night)

  def surface_margin(self):
    """How far below the top of its swim box the surface starts to push
    it down (m), before _steer_clear caps it to its share of the box."""
    top = self.species.surface_margin
    if top is None:
      top = MARGIN
    mod = self.species.night
    if mod is None or mod.surface_margin is None or not self.night:
      return top
    return daynight.blend(top, mod.surface_margin, self.night)

  def body(self):
    """The body capsule: (front, back, radius)."""
    f = self.forward()
    p = (self.x, self.y, self.z)
    length = self.length
    return (vec.add(p, vec.scale(f, BODY_FRONT * length)),
            vec.sub(p, vec.scale(f, BODY_BACK * length)),
            BODY_RADIUS * length)

  # Who has a say in where it goes

  @property
  def user_steered(self):
    """Whether the user steers it, on its own or with its school, the
    steer on or blending out (tankful.sim.steering)."""
    return (self.steer is not None
            or getattr(self.school, 'steer', None) is not None)

  @property
  def anchored(self):
    """Whether its own states, not swimming, hold it where it is now (a
    pleco on the glass, a shrimp picking): it is not pushed about."""
    return False

  @property
  def startled(self):
    """How startled it is: 1 just bumped, easing to 0 over startle_time."""
    if self._startled_at is None:
      return 0.0
    left = 1.0 - (self.time - self._startled_at) / self.startle_time
    return left if left > 0 else 0.0

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
    steer = self.steered
    if steer:
      self.mode = CRUISE
    else:
      self._update_mode(dt)
    want, z_want = self._desired(others)
    if steer:
      want = self._steered(want, steer)
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

  @property
  def steered(self):
    """The Steer on the fish if it has any say now (weight above 0),
    else None.  Sets the depth it holds when first steered, and forgets
    it once let go."""
    steer = self.steer
    if steer is None:
      self._steer_y = None
      return None
    if self._steer_y is None:
      self._steer_y = self.y
    return steer if steer.weight > 0 else None

  def _steered(self, want, steer):
    """want blended by steer's weight toward its direction: across the
    screen (x) and up or down (z), drawn back to the held depth.  Asked
    only to climb or dive, the fish keeps moving the way it faces across
    the screen, as a fish can't rise straight up."""
    dx, dz = steer.direction
    if abs(dx) < 1e-6:
      dx = math.copysign(STEER_CLIMB_RUN, math.cos(self.yaw))
    dy = vec.clamp((self._steer_y - self.y) / STEER_HOLD_NEAR,
                   -1.0, 1.0) * STEER_HOLD
    user = vec.normalized((dx, dy, dz))
    w = steer.weight
    mixed = tuple(want[i] * (1.0 - w) + user[i] * w for i in range(3))
    return vec.normalized(mixed, user)

  def _update_mode(self, dt):
    s = self.species
    if self.mode == HOVER:
      self.hover_left -= dt
      if self.hover_left <= 0 or self.danger > 0.8:
        self.mode, self.mode_time = CRUISE, 0.0
    elif (self.mode_time > MIN_CRUISE and self.danger < 0.5
          and self.rng.random() < s.hover_chance * self._hover_factor() * dt):
      self.mode, self.mode_time = HOVER, 0.0
      self.hover_left = (self.rng.uniform(*s.hover_time)
                         * self.by_night('hover_time'))

  def _hover_factor(self):
    """How much more often than by day it stops to hover now.  A fish
    drawn to the plants at night hovers more only once it is there."""
    if self.plant_gap is not None and self.plant_gap > PLANT_NEAR:
      return 1.0
    return self.by_night('hover')

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
    self._seek_plants(want)
    self.danger = self._steer_clear(want)
    self._mind_others(want, others)
    return vec.normalized(tuple(want), self.forward()), z_want

  def _seek_plants(self, want):
    """At night, add to want a pull toward the nearest plant clump, as
    hard as the species' Night says, easing off as the fish comes within
    PLANT_KEEP of its body lengths of the leaves.  Sets plant_gap: how
    far it is from there (m), or None when not drawn to the plants."""
    mod = self.species.night
    pull = mod.plants * self.night if mod is not None else 0.0
    if pull <= 0 or not self._plants:
      self.plant_gap = None
      return
    pos = (self.x, self.y, self.z)
    best = None
    for plant in self._plants:
      c = vec.closest_on_segment(pos, plant.a, plant.b)
      d = math.dist(pos, c) - self.clearance(plant)
      if best is None or d < best[0]:
        best = (d, c)
    d, c = best
    gap = d - PLANT_KEEP * self.length
    self.plant_gap = max(0.0, gap)
    if gap <= 0:
      return
    toward = vec.normalized(vec.sub(c, pos), self.forward())
    w = pull * min(1.0, gap / 0.1)
    for axis in range(3):
      want[axis] += toward[axis] * w

  def _depth_target(self):
    lo, hi = self.depth_band()
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
    # The surface's margin is the species' own; neither it nor the sand's
    # takes more than its share of the box's height
    cap = max(z1 - z0, 0.0) * VERTICAL_MARGIN_SHARE
    floor, top = min(MARGIN, cap), min(self.surface_margin(), cap)
    for axis, (a, b) in enumerate(((x0, x1), (y0, y1), (z0, z1))):
      lo, hi = (floor, top) if axis == 2 else (MARGIN, MARGIN)
      if lo <= 0 or hi <= 0:
        continue
      for p in (pos[axis], ahead[axis]):
        near_lo = (a + lo - p) / lo
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
    another kind pushes less.  A fish it bumps into startles it
    (_bump), and while startled it darts away.

    Every fish checks every other each step, so the fish of other kinds
    that are a separation or more apart along any axis, which can only
    be farther, are passed over before anything else is worked out.
    That is never near enough for their bodies to touch: two bodies
    reach at most 2 BODY_REACH of the longer one's length, less than
    SEPARATION."""
    fwd = self.forward()
    x, y, z = self.x, self.y, self.z
    species = self.species
    length = self.length
    bumps = self.may_startle
    for other in others:
      if other is self or other in skip:
        continue
      dx, dy, dz = x - other.x, y - other.y, z - other.z
      other_length = other.length
      sep = SEPARATION * max(length, other_length)
      same = other.species is species
      if not same and (abs(dx) >= sep or abs(dy) >= sep or abs(dz) >= sep):
        continue
      off = (dx, dy, dz)
      d = math.sqrt(dx * dx + dy * dy + dz * dz)
      if (bumps and d < BODY_REACH * (length + other_length)
          and self._bump(other)):
        bumps = False
      if d < sep:
        away = vec.normalized(off, (-fwd[0], -fwd[1], 0.0))
        w = (1.0 - d / sep) ** 2 * 3.0
        if not same:
          w *= min(1.0, other_length / length)
        for axis in range(3):
          want[axis] += away[axis] * w
      elif d > COHESION and same:
        toward = vec.scale(vec.normalized(off), -0.12)
        for axis in range(3):
          want[axis] += toward[axis]
    startle = self.startled
    if startle:
      for axis in range(3):
        want[axis] += self._startle_away[axis] * W_STARTLE * startle

  def _bump(self, other):
    """If self's body touches other's, startle them both: each darts away
    from the other.  Whether self was startled.  self is one that may be
    (may_startle).

    Both are startled here, by whichever steps first, since its step then
    pushes them apart (_keep_apart) before the other's step looks.  Fish
    of one group (a school, shoal or colony: Fish.school) keep apart by
    their separation instead.  A fish the user steers, or held where it
    is (anchored), is never startled, so only the fish that bumps it
    flees.  Bumping into a fish whose startles_others is off (a shrimp)
    doesn't startle the fish, only the shrimp, when it swims."""
    mine = other.startles_others
    theirs = self.startles_others and other.may_startle
    if not (mine or theirs) or (
        self.school is not None and other.school is self.school):
      return False
    a0, a1, ra = self.body()
    b0, b1, rb = other.body()
    p, q = vec.closest_between_segments(a0, a1, b0, b1)
    off = vec.sub(p, q)
    if vec.length(off) >= ra + rb:
      return False
    fwd = self.forward()
    away = vec.normalized(off, vec.normalized(
      (self.x - other.x, self.y - other.y, self.z - other.z),
      (-fwd[1], fwd[0], 0.0)))
    if mine:
      self._startle(away)
    if theirs:
      other._startle(vec.scale(away, -1.0))
    return mine

  @property
  def may_startle(self):
    """Whether a bump would startle it now: not steered by the user, not
    held where it is, and calm again since the last one (STARTLE_CALM)."""
    return (not self.user_steered and not self.anchored
            and (self._startled_at is None
                 or self.time - self._startled_at >= STARTLE_CALM))

  def _startle(self, away):
    """Dart off along away (a unit vector): a kick of speed, and a while
    swimming that way (startled)."""
    fwd = self.forward()
    # Mostly level: up or down is where the sand and surface are
    self._startle_away = vec.normalized((away[0], away[1], away[2] * 0.5),
                                        (-fwd[1], fwd[0], 0.0))
    self._startled_at = self.time
    self.bumps += 1
    self.mode, self.mode_time = CRUISE, 0.0
    # The kick of speed comes in its own step (_swim): the other fish of
    # a bump may have stepped already, its gait set to its speed
    self._kick = True

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
    steer = self.steered
    if steer:
      # Steered, it cruises, slowing only to turn hard
      along = vec.dot(self.forward(), want)
      user = self.swim_speed * (0.55 + 0.45 * max(0.0, along))
      target += (user - target) * steer.weight
    startle = self.startled
    if startle:
      # Bumped: away fast, from a kick
      target = max(target, self.max_speed * STARTLE_SPEED * startle)
      if self._kick:
        self._kick = False
        self.speed = min(self.max_speed,
                         self.speed + STARTLE_KICK * self.cruise_speed)
        self.stroking, self.stroke = True, 1.0
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
      return (s.hover_speed * self.size * self.by_night('speed'),
              s.glide_time * 0.35)
    pace = 0.8 + 0.35 * self._pace(self.time)
    fwd = self.forward()
    # Slow down to turn hard, and near walls and decor
    along = vec.dot(fwd, want)
    target = (self.swim_speed * pace * (0.55 + 0.45 * max(0.0, along))
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
    """Move apart from fish nearer than their MIN_GAP, by self's share
    of the overlap; the other fish takes the rest on its own step.  A
    fish held where it is (anchored) or that the user steers holds its
    place, and the other takes the whole overlap: the user's fish goes
    where it is steered, and only the fish in its way gives."""
    species = self.species
    length = self.length
    steered = None
    for other in others:
      if other is self:
        continue
      dx, dy, dz = self.x - other.x, self.y - other.y, self.z - other.z
      other_length = other.length
      if other.species is species:
        gap = MIN_GAP * max(length, other_length)
      else:
        gap = MIN_GAP * 0.5 * (length + other_length)
      # A gap or more apart along an axis is farther: most fish are
      if abs(dx) >= gap or abs(dy) >= gap or abs(dz) >= gap:
        continue
      off = (dx, dy, dz)
      d = math.sqrt(dx * dx + dy * dy + dz * dz)
      if d < gap:
        if steered is None:
          steered = self.user_steered
        other_steered = other.user_steered
        if other.anchored or (other_steered and not steered):
          share = 1.0
        elif steered and not other_steered:
          continue
        elif other.species is species:
          share = 0.5
        else:
          share = other_length / (length + other_length)
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
      'startled': round(self.startled, 3),
      'bumps': self.bumps,
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
