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


def closest_between_segments(p0, p1, q0, q1):
  """The nearest points (on p0-p1, on q0-q1) of two segments."""
  d1, d2, r = sub(p1, p0), sub(q1, q0), sub(p0, q0)
  a, e, f = dot(d1, d1), dot(d2, d2), dot(d2, r)
  if a < 1e-12 and e < 1e-12:
    return p0, q0
  if a < 1e-12:
    s, t = 0.0, clamp(f / e, 0.0, 1.0)
  else:
    c = dot(d1, r)
    if e < 1e-12:
      s, t = clamp(-c / a, 0.0, 1.0), 0.0
    else:
      b = dot(d1, d2)
      denom = a * e - b * b
      s = clamp((b * f - c * e) / denom, 0.0, 1.0) if denom > 1e-12 else 0.0
      t = (b * s + f) / e
      if t < 0.0:
        s, t = clamp(-c / a, 0.0, 1.0), 0.0
      elif t > 1.0:
        s, t = clamp((b - c) / a, 0.0, 1.0), 1.0
  return add(p0, scale(d1, s)), add(q0, scale(d2, t))


def quaternion(m):
  """The unit quaternion (w, x, y, z) of the 3x3 rotation m (rows)."""
  t = m[0][0] + m[1][1] + m[2][2]
  if t > 0:
    s = 2.0 * math.sqrt(t + 1.0)
    return (0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s,
            (m[1][0] - m[0][1]) / s)
  if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
    s = 2.0 * math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2])
    return ((m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s,
            (m[0][2] + m[2][0]) / s)
  if m[1][1] > m[2][2]:
    s = 2.0 * math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2])
    return ((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s,
            (m[1][2] + m[2][1]) / s)
  s = 2.0 * math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1])
  return ((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s,
          (m[1][2] + m[2][1]) / s, 0.25 * s)
