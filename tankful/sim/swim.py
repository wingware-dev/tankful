"""The swim wave: the spine's rotations for a fish's gait right now.

Every rig (tools/species/<name>.py) has a spine chain from the head back
to the tail fin, and the species' fin bones on it:

  Head -> Spine.0 -> Spine.1 -> Spine.2 -> Tail

Every bone is made with roll 0, so for the spine, which points back along
the fish, bone z is the fish's up and a positive z rotation swings the
bones behind toward the fish's right (-y).

A traveling wave runs down the spine (body and caudal undulation): it
grows toward the tail and lags along it, and its frequency and swing are
the fish's (tankful.sim.fish: beat_freq, wave).  A turn bends the whole
spine into the curve.  Each species' module poses its fins
(tankful.sim.species.<name>.pose).
"""

import math

SPINE = ('Spine.0', 'Spine.1', 'Spine.2', 'Tail')

# Each spine bone's share of the swing, head to tail: a stiff front and a
# supple rear, as in a disc-bodied fish
ENVELOPE = (0.08, 0.24, 0.55, 1.0)
# The phase lag from one spine bone to the next: about one body wave over
# the length
LAG = 0.9
# How much of a turn bends each spine bone, per rad/s of heading change
BEND = (0.05, 0.07, 0.07, 0.05)
MAX_BEND = 0.5


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


def spine_pose(fish):
  """{bone: (rx, ry, rz)} for the Head and SPINE of fish (a
  tankful.sim.fish.Fish) now: the body wave and the turn."""
  angles = {'Head': (0.0, 0.0, 0.0)}
  for name, rz in zip(SPINE, spine_angles(fish.wave, fish.beat_phase,
                                          fish.yaw_rate)):
    angles[name] = (0.0, 0.0, rz)
  return angles
