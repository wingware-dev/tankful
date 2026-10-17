import unittest
from unittest import mock

from tankful.factors import base
from tankful.factors import effects
from tankful.factors import registry
from tankful.factors import standins
from tankful.game import factor_hud
from tankful.game import scenery
from tankful.game.factor_hud import FactorHud
from tankful.game.input import InputState
from tankful.sim import daynight
from tankful.sim import weather
from tankful.sim.species import angelfish
from tankful.sim.species import guppy
from tankful.sim.species import neon_tetra
from tankful.sim.species import pleco
from tankful.sim.tank import Tank, factor_species

from tests.test_factor_hud import WINDOW, make_controller
from tests.test_lighting import make_lighting
from tests.test_scenery import FakeObject, FakeObjects


class LightningTests(unittest.TestCase):

  def run_for(self, lightning, seconds, flicker, dt=1 / 60):
    strikes = 0
    for _ in range(int(seconds / dt)):
      strikes += lightning.step(dt, flicker)
    return strikes

  def test_no_flicker_no_strikes(self):
    lightning = weather.Lightning()
    self.assertEqual(self.run_for(lightning, 600, 0.0), 0)
    self.assertEqual(lightning.level, 0.0)

  def test_strikes_as_often_as_flicker_says(self):
    full = self.run_for(weather.Lightning(), 600, 1.0)
    # About STRIKE_RATE a second, less the gaps after each
    self.assertGreater(full, 600 * weather.STRIKE_RATE * 0.5)
    self.assertLess(full, 600 * weather.STRIKE_RATE * 1.5)
    light = self.run_for(weather.Lightning(), 600, 0.25)
    self.assertLess(light, full * 0.5)
    self.assertGreater(light, 0)

  def test_strikes_keep_their_gap(self):
    lightning = weather.Lightning()
    dt = 1 / 60
    last = None
    for i in range(int(600 / dt)):
      if lightning.step(dt, 1.0):
        if last is not None:
          self.assertGreaterEqual((i - last) * dt,
                                  weather.STRIKE_GAP - 1e-9)
        last = i

  def test_a_strike_flashes_then_goes_dark(self):
    lightning = weather.Lightning()
    dt = 1 / 60
    while not lightning.step(dt, 1.0):
      pass
    levels = [lightning.level]
    for _ in range(60):
      lightning.step(dt, 0.0)
      levels.append(lightning.level)
    self.assertGreater(max(levels), 0.9)
    self.assertTrue(all(0.0 <= v <= 1.0 for v in levels))
    self.assertEqual(levels[-1], 0.0)
    # More than one flash: dark between them
    lit = [v > 0.05 for v in levels]
    self.assertGreaterEqual(sum(1 for a, b in zip(lit, lit[1:])
                                if b and not a), 2)

  def test_seeded(self):
    a, b = weather.Lightning(), weather.Lightning()
    for _ in range(3000):
      self.assertEqual(a.step(1 / 60, 1.0), b.step(1 / 60, 1.0))

  def test_rain_clock_wraps(self):
    self.assertEqual(weather.rain_clock(12.5), 12.5)
    self.assertAlmostEqual(weather.rain_clock(weather.RAIN_WRAP + 3.0), 3.0)


class SkittishSpeciesTests(unittest.TestCase):

  def test_skittish_fish_flick_wander_and_turn_more(self):
    s = guppy.SPECIES
    f = factor_species(s, 1.0, 0.0, 1.0)
    self.assertAlmostEqual(f.flick_chance, s.flick_chance * 7.0)
    self.assertGreater(f.wander_turn, s.wander_turn)
    self.assertGreater(f.max_turn_rate, s.max_turn_rate)
    self.assertGreater(f.turn_accel, s.turn_accel)
    self.assertLess(f.hover_chance, s.hover_chance)
    self.assertEqual(f.cruise_speed, s.cruise_speed)

  def test_calm_is_unchanged(self):
    s = guppy.SPECIES
    self.assertEqual(factor_species(s, 1.0, 0.0, 0.0), s)


def stocked():
  tank = Tank()
  angelfish.stock(tank)
  neon_tetra.stock(tank)
  guppy.stock(tank)
  pleco.stock(tank)
  return tank


class StartleTests(unittest.TestCase):

  def test_startle_flicks_and_darts_but_leaves_some_be(self):
    tank = stocked()
    tank.step(1 / 60)
    angel = tank.fish[0]
    steered = [f for f in tank.fish if f.species.name == 'guppy'][0]
    steered.steer = object()
    plec = [f for f in tank.fish if f.species.name == 'pleco'][0]
    plec_speed = plec.speed
    n = tank.startle(1.0)
    self.assertGreater(n, 0)
    self.assertAlmostEqual(angel.speed, angel.max_speed * 0.9)
    flickers = [f for f in tank.fish if hasattr(f, 'flick_left')
                and f is not steered]
    self.assertTrue(flickers)
    for f in flickers:
      self.assertGreater(f.flick_left, 0, f.name)
      self.assertNotEqual(f.flick_turn, 0, f.name)
    self.assertEqual(steered.flick_left, 0.0)
    self.assertEqual(plec.speed, plec_speed)
    self.assertEqual(tank.startles, 1)

  def test_chance_zero_startles_none(self):
    tank = stocked()
    self.assertEqual(tank.startle(0.0), 0)

  def test_storm_strikes_startle_skittish_fish(self):
    tank = stocked()
    tank.set_factor(skittish=0.8, flicker=1.0)
    for _ in range(60 * 40):
      tank.step(1 / 60)
    self.assertGreater(tank.lightning.strikes, 0)
    self.assertEqual(tank.startles, tank.lightning.strikes)
    snap = tank.snapshot()
    self.assertEqual(snap['factor']['skittish'], 0.8)
    self.assertEqual(snap['lightning']['strikes'], tank.lightning.strikes)

  def test_lightning_without_skittish_startles_none(self):
    tank = stocked()
    tank.set_factor(flicker=1.0)
    for _ in range(60 * 40):
      tank.step(1 / 60)
    self.assertGreater(tank.lightning.strikes, 0)
    self.assertEqual(tank.startles, 0)

  def test_skittish_alone_swaps_species_and_back(self):
    tank = stocked()
    own = tank.fish[0].species
    tank.set_factor(skittish=0.5)
    tank.step(1 / 60)
    self.assertIsNot(tank.fish[0].species, own)
    self.assertGreater(tank.fish[0].species.wander_turn, own.wander_turn)
    tank.set_factor()
    tank.step(1 / 60)
    self.assertIs(tank.fish[0].species, own)


class FlashLookTests(unittest.TestCase):

  def test_flash_brightens_and_cools(self):
    look = daynight.look(1.0)
    calm = factor_hud.adjust_look(look, effects.NEUTRAL, 0.0)
    flash = factor_hud.adjust_look(look, effects.NEUTRAL, 1.0)
    self.assertEqual(calm, look)
    self.assertAlmostEqual(flash.lamp, look.lamp * (1 + factor_hud.FLASH_LAMP))
    self.assertEqual(flash.lamp_color, factor_hud.FLASH_COLOR)
    self.assertGreater(flash.caustics, look.caustics)
    self.assertGreater(flash.panel[0], look.panel[0])
    self.assertEqual(flash.room, look.room)

  def test_tint_colors_panel_and_sheen(self):
    look = daynight.look(1.0)
    e = effects.Effects(tint=(0.8, 0.9, 1.0))
    out = factor_hud.adjust_look(look, e)
    self.assertAlmostEqual(out.panel[0], look.panel[0] * 0.8)
    self.assertAlmostEqual(out.sheen[1], look.sheen[1] * 0.9)
    self.assertEqual(out.panel[2], look.panel[2])


def make_rain_scenery():
  sheet = FakeObject(scenery.RAIN)
  sheet.visible = True
  pool = mock.Mock(capacity=0, bubbles=[], pop_events=[], rate=18.0)
  with mock.patch.object(scenery.log, 'warning'):
    s = scenery.Scenery(mock.Mock(objects=FakeObjects([sheet])), pool)
  return s, sheet


class RainSceneryTests(unittest.TestCase):

  def test_hidden_until_it_rains(self):
    s, sheet = make_rain_scenery()
    self.assertFalse(sheet.visible)
    s.update(1.0, 0.1)
    self.assertFalse(sheet.visible)

  def test_rain_shows_clock_strength_and_glow(self):
    s, sheet = make_rain_scenery()
    s.set_rain(0.6)
    s.update(12.5, 0.1)
    self.assertTrue(sheet.visible)
    self.assertEqual(sheet.color, (12.5, 0.6, 0.0, 1.0))
    s.set_look(daynight.look(0.0))
    s.update(weather.RAIN_WRAP + 1.0, 0.1)
    r, g, b, a = sheet.color
    self.assertAlmostEqual(r, 1.0)
    self.assertLess(a, 0.5)
    self.assertEqual(s.snapshot()['rain'], 0.6)

  def test_drizzle_below_min_and_dry_hide_it(self):
    s, sheet = make_rain_scenery()
    s.set_rain(0.6)
    s.update(1.0, 0.1)
    s.set_rain(weather.RAIN_MIN / 2)
    s.update(1.1, 0.1)
    self.assertFalse(sheet.visible)
    s.set_rain(-1.0)
    self.assertEqual(s.rain, 0.0)
    s.set_rain(3.0)
    self.assertEqual(s.rain, 1.0)

  def test_no_sheet_is_warned_and_harmless(self):
    pool = mock.Mock(capacity=0, bubbles=[], pop_events=[])
    with mock.patch.object(scenery.log, 'warning') as warned:
      s = scenery.Scenery(mock.Mock(objects=FakeObjects([])), pool)
    self.assertTrue(any(scenery.RAIN in str(c) for c in warned.call_args_list))
    s.set_rain(1.0)
    s.update(1.0, 0.1)


class WeatherSkyTests(unittest.TestCase):

  def effects(self, sky):
    env = {} if sky is None else {standins.WEATHER_ENV: sky}
    value, label = standins.reading('weather', env)
    return registry.get('weather').effects_for(base.Reading(value, label))

  def test_rain_by_default(self):
    self.assertEqual(standins.reading('weather', {}),
                     standins.READINGS['weather'])
    self.assertGreater(self.effects(None).surface_agitation, 0.5)

  def test_storm_flickers_and_is_skittish(self):
    e = self.effects('Storm')
    self.assertGreater(e.flicker, 0.5)
    self.assertGreater(e.skittish, 0.5)
    self.assertGreater(e.surface_agitation, 0.8)

  def test_snow_is_cool(self):
    r, g, b = self.effects('snow').tint
    self.assertLess(r, b)

  def test_clear_and_cloudy_are_dry(self):
    for sky in ('clear', 'cloudy'):
      self.assertLess(self.effects(sky).surface_agitation, 0.2, sky)

  def test_bad_sky_fails_at_start(self):
    with self.assertRaises(ValueError):
      standins.for_env({standins.ENV: '1', standins.WEATHER_ENV: 'hail'})
    self.assertIsNone(standins.for_env({standins.WEATHER_ENV: 'hail'}))


class HudWeatherTests(unittest.TestCase):

  def make(self, sky):
    self.tank = stocked()
    self.lighting = make_lighting(self.tank.light)
    self.scenery = mock.Mock()
    with mock.patch.dict('os.environ', {standins.WEATHER_ENV: sky}):
      self.controller = make_controller()
      self.hud = FactorHud(self.tank, self.lighting, self.controller,
                           scenery=self.scenery)
      self.input = InputState()
      self.input.key_down('f')
      self.frame()
      self.input.key_up('f')
      self.input.key_down('2')
      self.frame()
      self.input.key_up('2')
      self.controller.thread.poller.poll()

  def frame(self, dt=1 / 60):
    self.hud.frame(self.input, WINDOW, dt)
    self.input.end_frame()
    self.tank.step(dt)
    self.lighting.update()

  def test_storm_reaches_tank_scenery_and_lamp(self):
    self.make('storm')
    lamps = set()
    for _ in range(60 * 30):
      self.frame()
      lamps.add(round(self.lighting.look.lamp, 1))
    self.assertGreater(self.tank.skittish, 0.5)
    self.assertGreater(self.tank.flicker, 0.5)
    self.assertGreater(self.tank.lightning.strikes, 0)
    rain = self.scenery.set_rain.call_args[0][0]
    self.assertGreater(rain, 0.8)
    # The flashes brightened the lamp past the storm's dim light
    self.assertGreater(max(lamps), daynight.DAY_LAMP)

  def test_rain_without_lightning(self):
    self.make('rain')
    for _ in range(60 * 10):
      self.frame()
    self.assertGreater(self.scenery.set_rain.call_args[0][0], 0.5)
    self.assertEqual(self.tank.lightning.strikes, 0)


if __name__ == '__main__':
  unittest.main()
