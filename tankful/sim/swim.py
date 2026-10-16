"""The swim animation: each bone's rotation for a fish's gait right now.

The rig (tools/scene_fish.py) is a spine chain from the head back to the
tail fin, with fin bones on it:

  Head -> Spine.0 -> Spine.1 -> Spine.2 -> Tail
  Head -> Pec.L, Pec.R, Pelvic.L, Pelvic.R
  Spine.0 -> Dorsal, Anal

Every bone is made with roll 0, so for the spine, which points back along
the fish, bone z is the fish's up and a positive z rotation swings the
bones behind toward the fish's right (-y).

A traveling wave runs down the spine (body and caudal undulation): it
grows toward the tail and lags along it, and its frequency and swing are
the fish's (tankful.sim.fish: beat_freq, wave).  A turn bends the whole
spine into the curve.  The pectorals scull when hovering and fold back
when cruising; the tall fins sway behind the body's motion, and the
pelvic threads trail back with speed.
"""

import math

SPINE = ('Spine.0', 'Spine.1', 'Spine.2', 'Tail')
FINS = ('Pec.L', 'Pec.R', 'Pelvic.L', 'Pelvic.R', 'Dorsal', 'Anal')
BONES = ('Head',) + SPINE + FINS

# Each spine bone's share of the swing, head to tail: a stiff front and a
# supple rear, as in a disc-bodied fish
ENVELOPE = (0.08, 0.24, 0.55, 1.0)
# The phase lag from one spine bone to the next: about one body wave over
# the length
LAG = 0.9
# How much of a turn bends each spine bone, per rad/s of heading change
BEND = (0.05, 0.07, 0.07, 0.05)
MAX_BEND = 0.5


def bones(species):
  """The bones of the species' rig: all of BONES for the angelfish; the
  spine alone for a small fish whose fins are too small to stroke."""
  return BONES if species.model == 'angelfish' else ('Head',) + SPINE


def spine_angles(wave, phase, yaw_rate=0.0):
  """Each spine bone's rotation about its z, relative to its parent.

  The absolute swing of bone k is wave * ENVELOPE[k] * sin(phase - k LAG):
  the tail's is wave.  A left turn (yaw_rate > 0) curves the body to the
  left, which swings the rear left (negative z).
  """
  out = []
  prev = 0.0
  bend = max(-MAX_BEND, min(MAX_BEND, yaw_rate))
  for k, env in enumerate(ENVELOPE):
    absolute = wave * env * math.sin(phase - k * LAG)
    out.append(absolute - prev - BEND[k] * bend)
    prev = absolute
  return out


def pose(fish):
  """{bone: (rx, ry, rz)} for fish (a tankful.sim.fish.Fish) now."""
  angles = {'Head': (0.0, 0.0, 0.0)}
  for name, rz in zip(SPINE, spine_angles(fish.wave, fish.beat_phase,
                                          fish.yaw_rate)):
    angles[name] = (0.0, 0.0, rz)

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
