"""The glass sucker: a bristlenose pleco that clings, rasps and darts.

A Pleco is a tankful.sim.fish.Fish that spends most of its time stuck
to a surface by its sucker mouth: the front or a side glass, the top of
a rock (tankful.sim.environment.perches) or the sand.  Its state
(Pleco.state) runs round

  ATTACHED -> RELEASING -> DARTING -> ATTACHING -> ATTACHED

- ATTACHED: its belly on the surface and its back away from it, so on
  the front glass the viewer sees its belly.  The mouth rasps
  (rasp_phase) and the fish inches along in pulses timed to the rasps,
  its heading wandering slowly over the surface and turning back from
  the surface's edges.  On a perch it rasps and turns in place.  After a
  while (ATTACH_TIME) it lets go.
- RELEASING: it pushes off along the surface's normal, turning to face
  the next spot (Pleco.target, chosen by choose_spot).
- DARTING: it swims there as a fish does, fast (the speeds and turns of
  SPECIES), steering round the decor, until it is
  within ARRIVE of the point just off the spot.  If it hasn't got there
  in DART_TIMEOUT it picks another spot.
- ATTACHING: it glides onto the spot, turning its belly to it, and
  clings.

RELEASING and ATTACHING follow a set path in a set time rather than
steering, so the fish always ends exactly on the surface.  release()
lets go early.

While it is on a surface the fish's frame is its own (Pleco.forward and
orientation): forward along the surface, its back along the normal.
"""

import math

from tankful.sim import environment as env
from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.fish import MAX_STEP, Fish
from tankful.sim.noise import SmoothNoise
from tankful.sim.species.base import Resident, Species
from tankful.sim.surfaces import (Sand, Spot, ease, signed_angle, tangent,
                                  turned)

# A bristlenose pleco: a flat-bellied armored catfish.  The speeds and
# turns here are for its darts between spots; the depth band, hovering
# and wander go unused
SPECIES = Species(
  name='pleco',
  length=0.10, height=0.05,
  clear_side=0.025, clear_up=0.02, clear_front=0.025,
  hover_speed=0.0, cruise_speed=0.24, max_speed=0.40,
  thrust=2.0, glide_time=0.5,
  pivot_rate=1.6, turn_radius=0.05, max_turn_rate=3.2,
  max_pitch=math.radians(55), pitch_rate=math.radians(140),
  max_bank=math.radians(20),
  depth_band=(0.0, 1.0),
  wander_frequency=0.2, wander_turn=0.15,
  hover_chance=0.0, hover_time=(1.0, 2.0),
  beat_base=1.5, beat_per_speed=1.6,
  wave_min=0.12, wave_max=0.55,
  fin_beat=3.0, fin_swing=0.2,
  turn_accel=14.0, roll_rate=3.0,
)

ATTACHED, RELEASING, DARTING, ATTACHING = (
  'attached', 'releasing', 'darting', 'attaching')

# The center's height above the surface it clings to, in lengths: the
# model's flat belly (tools/species/pleco.py) is this far below its center
BELLY = 0.045
# The surface on the glass is this far inside it, clear of the water's
# front face
GLASS_GAP = 0.003
# How long it clings (s), by the kind of surface
ATTACH_TIME = {'glass': (25.0, 55.0), 'sand': (10.0, 25.0),
               'perch': (10.0, 25.0)}
# Rasps per second, and the inching speed they average (m/s per length)
RASP_RATE = 1.6
INCH_SPEED = 0.08
# How fast the heading wanders on a surface, and turns back from its
# edges (rad/s), and how near an edge (m) it starts to turn
HEADING_WANDER = 0.35
EDGE_TURN = 0.9
EDGE_ZONE = 0.04
# Letting go: how far it pushes off (m), and how long that and settling
# onto a spot take (s)
PUSH_OFF = 0.04
RELEASE_TIME = 0.5
SETTLE_TIME = 0.8
# How far off the spot the dart aims (m), how near that it must come,
# and how long it may take (s)
APPROACH = 0.05
ARRIVE = 0.03
DART_TIMEOUT = 10.0
# A new spot is at least this far from the last (m)
MIN_HOP = 0.12
# How far it keeps from the edges of a surface, in lengths
EDGE = 0.6
# The side panes are used only this far toward the back (m): behind it
# the plants crowd the glass
SIDE_BACK = 0.06
# The sand it uses: in front of this y, where the viewer sees it
SAND_BACK = 0.0
# How often it picks each kind of spot
SPOT_WEIGHTS = (('front', 0.45), ('side', 0.15), ('perch', 0.2),
                ('sand', 0.2))

# Surfaces

class Glass:
  """A pane, from inside: the front (y), or a side (x)."""

  kind = 'glass'
  still = False

  def __init__(self, name, axis, sign, edge, back=None):
    self.name = name
    self.axis = axis
    self.along = 1 - axis
    inner = (env.INNER_X, env.INNER_Y)
    self.pos = sign * (inner[axis] - GLASS_GAP)
    n = [0.0, 0.0, 0.0]
    n[axis] = -sign
    self.normal = tuple(n)
    e = [0.0, 0.0, 0.0]
    e[self.along] = 1.0
    self.e_along = tuple(e)
    self.edge = edge
    lo, hi = -inner[self.along] + edge, inner[self.along] - edge
    if back is not None:
      hi = min(hi, back)
    self.span = (lo, hi)

  def _z_range(self, a):
    p = [0.0, 0.0]
    p[self.axis] = self.pos
    p[self.along] = vec.clamp(a, *self.span)
    return env.sand_height(*p) + self.edge, env.WATER_LEVEL - self.edge

  def contact(self, p):
    q = list(p)
    q[self.axis] = self.pos
    return tuple(q), self.normal

  def edges(self, c):
    """[(how far inside the edge, the way back in)] for each edge."""
    a = c[self.along]
    z0, z1 = self._z_range(a)
    lo, hi = self.span
    neg_along = vec.scale(self.e_along, -1.0)
    return [(a - lo, self.e_along), (hi - a, neg_along),
            (c[2] - z0, (0.0, 0.0, 1.0)), (z1 - c[2], (0.0, 0.0, -1.0))]

  def clamp(self, c):
    q = list(c)
    q[self.along] = vec.clamp(q[self.along], *self.span)
    z0, z1 = self._z_range(q[self.along])
    q[2] = vec.clamp(q[2], z0, z1)
    q[self.axis] = self.pos
    return tuple(q)

  def random_point(self, rng):
    a = rng.uniform(*self.span)
    z0, z1 = self._z_range(a)
    q = [0.0, 0.0, rng.uniform(z0, z1)]
    q[self.axis] = self.pos
    q[self.along] = a
    return tuple(q)

  def heading(self, angle):
    """The direction angle from along the pane toward up."""
    return vec.add(vec.scale(self.e_along, math.cos(angle)),
                   (0.0, 0.0, math.sin(angle)))


class Perch:
  """A spot on the decor (tankful.sim.environment.perches): the fish
  clings there and turns in place."""

  kind = 'perch'
  still = True

  def __init__(self, perch):
    self.name = perch.name
    self.obstacle = perch.obstacle
    self.point = perch.point
    self.normal = vec.normalized(perch.normal)

  def contact(self, p):
    return self.point, self.normal

  def edges(self, c):
    return []

  def clamp(self, c):
    return self.point

  def random_point(self, rng):
    return self.point

  def heading(self, angle):
    return (math.cos(angle), math.sin(angle), 0.0)


def surfaces(length):
  """The surfaces a pleco of length can cling to, by kind of spot."""
  edge = EDGE * length
  return {
    'front': [Glass('GlassFront', 1, -1, edge)],
    'side': [Glass('GlassLeft', 0, -1, edge, SIDE_BACK),
             Glass('GlassRight', 0, 1, edge, SIDE_BACK)],
    'perch': [Perch(p) for p in env.perches()],
    'sand': [Sand(edge, SAND_BACK)],
  }


def choose_spot(rng, by_kind, current=None, avoid=None):
  """A spot to go to: a surface by SPOT_WEIGHTS, a point on it at least
  MIN_HOP from avoid (the point it is leaving), and a heading.  Not the
  perch it is on (current)."""
  total = sum(w for _, w in SPOT_WEIGHTS)
  for _ in range(40):
    r = rng.uniform(0, total)
    for kind, w in SPOT_WEIGHTS:
      r -= w
      if r <= 0:
        break
    surface = rng.choice(by_kind[kind])
    if surface.still and surface is current:
      continue
    point = surface.random_point(rng)
    if avoid is not None and math.dist(point, avoid) < MIN_HOP:
      continue
    _, normal = surface.contact(point)
    angle = rng.uniform(0.3, math.pi - 0.3) if surface.kind == 'glass' \
      else rng.uniform(-math.pi, math.pi)
    heading = tangent(surface.heading(angle), normal)
    return Spot(surface, point, normal, heading)
  # Nowhere else came up: the middle of the front glass
  surface = by_kind['front'][0]
  point = surface.clamp((0.0, 0.0, env.WATER_LEVEL / 2))
  return Spot(surface, point, surface.normal, (0.0, 0.0, 1.0))


# The fish

class Pleco(Fish):

  def __init__(self, name, species, size=1.0, seed=0,
               start=(0.0, -0.19, 0.2, math.pi / 2)):
    # Set before Fish.__init__, which places the fish (_limit_position)
    self.state = ATTACHED
    self._frame = None
    super().__init__(name, species, size, seed, start[:3], 0.0)
    self.surfaces = surfaces(self.length)
    self.state_time = 0.0
    self.attach_left = 0.0
    self.rasp_phase = self.rng.uniform(0, 2 * math.pi)
    self.sway_phase = self.rng.uniform(0, 2 * math.pi)
    # How much it swims (1) rather than clings (0), for the pose
    self.swimming = 0.0
    self.target = None
    self.darts = 0
    self.surface = None
    self.contact = None
    self.normal = None
    self.heading = None
    self._path = None
    self._skip = ()
    self._depart = None
    self._heading_noise = SmoothNoise(seed * 7 + 5, 0.08)
    self._inch_noise = SmoothNoise(seed * 7 + 6, 0.05)
    # Cling to the surface nearest the start
    p = start[:3]
    surface = min((s for group in self.surfaces.values() for s in group),
                  key=lambda s: math.dist(p, s.contact(p)[0]))
    point = surface.clamp(surface.contact(p)[0])
    _, normal = surface.contact(point)
    heading = tangent(surface.heading(start[3]), normal) or tangent(
      (0.0, 0.0, 1.0), normal) or (1.0, 0.0, 0.0)
    self._cling_to(surface, point, normal, heading)

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

  def _cling_to(self, surface, point, normal, heading):
    self.surface = surface
    self.contact = point
    self.normal = normal
    self.heading = heading
    self.attach_left = self.rng.uniform(*ATTACH_TIME[
      'perch' if surface.still else surface.kind])
    self.target = None
    self.speed = 0.0
    self._place()
    self._set_state(ATTACHED)

  def _place(self):
    """Put the center and frame where the contact, normal and heading say."""
    c = vec.add(self.contact, vec.scale(self.normal, BELLY * self.length))
    self.x, self.y, self.z = c
    self._frame = vec.frame(self.heading, self.normal)
    h = self.heading
    self.yaw = math.atan2(h[1], h[0])
    self.pitch = math.asin(vec.clamp(h[2], -1.0, 1.0))

  def release(self):
    """Let go of the surface for a new spot.  Whether it was attached."""
    if self.state != ATTACHED:
      return False
    self.target = choose_spot(self.rng, self.surfaces, self.surface,
                              self.contact)
    start = (self.x, self.y, self.z)
    end = vec.add(start, vec.scale(self.normal, PUSH_OFF))
    approach = self._approach()
    turn = self._swim_frame(vec.normalized(vec.sub(approach, end),
                                           self.normal))
    self._path = (start, vec.quaternion(self._frame), end,
                  vec.quaternion(turn), RELEASE_TIME)
    self._depart = (self.contact, getattr(self.surface, 'obstacle', None))
    self.surface = None
    self._set_state(RELEASING)
    return True

  def _approach(self):
    t = self.target
    return vec.add(t.point, vec.scale(t.normal, APPROACH))

  def _settle(self):
    """Start onto the target from where the dart left off."""
    t = self.target
    heading = tangent(self.forward(), t.normal) or t.heading
    self.contact, self.normal, self.heading = t.point, t.normal, heading
    start = (self.x, self.y, self.z)
    start_q = vec.quaternion(self.orientation())
    end = vec.add(t.point, vec.scale(t.normal, BELLY * self.length))
    end_q = vec.quaternion(vec.frame(heading, t.normal))
    self._path = (start, start_q, end, end_q, SETTLE_TIME)
    self._frame = self.orientation()
    self._set_state(ATTACHING)

  def _retarget(self):
    self.target = choose_spot(self.rng, self.surfaces, None,
                              (self.x, self.y, self.z))
    self.state_time = 0.0

  # The step

  def step(self, dt, others=()):
    if dt < 0:
      raise ValueError('dt must not be negative: %r' % dt)
    dt = min(dt, MAX_STEP)
    if dt == 0:
      return
    self.state_time += dt
    self.rasp_phase = (self.rasp_phase
                       + 2 * math.pi * RASP_RATE * dt) % (2 * math.pi)
    if self.state == DARTING:
      self._dart(dt, others)
      return
    self.time += dt
    if self.state == ATTACHED:
      self._cling(dt)
    else:
      self._follow_path(dt)
    self._gait(dt)

  def _cling(self, dt):
    self.swimming = max(0.0, self.swimming - dt / SETTLE_TIME)
    self.sway_phase = (self.sway_phase + 2 * math.pi * 0.25 * dt) % (
      2 * math.pi)
    surface = self.surface
    n = self.normal
    turn = self._heading_noise(self.time) * HEADING_WANDER
    if surface.still:
      # On a perch: rasping in place, turning now and then
      self.speed = 0.0
      self.heading = turned(self.heading, n, turn * 0.5 * dt)
    else:
      # Turn back from the nearest edge, harder the nearer
      depth, inward = min(surface.edges(self.contact),
                          key=lambda e: e[0])
      inward = tangent(inward, n)
      if depth < EDGE_ZONE and inward is not None:
        err = signed_angle(self.heading, inward, n)
        near = 1.0 - max(0.0, depth) / EDGE_ZONE
        turn += vec.clamp(err * 2.0, -1.0, 1.0) * EDGE_TURN * near
      self.heading = turned(self.heading, n, turn * dt)
      # Inch along in pulses, one per rasp, pausing now and then
      pace = vec.clamp(0.6 + self._inch_noise(self.time), 0.0, 1.0)
      pulse = 2.0 * max(0.0, math.sin(self.rasp_phase)) ** 2
      self.speed = INCH_SPEED * self.length * pace * pulse
      moved = vec.add(self.contact, vec.scale(self.heading, self.speed * dt))
      self.contact, self.normal = surface.contact(surface.clamp(moved))
      self.heading = tangent(self.heading, self.normal) or self.heading
    self._place()
    self.attach_left -= dt
    if self.attach_left <= 0:
      self.release()

  def _follow_path(self, dt):
    start, start_q, end, end_q, duration = self._path
    t = ease(self.state_time / duration)
    before = (self.x, self.y, self.z)
    self.x, self.y, self.z = vec.lerp(start, end, t)
    self._frame = vec.rotation(vec.slerp(start_q, end_q, t))
    self.speed = math.dist(before, (self.x, self.y, self.z)) / dt
    if self.state == RELEASING:
      self.swimming = t
      if self.state_time >= duration:
        # Off the surface: swim from here, facing the way it turned
        self._frame = None
        self.speed = self.cruise_speed * 0.5
        self.stroking, self.stroke = True, 1.0
        self.darts += 1
        self._set_state(DARTING)
    else:
      self.swimming = 1.0 - t
      if self.state_time >= duration:
        t = self.target
        self._cling_to(t.surface, t.point, t.normal, self.heading)

  def _dart(self, dt, others):
    self.swimming = 1.0
    target_obstacle = getattr(self.target.surface, 'obstacle', None)
    point, depart_obstacle = self._depart
    self._skip = {target_obstacle}
    if math.dist(point, (self.x, self.y, self.z)) < 2 * APPROACH:
      self._skip.add(depart_obstacle)
    Fish.step(self, dt, others)
    if math.dist((self.x, self.y, self.z), self._approach()) < ARRIVE:
      self._settle()
    elif self.state_time > DART_TIMEOUT:
      self._retarget()

  # Fish steering, while darting

  def _update_mode(self, dt):
    pass

  def _desired(self, others):
    goal = self._approach()
    pos = (self.x, self.y, self.z)
    off = vec.sub(goal, pos)
    d = vec.length(off)
    toward = vec.normalized(off, self.forward())
    # The glass and decor push it off less the nearer it is to the spot,
    # which is on one of them
    clear = [0.0, 0.0, 0.0]
    danger = self._steer_clear(clear)
    k = vec.clamp((d - 0.04) / 0.25, 0.0, 1.0)
    want = [toward[i] * 2.5 + clear[i] * k for i in range(3)]
    self.danger = danger * k
    self._mind_others(want, others)
    return vec.normalized(tuple(want), self.forward()), goal[2]

  def _target_speed(self, want):
    d = math.dist((self.x, self.y, self.z), self._approach())
    along = vec.dot(self.forward(), want)
    target = (self.cruise_speed * vec.clamp(d / 0.12, 0.3, 1.0)
              * (0.5 + 0.5 * max(0.0, along)))
    return target, self.species.glide_time

  def _obstacles_near(self, pos, pad):
    for obstacle in super()._obstacles_near(pos, pad):
      if obstacle.name not in self._skip:
        yield obstacle

  def _limit_position(self):
    # On a surface, or on its way on or off, the path holds it
    if self.state == DARTING:
      super()._limit_position()

  def snapshot(self):
    snap = super().snapshot()
    snap.update({
      'state': self.state,
      'surface': self.surface.name if self.surface else None,
      'contact': [round(v, 4) for v in self.contact],
      'normal': [round(v, 4) for v in self.normal],
      'target': self.target.surface.name if self.target else None,
      'attach_left': round(self.attach_left, 2),
      'darts': self.darts,
    })
    return snap


# The pose
#
# The rig (tools/species/pleco.py) is the spine chain of tankful.sim.swim,
# with fin bones that all point straight back at rest (so bone x is the
# fish's left and z its back), and the mouth's:
#
#   Head -> Spine.0 -> Spine.1 -> Spine.2 -> Tail
#   Head -> Mouth -> Jaw; Head -> Pec.L, Pec.R, Dorsal
#   Spine.0 -> Pelvic.L, Pelvic.R
#
# The model rests as the fish clings: pectoral and pelvic fins spread
# flat and the dorsal fin raised.  Swimming, the paired fins fold back
# along the body.

SPINE = ('Spine.0', 'Spine.1', 'Spine.2', 'Tail')
BONES = ('Head',) + SPINE + ('Mouth', 'Jaw', 'Pec.L', 'Pec.R', 'Pelvic.L',
                             'Pelvic.R', 'Dorsal')
# The tail's slow sweep while clinging (radians)
SWAY = 0.10
# How far the paired fins fold back when swimming, and the dorsal fin
# lies down when clinging (radians)
PEC_FOLD = 0.75
PELVIC_FOLD = 0.6
DORSAL_FOLD = 0.9


def pose(fish):
  """{bone: (rx, ry, rz)} for a Pleco now."""
  sw = fish.swimming
  rest = 1.0 - sw
  swimming = swim.spine_angles(fish.wave, fish.beat_phase, fish.yaw_rate)
  clinging = swim.spine_angles(SWAY, fish.sway_phase)
  angles = {'Head': (0.0, 0.0, 0.025 * rest * math.sin(fish.rasp_phase)),
            'Mouth': (0.06 * rest * math.sin(fish.rasp_phase), 0.0, 0.0),
            'Jaw': (0.0, 0.0, 0.0)}
  for name, a, b in zip(SPINE, swimming, clinging):
    angles[name] = (0.0, 0.0, sw * a + rest * b)
  flutter = sw * 0.12 * math.sin(fish.fin_phase)
  for name, side, fold in (('Pec.L', 1.0, PEC_FOLD), ('Pec.R', -1.0, PEC_FOLD),
                           ('Pelvic.L', 1.0, PELVIC_FOLD),
                           ('Pelvic.R', -1.0, PELVIC_FOLD)):
    # Positive z swings a fin toward the fish's right: in, for the left
    angles[name] = (flutter, 0.0, side * fold * sw)
  angles['Dorsal'] = (-DORSAL_FOLD * rest, 0.0,
                      0.3 * (sw * swimming[1] + rest * clinging[1]))
  return angles


def scales(fish):
  """{bone: (sx, sy, sz)}: the sucker disc works with each rasp, and the
  jaws within it open and close."""
  rest = 1.0 - fish.swimming
  p = fish.rasp_phase
  disc = 1.0 + rest * 0.08 * math.sin(p)
  jaw = 1.0 - rest * 0.45 * (0.5 + 0.5 * math.sin(p + 1.2))
  return {'Mouth': (disc, disc, disc), 'Jaw': (jaw, jaw, jaw)}


def plecos():
  """The plecos in the tank.  start is a point near the surface each
  starts clinging to, and its heading there."""
  return [Resident('Pleco', SPECIES, 1.15, 505, (-0.05, -0.19, 0.24, 1.35))]


def stock(tank):
  """Add the plecos to tank, and return them."""
  out = []
  for r in plecos():
    out.append(Pleco(r.name, r.species, r.size, r.seed, r.start))
  tank.fish.extend(out)
  return out
