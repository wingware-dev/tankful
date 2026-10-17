"""Angelfish: tall, disc-bodied fish that glide slowly round the decor.

Each is a tankful.sim.fish.Fish.  The rig (tools/species/angelfish.py)
is the spine chain of tankful.sim.swim with the fin bones on it:

  Head -> Spine.0 -> Spine.1 -> Spine.2 -> Tail
  Head -> Pec.L, Pec.R, Pelvic.L, Pelvic.R
  Spine.0 -> Dorsal, Anal

The pectorals scull when hovering and fold back when cruising; the tall
fins sway behind the body's motion, and the pelvic threads trail back
with speed.
"""

import math

from tankful.sim import fish as sim_fish
from tankful.sim import swim
from tankful.sim.daynight import Night
from tankful.sim.species.base import Resident, Species

SPECIES = Species(
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
  # At night they drift slowly down among the plants and hover there
  night=Night(speed=0.45, depth_band=(0.25, 0.6), hover=5.0, hover_time=2.0,
              plants=1.2),
)

FINS = ('Pec.L', 'Pec.R', 'Pelvic.L', 'Pelvic.R', 'Dorsal', 'Anal')
BONES = ('Head',) + swim.SPINE + FINS


def residents():
  """The angelfish in the tank."""
  return [
    Resident('Angelfish.0', SPECIES, 1.0, 101, (-0.18, -0.05, 0.30, 0.3)),
    Resident('Angelfish.1', SPECIES, 0.9, 202, (0.14, 0.0, 0.26, 2.8)),
  ]


def stock(tank):
  return sim_fish.stock(tank, residents())


def pose(fish):
  """{bone: (rx, ry, rz)} for fish now."""
  angles = swim.spine_pose(fish)

  # Pectorals: folded along the body when cruising, sculling alternately
  # when hovering, feathering as they go
  hover = fish.hovering
  amp = fish.fin_amp
  for name, side, offset in (('Pec.L', 1.0, 0.0), ('Pec.R', -1.0, 2.7)):
    p = fish.fin_phase + offset
    spread = 0.12 + 0.35 * hover + amp * 0.5 * (1 + math.sin(p))
    angles[name] = (0.0, side * 0.5 * amp * math.cos(p), -side * spread)

  # Dorsal and anal fins: sway behind the body's swing, a little more
  # when the body is still and the fin ripple carries the motion
  sway = (fish.wave * 0.35 * math.sin(fish.beat_phase - 2.2)
          + 0.04 * hover * math.sin(fish.fin_phase * 0.5))
  angles['Dorsal'] = (0.0, 0.0, sway)
  angles['Anal'] = (0.0, 0.0, -sway)

  # Pelvic threads: swept back by speed, swaying slowly
  pace = min(1.0, fish.speed / max(fish.cruise_speed, 1e-6))
  for name, offset in (('Pelvic.L', 0.0), ('Pelvic.R', 1.3)):
    s = math.sin(0.5 * fish.beat_phase + offset)
    angles[name] = (0.35 * pace + 0.06 * s, 0.0, 0.05 * s)
  return angles


def scales(fish):
  """{bone: (sx, sy, sz)}: no bone scales."""
  return {}
