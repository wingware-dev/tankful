"""The tank's fixed scenery: sand, decor, plants and the airstone.

Both tools/build_scene.py (which makes the meshes) and the game (which
animates plants and bubbles, and later steers fish around the decor) read
the layout from here, so it has a single source.  Everything is
deterministic, so a rebuilt scene matches the running sim.

Coordinates match tankful.sim.tank.Tank: meters, origin at the center of
the tank floor, x to the viewer's right, y away from the viewer (toward
the back glass) and z up.
"""

import collections
import math
import random

TANK_W, TANK_D, TANK_H = 1.0, 0.4, 0.5
GLASS = 0.006
WATER_LEVEL = TANK_H - 0.04

# The inside of the glass
INNER_X = TANK_W / 2 - GLASS
INNER_Y = TANK_D / 2 - GLASS

# Sand depth at the front and back glass: the bed slopes up toward the back
SAND_FRONT = 0.032
SAND_BACK = 0.085

Rock = collections.namedtuple('Rock', 'name x y size yaw seed')
Driftwood = collections.namedtuple('Driftwood', 'name x y yaw seed')
Plant = collections.namedtuple(
  'Plant', 'name kind x y height count seed phase amplitude frequency')

# Plant kinds: the bones per leaf chain, and whether it sways much
PLANT_BONES = {'vallisneria': 4, 'sword': 3, 'moss': 1}


def _smoothstep(t):
  t = min(1.0, max(0.0, t))
  return t * t * (3 - 2 * t)


def sand_height(x, y):
  """The height of the sand surface above the tank floor at x, y.

  A slope from SAND_FRONT at the front glass to SAND_BACK at the back,
  with low dunes and ripples on top.  Defined for any x, y; the build
  samples it across the inside of the tank.
  """
  back = _smoothstep((y + INNER_Y) / (2 * INNER_Y))
  h = SAND_FRONT + (SAND_BACK - SAND_FRONT) * back
  # Broad dunes, then fine ripples running roughly across the tank
  h += 0.006 * math.sin(4.1 * x + 1.3) * math.cos(6.3 * y - 0.4)
  h += 0.004 * math.sin(7.7 * x - 2.0 * y + 0.7)
  h += 0.0012 * math.sin(55.0 * x + 9.0 * y + 3.0 * math.sin(5.0 * x))
  # A gentle mound under the decor on the left
  dx, dy = x + 0.28, y - 0.06
  h += 0.012 * math.exp(-(dx * dx + dy * dy) / 0.012)
  return h


def rocks():
  return [
    Rock('Rock.BackLeft', -0.33, 0.12, (0.13, 0.10, 0.11), 0.4, 11),
    Rock('Rock.Left', -0.21, 0.04, (0.085, 0.07, 0.065), 1.9, 12),
    Rock('Rock.Pebble1', -0.13, -0.05, (0.04, 0.035, 0.025), 0.7, 13),
    Rock('Rock.Right', 0.27, 0.10, (0.10, 0.08, 0.075), 2.6, 14),
    Rock('Rock.Pebble2', 0.33, -0.03, (0.035, 0.03, 0.02), 1.1, 15),
  ]


def driftwood():
  return [Driftwood('Driftwood', 0.06, 0.06, 0.35, 21)]


def plants():
  """The plants, back to front.  count is the leaves (or moss lumps)."""
  rng = random.Random(7)
  out = []

  def add(kind, name, x, y, height, count, amplitude, frequency):
    out.append(Plant(name, kind, x, y, height, count, rng.randrange(1 << 16),
                     rng.uniform(0, 2 * math.pi), amplitude, frequency))

  # Vallisneria: tall ribbons along the back, thicker in the corners
  for i, (x, y, n) in enumerate(((-0.42, 0.15, 12), (-0.30, 0.165, 9),
                                 (-0.12, 0.17, 8), (0.18, 0.165, 9),
                                 (0.42, 0.14, 12))):
    add('vallisneria', 'Vallisneria.%d' % i, x, y,
        rng.uniform(0.33, 0.40), n, 0.16, rng.uniform(0.28, 0.36))
  # Amazon swords: broad rosettes in the midground
  for i, (x, y) in enumerate(((-0.07, 0.10), (0.36, 0.03))):
    add('sword', 'Sword.%d' % i, x, y, rng.uniform(0.17, 0.21), 11,
        0.06, rng.uniform(0.22, 0.28))
  # Moss: low clumps on the sand and against the decor
  for i, (x, y) in enumerate(((-0.25, -0.06), (-0.04, -0.02), (0.20, -0.05),
                              (0.12, 0.11), (-0.40, -0.02))):
    add('moss', 'Moss.%d' % i, x, y, rng.uniform(0.025, 0.04), 14,
        0.03, rng.uniform(0.25, 0.4))
  return out


# The airstone sits near the back, in the gap between two vallisneria
# clumps, so its stream rises in plain view
AIRSTONE_XY = (0.30, 0.165)
AIRSTONE_SIZE = (0.05, 0.022, 0.016)


def airstone_position():
  """The point bubbles leave the airstone from."""
  x, y = AIRSTONE_XY
  return (x, y, sand_height(x, y) + AIRSTONE_SIZE[2] * 0.9)


def inside(x, y, margin=0.0):
  """Whether x, y is within the glass, margin meters from it."""
  return abs(x) <= INNER_X - margin and abs(y) <= INNER_Y - margin


# Spots on the decor where a pleco (tankful.sim.species.pleco) can cling: the
# point its belly rests on and the surface's normal there.  The rocks are
# lumpy (tools/scene_env.py, build_rocks), so these were measured on the
# built meshes: a plane fitted over a pleco-sized patch of each top, the
# point raised to clear most of the bumps.  tools/species/pleco.py checks
# them against the meshes when it builds the scene.
Perch = collections.namedtuple('Perch', 'name obstacle point normal')


def perches():
  return [
    Perch('Rock.Right.Top', 'Rock.Right', (0.27, 0.10, 0.132),
          (-0.133, -0.062, 0.989)),
    Perch('Rock.BackLeft.Top', 'Rock.BackLeft', (-0.33, 0.12, 0.155),
          (0.075, -0.049, 0.996)),
  ]


# Decor obstacles for the fish: capsules (a segment with a radius) that
# wrap each rock, the driftwood's trunk and branches, and each plant clump
# from the sand up.  Plants are soft (fish brush past leaves) so the game
# lets fish closer to them than to wood and stone.
Obstacle = collections.namedtuple('Obstacle', 'name a b radius soft')

# The driftwood, in its own space before yaw: the trunk and the two
# branches that reach into open water (tools/scene_env.py, build_driftwood)
_WOOD_PARTS = (
  ((-0.18, -0.02, 0.016), (0.17, 0.03, 0.035), 0.034),
  ((-0.07, 0.0, 0.025), (-0.11, 0.05, 0.25), 0.022),
  ((0.04, 0.01, 0.03), (0.11, -0.02, 0.18), 0.018),
)
# How far each plant kind's leaves spread from its base, as a fraction of
# its height
_PLANT_SPREAD = {'vallisneria': 0.12, 'sword': 0.42, 'moss': 1.2}


def obstacles():
  out = []
  for rock in rocks():
    sx, sy, sz = rock.size
    z = sand_height(rock.x, rock.y) + sz * 0.18
    # The mesh is the ellipsoid of rock.size, bumped out by up to a third
    r = 0.55 * max(sx, sy)
    top = (rock.x, rock.y, z + max(0.0, 0.6 * sz - r))
    out.append(Obstacle(rock.name, (rock.x, rock.y, z), top, r, False))
  for wood in driftwood():
    c, s = math.cos(wood.yaw), math.sin(wood.yaw)
    base = sand_height(wood.x, wood.y) - 0.008

    def place(p):
      return (wood.x + c * p[0] - s * p[1], wood.y + s * p[0] + c * p[1],
              base + p[2])
    for i, (a, b, r) in enumerate(_WOOD_PARTS):
      out.append(Obstacle('%s.%d' % (wood.name, i), place(a), place(b), r,
                          False))
  for plant in plants():
    z = sand_height(plant.x, plant.y)
    r = max(0.012, _PLANT_SPREAD[plant.kind] * plant.height)
    out.append(Obstacle(plant.name, (plant.x, plant.y, z),
                        (plant.x, plant.y, z + plant.height * 0.95), r, True))
  return out
