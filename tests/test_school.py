import json
import math
import unittest

from tankful.sim import environment as env
from tankful.sim import fish as sim_fish
from tankful.sim import school as sim_school
from tankful.sim import species
from tankful.sim import swim
from tankful.sim import vec
from tankful.sim.school import school_members
from tankful.sim.species import angelfish, neon_tetra
from tankful.sim.species.neon_tetra import SPECIES as NEON_TETRA, schools
from tankful.sim.tank import Tank

DT = 1 / 60.0


def stocked():
  """The whole tank: the angelfish and the school."""
  tank = Tank()
  angelfish.stock(tank)
  neon_tetra.stock(tank)
  return tank


def run(tank, seconds, dt=DT, each=None):
  for _ in range(int(round(seconds / dt))):
    tank.step(dt)
    if each is not None:
      each(tank)


def pos(f):
  return (f.x, f.y, f.z)


def body_gap(a, b):
  """How far apart two members' body capsules are (negative: overlap)."""
  a0, a1, ra = a.body()
  b0, b1, rb = b.body()
  p, q = vec.closest_between_segments(a0, a1, b0, b1)
  return vec.length(vec.sub(p, q)) - ra - rb


def heading(members):
  """The school's mean heading, and how well its members agree on it (0
  to 1, the polarization)."""
  x = sum(f.forward()[0] for f in members) / len(members)
  y = sum(f.forward()[1] for f in members) / len(members)
  return math.atan2(y, x), math.hypot(x, y)


class SchoolCohesionTests(unittest.TestCase):

  def test_school_holds_together(self):
    tank = stocked()
    school = tank.schools[0]
    length = school.species.length
    far, spreads = [], []
    alone = {f.name: 0.0 for f in school.members}

    def check(tank):
      if tank.time < 5.0:
        return
      c = school.centroid()
      far.append(max(math.dist(pos(f), c) for f in school.members))
      spreads.append(school.spread())
      # Nobody strays out of sight of the rest for long: one may round
      # the far side of a branch from the others, but not stay there
      for f in school.members:
        nearest = min(math.dist(pos(f), pos(g)) for g in school.members
                      if g is not f)
        alone[f.name] = (alone[f.name] + DT
                         if nearest > sim_school.VIEW * length else 0.0)
        self.assertLess(alone[f.name], 3.0, f.name)
    run(tank, 240.0, each=check)
    self.assertLess(max(far), 0.25)
    self.assertLess(sum(spreads) / len(spreads), 0.06)
    # Close, but not a clump: the spacing keeps them about a length apart
    self.assertGreater(min(spreads), 0.8 * length)

  def test_follows_its_goal_around_the_tank(self):
    tank = stocked()
    school = tank.schools[0]
    xs, lags = [], []

    def check(tank):
      c = school.centroid()
      xs.append(c[0])
      if tank.time > 5.0:
        lags.append(math.dist(c, school.goal))
    run(tank, 240.0, each=check)
    self.assertGreater(max(xs) - min(xs), 0.5)
    self.assertLess(sum(lags) / len(lags), 0.06)

  def test_swims_mostly_aligned(self):
    tank = stocked()
    school = tank.schools[0]
    polar = []
    run(tank, 180.0, each=lambda tank: polar.append(heading(
      school.members)[1]))
    self.assertGreater(sum(polar) / len(polar), 0.75)

  def test_turns_as_a_group(self):
    tank = stocked()
    school = tank.schools[0]
    turns = []
    start = None

    def check(tank):
      nonlocal start
      if school.swing and start is None:
        start = (tank.time, heading(school.members)[0])
      elif start is not None and tank.time - start[0] >= 4.0:
        h, polar = heading(school.members)
        turns.append((abs(vec.wrap_angle(h - start[1])), polar))
        if not school.swing:
          start = None
    run(tank, 300.0, each=check)
    self.assertGreaterEqual(len(turns), 8)
    # The school comes round with its goal, and comes out of the turn
    # still swimming together
    turned = [t for t, polar in turns if t > 1.0 and polar > 0.6]
    self.assertGreater(len(turned), 0.6 * len(turns))

  def test_members_flick_and_rejoin(self):
    tank = stocked()
    school = tank.schools[0]
    flicked = set()
    fastest = 0.0
    out = {}
    back = []

    def check(tank):
      nonlocal fastest
      c = school.centroid()
      for f in school.members:
        if f.flicking:
          flicked.add(f.name)
          fastest = max(fastest, f.speed / f.cruise_speed)
          out.setdefault(f.name, tank.time)
        elif f.name in out and tank.time - out[f.name] > 3.0:
          back.append(math.dist(pos(f), c))
          del out[f.name]
    run(tank, 180.0, each=check)
    self.assertGreater(len(flicked), 10)
    self.assertGreater(fastest, 1.8)
    # Three seconds on, they are back among the rest
    self.assertLess(sum(back) / len(back), 0.08)
    self.assertLess(max(back), 0.2)


class SchoolSpacingTests(unittest.TestCase):

  def assert_no_overlap(self, members, slack=1e-5):
    for i, a in enumerate(members):
      for b in members[i + 1:]:
        gap = body_gap(a, b)
        self.assertGreater(gap, -slack, (a.name, b.name, gap))

  def test_bodies_never_overlap(self):
    tank = stocked()
    school = tank.schools[0]
    self.assert_no_overlap(school.members)
    run(tank, 120.0, each=lambda tank: self.assert_no_overlap(school.members))

  def test_no_overlap_through_hitches(self):
    tank = stocked()
    school = tank.schools[0]
    for dt in (0.0, 0.5, 3.0, 1e-4, 0.25, 0.1) * 30:
      tank.step(dt)
      self.assert_no_overlap(school.members)

  def test_packed_start_comes_apart(self):
    # Every member started on the same spot, facing the same way: too
    # tangled to undo in one step, but they part within a second and
    # stay apart
    tank = Tank()
    school = sim_school.School('S', NEON_TETRA, 1, (0.0, -0.05, 0.25, 0.0))
    for i in range(12):
      tank.fish.append(sim_school.Member('S.%d' % i, NEON_TETRA, school,
                                         seed=i, position=(0.0, -0.05, 0.25)))
    tank.schools.append(school)
    run(tank, 1.0)
    run(tank, 10.0, each=lambda tank: self.assert_no_overlap(school.members))

  def test_keeps_clear_of_the_angelfish(self):
    tank = stocked()
    school = tank.schools[0]
    angels = [f for f in tank.fish if f.school is None]
    closest = math.inf

    def check(tank):
      nonlocal closest
      for a in angels:
        for f in school.members:
          closest = min(closest, math.dist(pos(a), pos(f)))
    run(tank, 180.0, each=check)
    gap = sim_fish.MIN_GAP * 0.5 * (angels[0].length + school.species.length)
    self.assertGreater(closest, 0.8 * gap)


class SchoolLimitsTests(unittest.TestCase):

  def test_members_keep_every_limit(self):
    tank = stocked()
    school = tank.schools[0]
    s = school.species
    eps = 1e-9

    def check(tank):
      for f in school.members:
        (x0, x1), (y0, y1), (z0, z1) = f.bounds()
        self.assertTrue(x0 - eps <= f.x <= x1 + eps, (f.name, f.x))
        self.assertTrue(y0 - eps <= f.y <= y1 + eps, (f.name, f.y))
        self.assertTrue(z0 - eps <= f.z <= z1 + eps, (f.name, f.z))
        for obstacle in env.obstacles():
          c = vec.closest_on_segment(pos(f), obstacle.a, obstacle.b)
          self.assertGreater(vec.length(vec.sub(pos(f), c)),
                             f.clearance(obstacle) - 1e-3,
                             (f.name, obstacle.name))
        self.assertTrue(0.0 <= f.speed <= f.max_speed + eps)
        self.assertLessEqual(abs(f.pitch), s.max_pitch + eps)
        self.assertLessEqual(abs(f.roll), s.max_bank + eps)
        self.assertLessEqual(abs(f.yaw_rate), s.max_turn_rate + eps)
        self.assertEqual(f.mode, sim_fish.CRUISE)
    run(tank, 120.0, each=check)

  def test_goal_stays_in_open_water(self):
    tank = stocked()
    school = tank.schools[0]
    pad = school._decor_pad()
    obstacles = env.obstacles()
    depths = []

    def check(tank):
      (x0, x1), (y0, y1), (z0, z1) = school.bounds()
      x, y, z = school.goal
      self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1)
      for obstacle in obstacles:
        c = vec.closest_on_segment(school.goal, obstacle.a, obstacle.b)
        self.assertGreater(vec.length(vec.sub(school.goal, c)),
                           obstacle.radius + pad - 1e-3, obstacle.name)
      depths.append((z - z0) / (z1 - z0))
    run(tank, 240.0, each=check)
    lo, hi = school.species.depth_band
    inside = sum(1 for d in depths if lo - 0.1 <= d <= hi + 0.1)
    self.assertGreater(inside / len(depths), 0.9)

  def test_negative_step(self):
    tank = stocked()
    with self.assertRaises(ValueError):
      tank.schools[0].step(-0.01)

  def test_repeatable(self):
    one, two = stocked(), stocked()
    run(one, 30.0)
    run(two, 30.0)
    self.assertEqual(one.snapshot(), two.snapshot())


class SchoolGroupTests(unittest.TestCase):

  def test_school_is_the_group(self):
    tank = stocked()
    school = tank.schools[0]
    spec = schools()[0]
    self.assertEqual(len(school.members), spec.count)
    self.assertEqual([f.name for f in school.members],
                     [r.name for r in school_members(spec)])
    for f in school.members:
      self.assertIs(f.school, school)
      self.assertIn(f, school)
      self.assertIs(sim_school.group_of(f), school)
      self.assertIn(f, tank.fish)
    angel = tank.fish[0]
    self.assertIsNone(angel.school)
    self.assertNotIn(angel, school)
    self.assertIs(sim_school.group_of(angel), angel)

  def test_snapshot(self):
    tank = stocked()
    run(tank, 2.0)
    snap = json.loads(json.dumps(tank.snapshot()))
    group = snap['schools'][0]
    self.assertEqual(group['name'], 'NeonTetras')
    self.assertEqual(group['species'], 'neon_tetra')
    self.assertEqual(len(group['members']), 15)
    members = [f for f in snap['fish'] if f.get('school') == 'NeonTetras']
    self.assertEqual([f['name'] for f in members], group['members'])
    self.assertIn('flicking', members[0])

  def test_members_vary_in_size_and_start_apart(self):
    members = school_members(schools()[0])
    sizes = [r.size for r in members]
    self.assertGreater(max(sizes) - min(sizes), 0.1)
    self.assertTrue(all(0.85 <= s <= 1.12 for s in sizes))
    starts = [r.start[:3] for r in members]
    for i, a in enumerate(starts):
      for b in starts[i + 1:]:
        self.assertGreater(math.dist(a, b), 0.5 * NEON_TETRA.length)

  def test_small_fish_rig_is_the_spine(self):
    tank = stocked()
    tetra = tank.schools[0].members[0]
    self.assertEqual(species.of(tetra.species).BONES, ('Head',) + swim.SPINE)
    self.assertEqual(species.of(tank.fish[0].species).BONES, angelfish.BONES)
    pose = neon_tetra.pose(tetra)
    self.assertEqual(set(pose), set(neon_tetra.BONES))
    self.assertEqual(neon_tetra.scales(tetra), {})


class SegmentTests(unittest.TestCase):

  def check(self, p0, p1, q0, q1, want_p, want_q):
    p, q = vec.closest_between_segments(p0, p1, q0, q1)
    for a, b in zip(p + q, want_p + want_q):
      self.assertAlmostEqual(a, b)

  def test_crossing(self):
    self.check((-1, 0, 0), (1, 0, 0), (0, -1, 1), (0, 1, 1),
               (0, 0, 0), (0, 0, 1))

  def test_ends(self):
    self.check((0, 0, 0), (1, 0, 0), (2, -1, 0), (2, 1, 0),
               (1, 0, 0), (2, 0, 0))
    self.check((0, 0, 0), (1, 0, 0), (-3, 0, 0), (-2, 0, 0),
               (0, 0, 0), (-2, 0, 0))

  def test_parallel_and_degenerate(self):
    p, q = vec.closest_between_segments((0, 0, 0), (1, 0, 0), (0, 1, 0),
                                        (1, 1, 0))
    self.assertAlmostEqual(vec.length(vec.sub(p, q)), 1.0)
    self.check((0, 0, 0), (0, 0, 0), (1, -1, 0), (1, 1, 0),
               (0, 0, 0), (1, 0, 0))
    self.check((0, 0, 0), (2, 0, 0), (1, 1, 0), (1, 1, 0),
               (1, 0, 0), (1, 1, 0))
    self.check((0, 0, 0), (0, 0, 0), (3, 0, 0), (3, 0, 0),
               (0, 0, 0), (3, 0, 0))


if __name__ == '__main__':
  unittest.main()
