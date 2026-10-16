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


def cross(a, b):
  return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0])


def lerp(a, b, t):
  return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
          a[2] + (b[2] - a[2]) * t)


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


def rotation(q):
  """The 3x3 rotation (rows) of the unit quaternion q (w, x, y, z)."""
  w, x, y, z = q
  return ((1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
          (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
          (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)))


def slerp(q0, q1, t):
  """The unit quaternion t of the way from q0 to q1, the short way round."""
  d = sum(a * b for a, b in zip(q0, q1))
  if d < 0:
    q1, d = tuple(-v for v in q1), -d
  if d > 0.9995:
    q = tuple(a + (b - a) * t for a, b in zip(q0, q1))
  else:
    theta = math.acos(d)
    s0 = math.sin((1 - t) * theta) / math.sin(theta)
    s1 = math.sin(t * theta) / math.sin(theta)
    q = tuple(s0 * a + s1 * b for a, b in zip(q0, q1))
  n = math.sqrt(sum(v * v for v in q))
  return tuple(v / n for v in q)


def frame(forward, up):
  """The 3x3 rotation (rows) whose columns are forward, up x forward (the
  left) and up, after making up square to forward."""
  f = normalized(forward)
  u = normalized(sub(up, scale(f, dot(up, f))), (0.0, 0.0, 1.0))
  left = cross(u, f)
  return ((f[0], left[0], u[0]), (f[1], left[1], u[1]), (f[2], left[2], u[2]))
