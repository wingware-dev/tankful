import collections
import math
import types
import unittest

from tankful.game.fishes import Fishes
from tankful.sim import environment as env
from tankful.sim import school as sim_school
from tankful.sim import vec
from tankful.sim.fish import Fish
from tankful.sim.species import angelfish, cherry_shrimp as cs, pleco
from tankful.sim.tank import Tank

DT = 1 / 60.0


def alone():
  """A tank with the shrimp and nothing else."""
  tank = Tank()
  return tank, cs.stock(tank)


def stocked():
  """The shrimp with the angelfish and the pleco about."""
  tank = Tank()
  angelfish.stock(tank)
  pleco.stock(tank)
  return tank, cs.stock(tank)


def steps(tank, seconds):
  for _ in range(int(round(seconds / DT))):
    tank.step(DT)
    yield


def column(m, j):
  return (m[0][j], m[1][j], m[2][j])


def up(s):
  return column(s.orientation(), 2)


def in_tank(test, s):
  for v in (s.x, s.y, s.z):
    test.assertTrue(math.isfinite(v))
  test.assertLessEqual(abs(s.x), env.INNER_X)
  test.assertLessEqual(abs(s.y), env.INNER_Y)
  test.assertGreater(s.z, env.sand_height(s.x, s.y))
  test.assertLess(s.z, env.WATER_LEVEL)


def assert_standing(test, s):
  """Its center STAND lengths off the contact, along the normal, its
  back along the normal, and the contact on its surface."""
  center = vec.add(s.contact, vec.scale(s.normal, cs.STAND * s.length))
  test.assertLess(math.dist(center, (s.x, s.y, s.z)), 1e-9)
  for a, b in zip(up(s), s.normal):
    test.assertAlmostEqual(a, b, places=6)
  on, _ = s.surface.contact(s.contact)
  test.assertLess(math.dist(on, s.contact), 1e-9)
  test.assertAlmostEqual(vec.dot(s.heading, s.normal), 0.0, places=6)


def hold(shrimp):
  """Keep shrimp picking where they are."""
  for s in shrimp:
    s.pick_left = 1e9


class ColonyTests(unittest.TestCase):

  def test_a_few_shrimp_in_one_colony(self):
    tank, shrimp = alone()
    self.assertEqual(len(shrimp), 4)
    self.assertEqual(tank.fish, shrimp)
    colony = shrimp[0].school
    self.assertIsInstance(colony, cs.Colony)
    self.assertEqual(colony.name, cs.COLONY)
    self.assertEqual(colony.members, shrimp)
    for s in shrimp:
      self.assertIs(s.school, colony)
      self.assertIn(s, colony)
      # Selecting one selects them all
      self.assertIs(sim_school.group_of(s), colony)
    self.assertEqual(len({s.name for s in shrimp}), 4)
    self.assertEqual(len({s.rng.random() for s in shrimp}), 4)
    # It doesn't step: it isn't one of the tank's schools
    self.assertEqual(tank.schools, [])
    c = colony.centroid()
    self.assertAlmostEqual(c[0], sum(s.x for s in shrimp) / 4)

  def test_start_on_the_sand_and_the_moss(self):
    _, shrimp = alone()
    self.assertEqual([s.surface.kind for s in shrimp],
                     ['sand', 'moss', 'sand', 'moss'])
    for s, r in zip(shrimp, cs.shrimps()):
      self.assertEqual(s.state, cs.PICKING)
      assert_standing(self, s)
      self.assertLess(math.dist((s.x, s.y), r.start[:2]), 0.03)
      # In front of the decor, where the viewer sees them
      self.assertLess(s.y, 0.0)

  def test_repeatable(self):
    a, sa = stocked()
    b, sb = stocked()
    for _ in steps(a, 60):
      pass
    for _ in steps(b, 60):
      pass
    self.assertGreater(sum(s.hops for s in sa), 0)
    self.assertEqual(a.snapshot(), b.snapshot())
    snap = sa[0].snapshot()
    self.assertEqual(snap['colony'], cs.COLONY)
    self.assertIn(snap['state'], (cs.PICKING, cs.LIFTING, cs.SWIMMING,
                                  cs.LANDING))


class PickingTests(unittest.TestCase):

  def test_stays_on_its_surface_within_the_edges(self):
    tank, shrimp = alone()
    hold(shrimp)
    surfaces = [s.surface for s in shrimp]
    for _ in steps(tank, 90):
      for s, surface in zip(shrimp, surfaces):
        self.assertEqual(s.state, cs.PICKING)
        self.assertIs(s.surface, surface)
        assert_standing(self, s)
        for depth, _ in surface.edges(s.contact):
          self.assertGreaterEqual(depth, -1e-3)

  def test_walks_now_and_then_and_picks_in_between(self):
    tank, shrimp = alone()
    hold(shrimp)
    s = shrimp[0]
    walking, picks = 0, 0
    path = 0.0
    before = s.contact
    last = math.sin(s.pick_phase)
    n = 0
    for _ in steps(tank, 120):
      n += 1
      if s.walking > 0.5:
        walking += 1
      path += math.dist(before, s.contact)
      before = s.contact
      now = math.sin(s.pick_phase)
      if last < 0 <= now:
        picks += 1
      last = now
      self.assertLessEqual(s.speed, cs.WALK_SPEED * s.length + 1e-9)
    # Some of the time walking, most of it still
    self.assertGreater(walking / n, 0.05)
    self.assertLess(walking / n, 0.7)
    self.assertGreater(path, 0.01)
    self.assertLess(path, 120 * cs.WALK_SPEED * s.length)
    # Its claws keep picking, slower while it walks
    self.assertGreater(picks, 120 * cs.PICK_RATE * 0.4)
    self.assertLess(picks, 120 * cs.PICK_RATE * 1.05)

  def test_claws_pick_in_turn(self):
    tank, shrimp = alone()
    hold(shrimp)
    s = shrimp[0]
    seen = set()
    for _ in steps(tank, 10):
      if s.walking < 0.1:
        p = cs.pose(s)
        left, right = p['Claw.L'][0], p['Claw.R'][0]
        # One reaches down (+) while the other lifts to the mouth (-)
        self.assertLessEqual(left * right, 1e-12)
        if abs(left) > 0.1:
          seen.add(left > 0)
    self.assertEqual(seen, {True, False})

  def test_keeps_off_the_other_shrimp(self):
    tank, shrimp = alone()
    hold(shrimp)
    a, b = shrimp[0], shrimp[2]
    # Side by side on the sand, facing each other
    b.contact = b.surface.clamp(vec.add(a.contact, (0.02, 0.0, 0.0)))
    b.heading, a.heading = (-1.0, 0.0, 0.0), (1.0, 0.0, 0.0)
    near = cs.KEEP_OFF * max(a.length, b.length)
    for _ in steps(tank, 20):
      pass
    self.assertGreater(math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)), near * 0.9)

  def test_lifts_off_when_its_time_is_up(self):
    tank, shrimp = alone()
    hold(shrimp)
    s = shrimp[0]
    s.pick_left = 1.0
    for _ in steps(tank, 0.9):
      pass
    self.assertEqual(s.state, cs.PICKING)
    for _ in steps(tank, 0.2):
      pass
    self.assertEqual(s.state, cs.LIFTING)
    self.assertIsNone(s.surface)
    self.assertIsNotNone(s.target)

  def test_lifts_off_when_a_fish_crowds_it(self):
    tank, shrimp = alone()
    hold(shrimp)
    s = shrimp[0]
    big = Fish('Big', angelfish.SPECIES, 1.0, 1)
    big.x, big.y, big.z = s.x, s.y + 0.01, s.z + 0.02
    big.step = lambda dt, others=(): None
    tank.fish.append(big)
    tank.step(DT)
    self.assertEqual(s.state, cs.LIFTING)
    self.assertNotEqual(shrimp[2].state, cs.LIFTING)


class StateMachineTests(unittest.TestCase):

  def test_the_states_run_round_in_order(self):
    tank, shrimp = alone()
    s = shrimp[1]
    seen = [s.state]
    while s.hops < 3 or s.state != cs.PICKING:
      tank.step(DT)
      if s.state != seen[-1]:
        seen.append(s.state)
      self.assertLess(tank.time, 200)
    cycle = [cs.PICKING, cs.LIFTING, cs.SWIMMING, cs.LANDING]
    self.assertEqual(seen, cycle * 3 + [cs.PICKING])

  def test_lift_only_from_a_surface(self):
    _, shrimp = alone()
    s = shrimp[0]
    self.assertTrue(s.lift())
    self.assertEqual(s.state, cs.LIFTING)
    self.assertFalse(s.lift())

  def test_rises_then_swims(self):
    tank, shrimp = alone()
    s = shrimp[0]
    start = (s.x, s.y, s.z)
    normal = s.normal
    s.lift()
    for _ in steps(tank, cs.LIFT_TIME - DT / 2):
      pass
    self.assertEqual(s.state, cs.LIFTING)
    off = vec.sub((s.x, s.y, s.z), start)
    self.assertAlmostEqual(vec.dot(off, normal), cs.LIFT, places=3)
    tank.step(DT)
    self.assertEqual(s.state, cs.SWIMMING)
    self.assertEqual(s.swimming, 1.0)
    self.assertIsNone(s._frame)

  def test_lands_exactly_on_the_spot(self):
    tank, shrimp = alone()
    s = shrimp[0]
    s.lift(tank.fish)
    target = s.target
    while s.state != cs.PICKING:
      tank.step(DT)
      self.assertLess(tank.time, 30)
    self.assertIs(s.surface, target.surface)
    self.assertEqual(s.contact, target.point)
    self.assertEqual(s.normal, target.normal)
    assert_standing(self, s)
    self.assertIsNone(s.target)
    self.assertEqual(s.swimming, 0.0)

  def test_picks_another_spot_when_one_is_taken(self):
    tank, shrimp = alone()
    s = shrimp[0]
    s.lift(tank.fish)
    for _ in steps(tank, cs.LIFT_TIME + 0.1):
      pass
    self.assertEqual(s.state, cs.SWIMMING)
    first = s.target
    sitter = Fish('Sitter', angelfish.SPECIES, 1.0, 2)
    sitter.x, sitter.y, sitter.z = vec.add(first.point, (0.0, 0.0, 0.02))
    sitter.step = lambda dt, others=(): None
    tank.fish.append(sitter)
    tank.step(DT)
    self.assertEqual(s.state, cs.SWIMMING)
    self.assertIsNot(s.target, first)

  def test_gives_up_on_a_spot_it_cannot_reach(self):
    tank, shrimp = alone()
    s = shrimp[0]
    s.lift()
    for _ in steps(tank, cs.LIFT_TIME + 0.1):
      pass
    first = s.target
    arrive = cs.ARRIVE
    cs.ARRIVE = -1.0
    try:
      for _ in steps(tank, cs.SWIM_TIMEOUT + 0.5):
        pass
    finally:
      cs.ARRIVE = arrive
    self.assertEqual(s.state, cs.SWIMMING)
    self.assertIsNot(s.target, first)
    self.assertLess(s.state_time, 1.0)

  def test_frame_is_a_rotation_in_every_state(self):
    tank, shrimp = alone()
    s = shrimp[0]
    s.lift()
    states = set()
    for _ in steps(tank, 20):
      states.add(s.state)
      m = s.orientation()
      for i in range(3):
        for j in range(3):
          d = sum(m[k][i] * m[k][j] for k in range(3))
          self.assertAlmostEqual(d, 1.0 if i == j else 0.0, places=6)
      f = s.forward()
      for a, b in zip(f, column(m, 0)):
        self.assertAlmostEqual(a, b, places=9)
    self.assertEqual(states, {cs.LIFTING, cs.SWIMMING, cs.LANDING,
                              cs.PICKING})

  def test_picks_at_sand_and_moss_and_stays_in_the_tank(self):
    tank, shrimp = stocked()
    kinds = collections.Counter()
    prev = {s: s.state for s in shrimp}
    swimming = 0
    total = 0
    for _ in steps(tank, 300):
      for s in shrimp:
        in_tank(self, s)
        total += 1
        if s.state == cs.SWIMMING:
          swimming += 1
        if s.state == cs.PICKING and prev[s] != cs.PICKING:
          kinds[s.surface.kind] += 1
          # Landed clear of the other shrimp
          for o in shrimp:
            if o is not s and o.state == cs.PICKING:
              self.assertGreater(math.dist((s.x, s.y, s.z),
                                           (o.x, o.y, o.z)),
                                 s.length * 1.2)
        prev[s] = s.state
    self.assertEqual(set(kinds), {'sand', 'moss'})
    self.assertGreaterEqual(sum(kinds.values()), 20)
    # Mostly picking; the swims are short
    self.assertLess(swimming / total, 0.25)


class SurfaceTests(unittest.TestCase):

  def test_the_moss_used_is_in_front(self):
    moss = cs.surfaces()['moss']
    names = [m.obstacle for m in moss]
    self.assertGreaterEqual(len(names), 3)
    plants = {p.name: p for p in env.plants()}
    for name in names:
      self.assertEqual(plants[name].kind, 'moss')
      self.assertLess(plants[name].y, cs.MOSS_BACK)

  def test_moss_spots_are_open(self):
    # Moss.1 grows under the driftwood: its spots, and the water above
    # them that a swim aims for, are clear of the wood
    import random
    rng = random.Random(3)
    hard = [o for o in env.obstacles() if not o.soft]
    for moss in cs.surfaces()['moss']:
      found = 0
      for _ in range(40):
        p = moss.random_point(rng)
        if p is None:
          continue
        found += 1
        _, normal = moss.contact(p)
        self.assertGreater(normal[2], 0.9)
        above = vec.add(p, (0.0, 0.0, cs.APPROACH))
        for o in hard:
          d = math.dist(above, vec.closest_on_segment(above, o.a, o.b))
          self.assertGreater(d - o.radius, cs.SPECIES.clear_side * 1.1,
                             (moss.name, o.name))
        self.assertLessEqual(math.dist(p[:2], moss.center), moss.WALK)
      self.assertGreater(found, 10, moss.name)

  def test_moss_clamp_keeps_off_the_wood(self):
    moss = [m for m in cs.surfaces()['moss'] if m.obstacle == 'Moss.1'][0]
    self.assertTrue(moss._hard)
    for a in range(0, 360, 15):
      r = math.radians(a)
      p = moss.clamp((moss.center[0] + 0.05 * math.cos(r),
                      moss.center[1] + 0.05 * math.sin(r), 0.0))
      for gap, _ in moss._decor(p):
        self.assertGreater(gap, -1e-3)
      self.assertLessEqual(math.dist(p[:2], moss.center), moss.WALK + 1e-3)

  def test_choose_spot_hops_near_and_keeps_off_mates(self):
    import random
    rng = random.Random(5)
    by_kind = cs.surfaces()
    here = (0.0, -0.12, env.sand_height(0.0, -0.12))
    mates = [(0.05, -0.12, 0.04), (-0.05, -0.1, 0.04)]
    hops = []
    for _ in range(100):
      spot = cs.choose_spot(rng, by_kind, here, mates)
      for m in mates:
        self.assertGreaterEqual(math.dist(spot.point, m),
                                cs.LAND_OFF * cs.SPECIES.length)
      self.assertAlmostEqual(vec.dot(spot.heading, spot.normal), 0.0)
      hops.append(math.dist(spot.point, here))
    near = [h for h in hops if cs.HOP[0] <= h <= cs.HOP[1]]
    self.assertGreater(len(near), 90)


class PoseTests(unittest.TestCase):

  def test_covers_the_bones(self):
    tank, shrimp = alone()
    shrimp[0].lift()
    for _ in steps(tank, 3):
      for s in shrimp:
        p = cs.pose(s)
        self.assertEqual(set(p), set(cs.BONES))
        for rot in p.values():
          self.assertEqual(len(rot), 3)
          for v in rot:
            self.assertTrue(math.isfinite(v))
        self.assertEqual(cs.scales(s), {})
    self.assertEqual(cs.BONES[:5], ('Head',) + cs.SPINE)

  def test_legs_step_walking_and_fold_swimming(self):
    _, shrimp = alone()
    s = shrimp[0]
    s.swimming, s.walking = 0.0, 0.0
    for phase in (0.0, 1.0, 2.0):
      s.step_phase = phase
      self.assertEqual(cs.pose(s)['Legs.L'][0], 0.0)
    s.walking, s.step_phase = 1.0, math.pi / 2
    p = cs.pose(s)
    self.assertAlmostEqual(p['Legs.L'][0], cs.LEG_SWING)
    self.assertAlmostEqual(p['Legs.R'][0], -cs.LEG_SWING)
    s.swimming = 1.0
    p = cs.pose(s)
    self.assertAlmostEqual(p['Legs.L'][0], cs.LEG_FOLD)
    self.assertAlmostEqual(p['Legs.R'][0], cs.LEG_FOLD)

  def test_swimmerets_beat_harder_swimming(self):
    _, shrimp = alone()
    s = shrimp[0]

    def swing(sw):
      s.swimming = sw
      out = 0.0
      for k in range(24):
        s.beat_phase = 2 * math.pi * k / 24
        out = max(out, abs(cs.pose(s)['Swim.1'][0]))
      return out
    self.assertAlmostEqual(swing(0.0), cs.SWIM_REST, places=2)
    self.assertAlmostEqual(swing(1.0), cs.SWIM_BEAT, places=2)


class Channel:

  def __init__(self):
    self.rotation_euler = None
    self.location = None
    self.rotation_quaternion = None


class FishesTests(unittest.TestCase):
  """The game's fish driver poses the colony as one rig."""

  def test_one_rig_for_the_colony(self):
    tank, shrimp = alone()
    channels = {}
    for s in shrimp:
      for bone in ('Root',) + cs.BONES:
        channels[s.name + ':' + bone] = Channel()
    updates = []
    rig = types.SimpleNamespace(name=cs.COLONY + '.Rig', channels=channels,
                                worldPosition=None,
                                update=lambda: updates.append(1))
    scene = types.SimpleNamespace(objects={rig.name: rig})
    fishes = Fishes(scene, tank.fish)
    self.assertEqual(fishes.snapshot(), {'rigs': [],
                                         'school_rigs': [rig.name],
                                         'members': 4})
    for _ in steps(tank, 1):
      pass
    fishes.update()
    self.assertEqual(updates, [1])
    for s in shrimp:
      root = channels[s.name + ':Root']
      self.assertEqual(root.location, (s.x, s.y, s.z))
      self.assertEqual(channels[s.name + ':Claw.L'].rotation_euler,
                       cs.pose(s)['Claw.L'])


if __name__ == '__main__':
  unittest.main()
