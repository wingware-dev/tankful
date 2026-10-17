import unittest
from unittest import mock

from tankful.factors import base
from tankful.factors import controller as controller_mod
from tankful.factors import effects
from tankful.factors import moon
from tankful.game import scenery
from tankful.game.factor_hud import AutoSwitch, FactorHud, light_weighted
from tankful.game.input import InputState
from tankful.sim import daynight
from tankful.sim.daynight import Light
from tankful.sim.species import angelfish
from tankful.sim.tank import Tank

from tests.test_factor_hud import WINDOW
from tests.test_lighting import make_lighting
from tests.test_scenery import FakeObject, FakeObjects

DAY = {'sun_elevation': 30.0, 'moon_illumination': 1.0}
NIGHT = {'sun_elevation': -30.0, 'moon_illumination': 1.0}


class AutoSwitchTests(unittest.TestCase):

  def setUp(self):
    self.light = Light()
    self.switch = AutoSwitch(self.light)

  def test_first_wish_sets_the_switch(self):
    self.assertFalse(self.switch.active)
    self.assertTrue(self.switch.update(False))
    self.assertFalse(self.light.on)
    self.assertTrue(self.switch.active)
    self.assertTrue(self.switch.following)

  def test_first_wish_as_the_switch_is_changes_nothing(self):
    self.assertFalse(self.switch.update(True))
    self.assertTrue(self.light.on)
    self.assertEqual(self.light.switches, 0)

  def test_flips_at_dusk_and_dawn(self):
    self.switch.update(True)
    self.assertTrue(self.switch.update(False))
    self.assertFalse(self.light.on)
    self.assertFalse(self.switch.update(False))
    self.assertTrue(self.switch.update(True))
    self.assertTrue(self.light.on)

  def test_viewer_override_holds_until_the_next_change(self):
    self.switch.update(False)
    self.light.toggle()
    self.assertFalse(self.switch.following)
    for _ in range(5):
      self.assertFalse(self.switch.update(False))
    self.assertTrue(self.light.on)
    # Dawn: the factor wants it on, as it already is
    self.assertFalse(self.switch.update(True))
    self.assertTrue(self.switch.following)
    # And at dusk the factor takes it again
    self.assertTrue(self.switch.update(False))
    self.assertFalse(self.light.on)

  def test_no_reading_leaves_it(self):
    self.switch.update(False)
    self.light.toggle()
    self.assertFalse(self.switch.update(None))
    self.assertTrue(self.light.on)
    self.assertFalse(self.switch.update(False))
    self.assertTrue(self.light.on)

  def test_reset_takes_the_next_wish_afresh(self):
    self.switch.update(False)
    self.light.toggle()
    self.switch.reset()
    self.assertFalse(self.switch.active)
    self.assertTrue(self.switch.update(False))
    self.assertFalse(self.light.on)


class LightWeightedTests(unittest.TestCase):

  E = effects.Effects(speed_scale=0.5, light_level=0.2, caustic_sharpness=0.4,
                      tint=(0.6, 0.8, 1.0), night_light=0.9)

  def test_all_is_as_it_is(self):
    self.assertIs(light_weighted(self.E, 1.0), self.E)

  def test_none_is_neutral_light_only(self):
    e = light_weighted(self.E, 0.0)
    self.assertEqual(e.light_level, 1.0)
    self.assertEqual(e.caustic_sharpness, 1.0)
    self.assertEqual(e.tint, (1.0, 1.0, 1.0))
    self.assertEqual(e.speed_scale, 0.5)
    self.assertEqual(e.night_light, 0.9)
    self.assertEqual(light_weighted(self.E, -1.0), e)

  def test_between(self):
    e = light_weighted(self.E, 0.5)
    self.assertAlmostEqual(e.light_level, 0.6)
    self.assertAlmostEqual(e.tint[0], 0.8)


class SettableSource(base.Source):
  """The Time & Moon factor's source, with a reading a test sets."""
  name = 'settable-moon'
  ttl = 60.0

  def __init__(self, value):
    self.value = value

  def fetch(self):
    return base.Reading(dict(self.value), 'moon')


class HudSwitchTests(unittest.TestCase):

  def setUp(self):
    self.tank = Tank()
    angelfish.stock(self.tank)
    self.light = self.tank.light
    self.lighting = make_lighting(self.light)
    self.clock = base.FakeClock()
    self.source = SettableSource(NIGHT)

    def make_source(factor, settings):
      if factor.key == 'moon':
        return self.source
      return base.StaticSource('standin-' + factor.key, {}, '')
    self.controller = controller_mod.FactorController(
      settings={'factor': 'none'},
      thread=base.FetchThread(clock=self.clock), save=False,
      make_source=make_source)
    self.hud = FactorHud(self.tank, self.lighting, self.controller)
    self.input = InputState()

  def frame(self, dt=0.1):
    self.hud.frame(self.input, WINDOW, dt)
    self.input.end_frame()
    self.tank.step(dt)
    self.lighting.update()

  def settle(self, seconds=20.0):
    for _ in range(int(seconds * 10)):
      self.frame()

  def pick(self, key):
    self.hud.menu.handle_input = mock.Mock(side_effect=[key])
    self.frame()
    del self.hud.menu.handle_input
    self.controller.thread.poller.poll()

  def sky(self, value):
    """A new reading, fetched as the clock passes the source's ttl."""
    self.source.value = value
    self.clock.advance(SettableSource.ttl)
    self.controller.thread.poller.poll()

  def test_picking_it_at_night_turns_the_light_off(self):
    self.assertTrue(self.light.on)
    self.pick('moon')
    self.frame()
    self.assertFalse(self.light.on)
    self.settle()
    self.assertEqual(self.light.level, 0.0)
    self.assertEqual(self.hud.light_weight, 0.0)
    # The night look under the full moon, the factor's light effects out
    self.assertEqual(self.lighting.look.lamp, daynight.look(0.0, 1.0).lamp)
    self.assertEqual(self.lighting.look.glint, 1.0)
    self.assertFalse(self.hud.snapshot()['auto_light'])

  def test_dusk_and_dawn_flip_it(self):
    self.source.value = DAY
    self.pick('moon')
    self.settle(2)
    self.assertTrue(self.light.on)
    self.sky(NIGHT)
    self.frame()
    self.assertFalse(self.light.on)
    self.sky(DAY)
    self.frame()
    self.assertTrue(self.light.on)

  def test_the_viewers_switch_holds_till_dawn(self):
    self.pick('moon')
    self.settle()
    self.light.toggle()
    self.sky(NIGHT)
    self.settle()
    self.assertTrue(self.light.on)
    # Lit at night by hand, the tank is the plain day tank
    self.assertEqual(self.hud.light_weight, 0.0)
    self.assertEqual(self.lighting.look.lamp, daynight.DAY_LAMP)
    self.sky(DAY)
    self.frame()
    self.sky(NIGHT)
    self.frame()
    self.assertFalse(self.light.on)

  def test_dusk_light_shows_while_lit(self):
    self.source.value = {'sun_elevation': moon.HORIZON + 0.5,
                         'moon_illumination': 0.5}
    self.pick('moon')
    self.settle()
    self.assertTrue(self.light.on)
    self.assertEqual(self.hud.light_weight, 1.0)
    want = moon.effects_for(base.Reading(self.source.value))
    self.assertAlmostEqual(self.lighting.look.lamp,
                           daynight.DAY_LAMP * want.light_level, delta=0.2)

  def test_another_factor_lets_the_switch_be(self):
    self.pick('moon')
    self.settle(2)
    self.assertFalse(self.light.on)
    self.pick('weather')
    self.settle(2)
    self.assertFalse(self.light.on)
    self.assertFalse(self.hud.switch.active)
    self.assertEqual(self.hud.light_weight, 1.0)
    self.light.toggle()
    self.settle(2)
    self.assertTrue(self.light.on)


def make_glint_scenery():
  patch = FakeObject(scenery.MOON_GLINT)
  patch.visible = True
  pool = mock.Mock(capacity=0, bubbles=[], pop_events=[], rate=18.0)
  with mock.patch.object(scenery.log, 'warning'):
    s = scenery.Scenery(mock.Mock(objects=FakeObjects([patch])), pool)
  return s, patch


class GlintSceneryTests(unittest.TestCase):

  def test_hidden_by_day(self):
    s, patch = make_glint_scenery()
    self.assertFalse(patch.visible)
    s.set_look(daynight.look(1.0, 1.0))
    s.update(1.0, 0.1)
    self.assertFalse(patch.visible)

  def test_shows_at_night_with_clock_and_brightness(self):
    s, patch = make_glint_scenery()
    s.set_look(daynight.look(0.0, 1.0))
    s.update(30.0, 0.1)
    self.assertTrue(patch.visible)
    self.assertEqual(patch.color, (daynight.glint_clock(30.0), 0.0, 0.0, 1.0))
    self.assertEqual(s.snapshot()['glint'], 1.0)
    s.set_look(daynight.look(0.0, 0.0))
    s.update(30.1, 0.1)
    self.assertFalse(patch.visible)

  def test_no_patch_is_warned_and_harmless(self):
    pool = mock.Mock(capacity=0, bubbles=[], pop_events=[], rate=18.0)
    with mock.patch.object(scenery.log, 'warning') as warned:
      s = scenery.Scenery(mock.Mock(objects=FakeObjects([])), pool)
    self.assertTrue(any(scenery.MOON_GLINT in str(c)
                        for c in warned.call_args_list))
    s.set_look(daynight.look(0.0, 1.0))
    s.update(1.0, 0.1)


if __name__ == '__main__':
  unittest.main()
