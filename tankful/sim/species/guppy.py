"""Guppies: small, quick livebearers in a loose shoal that keeps to the
middle and top of the water.

Each guppy is a Guppy, a tankful.sim.fish.Fish, male or female.  Both
now and then flick: a quick dart aside on a snap of the tail.  The
males, smaller and with big fan tails, take turns chasing the females:

- a male at rest (CHASE_REST) may pick the nearest female within
  CHASE_RANGE and chase her for a while (CHASE_TIME), steering for a
  spot just behind and below her and swimming fast to close on it;
- close behind her (DISPLAY_RANGE) he displays: his body quivers in an
  S, his tail fan spreads and his dorsal fin rises (Guppy.display);
- she speeds up and turns away from a male chasing her close
  (FLEE_RANGE);
- he gives up when the time is out or she gets away, and rests.

The shoal (Shoal) holds no goal of its own, as a school does
(tankful.sim.school): the fish keep loosely together by the ordinary
pull between fish of a kind.  It is the group the model builds as one
armature (tools/species/guppy.py), so each member's bones are prefixed
with its name, under a Root bone, as for the neon tetras.

The rig is the spine chain with the fins on it:

  Head -> Spine.0 -> Spine.1 -> Spine.2 -> Tail -> Caudal
  Head -> Pec.L, Pec.R
  Spine.0 -> Dorsal

Caudal is the fan: it swings behind the tail's beat, snaps on a flick,
and scales taller as it spreads.
"""

import math

from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.fish import CRUISE, HOVER, Fish
from tankful.sim.species.base import Resident, Species

SPECIES = Species(
  name='guppy',
  length=0.042, height=0.016,
  clear_side=0.016, clear_up=0.010, clear_front=0.018,
  hover_speed=0.01, cruise_speed=0.085, max_speed=0.36,
  thrust=1.0, glide_time=0.4,
  pivot_rate=1.8, turn_radius=0.022, max_turn_rate=5.0,
  max_pitch=math.radians(30), pitch_rate=math.radians(80),
  max_bank=math.radians(26),
  depth_band=(0.55, 0.93),
  wander_frequency=0.3, wander_turn=0.5,
  hover_chance=0.03, hover_time=(0.8, 2.0),
  beat_base=3.0, beat_per_speed=1.7,
  wave_min=0.18, wave_max=0.55,
  fin_beat=7.0, fin_swing=0.35,
  turn_accel=16.0, roll_rate=3.0,
  flick_chance=0.12, flick_turn=1.0,
)

MALE, FEMALE = 'male', 'female'

FINS = ('Caudal', 'Pec.L', 'Pec.R', 'Dorsal')
BONES = ('Head',) + swim.SPINE + FINS

# How long a flick lasts (s), and how fast it beats the tail then
FLICK_TIME = 0.3
FLICK_BEAT = 2.2
# Chasing: how often (per s) a resting male starts, how long he rests
# first and chases (s), and how far off (m) a female may be
CHASE_CHANCE = 0.25
CHASE_REST = (3.0, 9.0)
CHASE_TIME = (3.0, 7.0)
CHASE_RANGE = 0.30
# Where he aims, behind and below her (her lengths), and how hard
CHASE_BEHIND, CHASE_BELOW = 1.1, 0.35
W_CHASE = 2.5
# He displays within this many of her lengths of the spot he aims for;
# she flees a chasing male within FLEE_RANGE of his lengths, this hard
DISPLAY_RANGE = 1.2
FLEE_RANGE = 3.0
W_FLEE = 1.2
# How fast the display comes on and goes (per s), and the quiver's rate
DISPLAY_RATE = 3.0
QUIVER = 9.0


class Shoal:
  """The guppies as a group: what the model builds as one armature, and
  what selecting one of them selects (tankful.sim.school.group_of)."""

  def __init__(self, name, species):
    self.name = name
    self.species = species
    self.members = []

  def add(self, fish):
    fish.school = self
    self.members.append(fish)

  def __contains__(self, fish):
    return fish in self.members

  def step(self, dt):
    """The shoal has no goal to move: its fish steer on their own."""

  def settle(self):
    """Nothing to settle: the fish keep apart as any fish do."""

  def males(self):
    return [f for f in self.members if f.male]

  def females(self):
    return [f for f in self.members if not f.male]

  def snapshot(self):
    return {
      'name': self.name,
      'species': self.species.name,
      'members': [f.name for f in self.members],
      'chases': {f.name: f.chase.name for f in self.members
                 if f.male and f.chase is not None},
    }


class Guppy(Fish):

  def __init__(self, name, species, sex, size=1.0, seed=0,
               position=(0, 0, 0.3), heading=0.0):
    if sex not in (MALE, FEMALE):
      raise ValueError('a guppy is male or female, not %r' % (sex,))
    self.sex = sex
    self.flick_left = 0.0
    self.flick_turn = 0.0
    self.chase = None
    self.chase_left = 0.0
    self.display = 0.0
    self.quiver_phase = 0.0
    self.fleeing = 0.0
    super().__init__(name, species, size, seed, position, heading)
    self.rest_left = self.rng.uniform(*CHASE_REST)

  @property
  def male(self):
    return self.sex == MALE

  @property
  def flicking(self):
    return self.flick_left > 0

  def _mates(self):
    return self.school.members if self.school is not None else ()

  def _update_mode(self, dt):
    s = self.species
    if self.flick_left > 0:
      self.flick_left = max(0.0, self.flick_left - dt)
    elif self.danger < 0.3 and self.rng.random() < s.flick_chance * dt:
      self.flick_left = FLICK_TIME
      self.flick_turn = (self.rng.choice((-1, 1)) * s.flick_turn
                         * self.rng.uniform(0.6, 1.0))
      self.stroking = True
      self.stroke = 1.0
    if self.male:
      self._update_chase(dt)
    busy = self.flicking or self.chase is not None or self.fleeing > 0
    if busy and self.mode == HOVER:
      self.mode, self.mode_time = CRUISE, 0.0
    elif not busy:
      super()._update_mode(dt)

  def _update_chase(self, dt):
    if self.chase is None:
      self.rest_left -= dt
      if self.rest_left <= 0 and self.rng.random() < CHASE_CHANCE * dt:
        her = self._nearest_female()
        if her is not None:
          self.chase = her
          self.chase_left = self.rng.uniform(*CHASE_TIME)
    else:
      self.chase_left -= dt
      her = self.chase
      if (self.chase_left <= 0
          or math.dist((self.x, self.y, self.z), (her.x, her.y, her.z))
          > 1.5 * CHASE_RANGE):
        self.stop_chase()
    near = (self.chase is not None
            and vec.length(vec.sub(self.chase_spot(),
                                   (self.x, self.y, self.z)))
            < DISPLAY_RANGE * self.chase.length)
    goal = 1.0 if near else 0.0
    step = DISPLAY_RATE * dt
    self.display += vec.clamp(goal - self.display, -step, step)
    self.quiver_phase = (self.quiver_phase
                         + 2 * math.pi * QUIVER * dt) % (2 * math.pi)

  def stop_chase(self):
    """Give up the chase and rest."""
    self.chase = None
    self.chase_left = 0.0
    self.rest_left = self.rng.uniform(*CHASE_REST)

  def _nearest_female(self):
    best, best_d = None, CHASE_RANGE
    for f in self._mates():
      if f.male:
        continue
      d = math.dist((self.x, self.y, self.z), (f.x, f.y, f.z))
      if d < best_d:
        best, best_d = f, d
    return best

  def chase_spot(self):
    """Where a male chasing her aims: just behind and below her."""
    her = self.chase
    back = vec.scale(her.forward(), -CHASE_BEHIND * her.length)
    return vec.add((her.x, her.y, her.z - CHASE_BELOW * her.length), back)

  def _chasers(self):
    """The males chasing self within FLEE_RANGE: [(male, offset from
    him, distance)]."""
    out = []
    for m in self._mates():
      if m.male and m.chase is self:
        off = (self.x - m.x, self.y - m.y, self.z - m.z)
        d = vec.length(off)
        if d < FLEE_RANGE * m.length:
          out.append((m, off, d))
    return out

  def _desired(self, others):
    s = self.species
    fwd = self.forward()
    wander = self._wander(self.time) * s.wander_turn
    if self.mode == HOVER:
      wander *= 0.4
    h = self.yaw + wander
    want = [math.cos(h), math.sin(h), 0.0]
    z_want = self._depth_target()
    want[2] = vec.clamp((z_want - self.z) / 0.08, -1.0, 1.0) * 0.45
    if self.chase is not None:
      off = vec.sub(self.chase_spot(), (self.x, self.y, self.z))
      toward = vec.normalized(off, fwd)
      for axis in range(3):
        want[axis] += toward[axis] * W_CHASE
      # Chasing, he follows her depth, not his own
      z_want = self.chase.z
    flee = 0.0
    for m, off, d in self._chasers():
      near = 1.0 - d / (FLEE_RANGE * m.length)
      flee = max(flee, near)
      away = vec.normalized(off, fwd)
      for axis in range(3):
        want[axis] += away[axis] * W_FLEE * near
    self.fleeing = flee
    if self.flicking:
      h = self.yaw + self.flick_turn
      want[0] += math.cos(h) * 4.0
      want[1] += math.sin(h) * 4.0
    want[2] = vec.clamp(want[2], -0.7, 0.7)
    self.danger = self._steer_clear(want)
    self._mind_others(want, others)
    return vec.normalized(tuple(want), fwd), z_want

  def _target_speed(self, want):
    s = self.species
    if self.flicking:
      return self.max_speed * 0.7, s.glide_time
    target, glide = super()._target_speed(want)
    if self.chase is not None:
      gap = vec.length(vec.sub(self.chase_spot(), (self.x, self.y, self.z)))
      # Close the gap fast, then hold her pace
      catch = vec.clamp(gap / (3 * self.length), 0.0, 1.0)
      target = max(target, self.chase.speed * (1.0 + 1.5 * catch))
    if self.fleeing:
      target *= 1.0 + 0.6 * self.fleeing
    return min(target, self.max_speed * 0.8), glide

  def _gait(self, dt):
    super()._gait(dt)
    if self.flicking:
      # The snap of the tail that drives a flick
      self.beat_phase = (self.beat_phase + 2 * math.pi * self.beat_freq
                         * FLICK_BEAT * dt) % (2 * math.pi)
      self.wave = max(self.wave, self.species.wave_max)

  def snapshot(self):
    snap = super().snapshot()
    snap['sex'] = self.sex
    snap['flicking'] = self.flicking
    snap['chasing'] = self.chase.name if self.chase is not None else None
    snap['display'] = round(self.display, 3)
    return snap


SHOAL = 'Guppies'


def residents():
  """The guppies in the tank, as (Resident, sex): three males, smaller,
  and three females, near the top toward the front left."""
  rows = (
    ('Guppy.M0', MALE, 0.80, (-0.14, -0.07, 0.36, 0.2)),
    ('Guppy.M1', MALE, 0.78, (-0.05, -0.03, 0.38, 2.9)),
    ('Guppy.M2', MALE, 0.82, (-0.22, 0.0, 0.34, 0.6)),
    ('Guppy.F0', FEMALE, 1.05, (-0.10, -0.09, 0.34, 0.1)),
    ('Guppy.F1', FEMALE, 1.0, (-0.02, -0.06, 0.37, 3.1)),
    ('Guppy.F2', FEMALE, 1.1, (-0.18, -0.03, 0.39, 0.4)),
  )
  return [(Resident(name, SPECIES, size, 707 + i, start), sex)
          for i, (name, sex, size, start) in enumerate(rows)]


def stock(tank):
  shoal = Shoal(SHOAL, SPECIES)
  out = []
  for res, sex in residents():
    x, y, z, heading = res.start
    g = Guppy(res.name, res.species, sex, res.size, res.seed, (x, y, z),
              heading)
    shoal.add(g)
    out.append(g)
  tank.fish.extend(out)
  tank.schools.append(shoal)
  return out


def pose(fish):
  """{bone: (rx, ry, rz)} for fish now."""
  angles = swim.spine_pose(fish)
  display = fish.display

  # A displaying male quivers in an S: the front and rear of the body
  # bend opposite ways, fast
  if display > 0:
    q = display * 0.22 * math.sin(fish.quiver_phase)
    for name, k in (('Spine.0', 1.0), ('Spine.1', -1.6), ('Spine.2', 1.2),
                    ('Tail', -0.6)):
      rx, ry, rz = angles[name]
      angles[name] = (rx, ry, rz + k * q)

  # The fan swings behind the tail's beat, wider for a flick
  swing = 0.45 if fish.flicking else 0.3
  angles['Caudal'] = (0.0, 0.0,
                      fish.wave * swing * math.sin(fish.beat_phase - 1.3))

  # Pectorals: flutter, fast, more when slow
  amp = fish.fin_amp
  for name, side, offset in (('Pec.L', 1.0, 0.0), ('Pec.R', -1.0, 2.4)):
    p = fish.fin_phase + offset
    spread = 0.15 + 0.3 * fish.hovering + amp * 0.5 * (1 + math.sin(p))
    angles[name] = (0.0, side * 0.4 * amp * math.cos(p), -side * spread)

  # Dorsal: laid back when swimming fast, raised on display, swaying
  # behind the body's swing
  pace = min(1.0, fish.speed / max(fish.cruise_speed, 1e-6))
  lift = 0.35 * display - 0.2 * pace
  sway = fish.wave * 0.25 * math.sin(fish.beat_phase - 2.0)
  angles['Dorsal'] = (lift, 0.0, sway)
  return angles


def scales(fish):
  """{bone: (sx, sy, sz)}: the fan spreads taller on display and in a
  flick."""
  spread = 1.0 + 0.25 * fish.display + (0.15 if fish.flicking else 0.0)
  return {'Caudal': (1.0, 1.0, spread)}
