"""The weather factor: the local weather outside sets the mood in the tank.

The location is a lat/lon from settings or, without one, a lookup by IP
address at ip-api.com (free for non-commercial use, HTTP only).  The
weather comes from Open-Meteo (no key), refreshed every 15 minutes.

Settings, under 'weather' (all optional):
  lat, lon: the location, skipping the IP lookup
  place: the name shown on the HUD (else the city ip-api gives)
  units: 'C' (default) or 'F'

The mapping, from Open-Meteo's WMO weather code:
  clear: bright light, sharp caustics
  cloudy: dimmer, softer light, more so the more cloud
  fog: dim, very soft light, a grey tint
  drizzle and rain: surface agitation, darker light, fish lower; heavier
    rain more so
  snow: a cool tint, slower fish
  storm: dark, a rough surface, skittish fish and a light flicker
"""

import logging
import urllib.parse

from tankful.factors import base
from tankful.factors import effects
from tankful.factors import net
from tankful.factors import settings as settings_mod

log = logging.getLogger('tankful.factors.weather')

LOCATION_URL = 'http://ip-api.com/json/?fields=status,message,lat,lon,city'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
CURRENT = ('weather_code,temperature_2m,cloud_cover,precipitation,is_day,'
           'wind_speed_10m')

# Open-Meteo's data is CC BY 4.0, which asks for this credit where it is
# shown: the HUD shows it while Weather is picked (Factor.credit)
CREDIT = 'Weather data by Open-Meteo.com'

CONDITIONS = ('clear', 'cloudy', 'fog', 'drizzle', 'rain', 'snow', 'storm')


def condition_for(code):
  """The condition for a WMO weather code (Open-Meteo's weather_code)."""
  if code <= 1:
    return 'clear'
  if code <= 3:
    return 'cloudy'
  if code in (45, 48):
    return 'fog'
  if 51 <= code <= 57:
    return 'drizzle'
  if 61 <= code <= 67 or 80 <= code <= 82:
    return 'rain'
  if 71 <= code <= 77 or code in (85, 86):
    return 'snow'
  if 95 <= code <= 99:
    return 'storm'
  return 'cloudy'


def parse_location(data):
  """(lat, lon, city) from an ip-api reply; raises ValueError if failed."""
  if not isinstance(data, dict) or data.get('status') != 'success':
    message = data.get('message') if isinstance(data, dict) else data
    raise ValueError('location lookup failed: %r' % (message,))
  return float(data['lat']), float(data['lon']), data.get('city') or ''


def forecast_url(lat, lon, units='C'):
  query = {
    'latitude': '%.4f' % lat,
    'longitude': '%.4f' % lon,
    'current': CURRENT,
    'timezone': 'auto',
  }
  if units == 'F':
    query['temperature_unit'] = 'fahrenheit'
  return FORECAST_URL + '?' + urllib.parse.urlencode(query, safe=',')


def _number(current, key, default=0.0):
  value = current.get(key)
  return default if value is None else float(value)


def parse_forecast(data):
  """The reading's value dict from an Open-Meteo reply.

  Raises ValueError (or KeyError, TypeError) on a reply without a current
  weather code.
  """
  if not isinstance(data, dict):
    raise ValueError('forecast is not a JSON object')
  if data.get('error'):
    raise ValueError('forecast error: %r' % data.get('reason'))
  current = data['current']
  code = int(current['weather_code'])
  temperature = current.get('temperature_2m')
  return {
    'code': code,
    'condition': condition_for(code),
    'temperature': None if temperature is None else float(temperature),
    'cloud_cover': _number(current, 'cloud_cover'),
    'precipitation': _number(current, 'precipitation'),
    'wind_speed': _number(current, 'wind_speed_10m'),
    'is_day': bool(_number(current, 'is_day', 1)),
  }


def label_for(value, place='', units='C'):
  """HUD text such as 'Seattle: rain, 12°C'."""
  text = value['condition']
  if value.get('temperature') is not None:
    text += ', %d°%s' % (round(value['temperature']), units)
  return '%s: %s' % (place, text) if place else text


class WeatherSource(base.Source):
  """Open-Meteo's current weather at a fixed or IP-looked-up location."""

  name = 'weather'
  ttl = 15 * 60.0
  retry = 2 * 60.0
  max_stale = 2 * 60 * 60.0

  def __init__(self, lat=None, lon=None, place='', units='C',
               fetch_json=net.fetch_json):
    self.location = None
    if lat is not None and lon is not None:
      self.location = (float(lat), float(lon), place)
    self.place = place
    self.units = units
    self._fetch_json = fetch_json

  def locate(self):
    """The (lat, lon, place) to use, looked up by IP once per source."""
    if self.location is None:
      lat, lon, city = parse_location(self._fetch_json(LOCATION_URL))
      self.location = (lat, lon, self.place or city)
      log.info('Weather location %.2f, %.2f (%s)', lat, lon, city)
    return self.location

  def fetch(self):
    lat, lon, place = self.locate()
    value = parse_forecast(self._fetch_json(forecast_url(lat, lon,
                                                         self.units)))
    return base.Reading(value, label_for(value, place, self.units))


def make_source(settings):
  own = settings_mod.section(settings, 'weather')
  units = 'F' if str(own.get('units', 'C')).upper().startswith('F') else 'C'
  lat, lon = own.get('lat'), own.get('lon')
  if lat is not None or lon is not None:
    try:
      lat, lon = float(lat), float(lon)
      if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('out of range')
    except (TypeError, ValueError):
      log.warning('Ignoring bad weather lat/lon %r, %r; looking up by IP',
                  own.get('lat'), own.get('lon'))
      lat = lon = None
  place = own.get('place') if isinstance(own.get('place'), str) else ''
  return WeatherSource(lat, lon, place, units)


# The look of each condition at its typical strength
LOOKS = {
  'clear': effects.Effects(light_level=1.15, caustic_sharpness=1.5),
  'cloudy': effects.Effects(light_level=0.8, caustic_sharpness=0.5),
  'fog': effects.Effects(light_level=0.7, caustic_sharpness=0.25,
                         tint=(0.9, 0.93, 0.95)),
  'drizzle': effects.Effects(light_level=0.75, caustic_sharpness=0.5,
                             surface_agitation=0.3, depth_shift=-0.2),
  'rain': effects.Effects(light_level=0.6, caustic_sharpness=0.4,
                          surface_agitation=0.6, depth_shift=-0.5,
                          speed_scale=0.95),
  'snow': effects.Effects(light_level=0.9, caustic_sharpness=0.5,
                          tint=(0.82, 0.9, 1.0), surface_agitation=0.1,
                          speed_scale=0.85),
  'storm': effects.Effects(light_level=0.45, caustic_sharpness=0.6,
                           surface_agitation=1.0, depth_shift=-0.6,
                           skittish=0.8, speed_scale=1.2, flicker=1.0),
}

# Rain at this rate (mm in the last hour) or more is heavy
HEAVY_RAIN = 8.0


def effects_for(reading):
  value = reading.value
  condition = value.get('condition', 'cloudy')
  look = LOOKS.get(condition, LOOKS['cloudy'])
  cloud = min(1.0, max(0.0, value.get('cloud_cover', 0.0) / 100.0))
  if condition == 'clear':
    # Mainly clear skies with some cloud soften toward cloudy
    look = effects.blend(look, LOOKS['cloudy'], 0.5 * cloud)
  elif condition == 'cloudy':
    # Partly cloudy is brighter than overcast
    look = effects.blend(LOOKS['clear'], look, 0.4 + 0.6 * cloud)
  elif condition in ('drizzle', 'rain'):
    heavy = min(1.0, value.get('precipitation', 0.0) / HEAVY_RAIN)
    look = effects.blend(look, LOOKS['storm'].replace(skittish=0.0,
                                                      flicker=0.0),
                         0.5 * heavy)
  # Wind roughens the surface: up to 0.3 more at 50 km/h
  wind = min(1.0, max(0.0, value.get('wind_speed', 0.0) / 50.0))
  return look.replace(
    surface_agitation=look.surface_agitation + 0.3 * wind).clamped()
