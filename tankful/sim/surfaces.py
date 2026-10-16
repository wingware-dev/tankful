"""Surfaces the bottom dwellers move over, and the geometry they share.

A surface (Sand here; Glass, Perch and MossTop in the species modules)
has a kind and a name, whether it stays put (still), and

- contact(p): the point on it nearest p and its normal there
- edges(c): [(how far inside the edge, the way back in)] for each edge
- clamp(c): c moved onto it, inside its edges
- random_point(rng): a point on it
- heading(angle): a direction along it
"""

import collections
import math

from tankful.sim import environment as env
from tankful.sim import vec

# A place on a surface: the surface, the point the fish rests on, the
# surface's normal there, and a heading along the surface to take if it
# arrives with none of its own
Spot = collections.namedtuple('Spot', 'surface point normal heading')


def ease(t):
  t = vec.clamp(t, 0.0, 1.0)
  return t * t * (3 - 2 * t)


def tangent(v, normal):
  """v made square to normal, as a unit vector (None if v is along it)."""
  t = vec.sub(v, vec.scale(normal, vec.dot(v, normal)))
  n = vec.length(t)
  return None if n < 1e-6 else vec.scale(t, 1.0 / n)


def signed_angle(a, b, axis):
  """The angle from a to b about axis, all unit and a, b square to it."""
  return math.atan2(vec.dot(axis, vec.cross(a, b)), vec.dot(a, b))


def turned(h, normal, angle):
  """h (square to normal) turned by angle about normal."""
  c, s = math.cos(angle), math.sin(angle)
  return vec.normalized(vec.add(vec.scale(h, c),
                                vec.scale(vec.cross(normal, h), s)), h)


class Sand:
  """The open sand in front of the decor, edge (m) in from its edges
  and in front of y = back."""

  kind = 'sand'
  still = False
  name = 'Sand'

  def __init__(self, edge, back):
    self.edge = edge
    self.x = (-env.INNER_X + edge, env.INNER_X - edge)
    self.y = (-env.INNER_Y + edge, back)
    self._obstacles = env.obstacles()

  def contact(self, p):
    x, y = p[0], p[1]
    h = 1e-3
    dx = (env.sand_height(x + h, y) - env.sand_height(x - h, y)) / (2 * h)
    dy = (env.sand_height(x, y + h) - env.sand_height(x, y - h)) / (2 * h)
    return (x, y, env.sand_height(x, y)), vec.normalized((-dx, -dy, 1.0))

  def _decor(self, c):
    """[(gap, away)] from each obstacle's footprint, gap past the edge."""
    out = []
    for o in self._obstacles:
      a, b = (o.a[0], o.a[1], 0.0), (o.b[0], o.b[1], 0.0)
      p = (c[0], c[1], 0.0)
      off = vec.sub(p, vec.closest_on_segment(p, a, b))
      out.append((vec.length(off) - o.radius - self.edge,
                  vec.normalized(off, (0.0, -1.0, 0.0))))
    return out

  def edges(self, c):
    (x0, x1), (y0, y1) = self.x, self.y
    out = [(c[0] - x0, (1.0, 0.0, 0.0)), (x1 - c[0], (-1.0, 0.0, 0.0)),
           (c[1] - y0, (0.0, 1.0, 0.0)), (y1 - c[1], (0.0, -1.0, 0.0))]
    return out + self._decor(c)

  def clamp(self, c):
    x, y = vec.clamp(c[0], *self.x), vec.clamp(c[1], *self.y)
    for gap, away in self._decor((x, y, 0.0)):
      if gap < 0:
        x, y = x - away[0] * gap, y - away[1] * gap
    x, y = vec.clamp(x, *self.x), vec.clamp(y, *self.y)
    return self.contact((x, y, 0.0))[0]

  def random_point(self, rng):
    for _ in range(50):
      p = (rng.uniform(*self.x), rng.uniform(*self.y), 0.0)
      if all(gap > 0 for gap, _ in self._decor(p)):
        return self.contact(p)[0]
    return self.clamp(p)

  def heading(self, angle):
    return (math.cos(angle), math.sin(angle), 0.0)
