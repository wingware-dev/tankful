"""Species: how each kind of fish is built and how it moves.

The sim (tankful.sim.fish), the swim animation (tankful.sim.swim) and the
model generator (tools/scene_fish.py) all read these, so a fish's size
and gait have a single source.  Lengths are meters, times seconds,
angles radians.
"""

import collections
import math
import random

Species = collections.namedtuple('Species', (
  'name',
  # Snout to the tip of the tail, and fin tip to fin tip top to bottom
  'length', 'height',
  # How near the glass, sand, surface and decor its center may come
  'clear_side', 'clear_up', 'clear_front',
  # Speeds: hovering, cruising and the most it ever swims
  'hover_speed', 'cruise_speed', 'max_speed',
  # Thrust while stroking, and how long a glide takes to lose 63% speed
  'thrust', 'glide_time',
  # The fastest heading change: on the spot, and how tight a turn can be
  'pivot_rate', 'turn_radius', 'max_turn_rate',
  'max_pitch', 'pitch_rate', 'max_bank',
  # The preferred depth, as fractions of the open water from the sand
  # (0) to the surface (1)
  'depth_band',
  # Wander: how fast the heading's noise varies, and how hard it turns
  'wander_frequency', 'wander_turn',
  # Hovering: how often (per second) a fish stops, and for how long
  'hover_chance', 'hover_time',
  # Tail beats per second at rest, plus per body length per second
  'beat_base', 'beat_per_speed',
  # Body wave: the tail's sideways swing (radians, summed over the
  # spine) at the slowest and the fastest stroke
  'wave_min', 'wave_max',
  # Pectoral fin beats per second, and their swing, when hovering
  'fin_beat', 'fin_swing',
  # The model and rig tools/scene_fish.py builds (tankful.sim.swim.bones)
  'model',
  # How fast the heading rate may change (rad/s^2), so turns ease in, and
  # how fast the bank follows the turn (rad/s)
  'turn_accel', 'roll_rate',
  # Quick flicks: how often (per second) a fish darts aside, and how far
  # it turns when it does (radians)
  'flick_chance', 'flick_turn',
), defaults=('angelfish', 2.5, 0.7, 0.0, 0.0))

ANGELFISH = Species(
  name='angelfish',
  length=0.12, height=0.18,
  clear_side=0.06, clear_up=0.09, clear_front=0.07,
  hover_speed=0.005, cruise_speed=0.065, max_speed=0.19,
  thrust=0.11, glide_time=2.2,
  pivot_rate=0.55, turn_radius=0.085, max_turn_rate=1.6,
  max_pitch=math.radians(22), pitch_rate=math.radians(25),
  max_bank=math.radians(16),
  depth_band=(0.4, 0.8),
  wander_frequency=0.07, wander_turn=0.45,
  hover_chance=0.07, hover_time=(3.0, 8.0),
  beat_base=0.9, beat_per_speed=1.6,
  wave_min=0.10, wave_max=0.42,
  fin_beat=2.2, fin_swing=0.55,
)

# Neon tetras: small, quick and slender, kept in a school
# (tankful.sim.school) that holds the middle of the water
NEON_TETRA = Species(
  name='neon_tetra',
  length=0.034, height=0.011,
  clear_side=0.014, clear_up=0.012, clear_front=0.016,
  hover_speed=0.008, cruise_speed=0.07, max_speed=0.32,
  thrust=0.9, glide_time=0.45,
  pivot_rate=1.4, turn_radius=0.025, max_turn_rate=4.5,
  max_pitch=math.radians(28), pitch_rate=math.radians(70),
  max_bank=math.radians(24),
  depth_band=(0.3, 0.62),
  wander_frequency=0.25, wander_turn=0.3,
  hover_chance=0.0, hover_time=(1.0, 2.0),
  beat_base=2.5, beat_per_speed=1.6,
  wave_min=0.16, wave_max=0.5,
  fin_beat=6.0, fin_swing=0.3,
  model='tetra',
  turn_accel=14.0, roll_rate=2.5,
  flick_chance=0.07, flick_turn=0.9,
)

SPECIES = {s.name: s for s in (ANGELFISH, NEON_TETRA)}

Resident = collections.namedtuple('Resident', 'name species size seed start')

# A school: its name, its species, how many, a seed for their sizes and
# places, and where it starts (x, y, z, heading)
SchoolSpec = collections.namedtuple('SchoolSpec',
                                    'name species count seed start')


def residents():
  """The fish in the tank: their object names, sizes and start points.

  size scales the species' length; start is (x, y, z, heading).
  """
  return [
    Resident('Angelfish.0', ANGELFISH, 1.0, 101, (-0.18, -0.05, 0.30, 0.3)),
    Resident('Angelfish.1', ANGELFISH, 0.9, 202, (0.14, 0.0, 0.26, 2.8)),
  ]


def schools():
  """The schools in the tank (tankful.sim.school)."""
  return [SchoolSpec('NeonTetras', NEON_TETRA, 15, 404, (0.12, -0.04, 0.22,
                                                         3.0))]


def school_members(spec):
  """Each member of the school spec as a Resident, around its start.

  The members are spread over a loose ball facing the school's heading,
  with sizes from 0.88 to 1.1 of the species' length.
  """
  rng = random.Random(spec.seed)
  x, y, z, heading = spec.start
  length = spec.species.length
  out = []
  for i in range(spec.count):
    # A spiral of points over a flattened ball, jittered
    a = i * 2.39996
    r = length * 1.4 * math.sqrt(i + 0.5)
    px = x + r * math.cos(a) + rng.uniform(-0.3, 0.3) * length
    py = y + 0.5 * r * math.sin(a) + rng.uniform(-0.3, 0.3) * length
    pz = z + rng.uniform(-1.2, 1.2) * length
    out.append(Resident('%s.%02d' % (spec.species.name.title().replace('_', ''),
                                     i),
                        spec.species, rng.uniform(0.88, 1.1),
                        spec.seed * 100 + i,
                        (px, py, pz, heading + rng.uniform(-0.3, 0.3))))
  return out
