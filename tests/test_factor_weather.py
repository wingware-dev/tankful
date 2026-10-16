import unittest
import urllib.parse

from tankful.factors import base
from tankful.factors import effects
from tankful.factors import net
from tankful.factors import registry
from tankful.factors import weather
from tankful.factors.base import Reading

# Canned replies in the shape the live services give
LOCATION = {'status': 'success', 'lat': 47.6062, 'lon': -122.3321,
            'city': 'Seattle'}
LOCATION_FAIL = {'status': 'fail', 'message': 'reserved range'}


def forecast(code, temperature=12.4, cloud_cover=0, precipitation=0.0,
             wind_speed=5.0, is_day=1):
  return {
    'latitude': 47.6, 'longitude': -122.3, 'timezone': 'America/Los_Angeles',
    'current_units': {'temperature_2m': '°C', 'wind_speed_10m': 'km/h'},
    'current': {
      'time': '2026-10-16T16:30', 'interval': 900,
      'weather_code': code, 'temperature_2m': temperature,
      'cloud_cover': cloud_cover, 'precipitation': precipitation,
      'is_day': is_day, 'wind_speed_10m': wind_speed,
    },
  }


class FakeWeb:
  """Answers fetch_json from canned replies; records the URLs asked."""

  def __init__(self, location=LOCATION, forecast_reply=None):
    self.location = location
    self.forecast = forecast_reply or forecast(0)
    self.urls = []

  def __call__(self, url, timeout=net.TIMEOUT):
    self.urls.append(url)
    reply = self.location if url.startswith('http://ip-api.com') else \
      self.forecast
    if isinstance(reply, BaseException):
      raise reply
    return reply

  def forecast_query(self):
    url = [u for u in self.urls if u.startswith(weather.FORECAST_URL)][-1]
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def reading_for(code, **kw):
  value = weather.parse_forecast(forecast(code, **kw))
  return Reading(value, weather.label_for(value))


def look(code, **kw):
  return weather.effects_for(reading_for(code, **kw))


class ConditionTests(unittest.TestCase):

  def test_codes(self):
    cases = {0: 'clear', 1: 'clear', 2: 'cloudy', 3: 'cloudy', 45: 'fog',
             48: 'fog', 51: 'drizzle', 57: 'drizzle', 61: 'rain',
             65: 'rain', 67: 'rain', 80: 'rain', 82: 'rain', 71: 'snow',
             77: 'snow', 85: 'snow', 86: 'snow', 95: 'storm', 96: 'storm',
             99: 'storm'}
    for code, condition in cases.items():
      self.assertEqual(weather.condition_for(code), condition, code)

  def test_unknown_code_is_cloudy(self):
    self.assertEqual(weather.condition_for(42), 'cloudy')

  def test_every_condition_has_a_look(self):
    self.assertEqual(set(weather.LOOKS), set(weather.CONDITIONS))


class ParseTests(unittest.TestCase):

  def test_location(self):
    self.assertEqual(weather.parse_location(LOCATION),
                     (47.6062, -122.3321, 'Seattle'))

  def test_location_failure(self):
    with self.assertRaises(ValueError):
      weather.parse_location(LOCATION_FAIL)
    with self.assertRaises(ValueError):
      weather.parse_location([])

  def test_forecast(self):
    value = weather.parse_forecast(forecast(63, temperature=9.6,
                                            cloud_cover=100,
                                            precipitation=2.5,
                                            wind_speed=20, is_day=0))
    self.assertEqual(value, {
      'code': 63, 'condition': 'rain', 'temperature': 9.6,
      'cloud_cover': 100.0, 'precipitation': 2.5, 'wind_speed': 20.0,
      'is_day': False})

  def test_forecast_missing_optional_fields(self):
    value = weather.parse_forecast({'current': {'weather_code': 3}})
    self.assertEqual(value['condition'], 'cloudy')
    self.assertIsNone(value['temperature'])
    self.assertEqual(value['cloud_cover'], 0.0)
    self.assertTrue(value['is_day'])

  def test_forecast_nulls(self):
    data = forecast(0)
    data['current']['cloud_cover'] = None
    data['current']['temperature_2m'] = None
    value = weather.parse_forecast(data)
    self.assertEqual(value['cloud_cover'], 0.0)
    self.assertIsNone(value['temperature'])

  def test_forecast_errors(self):
    for bad in ({'error': True, 'reason': 'Latitude must be in range'},
                {'current': {}}, {}, 'text'):
      with self.assertRaises((ValueError, KeyError, TypeError)):
        weather.parse_forecast(bad)

  def test_forecast_url(self):
    url = weather.forecast_url(47.60621, -122.33207)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    self.assertTrue(url.startswith('https://api.open-meteo.com/v1/forecast?'))
    self.assertEqual(query['latitude'], ['47.6062'])
    self.assertEqual(query['longitude'], ['-122.3321'])
    self.assertIn('weather_code', query['current'][0].split(','))
    self.assertNotIn('temperature_unit', query)
    self.assertIn(',', url)  # the field list stays readable

  def test_forecast_url_fahrenheit(self):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(
      weather.forecast_url(0, 0, 'F')).query)
    self.assertEqual(query['temperature_unit'], ['fahrenheit'])


class LabelTests(unittest.TestCase):

  def test_label(self):
    value = weather.parse_forecast(forecast(61, temperature=11.6))
    self.assertEqual(weather.label_for(value), 'rain, 12°C')
    self.assertEqual(weather.label_for(value, 'Seattle'),
                     'Seattle: rain, 12°C')
    self.assertEqual(weather.label_for(value, units='F'), 'rain, 12°F')

  def test_label_without_temperature(self):
    value = weather.parse_forecast({'current': {'weather_code': 0}})
    self.assertEqual(weather.label_for(value), 'clear')


class SourceTests(unittest.TestCase):

  def test_ttl_is_fifteen_minutes(self):
    self.assertEqual(weather.WeatherSource.ttl, 900)
    self.assertEqual(weather.WeatherSource.name, 'weather')

  def test_fetches_with_shared_helper(self):
    self.assertIs(weather.WeatherSource()._fetch_json, net.fetch_json)

  def test_looks_up_location_once(self):
    web = FakeWeb(forecast_reply=forecast(61))
    source = weather.WeatherSource(fetch_json=web)
    with self.assertLogs('tankful.factors.weather', 'INFO'):
      reading = source.fetch()
    source.fetch()
    self.assertEqual(reading.value['condition'], 'rain')
    self.assertEqual(reading.label, 'Seattle: rain, 12°C')
    self.assertEqual(sum(u.startswith('http://ip-api.com') for u in web.urls),
                     1)
    self.assertEqual(web.forecast_query()['latitude'], ['47.6062'])

  def test_fixed_location_skips_lookup(self):
    web = FakeWeb()
    source = weather.WeatherSource(10.0, 20.0, fetch_json=web)
    self.assertEqual(source.fetch().label, 'clear, 12°C')
    self.assertFalse(any(u.startswith('http://ip-api.com') for u in web.urls))
    self.assertEqual(web.forecast_query()['longitude'], ['20.0000'])

  def test_place_overrides_city(self):
    web = FakeWeb()
    source = weather.WeatherSource(place='Home', fetch_json=web)
    with self.assertLogs('tankful.factors.weather', 'INFO'):
      self.assertEqual(source.fetch().label, 'Home: clear, 12°C')

  def test_failed_lookup_raises_and_retries(self):
    web = FakeWeb(location=LOCATION_FAIL)
    source = weather.WeatherSource(fetch_json=web)
    with self.assertRaises(ValueError):
      source.fetch()
    web.location = LOCATION
    with self.assertLogs('tankful.factors.weather', 'INFO'):
      self.assertEqual(source.fetch().value['condition'], 'clear')

  def test_network_error_fails_soft_in_poller(self):
    web = FakeWeb(forecast_reply=OSError('no route to host'))
    clock = base.FakeClock()
    poller = base.Poller(weather.WeatherSource(1, 2, fetch_json=web),
                         clock=clock)
    with self.assertLogs('tankful.factors', 'WARNING'):
      self.assertEqual(poller.poll(), weather.WeatherSource.retry)
    status = poller.status()
    self.assertTrue(status.offline)
    self.assertIsNone(status.reading)
    self.assertIs(registry.get('weather').effects_for(status.reading),
                  effects.NEUTRAL)

  def test_poller_refreshes_every_fifteen_minutes(self):
    web = FakeWeb(forecast_reply=forecast(0))
    clock = base.FakeClock()
    poller = base.Poller(weather.WeatherSource(1, 2, fetch_json=web),
                         clock=clock)
    self.assertEqual(poller.poll(), 900)
    web.forecast = forecast(95)
    clock.advance(899)
    poller.poll()
    self.assertEqual(poller.status().reading.value['condition'], 'clear')
    clock.advance(1)
    poller.poll()
    self.assertEqual(poller.status().reading.value['condition'], 'storm')


class MakeSourceTests(unittest.TestCase):

  def test_default_looks_up_by_ip(self):
    source = weather.make_source({'factor': 'weather'})
    self.assertIsInstance(source, weather.WeatherSource)
    self.assertIsNone(source.location)
    self.assertEqual(source.units, 'C')

  def test_settings(self):
    source = weather.make_source({'weather': {
      'lat': '47.6', 'lon': -122.3, 'place': 'Home', 'units': 'f'}})
    self.assertEqual(source.location, (47.6, -122.3, 'Home'))
    self.assertEqual(source.units, 'F')

  def test_bad_location_falls_back_to_lookup(self):
    for own in ({'lat': 'north', 'lon': 1}, {'lat': 95, 'lon': 0},
                {'lat': 10}, {'lon': 200, 'lat': 0}):
      with self.assertLogs('tankful.factors.weather', 'WARNING'):
        self.assertIsNone(weather.make_source({'weather': own}).location)

  def test_bad_place_ignored(self):
    self.assertEqual(weather.make_source({'weather': {'place': 3}}).place,
                     '')

  def test_registry_finds_it(self):
    factor = registry.get('weather')
    self.assertTrue(factor.available)
    self.assertIsInstance(factor.make_source({}), weather.WeatherSource)


class MappingTests(unittest.TestCase):

  def test_clear_is_bright_and_sharp(self):
    e = look(0)
    self.assertGreater(e.light_level, 1.0)
    self.assertGreater(e.caustic_sharpness, 1.0)
    self.assertEqual(e.surface_agitation, 0.3 * 5 / 50.0)

  def test_mainly_clear_cloud_softens(self):
    self.assertLess(look(1, cloud_cover=60).light_level, look(0).light_level)

  def test_cloudy_is_dimmer_and_softer(self):
    e = look(3, cloud_cover=100)
    self.assertLess(e.light_level, 1.0)
    self.assertLess(e.caustic_sharpness, 1.0)
    partly = look(2, cloud_cover=40)
    self.assertGreater(partly.light_level, e.light_level)
    self.assertLess(partly.light_level, look(0).light_level)

  def test_rain_agitates_darkens_and_sinks(self):
    e = look(61, precipitation=1.0)
    clear = look(0)
    self.assertGreater(e.surface_agitation, clear.surface_agitation + 0.4)
    self.assertLess(e.light_level, look(3, cloud_cover=100).light_level)
    self.assertLess(e.depth_shift, 0)
    self.assertEqual(e.skittish, 0)
    self.assertEqual(e.flicker, 0)

  def test_heavier_rain_is_stronger(self):
    light, heavy = look(61, precipitation=0.5), look(65, precipitation=12)
    self.assertLess(heavy.light_level, light.light_level)
    self.assertLess(heavy.depth_shift, light.depth_shift)
    self.assertGreater(heavy.surface_agitation, light.surface_agitation)
    self.assertEqual(heavy.flicker, 0)

  def test_drizzle_is_milder_than_rain(self):
    self.assertGreater(look(51).light_level, look(61).light_level)
    self.assertGreater(look(51).depth_shift, look(61).depth_shift)

  def test_storm_is_skittish_and_flickers(self):
    e = look(95)
    self.assertGreater(e.skittish, 0.5)
    self.assertEqual(e.flicker, 1.0)
    self.assertLess(e.light_level, look(61).light_level)
    for code in (0, 3, 45, 61, 71):
      self.assertEqual(look(code).flicker, 0.0, code)
      self.assertEqual(look(code).skittish, 0.0, code)

  def test_snow_is_cool(self):
    r, g, b = look(73).tint
    self.assertLess(r, g)
    self.assertLess(g, b)
    self.assertEqual(look(0).tint, (1.0, 1.0, 1.0))

  def test_fog_is_soft(self):
    self.assertLess(look(45).caustic_sharpness, look(3).caustic_sharpness)

  def test_wind_roughens_surface(self):
    self.assertGreater(look(0, wind_speed=40).surface_agitation,
                       look(0, wind_speed=0).surface_agitation)

  def test_all_inside_ranges(self):
    for code in (0, 1, 2, 3, 45, 51, 61, 65, 71, 80, 95, 99):
      e = look(code, cloud_cover=100, precipitation=50, wind_speed=150)
      self.assertEqual(e.clamped(), e, code)

  def test_unknown_condition_value_is_cloudy(self):
    e = weather.effects_for(Reading({'condition': 'hail?'}))
    self.assertEqual(e, weather.LOOKS['cloudy'])


if __name__ == '__main__':
  unittest.main()
