import json
import math
import unittest

from tankful.sim import environment as env
from tankful.sim import fish as sim_fish
from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.fish import Fish
from tankful.sim.species import angelfish
from tankful.sim.species.angelfish import SPECIES as ANGELFISH, residents
from tankful.sim.tank import Tank

DT = 1 / 60.0


def stocked():
  tank = Tank()
  angelfish.stock(tank)
  return tank


def run(tank, seconds, dt=DT, each=None):
  for _ in range(int(round(seconds / dt))):
    tank.step(dt)
    if each is not None:
      for f in tank.fish:
        each(f)


class FishLimitsTests(unittest.TestCase):

  def assert_within_limits(self, f):
    s = f.species
    (x0, x1), (y0, y1), (z0, z1) = f.bounds()
    eps = 1e-9
    self.assertTrue(x0 - eps <= f.x <= x1 + eps, (f.name, f.x))
    self.assertTrue(y0 - eps <= f.y <= y1 + eps, (f.name, f.y))
    self.assertTrue(z0 - eps <= f.z <= z1 + eps, (f.name, f.z, z0, z1))
    for obstacle in env.obstacles():
      c = vec.closest_on_segment((f.x, f.y, f.z), obstacle.a, obstacle.b)
      d = vec.length(vec.sub((f.x, f.y, f.z), c))
      # Pushing out of one obstacle may clip into the glass's limit, so
      # allow a millimeter
      self.assertGreater(d, f.clearance(obstacle) - 1e-3,
                         (f.name, obstacle.name))
    self.assertTrue(0.0 <= f.speed <= f.max_speed + eps, f.speed)
    self.assertLessEqual(abs(f.pitch), s.max_pitch + eps)
    self.assertLessEqual(abs(f.roll), s.max_bank + eps)
    self.assertLessEqual(abs(f.yaw_rate), s.max_turn_rate + eps)

  def test_long_swim_keeps_every_limit(self):
    tank = stocked()
    modes = set()
    seen = {f.name: [] for f in tank.fish}

    def check(f):
      self.assert_within_limits(f)
      modes.add(f.mode)
      seen[f.name].append((f.x, f.y, f.z))
    run(tank, 240.0, each=check)
    # Both cruised and hovered, and got around the tank
    self.assertEqual(modes, {sim_fish.CRUISE, sim_fish.HOVER})
    for name, points in seen.items():
      xs = [p[0] for p in points]
      self.assertGreater(max(xs) - min(xs), 0.4, name)

  def test_heading_changes_within_turn_limit(self):
    tank = stocked()
    last = {f.name: f.yaw for f in tank.fish}
    for _ in range(int(60 / DT)):
      tank.step(DT)
      for f in tank.fish:
        turned = abs(vec.wrap_angle(f.yaw - last[f.name]))
        self.assertLessEqual(turned, ANGELFISH.max_turn_rate * DT + 1e-9)
        last[f.name] = f.yaw

  def test_turns_tighter_when_faster(self):
    f = Fish('f', ANGELFISH)
    self.assertAlmostEqual(f.max_turn(0.0), ANGELFISH.pivot_rate)
    self.assertGreater(f.max_turn(0.05), f.max_turn(0.01))
    self.assertEqual(f.max_turn(10.0), ANGELFISH.max_turn_rate)

  def test_hitches_and_odd_steps(self):
    tank = stocked()
    for dt in (0.0, 0.5, 3.0, 1e-4, 0.25) * 40:
      tank.step(dt)
      for f in tank.fish:
        self.assert_within_limits(f)
    with self.assertRaises(ValueError):
      tank.fish[0].step(-0.01)

  def test_starts_inside_whatever_it_is_given(self):
    for pos in ((5.0, -3.0, 9.0), (-1.0, 1.0, -1.0), (0.06, 0.06, 0.05)):
      f = Fish('f', ANGELFISH, position=pos)
      (x0, x1), (y0, y1), (z0, z1) = f.bounds()
      self.assertTrue(x0 <= f.x <= x1 and y0 <= f.y <= y1 and z0 <= f.z <= z1)
      # A corner crowded by a plant clump may leave it in the clump, but
      # it soon steers clear
      for _ in range(int(10 / DT)):
        f.step(DT)
      self.assert_within_limits(f)

  def test_banks_into_turns(self):
    tank = stocked()
    agree = disagree = 0

    def check(f):
      nonlocal agree, disagree
      if abs(f.yaw_rate) > 0.25 and f.speed > 0.5 * f.cruise_speed:
        # Turning left (yaw_rate > 0) leans the back left: negative roll
        if abs(f.roll) > 0.01:
          if f.roll * f.yaw_rate < 0:
            agree += 1
          else:
            disagree += 1
    run(tank, 180.0, each=check)
    self.assertGreater(agree, 200)
    self.assertGreater(agree, 9 * disagree)

  def test_prefers_its_depth_band(self):
    tank = stocked()
    fracs = []

    def check(f):
      (_, _), (_, _), (z0, z1) = f.bounds()
      fracs.append((f.z - z0) / (z1 - z0))
    run(tank, 180.0, each=check)
    lo, hi = ANGELFISH.depth_band
    inside = sum(1 for v in fracs if lo - 0.15 <= v <= hi + 0.15)
    self.assertGreater(inside / len(fracs), 0.85)

  def test_fish_keep_apart(self):
    tank = stocked()
    a, b = tank.fish
    closest = math.inf
    for _ in range(int(180 / DT)):
      tank.step(DT)
      closest = min(closest, math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)))
    self.assertGreater(closest, 0.8 * sim_fish.MIN_GAP * ANGELFISH.length)

  def test_repeatable(self):
    one, two = stocked(), stocked()
    run(one, 30.0)
    run(two, 30.0)
    self.assertEqual(one.snapshot(), two.snapshot())

  def surface_push(self, surface_margin, below, clear_up=0.01):
    """The up/down push _steer_clear gives a still fish level in the
    middle of its swim box, below meters under its top.  The default
    clear_up leaves the box tall enough that no margin is capped."""
    species = ANGELFISH._replace(surface_margin=surface_margin,
                                 clear_up=clear_up)
    return self.vertical_push(species, lambda z0, z1: z1 - below)

  def vertical_push(self, species, height):
    """The up/down push _steer_clear gives a still fish of species level
    in the middle of its swim box, at height(z0, z1) of its box's floor
    and top, with no decor about."""
    f = Fish('Probe', species, 1.0, 1, (0.0, 0.0, 0.3), 0.0)
    (x0, x1), (y0, y1), (z0, z1) = f.bounds()
    f.x, f.y, f.z = (x0 + x1) / 2, (y0 + y1) / 2, height(z0, z1)
    f.speed = 0.0
    # Only the walls: no decor pushes
    f._obstacles_near = lambda pos, reach: ()
    want = [0.0, 0.0, 0.0]
    f._steer_clear(want)
    return want[2]

  def test_surface_margin(self):
    self.assertIsNone(ANGELFISH.surface_margin)
    # By default the surface pushes down within MARGIN of the top
    self.assertLess(self.surface_push(None, 0.08), 0)
    self.assertAlmostEqual(self.surface_push(None, 0.08),
                           self.surface_push(sim_fish.MARGIN, 0.08))
    # A smaller margin: no push until nearer the top, then less of one
    self.assertEqual(self.surface_push(0.06, 0.08), 0.0)
    self.assertLess(self.surface_push(0.06, 0.03), 0)
    self.assertGreater(self.surface_push(0.06, 0.03),
                       self.surface_push(None, 0.03))

  def decor_push(self, gap):
    """The up/down push _steer_clear gives a still fish level in the
    middle of its swim box over a rock whose clearance is gap below it."""
    f = Fish('Probe', ANGELFISH, 1.0, 1, (0.0, 0.0, 0.3), 0.0)
    (x0, x1), (y0, y1), (z0, z1) = f.bounds()
    f.x, f.y, f.z = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    f.speed = 0.0
    rock = env.Obstacle('Rock', None, None, 0.03, False)
    clear = f.clearance(rock)
    at = (f.x, f.y, f.z - clear - gap)
    rock = rock._replace(a=at, b=at)
    f._obstacles_near = lambda pos, reach: (rock,)
    want = [0.0, 0.0, 0.0]
    f._steer_clear(want)
    return want[2]

  def test_decor_margin(self):
    # The decor pushes only within DECOR_MARGIN of its clearance, less
    # than the walls' MARGIN, so a fish may swim down near it
    self.assertLess(sim_fish.DECOR_MARGIN, sim_fish.MARGIN)
    self.assertEqual(self.decor_push(sim_fish.DECOR_MARGIN + 0.01), 0.0)
    near = self.decor_push(0.5 * sim_fish.DECOR_MARGIN)
    self.assertGreater(near, 0.0)
    self.assertGreater(self.decor_push(0.1 * sim_fish.DECOR_MARGIN), near)

  def test_vertical_margins_capped(self):
    # The angelfish's box is short: the sand and surface each push only
    # within their share of it, leaving the middle half free
    (_, _), (_, _), (z0, z1) = Fish('Probe', ANGELFISH, 1.0, 1,
                                    (0.0, 0.0, 0.3), 0.0).bounds()
    share = sim_fish.VERTICAL_MARGIN_SHARE
    self.assertLess((z1 - z0) * share, sim_fish.MARGIN)
    for frac in (share + 0.01, 0.5, 1.0 - share - 0.01):
      self.assertEqual(
        self.vertical_push(ANGELFISH, lambda a, b: a + (b - a) * frac), 0.0)
    self.assertGreater(
      self.vertical_push(ANGELFISH, lambda a, b: a + (b - a) * 0.1), 0.0)
    self.assertLess(
      self.vertical_push(ANGELFISH, lambda a, b: a + (b - a) * 0.9), 0.0)
    # A smaller surface margin than the cap is kept
    small = ANGELFISH._replace(surface_margin=0.02)
    self.assertEqual(
      self.vertical_push(small, lambda a, b: b - 0.03), 0.0)
    self.assertLess(self.vertical_push(small, lambda a, b: b - 0.01), 0.0)


class FishNeighborTests(unittest.TestCase):
  """_mind_others and _keep_apart pass over the fish of other kinds too
  far off to matter, and only those."""

  def setUp(self):
    self.fish = Fish('Probe', ANGELFISH, 1.0, 1, (0.0, -0.05, 0.3), 0.0)
    self.other_kind = ANGELFISH._replace(name='other_kind')

  def neighbor(self, species, off):
    other = Fish('Other', species, 1.0, 2, (0.0, -0.05, 0.3), 0.0)
    other.x, other.y, other.z = vec.sub(
      (self.fish.x, self.fish.y, self.fish.z), off)
    return other

  def mind(self, other):
    want = [0.0, 0.0, 0.0]
    self.fish._mind_others(want, [self.fish, other])
    return want

  def test_mind_others_of_another_kind(self):
    sep = sim_fish.SEPARATION * ANGELFISH.length
    self.assertEqual(self.mind(self.neighbor(self.other_kind,
                                             (sep, 0.0, 0.0))), [0.0] * 3)
    self.assertEqual(self.mind(self.neighbor(self.other_kind,
                                             (0.0, 0.0, -2 * sep))),
                     [0.0] * 3)
    # Within sep along every axis, but farther than sep in all
    self.assertEqual(self.mind(self.neighbor(self.other_kind,
                                             (0.9 * sep, 0.9 * sep, 0.0))),
                     [0.0] * 3)
    self.assertGreater(self.mind(self.neighbor(self.other_kind,
                                               (0.9 * sep, 0.0, 0.0)))[0], 0)

  def test_mind_others_of_its_own_kind_far_off(self):
    # Its own kind draws it together however far apart
    off = (0.0, 0.0, -(sim_fish.COHESION + 0.05))
    want = self.mind(self.neighbor(ANGELFISH, off))
    self.assertAlmostEqual(want[2], 0.12)

  def test_mind_smaller_others_less_up_and_down(self):
    # A fish of another kind a quarter its length pushes it a quarter as
    # hard across, but a sixteenth as hard up or down, so it may swim
    # over a crowd of small fish below
    small = self.other_kind._replace(length=ANGELFISH.length / 4)
    sep = sim_fish.SEPARATION * ANGELFISH.length
    # Near enough to touch: no startle, only the push apart
    self.fish.startles_others = False
    for axis in range(3):
      off = [0.0, 0.0, 0.0]
      off[axis] = 0.5 * sep
      pushes = []
      for species in (self.other_kind, small):
        other = self.neighbor(species, off)
        other.startles_others = False
        pushes.append(self.mind(other)[axis])
      full, less = pushes
      self.assertGreater(full, 0)
      self.assertAlmostEqual(less, full / (16 if axis == 2 else 4))

  def keep_apart(self, other):
    before = (self.fish.x, self.fish.y, self.fish.z)
    self.fish._keep_apart([self.fish, other])
    return vec.sub((self.fish.x, self.fish.y, self.fish.z), before)

  def test_keep_apart(self):
    gap = sim_fish.MIN_GAP * ANGELFISH.length
    self.assertEqual(self.keep_apart(self.neighbor(self.other_kind,
                                                   (0.0, gap, 0.0))),
                     (0.0, 0.0, 0.0))
    self.assertEqual(self.keep_apart(self.neighbor(
      self.other_kind, (0.8 * gap, 0.8 * gap, 0.0))), (0.0, 0.0, 0.0))
    moved = self.keep_apart(self.neighbor(self.other_kind,
                                          (0.0, 0.5 * gap, 0.0)))
    # Equal lengths: half the overlap each
    self.assertAlmostEqual(moved[1], 0.25 * gap)
    moved = self.keep_apart(self.neighbor(ANGELFISH, (0.0, 0.0, 0.5 * gap)))
    self.assertAlmostEqual(moved[2], 0.25 * gap)


class FishGaitTests(unittest.TestCase):

  def test_beat_frequency_follows_speed(self):
    tank = stocked()
    samples = []
    run(tank, 120.0, each=lambda f: samples.append(
      (f.speed, f.beat_freq, f.length)))
    for speed, freq, length in samples:
      self.assertAlmostEqual(
        freq, ANGELFISH.beat_base + ANGELFISH.beat_per_speed * speed / length)
    fast = [f for s, f, _ in samples if s > 0.05]
    slow = [f for s, f, _ in samples if s < 0.01]
    self.assertTrue(fast and slow)
    self.assertGreater(min(fast), max(slow))

  def test_hovering_is_fins_only(self):
    tank = stocked()
    f = tank.fish[0]
    hovered = 0.0
    for _ in range(int(400 / DT)):
      tank.step(DT)
      hovered = hovered + DT if f.mode == sim_fish.HOVER else 0.0
      if hovered > 2.5:
        break
    self.assertGreater(hovered, 2.5, 'never hovered for long')
    self.assertLess(f.speed, 0.2 * f.cruise_speed)
    # The pectorals scull while the body is all but still
    spine, fins = [], []
    for _ in range(60):
      tank.step(DT)
      pose = angelfish.pose(f)
      spine.append(sum(abs(pose[b][2]) for b in swim.SPINE))
      fins.append(pose['Pec.L'][2])
    self.assertLess(max(spine), 0.12)
    self.assertGreater(max(fins) - min(fins), 0.3)

  def test_wave_is_wider_when_stroking_fast(self):
    f = Fish('f', ANGELFISH)
    f.stroke = 1.0
    f.speed = f.cruise_speed
    f._gait(DT)
    fast = f.wave
    f.speed = 0.1 * f.cruise_speed
    f._gait(DT)
    self.assertGreater(fast, 2 * f.wave)
    f.stroke = 0.0
    f.speed = f.cruise_speed
    f._gait(DT)
    self.assertLess(f.wave, 0.2 * fast)


class FishPoseTests(unittest.TestCase):

  def test_orientation_is_a_rotation_facing_forward(self):
    f = Fish('f', ANGELFISH)
    for yaw, pitch, roll in ((0, 0, 0), (1.0, 0.3, -0.2), (-2.5, -0.35, 0.25)):
      f.yaw, f.pitch, f.roll = yaw, pitch, roll
      m = f.orientation()
      cols = [tuple(m[i][j] for i in range(3)) for j in range(3)]
      for i in range(3):
        for j in range(3):
          self.assertAlmostEqual(vec.dot(cols[i], cols[j]),
                                 1.0 if i == j else 0.0)
      # The fish's +x is its heading
      for a, b in zip(cols[0], f.forward()):
        self.assertAlmostEqual(a, b)
    # Rolling negative leans the back (+z) toward the fish's left (+y)
    f.yaw, f.pitch, f.roll = 0.0, 0.0, -0.2
    self.assertGreater(f.orientation()[1][2], 0)

  def test_snapshot(self):
    tank = stocked()
    run(tank, 1.0)
    snap = tank.snapshot()
    self.assertEqual([f['name'] for f in snap['fish']],
                     [r.name for r in residents()])
    self.assertEqual(snap['fish'][0]['species'], 'angelfish')
    json.dumps(snap)


if __name__ == '__main__':
  unittest.main()
