"""Small 3D vector helpers on plain tuples, for the stdlib-only sim."""

import math


def add(a, b):
  return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
  return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, s):
  return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def length(a):
  return math.sqrt(dot(a, a))


def normalized(a, fallback=(1.0, 0.0, 0.0)):
  n = length(a)
  if n < 1e-12:
    return fallback
  return (a[0] / n, a[1] / n, a[2] / n)


def clamp(v, lo, hi):
  return lo if v < lo else hi if v > hi else v


def wrap_angle(a):
  """a in radians, wrapped into [-pi, pi)."""
  return (a + math.pi) % (2 * math.pi) - math.pi


def closest_on_segment(p, a, b):
  """The point of segment a-b nearest to p."""
  ab = sub(b, a)
  denom = dot(ab, ab)
  if denom < 1e-12:
    return a
  t = clamp(dot(sub(p, a), ab) / denom, 0.0, 1.0)
  return add(a, scale(ab, t))
