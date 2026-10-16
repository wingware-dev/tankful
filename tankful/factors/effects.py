"""What an external factor does to the tank: one value the sim and lights read.

Each factor maps its latest reading to an Effects value (see registry.py),
and the game applies only that value: the sim scales swim speed and moves
the depth band, and the lighting sets level, caustics, tint and the night
light.  NEUTRAL leaves the tank exactly as it is with no factor.

All of it is plain data, so it runs under UPBGE's Python and in the tests.
"""

import dataclasses
import math


@dataclasses.dataclass(frozen=True)
class Effects:
  """The tank's response to a factor.  The defaults are neutral.

  speed_scale: multiplies swim speed (1 is normal, below 1 sluggish).
  depth_shift: moves the band fish prefer, from -1 (near the sand) through
    0 (unchanged) to +1 (near the surface).
  light_level: multiplies the tank light (1 is normal).
  caustic_sharpness: 0 is fully soft caustics, 1 normal, above 1 crisper.
  tint: an rgb multiplier on the light, each 0..1 (white is none).
  surface_agitation: ripples and drops on the surface, 0 calm to 1 stormy.
  skittish: 0 calm to 1 fish dart and startle.
  night_light: a dim blue moonlight, 0 off to 1 full.
  flicker: lightning flicker of the tank light, 0 none to 1 frequent.
  """
  speed_scale: float = 1.0
  depth_shift: float = 0.0
  light_level: float = 1.0
  caustic_sharpness: float = 1.0
  tint: tuple = (1.0, 1.0, 1.0)
  surface_agitation: float = 0.0
  skittish: float = 0.0
  night_light: float = 0.0
  flicker: float = 0.0

  def clamped(self):
    """This value with each field inside RANGES (and NaN made neutral)."""
    changes = {}
    for name, (low, high) in RANGES.items():
      changes[name] = _clamp(getattr(self, name), low, high,
                             getattr(NEUTRAL, name))
    tint = tuple(self.tint)[:3] if _is_triple(self.tint) else (1.0, 1.0, 1.0)
    changes['tint'] = tuple(_clamp(c, 0.0, 1.0, 1.0) for c in tint)
    return dataclasses.replace(self, **changes)

  def replace(self, **changes):
    """A copy with some fields changed."""
    return dataclasses.replace(self, **changes)


# Each scalar field's allowed range
RANGES = {
  'speed_scale': (0.25, 2.0),
  'depth_shift': (-1.0, 1.0),
  'light_level': (0.0, 1.5),
  'caustic_sharpness': (0.0, 2.0),
  'surface_agitation': (0.0, 1.0),
  'skittish': (0.0, 1.0),
  'night_light': (0.0, 1.0),
  'flicker': (0.0, 1.0),
}

NEUTRAL = Effects()


def _is_triple(value):
  try:
    return len(value) >= 3
  except TypeError:
    return False


def _clamp(value, low, high, fallback):
  try:
    value = float(value)
  except (TypeError, ValueError):
    return fallback
  if math.isnan(value):
    return fallback
  return min(high, max(low, value))


def _lerp(a, b, t):
  # This form gives exactly a at t=0 and b at t=1
  return a * (1.0 - t) + b * t


def blend(a, b, t):
  """Effects t of the way from a to b (t is clamped to 0..1)."""
  t = min(1.0, max(0.0, t))
  changes = {name: _lerp(getattr(a, name), getattr(b, name), t)
             for name in RANGES}
  changes['tint'] = tuple(_lerp(x, y, t) for x, y in zip(a.tint, b.tint))
  return Effects(**changes)


def approach(current, target, dt, time_constant=2.0):
  """Ease current toward target over a step of dt seconds.

  Exponential smoothing, so a new reading or a change of factor fades in
  over a few seconds rather than snapping, whatever the frame rate.
  """
  if time_constant <= 0:
    return target
  return blend(current, target, 1.0 - math.exp(-max(0.0, dt) / time_constant))


def mix(*weighted):
  """A weighted average of (Effects, weight) pairs, for combined moods.

  With no weight at all it is NEUTRAL.
  """
  total = sum(w for _, w in weighted if w > 0)
  if total <= 0:
    return NEUTRAL
  changes = {name: sum(getattr(e, name) * w for e, w in weighted if w > 0)
             / total for name in RANGES}
  changes['tint'] = tuple(
    sum(e.tint[i] * w for e, w in weighted if w > 0) / total
    for i in range(3))
  return Effects(**changes)
