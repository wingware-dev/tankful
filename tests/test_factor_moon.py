import datetime
import io
import json
import unittest

from tankful.factors import astro
from tankful.factors import base
from tankful.factors import effects
from tankful.factors import moon
from tankful.factors import registry
from tankful.factors.base import FakeClock


def utc(*args):
  """Unix time for a UTC date and time."""
  return datetime.datetime(*args, tzinfo=datetime.timezone.utc).timestamp()


def hhmm(t):
  return datetime.datetime.fromtimestamp(
    t, datetime.timezone.utc).strftime('%H:%M')


# 2026's new and full moons (UTC, from the published lunar phase tables)
NEW_MOONS_2026 = [
  (1, 18, 19, 52), (2, 17, 12, 1), (3, 19, 1, 23), (4, 17, 11, 52),
  (5, 16, 20, 1), (6, 15, 2, 54), (7, 14, 9, 43), (8, 12, 17, 37),
  (9, 11, 3, 27), (10, 10, 15, 50), (11, 9, 7, 2), (12, 9, 0, 52),
]
FULL_MOONS_2026 = [
  (1, 3, 10, 3), (2, 1, 22, 9), (3, 3, 11, 38), (4, 2, 2, 12),
  (5, 1, 17, 23), (5, 31, 8, 45), (6, 29, 23, 57), (7, 29, 14, 36),
  (8, 28, 4, 18), (9, 26, 16, 49), (10, 26, 4, 12), (11, 24, 14, 53),
  (12, 24, 1, 28),
]

BOSTON = (42.36, -71.06)
LONDON = (51.48, 0.0)
SVALBARD = (78.2, 15.6)


def angle_off(elongation, target):
  return abs((elongation - target + 180.0) % 360.0 - 180.0)


class MoonPhaseTests(unittest.TestCase):

  def test_new_moons_2026(self):
    for month, day, hour, minute in NEW_MOONS_2026:
      t = utc(2026, month, day, hour, minute)
      with self.subTest(month=month, day=day):
        # Half a degree of elongation is about an hour
        self.assertLess(angle_off(astro.moon_elongation(t), 0.0), 0.5)
        self.assertLess(astro.moon_illumination(t), 0.001)
        self.assertEqual(astro.phase_name(astro.moon_phase(t)), 'new moon')

  def test_full_moons_2026(self):
    for month, day, hour, minute in FULL_MOONS_2026:
      t = utc(2026, month, day, hour, minute)
      with self.subTest(month=month, day=day):
        self.assertLess(angle_off(astro.moon_elongation(t), 180.0), 0.5)
        self.assertGreater(astro.moon_illumination(t), 0.999)
        self.assertAlmostEqual(astro.moon_phase(t), 0.5, delta=0.002)
        self.assertEqual(astro.phase_name(astro.moon_phase(t)), 'full moon')

  def test_quarters(self):
    # First quarter 2026-01-26 04:47, last quarter 2026-01-10 15:48 UTC
    first = utc(2026, 1, 26, 4, 47)
    last = utc(2026, 1, 10, 15, 48)
    self.assertAlmostEqual(astro.moon_illumination(first), 0.5, delta=0.01)
    self.assertAlmostEqual(astro.moon_illumination(last), 0.5, delta=0.01)
    self.assertEqual(astro.phase_name(astro.moon_phase(first)),
                     'first quarter')
    self.assertEqual(astro.phase_name(astro.moon_phase(last)),
                     'last quarter')

  def test_age_grows_through_the_month(self):
    start = utc(2026, 1, 18, 20, 0)
    ages = [astro.moon_age(start + d * astro.DAY) for d in range(29)]
    self.assertLess(ages[0], 0.2)
    self.assertEqual(ages, sorted(ages))
    # 28 days on is 2026-02-15, a day and a half before the next new moon
    self.assertAlmostEqual(ages[-1], 27.9, delta=0.1)

  def test_waxing_and_waning(self):
    self.assertEqual(astro.phase_name(0.12), 'waxing crescent')
    self.assertEqual(astro.phase_name(0.38), 'waxing gibbous')
    self.assertEqual(astro.phase_name(0.62), 'waning gibbous')
    self.assertEqual(astro.phase_name(0.88), 'waning crescent')
    self.assertEqual(astro.phase_name(0.97), 'new moon')


class SunTests(unittest.TestCase):

  def test_boston_midsummer(self):
    # Published: sunrise 5:07 and sunset 8:25 pm EDT
    rise, set_ = astro.sun_times(utc(2026, 6, 21, 16), *BOSTON)
    self.assertEqual(hhmm(rise), '09:07')
    self.assertIn(hhmm(set_), ('00:24', '00:25'))

  def test_london_midwinter(self):
    # Published: sunrise 8:04 and sunset 3:53 pm GMT
    rise, set_ = astro.sun_times(utc(2026, 12, 21, 12), *LONDON)
    self.assertIn(hhmm(rise), ('08:03', '08:04'))
    self.assertEqual(hhmm(set_), '15:53')

  def test_elevation_is_on_horizon_at_sunrise(self):
    rise, set_ = astro.sun_times(utc(2026, 3, 20, 12), *LONDON)
    for t in (rise, set_):
      self.assertAlmostEqual(astro.sun_elevation(t, *LONDON), astro.HORIZON,
                             delta=0.05)

  def test_polar_day_and_night(self):
    self.assertEqual(astro.sun_times(utc(2026, 6, 21, 12), *SVALBARD),
                     (None, None))
    self.assertEqual(astro.sun_times(utc(2026, 12, 21, 12), *SVALBARD),
                     (None, None))
    self.assertGreater(astro.sun_elevation(utc(2026, 6, 21, 0), *SVALBARD), 0)
    self.assertLess(astro.sun_elevation(utc(2026, 12, 21, 12), *SVALBARD), 0)

  def test_solar_noon_is_highest(self):
    noon = astro.solar_noon(utc(2026, 6, 21, 17), *BOSTON[1:])
    high = astro.sun_elevation(noon, *BOSTON)
    for offset in (-600, 600):
      self.assertLess(astro.sun_elevation(noon + offset, *BOSTON), high)
    self.assertAlmostEqual(high, 90 - 42.36 + 23.44, delta=0.05)


class ReadingTests(unittest.TestCase):

  def test_full_moon_night(self):
    # 2026-10-26 04:12 UTC: full moon, past midnight in Boston
    r = moon.reading_at(utc(2026, 10, 26, 4, 12), *BOSTON)
    self.assertEqual(r.value['phase'], 'night')
    self.assertEqual(r.label, 'Night, full moon 100%')
    e = moon.effects_for(r)
    self.assertAlmostEqual(e.night_light, 1.0, places=3)
    self.assertLess(e.light_level, 0.5)

  def test_new_moon_night_is_dark(self):
    r = moon.reading_at(utc(2026, 10, 10, 5, 0), *BOSTON)
    self.assertEqual(r.value['phase'], 'night')
    self.assertEqual(r.label, 'Night, new moon 0%')
    self.assertAlmostEqual(moon.effects_for(r).night_light,
                           moon.NIGHT_LIGHT_NEW, places=2)

  def test_day_is_neutral(self):
    r = moon.reading_at(utc(2026, 10, 16, 17, 0), *BOSTON)
    self.assertEqual(r.value['phase'], 'day')
    self.assertTrue(r.label.startswith('Day, '))
    self.assertEqual(moon.effects_for(r), effects.NEUTRAL)

  def test_dusk_and_dawn(self):
    rise, set_ = astro.sun_times(utc(2026, 10, 16, 17), *BOSTON)
    evening = moon.reading_at(set_, *BOSTON)
    morning = moon.reading_at(rise, *BOSTON)
    self.assertEqual(evening.value['phase'], 'dusk')
    self.assertEqual(morning.value['phase'], 'dusk')
    self.assertTrue(evening.label.startswith('Dusk, '))
    self.assertTrue(morning.label.startswith('Dawn, '))
    # At sunset the tank is at full dusk: warm and dimmer
    dusk = moon.effects_for(evening)
    for name in effects.RANGES:
      self.assertAlmostEqual(getattr(dusk, name), getattr(moon.DUSK, name),
                             places=4)
    for got, want in zip(dusk.tint, moon.DUSK.tint):
      self.assertAlmostEqual(got, want, places=4)

  def test_values(self):
    t = utc(2026, 10, 16, 20, 0)
    value = moon.reading_at(t, *BOSTON, how='ip').value
    rise, set_ = astro.sun_times(t, *BOSTON)
    self.assertEqual(value['sunrise'], rise)
    self.assertEqual(value['sunset'], set_)
    self.assertEqual((value['lat'], value['lon']), BOSTON)
    self.assertEqual(value['located_by'], 'ip')
    self.assertAlmostEqual(value['moon_age'],
                           value['moon_phase'] * astro.SYNODIC_MONTH)


def reading(elevation, illumination=0.5):
  return base.Reading({'sun_elevation': elevation,
                       'moon_illumination': illumination})


class EffectsTests(unittest.TestCase):

  def test_phases(self):
    self.assertEqual(moon.effects_for(reading(30)), moon.DAY)
    self.assertEqual(moon.effects_for(reading(moon.DAY_START)), moon.DAY)
    self.assertEqual(moon.effects_for(reading(moon.HORIZON)), moon.DUSK)
    night = moon.effects_for(reading(-20, 1.0))
    self.assertEqual(night, moon.NIGHT.replace(night_light=1.0))

  def test_fades_as_the_sun_sets(self):
    # Strictly dimmer at each degree from the start of dusk to full night
    levels = [moon.effects_for(reading(e)).light_level for e in range(6, -7, -1)]
    for brighter, dimmer in zip(levels, levels[1:]):
      self.assertGreater(brighter, dimmer)

  def test_continuous_at_the_boundaries(self):
    for edge in (moon.DAY_START, moon.HORIZON, moon.NIGHT_START):
      above = moon.effects_for(reading(edge + 1e-9))
      below = moon.effects_for(reading(edge - 1e-9))
      for name in effects.RANGES:
        self.assertAlmostEqual(getattr(above, name), getattr(below, name),
                               places=6)

  def test_moon_sets_night_light(self):
    lights = [moon.effects_for(reading(-30, i / 10)).night_light
              for i in range(11)]
    self.assertEqual(lights, sorted(lights))
    self.assertAlmostEqual(lights[0], moon.NIGHT_LIGHT_NEW)
    self.assertAlmostEqual(lights[-1], moon.NIGHT_LIGHT_FULL)
    self.assertEqual(moon.effects_for(reading(30, 1.0)).night_light, 0.0)

  def test_within_ranges(self):
    for e in range(-90, 91, 3):
      result = moon.effects_for(reading(e, 1.0))
      self.assertEqual(result, result.clamped())

  def test_through_the_registry(self):
    factor = registry.get('moon')
    self.assertTrue(factor.available)
    r = moon.reading_at(utc(2026, 10, 26, 4, 12), *BOSTON)
    self.assertEqual(factor.effects_for(r), moon.effects_for(r))


class FakeResponse(io.BytesIO):

  def __enter__(self):
    return self

  def __exit__(self, *exc):
    self.close()


class LocationTests(unittest.TestCase):

  def test_settings_location(self):
    source = moon.make_source({'moon': {'lat': 47.6, 'lon': -122.3}})
    self.assertEqual(source.location, (47.6, -122.3))
    self.assertFalse(source.locate)

  def test_falls_back_to_weather_location(self):
    source = moon.make_source({'weather': {'lat': '51.5', 'lon': 0}})
    self.assertEqual(source.location, (51.5, 0.0))

  def test_bad_location_ignored(self):
    with self.assertLogs('tankful.factors', 'WARNING'):
      source = moon.make_source({'moon': {'lat': 123, 'lon': 4}})
    self.assertIsNone(source.location)
    with self.assertLogs('tankful.factors', 'WARNING'):
      source = moon.make_source({'moon': {'lat': 'north', 'lon': 4}})
    self.assertIsNone(source.location)

  def test_guess_from_time_zone(self):
    self.assertEqual(moon.guess_location(-5 * 3600), (moon.DEFAULT_LAT, -75.0))
    self.assertEqual(moon.guess_location(9 * 3600), (moon.DEFAULT_LAT, 135.0))
    self.assertEqual(moon.guess_location(14 * 3600)[1], 180.0)
    source = moon.MoonSource(utc_offset=3600, clock=lambda: 0.0,
                             lookup=self.fail)
    self.assertEqual(source.where(0.0), (moon.DEFAULT_LAT, 15.0, 'timezone'))

  def test_ip_lookup(self):
    calls = []

    def urlopen(url, timeout):
      calls.append((url, timeout))
      return FakeResponse(json.dumps(
        {'status': 'success', 'lat': 42.36, 'lon': -71.06}).encode())
    self.assertEqual(moon.ip_location(urlopen), BOSTON)
    self.assertEqual(calls, [(moon.IP_LOOKUP_URL, 5.0)])

  def test_ip_lookup_failure_raises(self):
    def urlopen(url, timeout):
      return FakeResponse(b'{"status": "fail"}')
    with self.assertRaises(ValueError):
      moon.ip_location(urlopen)

  def test_locate_looks_up_once(self):
    lookups = []

    def lookup():
      lookups.append(1)
      return BOSTON
    source = moon.MoonSource(locate=True, lookup=lookup, utc_offset=0)
    self.assertEqual(source.where(0.0), BOSTON + ('ip',))
    self.assertEqual(source.where(100.0), BOSTON + ('ip',))
    self.assertEqual(len(lookups), 1)

  def test_failed_lookup_guesses_then_retries(self):
    results = [OSError('offline'), BOSTON]

    def lookup():
      result = results.pop(0)
      if isinstance(result, Exception):
        raise result
      return result
    source = moon.MoonSource(locate=True, lookup=lookup, utc_offset=0)
    with self.assertLogs('tankful.factors', 'WARNING'):
      self.assertEqual(source.where(0.0), (moon.DEFAULT_LAT, 0.0, 'timezone'))
    # No new lookup until the retry interval has passed
    self.assertEqual(source.where(60.0), (moon.DEFAULT_LAT, 0.0, 'timezone'))
    self.assertEqual(len(results), 1)
    self.assertEqual(source.where(moon.LOOKUP_RETRY), BOSTON + ('ip',))

  def test_settings_location_skips_lookup(self):
    source = moon.make_source({'moon': {'lat': 1, 'lon': 2, 'locate': True}})
    self.assertFalse(source.locate)
    source.lookup = self.fail
    self.assertEqual(source.where(0.0), (1.0, 2.0, 'settings'))


class PollerTests(unittest.TestCase):

  def test_polls_with_the_clock(self):
    clock = FakeClock(utc(2026, 10, 26, 4, 12))
    source = moon.MoonSource(BOSTON, clock=clock)
    poller = base.Poller(source, clock=clock)
    self.assertEqual(poller.poll(), source.ttl)
    status = poller.status()
    self.assertEqual(status.source, 'moon')
    self.assertFalse(status.offline)
    self.assertEqual(status.label, 'Night, full moon 100%')
    self.assertEqual(status.reading.time, clock.now)
    # Nothing is fetched before the ttl is up, then the sky moves on
    clock.advance(30)
    self.assertAlmostEqual(poller.poll(), 30.0)
    clock.advance(12 * 3600)
    poller.poll()
    self.assertTrue(poller.status().label.startswith('Day, '))

  def test_registry_makes_the_source(self):
    source = registry.get('moon').make_source({'factor': 'moon',
                                               'moon': {'lat': 0, 'lon': 0}})
    self.assertIsInstance(source, moon.MoonSource)
    self.assertEqual(source.name, 'moon')
    self.assertIsInstance(source.fetch(), base.Reading)


if __name__ == '__main__':
  unittest.main()
