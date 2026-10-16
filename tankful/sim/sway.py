"""Plant sway: the bend of each bone in a leaf chain over time.

A slow, gusting current pushes every plant the same way, and a wave
travels up each leaf, so the tips move most and lag the base.  The game
applies the angles to the plant armatures' bones (tankful.game.scenery).
"""

import math


def current(t):
  """The current's strength at time t: a slow, irregular gust, 0.35 to 1."""
  g = math.sin(0.21 * t) * math.sin(0.083 * t + 1.1)
  return 0.675 + 0.325 * g


def chain_angles(t, bones, phase, amplitude, frequency, leaf=0):
  """[(bend_x, bend_y), ...] in radians for each bone, base first.

  bend_x tips the bone toward the viewer and away, bend_y side to side.
  Each bone's bend adds to its parent's, so the tip's total lean is the
  sum, which stays within 1.2 * amplitude on either axis.  leaf offsets
  the phase so the leaves of one plant do not move as one.
  """
  if bones < 1:
    return []
  gust = current(t)
  w = 2 * math.pi * frequency
  p = phase + 1.7 * leaf
  out = []
  # The bend is spread over the chain, weighted toward the tip
  weights = [(i + 1) for i in range(bones)]
  total = float(sum(weights))
  for i, weight in enumerate(weights):
    share = amplitude * weight / total
    lag = 0.55 * i
    side = math.sin(w * t + p - lag) + 0.5 * math.sin(1.9 * w * t + 2 * p - lag)
    fore = math.sin(0.8 * w * t + p + 0.9 - lag)
    out.append((share * gust * fore * (2 / 3.0),
                share * gust * side * (2 / 3.0) + share * 0.5 * (gust - 0.675)))
  return out
