import json
import os
import tempfile
import unittest
from unittest import mock

from tankful.factors import base
from tankful.factors import controller as controller_mod
from tankful.factors import effects
from tankful.factors import registry
from tankful.factors import settings as settings_mod
from tankful.factors import standins
from tankful.game import factor_hud
from tankful.game.factor_hud import FactorHud, FactorMenu
from tankful.game.input import InputState
from tankful.sim import daynight
from tankful.sim.species import angelfish
from tankful.sim.tank import Tank

from tests.test_lighting import make_lighting

WINDOW = (1280, 720)


def center(rect):
  left, top, right, bottom = rect
  return ((left + right) / 2, (top + bottom) / 2)


class MenuTests(unittest.TestCase):

  def setUp(self):
    self.menu = FactorMenu()
    self.input = InputState()

  def frame(self, current='none'):
    picked = self.menu.handle_input(self.input, WINDOW, current)
    self.input.end_frame()
    return picked

  def press(self, key, current='none'):
    self.input.key_down(key)
    picked = self.frame(current)
    self.input.key_up(key)
    return picked

  def click(self, x, y, button='left'):
    self.input.click(x, y, button)
    return self.frame()

  def test_offers_the_factors_in_order(self):
    self.assertEqual([f.label for f in self.menu.factors],
                     ['None', 'Weather', 'Time & Moon', 'Battery', 'Stock'])

  def test_f_toggles(self):
    self.assertIsNone(self.press('f'))
    self.assertTrue(self.menu.open)
    self.press('F')
    self.assertFalse(self.menu.open)

  def test_gear_click_toggles(self):
    gear = center(self.menu.gear_rect(WINDOW))
    self.click(*gear)
    self.assertTrue(self.menu.open)
    self.click(*gear)
    self.assertFalse(self.menu.open)

  def test_click_on_a_row_picks_and_closes(self):
    self.press('f')
    rows = self.menu.row_rects(WINDOW)
    self.assertEqual(self.click(*center(rows[1])), 'weather')
    self.assertFalse(self.menu.open)

  def test_rows_do_nothing_while_closed(self):
    rows = self.menu.row_rects(WINDOW)
    self.assertIsNone(self.click(*center(rows[1])))
    self.assertIsNone(self.press('2'))

  def test_click_on_the_title_keeps_it_open(self):
    self.press('f')
    left, top, right, _ = self.menu.panel_rect(WINDOW)
    self.assertIsNone(self.click(left + 5, top + 5))
    self.assertTrue(self.menu.open)

  def test_click_elsewhere_closes(self):
    self.press('f')
    self.assertIsNone(self.click(640, 360))
    self.assertFalse(self.menu.open)

  def test_right_click_does_nothing(self):
    self.press('f')
    rows = self.menu.row_rects(WINDOW)
    self.assertIsNone(self.click(*center(rows[1]), button='right'))
    self.assertTrue(self.menu.open)

  def test_number_keys_pick(self):
    self.press('f')
    self.assertEqual(self.press('5'), 'stock')
    self.assertFalse(self.menu.open)
    # As bge names them
    self.press('f')
    self.assertEqual(self.press('THREEKEY'), 'moon')

  def test_arrows_and_enter_from_the_current(self):
    self.press('f')
    self.press('down', current='weather')
    self.assertEqual(self.menu.cursor, 2)
    self.press('up')
    self.press('up')
    self.assertEqual(self.press('enter'), 'none')
    # Up from the first row wraps to the last
    self.press('f')
    self.press('up', current='none')
    self.assertEqual(self.press('enter'), 'stock')

  def test_enter_without_arrows_does_nothing(self):
    self.press('f')
    self.assertIsNone(self.press('enter'))
    self.assertTrue(self.menu.open)

  def test_hit(self):
    gear = center(self.menu.gear_rect(WINDOW))
    row = center(self.menu.row_rects(WINDOW)[0])
    self.assertTrue(self.menu.hit(WINDOW, *gear))
    self.assertFalse(self.menu.hit(WINDOW, *row))
    self.press('f')
    self.assertTrue(self.menu.hit(WINDOW, *row))
    self.assertFalse(self.menu.hit(WINDOW, 640, 360))

  def test_layout_scales_with_the_window(self):
    small = self.menu.panel_rect((640, 360))
    big = self.menu.panel_rect(WINDOW)
    for a, b in zip(small, big):
      self.assertAlmostEqual(a * 2, b)
    rows = self.menu.row_rects(WINDOW)
    self.assertEqual(len(rows), 5)
    self.assertEqual(rows[-1][3], big[3])
    self.assertGreater(rows[0][1], big[1])
    # The label sits right of the gear, level with it
    x, y = self.menu.label_pos(WINDOW)
    gear = self.menu.gear_rect(WINDOW)
    self.assertGreater(x, gear[2])
    self.assertEqual(y, center(gear)[1])
    # The credit sits at the bottom left, below the open menu
    x, y = self.menu.credit_pos(WINDOW)
    self.assertEqual(x, gear[0])
    self.assertGreater(y, big[3])
    self.assertLess(y, WINDOW[1])


class AdjustLookTests(unittest.TestCase):

  def test_neutral_changes_nothing(self):
    look = daynight.look(1.0)
    self.assertEqual(factor_hud.adjust_look(look, effects.NEUTRAL), look)

  def test_scales_lamp_color_and_caustics(self):
    look = daynight.look(1.0)
    e = effects.Effects(light_level=0.5, caustic_sharpness=0.4,
                        tint=(0.5, 1.0, 1.0))
    out = factor_hud.adjust_look(look, e)
    self.assertAlmostEqual(out.lamp, look.lamp * 0.5)
    self.assertAlmostEqual(out.lamp_color[0], look.lamp_color[0] * 0.5)
    self.assertEqual(out.lamp_color[1:], look.lamp_color[1:])
    self.assertAlmostEqual(out.caustics, look.caustics * 0.2)
    # The room, which costs a frame stall to write, is left alone
    self.assertEqual(out.room, look.room)

  def test_caustics_are_capped(self):
    look = daynight.look(1.0)
    e = effects.Effects(light_level=1.5, caustic_sharpness=2.0)
    out = factor_hud.adjust_look(look, e)
    self.assertAlmostEqual(out.caustics, look.caustics * factor_hud.MAX_CAUSTICS)


class QuantizeTests(unittest.TestCase):

  def test_steps(self):
    e = effects.Effects(speed_scale=0.98731, light_level=0.5912,
                        tint=(0.9031, 1.0, 0.4449))
    q = factor_hud.quantize(e)
    self.assertEqual(q.speed_scale, 0.985)
    self.assertEqual(q.light_level, 0.59)
    self.assertEqual(q.tint, (0.905, 1.0, 0.445))
    self.assertEqual(factor_hud.quantize(effects.NEUTRAL), effects.NEUTRAL)


class MoonFollowerTests(unittest.TestCase):

  def test_follows_night_light_and_returns_to_default(self):
    moon = factor_hud.MoonFollower()
    self.assertEqual(moon.update(0.0, 1.0), daynight.MOON_DEFAULT)
    for _ in range(600):
      value = moon.update(0.9, 1 / 60)
    self.assertAlmostEqual(value, 0.9, delta=factor_hud.EFFECT_STEP)
    for _ in range(600):
      value = moon.update(0.0, 1 / 60)
    self.assertEqual(value, daynight.MOON_DEFAULT)

  def test_eases(self):
    moon = factor_hud.MoonFollower()
    value = moon.update(1.0, 0.1)
    self.assertGreater(value, daynight.MOON_DEFAULT)
    self.assertLess(value, 0.6)


class GearTests(unittest.TestCase):

  def test_ring_inside_radius(self):
    tris = factor_hud.gear_triangles(100, 50, 15)
    self.assertEqual(len(tris), 2 * 8 * 6)
    for tri in tris:
      self.assertEqual(len(tri), 3)
      for x, y in tri:
        r = ((x - 100) ** 2 + (y - 50) ** 2) ** 0.5
        self.assertGreaterEqual(r, 15 * 0.42 - 1e-9)
        self.assertLessEqual(r, 15 + 1e-9)


def make_controller(make_source=standins.make_source, factor='none'):
  thread = base.FetchThread()
  return controller_mod.FactorController(
    settings={'factor': factor}, thread=thread, save=False,
    make_source=make_source)


class HudTests(unittest.TestCase):

  def setUp(self):
    self.tank = Tank()
    angelfish.stock(self.tank)
    self.lighting = make_lighting(self.tank.light)
    self.controller = make_controller()
    self.scene = mock.Mock(post_draw=[])
    self.hud = FactorHud(self.tank, self.lighting, self.controller,
                         scene=self.scene, window=lambda: WINDOW)
    self.input = InputState()

  def frame(self, dt=1 / 60):
    self.hud.frame(self.input, WINDOW, dt)
    self.input.end_frame()
    self.tank.step(dt)
    self.lighting.update()

  def poll(self):
    self.controller.thread.poller.poll()

  def pick(self, number):
    self.input.key_down('f')
    self.frame()
    self.input.key_up('f')
    self.input.key_down(str(number))
    self.frame()
    self.input.key_up(str(number))
    self.poll()

  def settle(self, seconds=20.0):
    for _ in range(int(seconds * 10)):
      self.frame(0.1)

  def test_draws_through_post_draw(self):
    self.assertEqual(self.scene.post_draw, [self.hud.draw])

  def test_none_leaves_the_tank_alone(self):
    look = self.lighting.look
    self.settle(2)
    self.assertEqual(self.hud.label, '')
    self.assertEqual(self.lighting.look, look)
    self.assertEqual(self.tank.speed_scale, 1.0)
    self.assertEqual(self.tank.light.moon, daynight.MOON_DEFAULT)

  def test_weather_reaches_the_tank_and_the_lights(self):
    self.pick(2)
    self.assertEqual(self.controller.key, 'weather')
    self.settle()
    self.assertEqual(self.hud.label, 'Weather: 14°C, rain')
    self.assertFalse(self.hud.offline)
    want = registry.get('weather').effects_for(
      base.Reading(*standins.READINGS['weather']))
    self.assertAlmostEqual(self.tank.speed_scale, want.speed_scale, delta=0.01)
    self.assertAlmostEqual(self.tank.depth_shift, want.depth_shift, delta=0.01)
    day = daynight.look(1.0)
    self.assertAlmostEqual(self.lighting.look.lamp,
                           day.lamp * want.light_level, delta=0.2)
    self.assertLess(self.lighting.look.caustics, 0.5)
    # Applied through the lamp, and the scenery's caustics follow
    self.assertEqual(self.lighting.lamp.blenderObject.data.energy,
                     self.lighting.look.lamp)
    snap = self.hud.snapshot()
    self.assertEqual(snap['factor'], 'weather')
    json.dumps(snap)

  def test_credit_shows_only_while_weather_is_picked(self):
    self.frame()
    self.assertEqual(self.hud.credit, '')
    self.pick(2)
    self.assertEqual(self.hud.credit, 'Weather data by Open-Meteo.com')
    self.assertEqual(self.hud.snapshot()['credit'], self.hud.credit)
    for number in (1, 3, 4, 5):
      self.pick(number)
      self.assertEqual(self.hud.credit, '', number)

  def test_eased_effects_settle(self):
    self.pick(2)
    self.settle()
    applied = self.lighting._applied
    for _ in range(20):
      self.frame(0.1)
    self.assertIs(self.lighting._applied, applied)

  def test_moon_sets_the_moon_and_back(self):
    self.pick(3)
    self.settle()
    illumination = standins.READINGS['moon'][0]['moon_illumination']
    from tankful.factors import moon
    self.assertAlmostEqual(self.tank.light.moon, moon.night_light(illumination),
                           delta=0.01)
    self.pick(1)
    self.settle()
    self.assertEqual(self.tank.light.moon, daynight.MOON_DEFAULT)
    self.assertEqual(self.tank.speed_scale, 1.0)
    self.assertEqual(self.tank.depth_shift, 0.0)

  def test_offline_source(self):
    self.controller = make_controller(standins.make_source_offline)
    self.hud = FactorHud(self.tank, self.lighting, self.controller)
    self.pick(5)
    self.frame()
    self.assertEqual(self.hud.label, 'Stock: offline')
    self.assertTrue(self.hud.offline)
    self.assertEqual(self.hud.effects, effects.NEUTRAL)

  def test_draw_without_bge_is_logged_once(self):
    with mock.patch.object(factor_hud.log, 'exception') as logged:
      self.hud.draw()
      self.hud.draw()
    self.assertEqual(logged.call_count, 1)

  def test_stop(self):
    self.controller.thread.start()
    self.assertTrue(self.hud.stop())


class SettingsPersistTests(unittest.TestCase):

  def test_choice_is_saved_and_restored(self):
    with tempfile.TemporaryDirectory() as tmp:
      with mock.patch.dict(os.environ, {'TANKFUL_CONFIG_DIR': tmp}):
        first = controller_mod.FactorController(
          thread=base.FetchThread(), make_source=standins.make_source)
        tank = Tank()
        hud = FactorHud(tank, make_lighting(tank.light), first)
        state = InputState()
        state.key_down('f')
        hud.frame(state, WINDOW, 0.0)
        state.end_frame()
        state.key_down('4')
        hud.frame(state, WINDOW, 0.0)
        self.assertEqual(settings_mod.load()['factor'], 'battery')
        again = controller_mod.FactorController(thread=base.FetchThread(),
                                                make_source=standins.make_source)
        self.assertEqual(again.key, 'battery')


if __name__ == '__main__':
  unittest.main()
