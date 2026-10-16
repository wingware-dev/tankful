import math
import unittest

from tankful.sim import environment as env
from tankful.sim import species
from tankful.sim import vec
from tankful.sim.species import corydoras
from tankful.sim.species.corydoras import SPECIES as CORY
from tankful.sim.tank import Tank

DT = 1 / 60.0


def alone():
  """A tank with the corydoras and nothing else."""
  tank = Tank()
  return tank, corydoras.stock(tank)


def steps(tank, seconds):
  for _ in range(int(round(seconds / DT))):
    tank.step(DT)
    yield


def mouth(f):
  """Where the fish's mouth is in the tank."""
  m = f.orientation()
  mx, mz = corydoras.MOUTH
  local = (mx * f.length, 0.0, mz * f.length)
  return tuple(sum(m[i][j] * local[j] for j in range(3)) + p
               for i, p in enumerate((f.x, f.y, f.z)))


class StockTests(unittest.TestCase):

  def test_five_in_one_group_on_the_sand_sifting(self):
    tank, fish = alone()
    self.assertEqual(len(fish), 5)
    self.assertEqual(tank.fish, fish)
    self.assertEqual(len({f.name for f in fish}), 5)
    self.assertEqual(len({f.rng.random() for f in fish}), 5)
    group = fish[0].school
    self.assertEqual(group.name, 'Corydoras')
    self.assertEqual(group.members, fish)
    for f in fish:
      for o in fish:
        if o is not f:
          self.assertGreaterEqual(math.dist((f.x, f.y), (o.x, o.y)),
                                  corydoras.SPACING * f.length)
      self.assertIs(f.school, group)
      self.assertIs(f.species, CORY)
      self.assertEqual(f.state, corydoras.SIFT)
      self.assertGreater(f.floor.gap(f.x, f.y), 0)
      self.assertAlmostEqual(f.z, f.ground_z())
    # Not in the tank's schools: they don't school
    self.assertEqual(tank.schools, [])

  def test_registered_after_the_pleco(self):
    names = species.NAMES
    self.assertIn('corydoras', species.present())
    self.assertLess(names.index('pleco'), names.index('corydoras'))
    tank = Tank()
    species.stock(tank)
    self.assertEqual([f.name for f in tank.fish
                      if f.species.name == 'corydoras'],
                     ['Corydoras.%d' % i for i in range(5)])

  def test_repeatable(self):
    snaps = []
    for _ in range(2):
      tank, _ = alone()
      for _ in steps(tank, 20):
        pass
      snaps.append(tank.snapshot())
    self.assertEqual(snaps[0], snaps[1])


class FloorTests(unittest.TestCase):

  def setUp(self):
    self.floor = corydoras.Floor(CORY.length)

  def test_inside_the_glass_and_in_front(self):
    self.assertGreater(self.floor.gap(0.1, -0.12), 0)
    self.assertLess(self.floor.gap(env.INNER_X, -0.12), 0)
    self.assertLess(self.floor.gap(0.1, -env.INNER_Y), 0)
    self.assertLess(self.floor.gap(0.1, corydoras.FLOOR_BACK + 0.01), 0)

  def test_clear_of_the_decor(self):
    for o in env.obstacles():
      if o.a[1] < corydoras.FLOOR_BACK:
        self.assertLess(self.floor.gap(o.a[0], o.a[1]), 0, o.name)
    # Moss.1 sits at (-0.04, -0.02): no hop across it
    self.assertFalse(self.floor.clear((-0.04, -0.12), (-0.04, 0.01)))
    self.assertTrue(self.floor.clear((0.05, -0.12), (0.12, -0.12)))


class OnTheSandTests(unittest.TestCase):

  def test_depth_stays_within_the_bottom_band(self):
    # The whole tank, so the others can push and crowd them
    tank = Tank()
    species.stock(tank)
    fish = [f for f in tank.fish if f.species is CORY]
    seen = set()
    for _ in steps(tank, 150):
      for f in fish:
        seen.add(f.state)
        # Over open sand all the time, dashing or not
        self.assertGreater(f.floor.gap(f.x, f.y), -1e-9, f.name)
        if f.state == corydoras.DASH:
          self.assertLess(f.z, env.WATER_LEVEL)
          continue
        h = f.above_sand()
        self.assertLessEqual(h, corydoras.BAND * f.length, f.name)
        # Never below lying level on the sand, less the ripples' slope
        self.assertGreaterEqual(h, corydoras.BELLY * f.length - 1e-3,
                                f.name)
    self.assertEqual(seen, {corydoras.SIFT, corydoras.HOP, corydoras.REST,
                            corydoras.DASH})

  def test_sifts_nose_down_with_its_mouth_on_the_sand(self):
    tank, fish = alone()
    f = fish[0]
    checked = 0
    for _ in steps(tank, 60):
      if f.state == corydoras.SIFT and f.tilt == 1.0:
        self.assertAlmostEqual(f.pitch, corydoras.SIFT_PITCH)
        x, y, z = mouth(f)
        self.assertAlmostEqual(z, env.sand_height(x, y), places=6)
        checked += 1
    self.assertGreater(checked, 600)

  def test_moves_smoothly(self):
    tank, fish = alone()
    before = [(f.x, f.y, f.z, f.yaw, f.pitch) for f in fish]
    for _ in steps(tank, 120):
      for f, (x, y, z, yaw, pitch) in zip(fish, before):
        moved = math.dist((x, y, z), (f.x, f.y, f.z))
        self.assertLessEqual(moved, CORY.max_speed * f.size * DT, f.name)
        self.assertLessEqual(abs(vec.wrap_angle(f.yaw - yaw)), 8.0 * DT)
        self.assertLessEqual(abs(f.pitch - pitch), 2 * CORY.pitch_rate * DT)
      before = [(f.x, f.y, f.z, f.yaw, f.pitch) for f in fish]

  def test_hops_keep_together_and_apart(self):
    tank, fish = alone()
    for _ in steps(tank, 180):
      cx = sum(f.x for f in fish) / len(fish)
      cy = sum(f.y for f in fish) / len(fish)
      for f in fish:
        self.assertLess(math.dist((f.x, f.y), (cx, cy)), 0.3)
        if (f.state == corydoras.HOP and f.state_time == DT
            and f.spot() != (f.x, f.y)):
          # A hop just started, not a turn on the spot: its spot clear of
          # the others'
          for o in fish:
            if o is not f:
              self.assertGreaterEqual(
                math.dist(f.spot(), o.spot()),
                corydoras.SPACING * f.length - 1e-9)
    for f in fish:
      self.assertGreater(f.hops, 10, f.name)

  def test_boxed_in_turns_on_the_spot(self):
    tank, fish = alone()
    f = fish[0]
    f._choose_hop = lambda others: None
    f.state_len = 0.0
    x, y, yaw = f.x, f.y, f.yaw
    f.puffs = [None] * corydoras.PUFFS
    tank.step(DT)
    self.assertIn(f.state, (corydoras.HOP, corydoras.REST))
    if f.state == corydoras.HOP:
      for _ in steps(tank, f.state_len + DT):
        pass
      self.assertAlmostEqual(f.x, x)
      self.assertAlmostEqual(f.y, y)
      self.assertNotAlmostEqual(f.yaw, yaw)


class PuffTests(unittest.TestCase):

  def test_puffs_only_while_sifting(self):
    tank, fish = alone()
    thrown = 0
    for _ in steps(tank, 90):
      for f in fish:
        if f.active_puffs():
          self.assertEqual(f.state, corydoras.SIFT, f.name)
          thrown += 1
    self.assertGreater(thrown, 1000)

  def test_a_new_puff_takes_a_free_slot_then_the_oldest(self):
    _, fish = alone()
    f = fish[0]
    f.puffs = [None, 0.5]
    f._puff()
    self.assertEqual(f.puffs, [0.0, 0.5])
    f.puffs = [0.2, 0.9]
    f._puff()
    self.assertEqual(f.puffs, [0.2, 0.0])
    f._age_puffs(corydoras.PUFF_LIFE)
    self.assertEqual(f.puffs, [None, None])
    self.assertEqual(f.active_puffs(), 0)

  def test_puff_scale_bursts_spreads_and_settles(self):
    hidden = (corydoras.HIDDEN,) * 3
    self.assertEqual(corydoras.puff_scale(None), hidden)
    self.assertEqual(corydoras.puff_scale(corydoras.PUFF_LIFE), hidden)
    life = corydoras.PUFF_LIFE
    sizes = [corydoras.puff_scale(life * k / 20) for k in range(1, 20)]
    spreads = [s[0] for s in sizes]
    rises = [s[2] for s in sizes]
    for s in sizes:
      self.assertEqual(s[0], s[1])
    # Wider all the way; up, then flat onto the sand by the end
    self.assertEqual(spreads, sorted(spreads))
    top = rises.index(max(rises))
    self.assertGreater(max(rises), 0.8)
    self.assertTrue(0 < top < len(rises) - 1)
    self.assertLess(rises[-1], 0.05)

  def test_pose_stands_the_puffs_upright(self):
    tank, fish = alone()
    for _ in steps(tank, 3):
      pass
    for f in fish:
      pose = corydoras.pose(f)
      self.assertEqual(set(pose), set(corydoras.BONES))
      for bone in corydoras.PUFF_BONES:
        self.assertEqual(pose[bone], (f.pitch, 0.0, 0.0))
      self.assertEqual(set(corydoras.scales(f)), set(corydoras.PUFF_BONES))


class DashTests(unittest.TestCase):

  def test_dashes_to_the_surface_and_back(self):
    tank, fish = alone()
    f = fish[2]
    f.air_left = 0.0
    top = env.WATER_LEVEL - corydoras.TOP_DEPTH * f.size
    highest = 0.0
    phases = []
    for _ in steps(tank, 15):
      if f.state == corydoras.DASH:
        highest = max(highest, f.z)
        if not phases or phases[-1] != f.phase:
          phases.append(f.phase)
      elif phases:
        break
    self.assertEqual(f.dashes, 1)
    self.assertEqual(phases, [corydoras.RISE, corydoras.GULP,
                              corydoras.DIVE])
    self.assertGreater(highest, top - 1e-6)
    self.assertLess(highest, env.WATER_LEVEL)
    # Back on the sand, sifting, level as it landed
    self.assertEqual(f.state, corydoras.SIFT)
    self.assertLessEqual(f.above_sand(), corydoras.BAND * f.length)
    self.assertIsNone(f.target)
    self.assertGreater(f.air_left, corydoras.AIR_EVERY[0] - 15)

  def test_lands_where_it_aimed(self):
    tank, fish = alone()
    f = fish[1]
    f.air_left = 0.0
    land = None
    for _ in steps(tank, 15):
      if f.state == corydoras.DASH and land is None:
        land = f.target
      elif f.state != corydoras.DASH and land is not None:
        break
    self.assertAlmostEqual(f.x, land[0], places=6)
    self.assertAlmostEqual(f.y, land[1], places=6)


if __name__ == '__main__':
  unittest.main()
