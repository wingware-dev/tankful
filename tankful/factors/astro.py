"""Low-precision sun and moon positions, computed locally.

Plain math on unix times (seconds, UTC) and degrees, with no network and
no third-party packages, so it runs under UPBGE's Python and in the tests.
The sun follows the NOAA / Astronomical Almanac low-precision formulas
(about 0.01 degrees, so sunrise and sunset to a minute or so), and the
moon's phase Meeus's main periodic terms (Astronomical Algorithms, ch. 48),
good to within a few hours of the true new and full moons.
"""

import math

SYNODIC_MONTH = 29.530588853    # days, new moon to new moon
DAY = 86400.0

# Sun elevations that mark the phases of the day, in degrees
HORIZON = -0.833         # sunrise and sunset: refraction plus the sun's radius
CIVIL_TWILIGHT = -6.0    # the end of dusk (and start of dawn)

_J2000 = 2451545.0       # julian day of 2000-01-01 12:00 UTC
_UNIX_EPOCH_JD = 2440587.5

PHASE_NAMES = (
  'new moon', 'waxing crescent', 'first quarter', 'waxing gibbous',
  'full moon', 'waning gibbous', 'last quarter', 'waning crescent',
)


def julian_day(t):
  """The julian day for unix time t."""
  return t / DAY + _UNIX_EPOCH_JD


def _wrap180(degrees):
  return (degrees + 180.0) % 360.0 - 180.0


def sun_position(t):
  """The sun's (right ascension, declination) in degrees at unix time t."""
  n = julian_day(t) - _J2000
  mean_longitude = 280.460 + 0.9856474 * n
  g = math.radians(357.528 + 0.9856003 * n)
  longitude = math.radians(mean_longitude + 1.915 * math.sin(g)
                           + 0.020 * math.sin(2 * g))
  obliquity = math.radians(23.439 - 0.0000004 * n)
  ra = math.degrees(math.atan2(math.cos(obliquity) * math.sin(longitude),
                               math.cos(longitude)))
  dec = math.degrees(math.asin(math.sin(obliquity) * math.sin(longitude)))
  return ra % 360.0, dec


def _sidereal_degrees(t):
  """Greenwich mean sidereal time at unix time t, in degrees."""
  n = julian_day(t) - _J2000
  return (280.46061837 + 360.98564736629 * n) % 360.0


def sun_hour_angle(t, lon):
  """The sun's local hour angle in degrees (-180..180, 0 at solar noon)."""
  ra, _ = sun_position(t)
  return _wrap180(_sidereal_degrees(t) + lon - ra)


def sun_elevation(t, lat, lon):
  """The sun's elevation above the horizon in degrees (no refraction)."""
  _, dec = sun_position(t)
  lat_r, dec_r = math.radians(lat), math.radians(dec)
  h = math.radians(sun_hour_angle(t, lon))
  s = (math.sin(lat_r) * math.sin(dec_r)
       + math.cos(lat_r) * math.cos(dec_r) * math.cos(h))
  return math.degrees(math.asin(max(-1.0, min(1.0, s))))


def _to_hour_angle(t, lon, target):
  """The time near t when the sun's hour angle is target degrees."""
  for _ in range(4):
    # The sun's hour angle runs at about 360 degrees per day
    t -= _wrap180(sun_hour_angle(t, lon) - target) / 360.0 * DAY
  return t


def solar_noon(t, lon):
  """The solar noon nearest to unix time t at longitude lon."""
  return _to_hour_angle(t, lon, 0.0)


def _event_hour_angle(t, lat, elevation):
  """The hour angle (0..180 degrees) at which the sun is at elevation.

  Uses the sun's declination at time t.  None when the sun doesn't reach
  that elevation that day, staying above or below it.
  """
  _, dec = sun_position(t)
  lat_r, dec_r = math.radians(lat), math.radians(dec)
  denominator = math.cos(lat_r) * math.cos(dec_r)
  if abs(denominator) < 1e-12:
    return None
  c = ((math.sin(math.radians(elevation)) - math.sin(lat_r) * math.sin(dec_r))
       / denominator)
  if not -1.0 < c < 1.0:
    return None
  return math.degrees(math.acos(c))


def sun_times(t, lat, lon, elevation=HORIZON):
  """(rise, set): unix times the sun crosses elevation on t's solar day.

  The solar day is the one whose noon is nearest t.  Either is None when
  the sun doesn't cross that elevation then (polar day or night).
  """
  noon = solar_noon(t, lon)
  times = []
  for sign in (-1.0, 1.0):
    event = noon
    for _ in range(3):
      # Refine with the sun's declination at the last estimate
      h0 = _event_hour_angle(event, lat, elevation)
      if h0 is None:
        event = None
        break
      event = _to_hour_angle(event, lon, sign * h0)
    times.append(event)
  return tuple(times)


def _moon_terms(t):
  """Meeus's mean elongation D, sun anomaly M, moon anomaly M' (degrees)."""
  T = (julian_day(t) - _J2000) / 36525.0
  d = 297.8501921 + 445267.1114034 * T - 0.0018819 * T * T
  m = 357.5291092 + 35999.0502909 * T - 0.0001536 * T * T
  mp = 134.9633964 + 477198.8675055 * T + 0.0087414 * T * T
  return d, m, mp


def moon_elongation(t):
  """The moon's elongation from the sun at unix time t, 0..360 degrees.

  0 is new moon, 90 first quarter, 180 full and 270 last quarter.
  """
  d, m, mp = (math.radians(x) for x in _moon_terms(t))
  elongation = (math.degrees(d)
                + 6.289 * math.sin(mp)
                - 2.100 * math.sin(m)
                + 1.274 * math.sin(2 * d - mp)
                + 0.658 * math.sin(2 * d)
                + 0.214 * math.sin(2 * mp)
                + 0.110 * math.sin(d))
  return elongation % 360.0


def moon_phase(t):
  """The moon's phase at unix time t, as a fraction of the cycle 0..1.

  0 (and 1) is new moon, 0.25 first quarter, 0.5 full, 0.75 last quarter.
  """
  return moon_elongation(t) / 360.0


def moon_age(t):
  """Days since the last new moon (0..29.53) at unix time t."""
  return moon_phase(t) * SYNODIC_MONTH


def moon_illumination(t):
  """The lit fraction of the moon's disc at unix time t, 0..1."""
  return (1.0 - math.cos(math.radians(moon_elongation(t)))) / 2.0


def phase_name(phase):
  """The usual name for a phase fraction, in eight parts of the cycle."""
  return PHASE_NAMES[int((phase % 1.0) * 8 + 0.5) % 8]
