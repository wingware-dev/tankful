"""The Time & Moon factor: the tank follows the real day and the moon.

Computed locally (see astro.py), so it needs no network.  The location is
the 'moon' settings section's lat and lon, else the weather factor's,
else a guess from the computer's time zone; with {'locate': true} in the
section it is looked up once from the IP address (ip-api.com) instead of
guessed.

The sun's elevation picks the phase of the day: day, dusk (or dawn) in
civil twilight, and night, blending between them so the tank fades
rather than snaps; at night the moon's illumination sets the night light.
"""

import json
import logging
import math
import time
import urllib.request

from tankful.factors import astro
from tankful.factors import base
from tankful.factors import effects
from tankful.factors import settings as settings_mod

log = logging.getLogger('tankful.factors')

# Sun elevations (degrees) bounding the phases: full day above DAY_START,
# full night below NIGHT_START, and dusk at HORIZON (sunset) between them
DAY_START = 6.0
HORIZON = astro.HORIZON
NIGHT_START = astro.CIVIL_TWILIGHT

# Latitude to assume with no location: the time zone gives only longitude
DEFAULT_LAT = 40.0

IP_LOOKUP_URL = 'http://ip-api.com/json/?fields=status,lat,lon'
LOOKUP_RETRY = 3600.0

# The tank at each phase.  Night's night_light is set by the moon.
DAY = effects.NEUTRAL
DUSK = effects.Effects(
  speed_scale=0.9, light_level=0.6, caustic_sharpness=0.6,
  tint=(1.0, 0.8, 0.62))
NIGHT = effects.Effects(
  speed_scale=0.75, depth_shift=-0.2, light_level=0.2,
  caustic_sharpness=0.25, tint=(0.62, 0.72, 1.0))

# Night light with no moon (starlight) and with a full moon
NIGHT_LIGHT_NEW = 0.08
NIGHT_LIGHT_FULL = 1.0


def _coordinate(section, key, limit):
  value = section.get(key)
  if value is None:
    return None
  try:
    value = float(value)
  except (TypeError, ValueError):
    value = math.nan
  if not -limit <= value <= limit:
    log.warning('moon: ignoring bad %s %r in settings', key, section.get(key))
    return None
  return value


def _location(section):
  """(lat, lon) from a settings section, or None."""
  lat = _coordinate(section, 'lat', 90.0)
  lon = _coordinate(section, 'lon', 180.0)
  if lat is None or lon is None:
    return None
  return lat, lon


def guess_location(utc_offset=None):
  """(lat, lon) guessed from the standard time zone offset (seconds east)."""
  if utc_offset is None:
    utc_offset = -time.timezone
  lon = max(-180.0, min(180.0, utc_offset / 3600.0 * 15.0))
  return DEFAULT_LAT, lon


def ip_location(urlopen=urllib.request.urlopen, timeout=5.0):
  """(lat, lon) for this computer's IP address from ip-api.com; raises
  on failure."""
  with urlopen(IP_LOOKUP_URL, timeout=timeout) as response:
    data = json.loads(response.read().decode('utf-8'))
  if data.get('status') != 'success':
    raise ValueError('ip-api lookup failed: %r' % (data,))
  return float(data['lat']), float(data['lon'])


class MoonSource(base.Source):
  """Reads the sun and moon for a location from the clock."""
  name = 'moon'
  ttl = 60.0      # the sun moves a quarter degree a minute
  retry = 60.0

  def __init__(self, location=None, locate=False, clock=time.time,
               lookup=ip_location, utc_offset=None):
    """location: (lat, lon), or None to look it up (locate) or guess."""
    self.location = location
    self.locate = locate and location is None
    self.clock = clock
    self.lookup = lookup
    self.utc_offset = utc_offset
    self._next_lookup = 0.0

  def where(self, now):
    """(lat, lon, how) for now: how is 'settings', 'ip' or 'timezone'."""
    if self.location is not None:
      return self.location + ('ip' if self.locate else 'settings',)
    if self.locate and now >= self._next_lookup:
      try:
        self.location = self.lookup()
        return self.location + ('ip',)
      except Exception:
        log.warning('moon: location lookup failed, guessing from the time '
                    'zone', exc_info=True)
        self._next_lookup = now + LOOKUP_RETRY
    return guess_location(self.utc_offset) + ('timezone',)

  def fetch(self):
    now = self.clock()
    lat, lon, how = self.where(now)
    return reading_at(now, lat, lon, how)


def reading_at(t, lat, lon, how='settings'):
  """The Reading for unix time t at a location."""
  elevation = astro.sun_elevation(t, lat, lon)
  sunrise, sunset = astro.sun_times(t, lat, lon)
  moon_phase = astro.moon_phase(t)
  illumination = astro.moon_illumination(t)
  if elevation >= DAY_START:
    phase = 'day'
  elif elevation <= NIGHT_START:
    phase = 'night'
  else:
    phase = 'dusk'
  morning = astro.sun_hour_angle(t, lon) < 0
  value = {
    'phase': phase,
    'morning': morning,
    'sun_elevation': elevation,
    'sunrise': sunrise,
    'sunset': sunset,
    'moon_phase': moon_phase,
    'moon_age': moon_phase * astro.SYNODIC_MONTH,
    'moon_illumination': illumination,
    'lat': lat,
    'lon': lon,
    'located_by': how,
  }
  shown = 'dawn' if phase == 'dusk' and morning else phase
  label = '%s, %s %d%%' % (shown.capitalize(), astro.phase_name(moon_phase),
                           round(illumination * 100))
  return base.Reading(value, label)


def night_light(illumination):
  """The night light for the moon's lit fraction (0..1)."""
  illumination = min(1.0, max(0.0, illumination))
  return NIGHT_LIGHT_NEW + (NIGHT_LIGHT_FULL - NIGHT_LIGHT_NEW) * illumination


def make_source(settings):
  section = settings_mod.section(settings, 'moon')
  location = (_location(section)
              or _location(settings_mod.section(settings, 'weather')))
  return MoonSource(location, locate=bool(section.get('locate')))


def effects_for(reading):
  value = reading.value
  elevation = float(value['sun_elevation'])
  night = NIGHT.replace(night_light=night_light(value['moon_illumination']))
  if elevation >= DAY_START:
    return DAY
  if elevation >= HORIZON:
    return effects.blend(DAY, DUSK,
                         (DAY_START - elevation) / (DAY_START - HORIZON))
  if elevation > NIGHT_START:
    return effects.blend(DUSK, night,
                         (HORIZON - elevation) / (HORIZON - NIGHT_START))
  return night
