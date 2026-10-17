"""What every species defines: its build and gait (Species), and who of
it lives in the tank (Resident).

Each species module (tankful.sim.species.<name>) makes one Species; the
sim (tankful.sim.fish), the swim animation and the model builder
(tools/species/<name>.py) all read it, so a fish's size and gait have a
single source.  Lengths are meters, times seconds, angles radians.
"""

import collections

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
  # How fast the heading rate may change (rad/s^2), so turns ease in, and
  # how fast the bank follows the turn (rad/s)
  'turn_accel', 'roll_rate',
  # Quick flicks: how often (per second) a fish darts aside, and how far
  # it turns when it does (radians)
  'flick_chance', 'flick_turn',
  # How far below the top of its swim box the surface starts to push the
  # fish down (m); None for tankful.sim.fish.MARGIN, as for the glass and
  # sand.  Surface fish set it smaller, to keep up near the surface
  'surface_margin',
  # How it behaves at full night (tankful.sim.daynight.Night), or None
  # for as by day
  'night',
), defaults=(2.5, 0.7, 0.0, 0.0, None, None))

# One fish: its object name, its Species, its size (which scales the
# species' length), a seed for its noise, and where it starts (x, y, z,
# heading)
Resident = collections.namedtuple('Resident', 'name species size seed start')
