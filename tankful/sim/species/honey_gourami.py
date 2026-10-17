"""Honey gouramis: small, slow, golden fish that keep near the surface
and probe what they meet with their feelers.

Each is a Gourami, a tankful.sim.fish.Fish that also works its feelers,
the long thread-like pelvic fins.  Each feeler (Gourami.feelers) trails
back and down from the chest until something comes within PROBE_RANGE
ahead: another fish, or the decor.  Then the feeler on its side (or both,
when it is straight ahead) swings down and forward to reach toward it,
following it as the fish moves, and the fish slows to feel it.  The
probe ends after a while, or when the thing drops behind or out of
reach.  Now and then, more often when hovering, a feeler reaches out
with nothing to aim at, as gouramis feel the water about them.

The rig (tools/species/honey_gourami.py) is the spine chain of
tankful.sim.swim with fin bones that all point straight back at rest (so
bone x is the fish's left and z its back):

  Head -> Spine.0 -> Spine.1 -> Spine.2 -> Tail
  Head -> Pec.L, Pec.R, Feeler.L, Feeler.R
  Spine.0 -> Dorsal, Anal

The feelers' threads hang FEELER_REST below the bone at rest.
"""

import math

from tankful.sim import vec
from tankful.sim import swim
from tankful.sim.daynight import Night
from tankful.sim.fish import MAX_STEP, Fish
from tankful.sim.species.base import Resident, Species

SPECIES = Species(
  name='honey_gourami',
  length=0.05, height=0.03,
  clear_side=0.02, clear_up=0.012, clear_front=0.025,
  hover_speed=0.003, cruise_speed=0.03, max_speed=0.12,
  thrust=0.06, glide_time=1.4,
  pivot_rate=0.7, turn_radius=0.04, max_turn_rate=1.8,
  max_pitch=math.radians(20), pitch_rate=math.radians(30),
  max_bank=math.radians(12),
  depth_band=(0.86, 1.0),
  wander_frequency=0.08, wander_turn=0.4,
  hover_chance=0.1, hover_time=(3.0, 9.0),
  beat_base=1.0, beat_per_speed=1.4,
  wave_min=0.08, wave_max=0.35,
  fin_beat=3.0, fin_swing=0.45,
  # A surface fish: the surface pushes it down only near the top
  surface_margin=0.06,
  # At night they hang still by the tall plants, a little below the top
  night=Night(speed=0.5, depth_band=(0.65, 0.9), hover=4.0, hover_time=2.0,
              plants=1.2),
)

FEELERS = ('Feeler.L', 'Feeler.R')
FINS = ('Pec.L', 'Pec.R') + FEELERS + ('Dorsal', 'Anal')
BONES = ('Head',) + swim.SPINE + FINS

# The male: honey-gold with a dark throat (tools/species/honey_gourami.py)
MALES = ('HoneyGourami.0',)

# How far ahead (m) a gourami notices things to probe, and how far to
# either side of straight ahead (radians)
PROBE_RANGE = 0.10
PROBE_CONE = 1.2
# A probe: how long a feeler holds out (s), how long it rests after, and
# how fast it reaches out and draws back (of its full reach per second)
PROBE_TIME = (1.2, 3.0)
PROBE_REST = (0.8, 2.5)
REACH_RATE = 1.6
# How often (per second) a resting feeler reaches out at nothing, and
# how much more often when hovering
IDLE_CHANCE = 0.06
HOVER_IDLE = 3.0
# How much the fish slows while a feeler is all the way out
PROBE_SLOW = 0.6
# The aim a feeler takes: how far to the side (radians) and below the
# fish's forward it can point
MAX_SIDE = 0.7
DIP = (math.radians(-10), math.radians(60))
# Straight ahead, within this angle (radians) both feelers reach out
BOTH = 0.25
# The thread's rest angle below straight back (radians): the model
# hangs it so
FEELER_REST = math.radians(35)


class Feeler:
  """One feeler's state: how far out it is (reach, 0 trailing to 1 all
  the way forward), where it aims (side, positive to the fish's left, and
  dip, below its forward), and what it probes (target, None for nothing
  in particular)."""

  def __init__(self, side):
    # +1 the left feeler, -1 the right
    self.sign = side
    self.reach = 0.0
    self.goal = 0.0
    self.side = 0.0
    self.dip = DIP[1] * 0.5
    self.target = None
    self.left = 0.0
    self.rest = 0.0
    self.probes = 0

  @property
  def probing(self):
    return self.goal > 0

  def start(self, target, side, dip, hold):
    self.target = target
    self.side, self.dip = side, dip
    self.goal = 1.0
    self.left = hold
    self.probes += 1

  def stop(self, rest):
    self.target = None
    self.goal = 0.0
    self.rest = rest


class Gourami(Fish):

  def __init__(self, name, species, size=1.0, seed=0, position=(0, 0, 0.4),
               heading=0.0):
    super().__init__(name, species, size, seed, position, heading)
    self.feelers = (Feeler(1), Feeler(-1))
    self.feeler_phase = self.rng.uniform(0, 2 * math.pi)

  @property
  def probing(self):
    """How far out the feeler furthest out is, 0 to 1."""
    return max(f.reach for f in self.feelers)

  def step(self, dt, others=()):
    super().step(dt, others)
    dt = min(max(dt, 0.0), MAX_STEP)
    if dt == 0:
      return
    self.feeler_phase = (self.feeler_phase
                         + 2 * math.pi * 0.3 * dt) % (2 * math.pi)
    self._probe(dt, others)

  def _target_speed(self, want):
    target, glide = super()._target_speed(want)
    return target * (1.0 - PROBE_SLOW * self.probing), glide

  # Probing

  def _local(self, point):
    """point in the fish's space: (forward, left, up) of its center."""
    off = vec.sub(point, (self.x, self.y, self.z))
    m = self.orientation()
    return tuple(sum(m[i][j] * off[i] for i in range(3)) for j in range(3))

  def _aim(self, point):
    """(side, dip, distance) toward point, or None if it is out of the
    probing cone or range."""
    fx, fy, fz = self._local(point)
    d = math.sqrt(fx * fx + fy * fy + fz * fz)
    if d > PROBE_RANGE or d < 1e-6:
      return None
    side = math.atan2(fy, fx)
    if abs(side) > PROBE_CONE:
      return None
    dip = math.atan2(-fz, math.hypot(fx, fy))
    return (vec.clamp(side, -MAX_SIDE, MAX_SIDE),
            vec.clamp(dip, *DIP), d)

  def _target_point(self, target):
    if isinstance(target, Fish):
      return (target.x, target.y, target.z)
    return vec.closest_on_segment((self.x, self.y, self.z), target.a,
                                  target.b)

  def _find_target(self, others):
    """The nearest thing to probe ahead: (target, side, dip), or None."""
    best = None
    pos = (self.x, self.y, self.z)
    candidates = [o for o in others if o is not self]
    candidates += list(self._obstacles_near(pos, PROBE_RANGE))
    for target in candidates:
      aim = self._aim(self._target_point(target))
      if aim is not None and (best is None or aim[2] < best[0]):
        best = (aim[2], target, aim[0], aim[1])
    return None if best is None else best[1:]

  def _probe(self, dt, others):
    busy = [f for f in self.feelers if f.probing]
    for f in busy:
      f.left -= dt
      aim = None
      if f.target is not None:
        aim = self._aim(self._target_point(f.target))
        if aim is not None:
          f.side, f.dip = aim[0], aim[1]
      if f.left <= 0 or (f.target is not None and aim is None):
        f.stop(self.rng.uniform(*PROBE_REST))
    for f in self.feelers:
      if not f.probing:
        f.rest -= dt
    free = [f for f in self.feelers if not f.probing and f.rest <= 0]
    if free:
      found = self._find_target(others)
      if found is not None:
        target, side, dip = found
        if abs(side) < BOTH:
          chosen = free
        else:
          chosen = [f for f in free if f.sign * side > 0]
        if not any(f.target is target for f in self.feelers):
          for f in chosen:
            f.start(target, side, dip, self.rng.uniform(*PROBE_TIME))
      elif self.rng.random() < IDLE_CHANCE * (
          1.0 + HOVER_IDLE * self.hovering) * dt:
        f = self.rng.choice(free)
        f.start(None, f.sign * self.rng.uniform(0.1, MAX_SIDE),
                self.rng.uniform(0.2, DIP[1]),
                self.rng.uniform(*PROBE_TIME))
    for f in self.feelers:
      f.reach += vec.clamp(f.goal - f.reach, -REACH_RATE * dt,
                           REACH_RATE * dt)

  def snapshot(self):
    snap = super().snapshot()
    snap['feelers'] = [{
      'reach': round(f.reach, 3),
      'target': None if f.target is None else f.target.name,
      'probes': f.probes,
    } for f in self.feelers]
    return snap


def residents():
  """The honey gouramis in the tank: a male and a female."""
  return [
    Resident('HoneyGourami.0', SPECIES, 1.0, 707, (-0.30, -0.06, 0.40, 0.2)),
    Resident('HoneyGourami.1', SPECIES, 0.92, 808, (0.26, 0.04, 0.39, 2.9)),
  ]


def stock(tank):
  """Add the gouramis to tank, and return them."""
  out = []
  for r in residents():
    x, y, z, heading = r.start
    out.append(Gourami(r.name, r.species, r.size, r.seed, (x, y, z), heading))
  tank.fish.extend(out)
  return out


# The pose

def feeler_angles(f, fish):
  """(rx, ry, rz) for feeler f: trailing back and down, lifted closer to
  the body by speed and swaying slowly; reaching out, swung down and
  forward to its aim (rx, which turns the thread through below the
  chest) and to the side (rz)."""
  pace = min(1.0, fish.speed / max(fish.cruise_speed, 1e-6))
  sway = math.sin(fish.feeler_phase + (0.0 if f.sign > 0 else 1.9))
  trail = 0.25 * pace + 0.08 * sway
  # From the rest angle, FEELER_REST below straight back, to dip below
  # straight ahead: rx is positive tip up
  out = FEELER_REST + f.dip - math.pi
  rx = (1.0 - f.reach) * trail + f.reach * out
  # Positive z swings toward the fish's right; spread a little to its own
  # side as well as toward the aim
  rz = -(f.reach * (f.side + f.sign * 0.15) + 0.04 * f.sign * sway)
  return (rx, 0.0, rz)


def pose(fish):
  """{bone: (rx, ry, rz)} for a Gourami now."""
  angles = swim.spine_pose(fish)
  hover = fish.hovering
  amp = fish.fin_amp
  # Pectorals: clear fans that scull alternately, more when hovering
  for name, side, offset in (('Pec.L', 1.0, 0.0), ('Pec.R', -1.0, 2.9)):
    p = fish.fin_phase + offset
    spread = 0.15 + 0.3 * hover + amp * 0.5 * (1 + math.sin(p))
    angles[name] = (0.0, side * 0.5 * amp * math.cos(p), -side * spread)
  for name, f in zip(FEELERS, fish.feelers):
    angles[name] = feeler_angles(f, fish)
  # Dorsal and anal fins: sway behind the body's swing
  sway = (fish.wave * 0.3 * math.sin(fish.beat_phase - 2.0)
          + 0.04 * hover * math.sin(fish.fin_phase * 0.5))
  angles['Dorsal'] = (0.0, 0.0, sway)
  angles['Anal'] = (0.0, 0.0, -sway)
  return angles


def scales(fish):
  """{bone: (sx, sy, sz)}: no bone scales."""
  return {}
