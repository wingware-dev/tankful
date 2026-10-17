import math
import unittest
from types import SimpleNamespace

from tankful.game import steering as game_steering
from tankful.sim import school as sim_school
from tankful.sim import species
from tankful.sim import steering
from tankful.sim import vec
from tankful.sim.fish import CRUISE, HOVER, STEER_TOP
from tankful.sim.species import angelfish, cherry_shrimp, corydoras, pleco
from tankful.sim.tank import Tank

DT = 1.0 / 60


def stocked():
  tank = Tank()
  species.stock(tank)
  return tank


def named(tank, name):
  return next(f for f in tank.fish if f.name == name)


def run(tank, control, seconds, keys=()):
  for _ in range(int(round(seconds / DT))):
    control.update(DT, keys)
    tank.step(DT)


def mean_speed(tank, control, fish, seconds, keys=()):
  """The mean speed of fish over seconds of running with keys."""
  total = 0.0
  steps = int(round(seconds / DT))
  for _ in range(steps):
    control.update(DT, keys)
    tank.step(DT)
    total += sum(f.speed for f in fish) / len(fish)
  return total / steps


class ControlStateTest(unittest.TestCase):

  def setUp(self):
    self.fish = SimpleNamespace(name='Fish', steer=None)
    self.control = steering.Control()

  def test_starts_idle_and_keys_do_nothing(self):
    c = self.control
    self.assertEqual(c.state, steering.IDLE)
    c.update(DT, ['left'])
    self.assertEqual(c.state, steering.IDLE)
    self.assertIsNone(c.steer)

  def test_select_then_steer_then_release(self):
    c, f = self.control, self.fish
    c.select(f)
    self.assertEqual(c.state, steering.SELECTED)
    c.update(DT, ['left'])
    self.assertEqual(c.state, steering.STEERING)
    self.assertIs(f.steer, c.steer)
    self.assertEqual(c.steer.direction, (-1.0, 0.0))
    # The weight ramps in over RAMP_IN
    self.assertAlmostEqual(c.steer.weight, DT / steering.RAMP_IN)
    for _ in range(30):
      c.update(DT, ['left'])
    self.assertEqual(c.steer.weight, 1.0)
    # Released, it blends out over BLEND_OUT, keeping the direction
    c.update(DT, [])
    self.assertEqual(c.state, steering.RELEASING)
    self.assertEqual(c.steer.direction, (-1.0, 0.0))
    self.assertLess(c.steer.weight, 1.0)
    steps = int(math.ceil(steering.BLEND_OUT / DT))
    for _ in range(steps):
      c.update(DT, [])
    self.assertEqual(c.state, steering.SELECTED)
    self.assertIsNone(c.steer)
    self.assertIsNone(f.steer)

  def test_no_time_no_change(self):
    c = self.control
    c.select(self.fish)
    c.update(DT, ['up'])
    w = c.steer.weight
    c.update(0.0, ['up'])
    self.assertEqual(c.steer.weight, w)
    c.update(0.0, [])
    self.assertEqual(c.state, steering.RELEASING)
    self.assertEqual(c.steer.weight, w)

  def test_pressing_again_while_releasing_takes_it_back(self):
    c = self.control
    c.select(self.fish)
    for _ in range(30):
      c.update(DT, ['right'])
    for _ in range(10):
      c.update(DT, [])
    s = c.steer
    w = s.weight
    c.update(DT, ['down'])
    self.assertIs(c.steer, s)
    self.assertEqual(c.state, steering.STEERING)
    self.assertEqual(s.direction, (0.0, -1.0))
    self.assertGreater(s.weight, w)

  def test_diagonals_are_unit_and_opposites_cancel(self):
    d = steering.arrows(['left', 'up'])
    self.assertAlmostEqual(math.hypot(*d), 1.0)
    self.assertLess(d[0], 0)
    self.assertGreater(d[1], 0)
    self.assertIsNone(steering.arrows(['left', 'right']))
    self.assertIsNone(steering.arrows(['space']))

  def test_selecting_another_lets_the_first_blend_out(self):
    c, f = self.control, self.fish
    g = SimpleNamespace(name='Other', steer=None)
    c.select(f)
    for _ in range(30):
      c.update(DT, ['left'])
    old = f.steer
    c.select(g)
    self.assertEqual(c.state, steering.SELECTED)
    self.assertIs(f.steer, old)
    self.assertEqual(c.fading, [old])
    c.update(DT, ['left'])
    # The keys steer only the new one; the old still fades
    self.assertIs(g.steer, c.steer)
    self.assertLess(old.weight, 1.0)
    for _ in range(int(math.ceil(steering.BLEND_OUT / DT))):
      c.update(DT, ['left'])
    self.assertIsNone(f.steer)
    self.assertEqual(c.fading, [])

  def test_reselecting_a_fading_group_picks_its_steer_up(self):
    c, f = self.control, self.fish
    g = SimpleNamespace(name='Other', steer=None)
    c.select(f)
    for _ in range(30):
      c.update(DT, ['left'])
    old = f.steer
    c.select(g)
    c.update(DT, [])
    c.select(f)
    c.update(DT, ['right'])
    self.assertIs(c.steer, old)
    self.assertEqual(c.fading, [])

  def test_deselect(self):
    c = self.control
    c.select(self.fish)
    c.update(DT, ['left'])
    c.select(None)
    self.assertEqual(c.state, steering.IDLE)
    self.assertEqual(len(c.fading), 1)

  def test_targets(self):
    tank = stocked()
    tetra = next(f for f in tank.fish if f.species.name == 'neon_tetra')
    school = sim_school.group_of(tetra)
    self.assertEqual(steering.targets(school), [school])
    cory = named(tank, 'Corydoras.0')
    self.assertEqual(steering.targets(sim_school.group_of(cory)),
                     cory.school.members)
    angel = named(tank, 'Angelfish.0')
    self.assertEqual(steering.targets(sim_school.group_of(angel)), [angel])

  def test_is_selected_covers_the_group(self):
    tank = stocked()
    tetras = [f for f in tank.fish if f.species.name == 'neon_tetra']
    c = self.control
    c.select(sim_school.group_of(tetras[3]))
    self.assertTrue(all(c.is_selected(f) for f in tetras))
    self.assertFalse(c.is_selected(named(tank, 'Angelfish.0')))
    snap = c.snapshot()
    self.assertEqual(snap['selected'], 'NeonTetras')
    self.assertEqual(len(snap['members']), len(tetras))


class SteeredFishTest(unittest.TestCase):

  def setUp(self):
    self.tank = stocked()
    self.control = steering.Control()

  def test_steered_left_goes_left_and_keeps_its_depth(self):
    f = named(self.tank, 'Angelfish.1')
    run(self.tank, self.control, 2.0)
    self.control.select(f)
    y0, x0 = f.y, f.x
    run(self.tank, self.control, 5.0, ['left'])
    self.assertLess(f.x, x0 - 0.1)
    self.assertAlmostEqual(f.y, y0, delta=0.03)
    # It faces the way it goes
    self.assertGreater(abs(vec.wrap_angle(f.yaw)), math.radians(140))
    self.assertEqual(f.mode, CRUISE)

  def test_banks_into_the_turn(self):
    f = named(self.tank, 'Angelfish.1')
    run(self.tank, self.control, 1.0)
    self.control.select(f)
    # Swing it round from its heading to the other way
    key = 'left' if math.cos(f.yaw) > 0 else 'right'
    rolls = []
    for _ in range(120):
      self.control.update(DT, [key])
      self.tank.step(DT)
      rolls.append(abs(f.roll))
    self.assertGreater(max(rolls), math.radians(3))

  def test_up_climbs(self):
    f = named(self.tank, 'Angelfish.0')
    run(self.tank, self.control, 1.0)
    self.control.select(f)
    z0 = f.z
    run(self.tank, self.control, 3.0, ['up'])
    self.assertGreater(f.z, z0 + 0.03)

  def test_never_hovers_while_steered(self):
    f = named(self.tank, 'Angelfish.0')
    f.mode = HOVER
    f.hover_left = 30.0
    self.control.select(f)
    run(self.tank, self.control, 0.5, ['right'])
    self.assertEqual(f.mode, CRUISE)

  def test_let_go_it_blends_back_and_swims_on(self):
    f = named(self.tank, 'Angelfish.1')
    self.control.select(f)
    run(self.tank, self.control, 3.0, ['left'])
    yaw = f.yaw
    # One step after the keys are up it still heads about the same way
    run(self.tank, self.control, DT)
    self.assertLess(abs(vec.wrap_angle(f.yaw - yaw)), 0.1)
    self.assertIsNotNone(f.steer)
    run(self.tank, self.control, steering.BLEND_OUT + 0.1)
    self.assertIsNone(f.steer)
    self.assertIsNone(f._steer_y)
    self.assertEqual(self.control.state, steering.SELECTED)
    run(self.tank, self.control, 10.0)
    (x0, x1), (y0, y1), (z0, z1) = f.bounds()
    self.assertTrue(x0 <= f.x <= x1 and y0 <= f.y <= y1 and z0 <= f.z <= z1)

  def test_steered_it_swims_faster_than_of_itself(self):
    f = named(self.tank, 'Angelfish.0')
    run(self.tank, self.control, 2.0)
    own = mean_speed(self.tank, self.control, [f], 4.0)
    self.control.select(f)
    run(self.tank, self.control, 1.0, ['right'])
    steered = mean_speed(self.tank, self.control, [f], 4.0, ['right'])
    self.assertGreater(steered, 1.5 * own)
    self.assertGreater(steered, 1.3 * f.cruise_speed)
    self.assertLessEqual(f.steered_speed(), STEER_TOP * f.max_speed)

  def test_stays_in_the_tank_steered_into_the_glass(self):
    f = named(self.tank, 'Angelfish.0')
    self.control.select(f)
    run(self.tank, self.control, 15.0, ['left'])
    (x0, x1), _, _ = f.bounds()
    self.assertGreaterEqual(f.x, x0)
    self.assertLess(f.x, x0 + 0.05)


class SteeredSchoolTest(unittest.TestCase):

  def test_the_school_follows_its_steered_goal_in_formation(self):
    tank = stocked()
    control = steering.Control()
    run(tank, control, 2.0)
    school = next(s for s in tank.schools if s.name == 'NeonTetras')
    control.select(school)
    c0 = school.centroid()
    g0 = school.goal
    # Long enough to cross open water, not to reach the plants on the
    # right, which the goal slides round (School._limit_goal)
    run(tank, control, 1.5, ['right'])
    self.assertGreater(school.goal[0], g0[0] + 0.1)
    self.assertAlmostEqual(school.goal[1], g0[1], delta=0.02)
    c1 = school.centroid()
    self.assertGreater(c1[0], c0[0] + 0.06)
    # Together, round the goal
    self.assertLess(school.spread(), 2.5 * school.radius)
    self.assertLess(math.dist(c1, school.goal), 3 * school.radius)
    # The members aren't steered one by one
    self.assertTrue(all(m.steer is None for m in school.members))
    self.assertIs(school.steer, control.steer)

  def test_steered_the_school_swims_faster_than_of_itself(self):
    tank = stocked()
    control = steering.Control()
    run(tank, control, 2.0)
    school = next(s for s in tank.schools if s.name == 'NeonTetras')
    own = mean_speed(tank, control, school.members, 2.5)
    control.select(school)
    run(tank, control, 0.5, ['left'])
    steered = mean_speed(tank, control, school.members, 2.5, ['left'])
    self.assertGreater(steered, 1.3 * own)
    self.assertLess(school.spread(), 2.5 * school.radius)

  def test_the_goal_turns_the_steered_way(self):
    tank = stocked()
    control = steering.Control()
    school = next(s for s in tank.schools if s.name == 'NeonTetras')
    control.select(school)
    run(tank, control, 6.0, ['right'])
    self.assertLess(abs(vec.wrap_angle(school.yaw)), 0.5)
    self.assertFalse(school.swing)


class SteeredPlecoTest(unittest.TestCase):

  def test_lets_go_then_swims_where_steered_and_reattaches_after(self):
    tank = stocked()
    control = steering.Control()
    p = next(f for f in tank.fish if isinstance(f, pleco.Pleco))
    self.assertEqual(p.state, pleco.ATTACHED)
    control.select(p)
    run(tank, control, DT, ['up'])
    self.assertEqual(p.state, pleco.RELEASING)
    run(tank, control, pleco.RELEASE_TIME + 0.1, ['up'])
    self.assertEqual(p.state, pleco.DARTING)
    z0 = p.z
    run(tank, control, 1.5, ['up'])
    self.assertGreater(p.z, z0 + 0.03)
    # However long it is steered, it settles nowhere
    run(tank, control, 12.0, ['right'])
    self.assertEqual(p.state, pleco.DARTING)
    run(tank, control, steering.BLEND_OUT + 0.1)
    self.assertIsNone(p.steer)
    for _ in range(int(30 / DT)):
      control.update(DT, ())
      tank.step(DT)
      if p.state == pleco.ATTACHED:
        break
    self.assertEqual(p.state, pleco.ATTACHED)


class SteeredShrimpTest(unittest.TestCase):

  def test_lifts_off_swims_and_lands_after(self):
    tank = stocked()
    control = steering.Control()
    s = next(f for f in tank.fish if isinstance(f, cherry_shrimp.Shrimp)
             and f.state == cherry_shrimp.PICKING)
    group = sim_school.group_of(s)
    control.select(group)
    run(tank, control, cherry_shrimp.LIFT_TIME + 0.2, ['up'])
    swimming = [m for m in group.members
                if m.state == cherry_shrimp.SWIMMING]
    self.assertIn(s, swimming)
    z0 = s.z
    run(tank, control, 1.0, ['up'])
    self.assertGreater(s.z, z0)
    run(tank, control, 10.0, ['left'])
    self.assertEqual(s.state, cherry_shrimp.SWIMMING)
    run(tank, control, steering.BLEND_OUT + 0.1)
    for _ in range(int(30 / DT)):
      control.update(DT, ())
      tank.step(DT)
      if s.state == cherry_shrimp.PICKING:
        break
    self.assertEqual(s.state, cherry_shrimp.PICKING)


class SteeredCorydorasTest(unittest.TestCase):

  def test_swims_free_then_dives_back_to_the_sand(self):
    tank = stocked()
    control = steering.Control()
    c = named(tank, 'Corydoras.1')
    control.select(sim_school.group_of(c))
    run(tank, control, DT, ['up'])
    self.assertEqual(c.state, corydoras.STEERED)
    h0 = c.above_sand()
    run(tank, control, 2.0, ['up'])
    self.assertGreater(c.above_sand(), h0 + 0.03)
    run(tank, control, steering.BLEND_OUT + 0.1)
    self.assertEqual(c.state, corydoras.DASH)
    self.assertEqual(c.phase, corydoras.DIVE)
    lowest = min(z for z in [c.z])
    for _ in range(int(5 / DT)):
      control.update(DT, ())
      tank.step(DT)
      lowest = min(lowest, c.above_sand())
      if c.state == corydoras.SIFT:
        break
    self.assertEqual(c.state, corydoras.SIFT)
    # Never into the sand on the way down
    self.assertGreater(lowest, 0.0)


class PickingTest(unittest.TestCase):

  # A camera at (0, -1, 0.25) looking along +y, 50 degrees across a 16:9
  # window
  WINDOW = (1280, 720)
  POS = (0.0, -1.0, 0.25)
  # Columns: right (+x), up (+z), back (-y)
  ROT = ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))

  def projection(self, shift=(0.0, 0.0)):
    f = 1.0 / math.tan(math.radians(25))
    aspect = self.WINDOW[0] / self.WINDOW[1]
    return ((f, 0.0, shift[0], 0.0), (0.0, f * aspect, shift[1], 0.0),
            (0.0, 0.0, -1.0, -0.2), (0.0, 0.0, -1.0, 0.0))

  def project(self, p, proj):
    """Window pixels of world point p, as the camera sees it."""
    off = vec.sub(p, self.POS)
    view = [sum(self.ROT[i][j] * off[i] for i in range(3)) for j in range(3)]
    clip = [sum(proj[i][j] * (view + [1.0])[j] for j in range(4))
            for i in range(4)]
    nx, ny = clip[0] / clip[3], clip[1] / clip[3]
    w, h = self.WINDOW
    return ((nx + 1) / 2 * w, (1 - ny) / 2 * h)

  def test_ray_goes_through_the_point_it_was_cast_at(self):
    for shift in ((0.0, 0.0), (0.1, -0.05)):
      proj = self.projection(shift)
      p = (0.21, 0.05, 0.31)
      px, py = self.project(p, proj)
      o, d = game_steering.screen_ray(px, py, self.WINDOW, self.POS,
                                      self.ROT, proj)
      t = vec.dot(vec.sub(p, o), d)
      closest = vec.add(o, vec.scale(d, t))
      self.assertLess(math.dist(closest, p), 1e-6)

  def test_center_of_window_looks_ahead(self):
    o, d = game_steering.screen_ray(640, 360, self.WINDOW, self.POS,
                                    self.ROT, self.projection())
    self.assertAlmostEqual(d[1], 1.0)

  def test_ray_hits_the_ellipsoid(self):
    rot = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    axes = (0.06, 0.02, 0.04)
    t = game_steering.ray_hit((0.0, -1.0, 0.0), (0.0, 1.0, 0.0),
                              (0.0, 0.0, 0.0), rot, axes)
    self.assertAlmostEqual(t, 1.0 - 0.02)
    # Off the end of it along x, it misses
    self.assertIsNone(game_steering.ray_hit(
      (0.07, -1.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 0.0), rot, axes))
    # Turned 90 degrees about z, its length lies along y and x is narrow
    turned = ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    self.assertIsNone(game_steering.ray_hit(
      (0.03, -1.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 0.0), turned, axes))
    self.assertIsNotNone(game_steering.ray_hit(
      (0.03, -1.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 0.0), rot, axes))
    # Behind the ray's start, it misses
    self.assertIsNone(game_steering.ray_hit(
      (0.0, 1.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 0.0), rot, axes))

  def test_picks_the_nearest_fish_and_misses_open_water(self):
    tank = stocked()
    proj = self.projection()
    a = named(tank, 'Angelfish.0')
    px, py = self.project((a.x, a.y, a.z), proj)
    o, d = game_steering.screen_ray(px, py, self.WINDOW, self.POS, self.ROT,
                                    proj)
    self.assertIs(game_steering.pick(o, d, tank.fish), a)
    # A tetra in front of the angelfish takes the click
    t = next(f for f in tank.fish if f.species.name == 'neon_tetra')
    t.x, t.y, t.z = vec.add((a.x, a.y, a.z), vec.scale(d, -0.1))
    self.assertIs(game_steering.pick(o, d, tank.fish), t)
    o, d = game_steering.screen_ray(5, 5, self.WINDOW, self.POS, self.ROT,
                                    proj)
    self.assertIsNone(game_steering.pick(o, d, tank.fish))

  def test_proxy_follows_the_fish(self):
    tank = stocked()
    a = named(tank, 'Angelfish.0')
    center, rot, axes = game_steering.proxy(a)
    self.assertEqual(center, (a.x, a.y, a.z))
    self.assertGreater(axes[0], axes[1])
    self.assertAlmostEqual(axes[0], 0.5 * a.length + game_steering.PICK_PAD)


class FakeObj:

  def __init__(self, name):
    self.name = name
    self.visible = True


class FakeFishes:

  def __init__(self, fish):
    self.fish = fish
    self.scales = {}

  def drawn(self):
    return set(self.fish)

  def set_scale(self, f, s):
    self.scales[f.name] = s


class FakeInput:

  def __init__(self, clicks=(), down=()):
    self._clicks = list(clicks)
    self._down = set(down)

  def clicks(self):
    return list(self._clicks)

  def is_down(self, key):
    return key in self._down


class SteeringGameTest(unittest.TestCase):

  def setUp(self):
    self.tank = stocked()
    keys = {sim_school.group_of(f).name for f in self.tank.fish}
    self.objects = {k + '.Outline': FakeObj(k + '.Outline') for k in keys}
    pick = PickingTest()
    self.camera = SimpleNamespace(worldPosition=pick.POS,
                                  worldOrientation=pick.ROT,
                                  projection_matrix=pick.projection(),
                                  getScreenPosition=lambda p: (0.5, 0.5))
    self.scene = SimpleNamespace(objects=self.objects,
                                 active_camera=self.camera)
    self.fishes = FakeFishes(self.tank.fish)
    self.steering = game_steering.Steering(self.scene, self.tank,
                                           self.fishes)
    self.pick = pick

  def click_on(self, f, **kw):
    x, y = self.pick.project((f.x, f.y, f.z), self.camera.projection_matrix)
    self.steering.frame(FakeInput([(x, y, 'left')]), PickingTest.WINDOW, DT,
                        **kw)

  def test_outlines_start_hidden(self):
    self.assertTrue(all(not o.visible for o in self.objects.values()))

  def test_click_selects_the_school_scales_and_outlines_it(self):
    t = next(f for f in self.tank.fish if f.species.name == 'neon_tetra')
    others = [f for f in self.tank.fish if f.species.name == 'neon_tetra']
    # Put it where nothing is in front of it
    t.x, t.y, t.z = 0.0, -0.17, 0.26
    self.click_on(t)
    self.assertIs(self.steering.control.selected, t.school)
    self.steering.show()
    self.assertTrue(all(self.fishes.scales[f.name] ==
                        game_steering.SELECTED_SCALE for f in others))
    self.assertTrue(self.objects['NeonTetras.Outline'].visible)
    self.assertTrue(self.steering.snapshot()['outline'])
    # Then open water: deselected, back to size, no outline
    self.steering.frame(FakeInput([(5, 5, 'left')]), PickingTest.WINDOW, DT)
    self.steering.show()
    self.assertIsNone(self.steering.control.selected)
    self.assertTrue(all(self.fishes.scales[f.name] == 1.0 for f in others))
    self.assertFalse(self.objects['NeonTetras.Outline'].visible)

  def test_a_click_taken_elsewhere_is_left_alone(self):
    a = named(self.tank, 'Angelfish.0')
    a.x, a.y, a.z = 0.0, -0.17, 0.26
    self.click_on(a, taken=lambda x, y: True)
    self.assertIsNone(self.steering.control.selected)
    self.click_on(a)
    self.assertIs(self.steering.control.selected, a)

  def test_arrows_steer_unless_another_control_has_them(self):
    a = named(self.tank, 'Angelfish.0')
    self.steering.control.select(a)
    self.steering.frame(FakeInput(down=['left']), PickingTest.WINDOW, DT,
                        keys=False)
    self.assertIsNone(a.steer)
    self.steering.frame(FakeInput(down=['left', 'l']), PickingTest.WINDOW, DT)
    self.assertIsNotNone(a.steer)
    self.assertEqual(self.steering.keys, ['left'])


if __name__ == '__main__':
  unittest.main()
