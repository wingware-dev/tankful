"""Neon tetras: small, quick and slender, kept in a school
(tankful.sim.school) that holds the middle of the water.

The rig (tools/species/neon_tetra.py) is the spine chain alone, as the
fins are too small to show strokes of their own.
"""

import math

from tankful.sim import school as sim_school
from tankful.sim import swim
from tankful.sim.daynight import Night
from tankful.sim.species.base import Species

SPECIES = Species(
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
  turn_accel=14.0, roll_rate=2.5,
  flick_chance=0.07, flick_turn=0.9,
  # At night the school slows, loosens and rests low over the sand
  night=Night(speed=0.4, depth_band=(0.0, 0.18), activity=0.2, loosen=1.8),
)

BONES = ('Head',) + swim.SPINE


def schools():
  """The schools of neon tetras in the tank."""
  return [sim_school.SchoolSpec('NeonTetras', SPECIES, 15, 404,
                                (0.12, -0.04, 0.22, 3.0))]


def stock(tank):
  return sim_school.stock(tank, schools())


def pose(fish):
  """{bone: (rx, ry, rz)} for fish now: the spine alone."""
  return swim.spine_pose(fish)


def scales(fish):
  """{bone: (sx, sy, sz)}: no bone scales."""
  return {}
