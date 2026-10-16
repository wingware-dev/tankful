"""Species: how each kind of fish is built and how it moves.

The sim (tankful.sim.fish), the swim animation (tankful.sim.swim) and the
model generator (tools/scene_fish.py) all read these, so a fish's size
and gait have a single source.  Lengths are meters, times seconds,
angles radians.
"""

import collections
import math

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
))

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

SPECIES = {s.name: s for s in (ANGELFISH,)}

Resident = collections.namedtuple('Resident', 'name species size seed start')


def residents():
  """The fish in the tank: their object names, sizes and start points.

  size scales the species' length; start is (x, y, z, heading).
  """
  return [
    Resident('Angelfish.0', ANGELFISH, 1.0, 101, (-0.18, -0.05, 0.30, 0.3)),
    Resident('Angelfish.1', ANGELFISH, 0.9, 202, (0.14, 0.0, 0.26, 2.8)),
  ]
