"""Selecting a fish with the mouse and steering it with the arrow keys.

Steering (one per App, tankful.game.main) feeds the user's clicks and
arrow keys to the sim's tankful.sim.steering.Control, and shows which
fish is current:

- A left click casts a ray from the camera through the mouse (screen_ray)
  against each fish's proxy, an ellipsoid round its body in its own
  frame (proxy), as the meshes' bounds are their rest pose at the
  origin.  The nearest fish hit selects its group (a school, shoal or
  colony, as tankful.sim.school.group_of gives it); a click on empty
  water deselects.  A click the light switch or the factor menu took is
  left alone, and the arrows are the menu's while it is open.
- The arrow keys down are the Control's keys each frame; it steers the
  current group and blends it back to its own swimming once they are up.
- The current fish are drawn SELECTED_SCALE larger (their rig, or for a
  school member its Root bone; tankful.game.fishes.Fishes.set_scale),
  their shadows as before, with their group's outline shown: <group>.Outline,
  an inverted hull of the body in faint, glowing yellow, skinned to the
  same rig (build_outlines in tools/scene_fish.py).

Only the selection's change touches the scene, so a selected fish costs
nothing per frame.
"""

import logging
import math

from tankful.game import fishes as game_fishes
from tankful.sim import school as sim_school
from tankful.sim import steering
from tankful.sim import vec

log = logging.getLogger('tankful.steering')

SELECTED_SCALE = 1.1
OUTLINE_SUFFIX = '.Outline'
# A fish's proxy: its body's height as a fraction of the species' (which
# counts the fins), and how much bigger than its body it is all round
# (m), so a small fish is easy to hit
BODY_HEIGHT = 0.75
PICK_PAD = 0.004


def group_key(fish):
  """The name of what selecting fish selects: its group's, or its own,
  as the model names that rig (<key>.Rig) and its outline."""
  return sim_school.group_of(fish).name


# Picking

def screen_ray(px, py, window, cam_pos, cam_rot, projection):
  """(origin, unit direction) of the ray from the camera through window
  pixel px, py (top left origin).  cam_rot: the camera's 3x3 world
  rotation as rows, its columns the camera's x (right), y (up) and z
  (back) axes; projection: its 4x4 projection matrix as rows."""
  w, h = window
  nx = 2.0 * px / w - 1.0
  ny = 1.0 - 2.0 * py / h
  p = projection
  if abs(p[3][3]) > 0.5:
    # Orthographic: parallel rays from the view plane
    ox = (nx - p[0][3]) / p[0][0]
    oy = (ny - p[1][3]) / p[1][1]
    origin = tuple(cam_pos[i] + cam_rot[i][0] * ox + cam_rot[i][1] * oy
                   for i in range(3))
    d = tuple(-cam_rot[i][2] for i in range(3))
    return origin, vec.normalized(d)
  # Perspective: the view-space direction through the point at z = -1
  vx = (nx + p[0][2]) / p[0][0]
  vy = (ny + p[1][2]) / p[1][1]
  d = tuple(cam_rot[i][0] * vx + cam_rot[i][1] * vy - cam_rot[i][2]
            for i in range(3))
  return tuple(cam_pos), vec.normalized(d)


def proxy(f):
  """f's pick proxy: (center, rotation rows from its space to the
  world's, (semi-axes along its forward, left and back))."""
  length = f.length
  width = length * game_fishes.SHADOW_WIDTH.get(
    f.species.name, game_fishes.DEFAULT_SHADOW_WIDTH)
  height = f.species.height * getattr(f, 'size', 1.0) * BODY_HEIGHT
  return ((f.x, f.y, f.z), f.orientation(),
          (0.5 * length + PICK_PAD, 0.5 * width + PICK_PAD,
           0.5 * height + PICK_PAD))


def ray_hit(origin, direction, center, rot, axes):
  """How far along the ray (origin, unit direction) it first meets the
  ellipsoid (center, rot, axes) as proxy gives it, or None.  A ray from
  inside it meets it at 0."""
  off = vec.sub(origin, center)
  # Into the ellipsoid's space, where it is the unit sphere
  o = [sum(rot[i][j] * off[i] for i in range(3)) / axes[j] for j in range(3)]
  d = [sum(rot[i][j] * direction[i] for i in range(3)) / axes[j]
       for j in range(3)]
  a = sum(v * v for v in d)
  b = 2.0 * sum(o[j] * d[j] for j in range(3))
  c = sum(v * v for v in o) - 1.0
  if c <= 0:
    return 0.0
  disc = b * b - 4 * a * c
  if a < 1e-12 or disc < 0:
    return None
  t = (-b - math.sqrt(disc)) / (2 * a)
  return t if t >= 0 else None


def pick(origin, direction, fish):
  """The fish of fish whose proxy the ray meets nearest, or None."""
  best = None
  for f in fish:
    t = ray_hit(origin, direction, *proxy(f))
    if t is not None and (best is None or t < best[0]):
      best = (t, f)
  return best[1] if best else None


def _rows(matrix, n):
  return tuple(tuple(matrix[i][j] for j in range(n)) for i in range(n))


class Steering:

  def __init__(self, scene, tank, fishes):
    self.scene = scene
    self.tank = tank
    self.fishes = fishes
    self.control = steering.Control()
    self.keys = []
    # The pickable fish: those the scene has a rig for
    drawn = fishes.drawn()
    self.fish = [f for f in tank.fish if f in drawn]
    self.outlines = {}
    for key in sorted({group_key(f) for f in self.fish}):
      obj = scene.objects.get(key + OUTLINE_SUFFIX)
      if obj is None:
        log.warning('no %s%s: its selection shows no outline', key,
                    OUTLINE_SUFFIX)
        continue
      obj.visible = False
      self.outlines[key] = obj
    self._shown = None
    self._window = None

  def frame(self, state, window, dt, taken=None, keys=True):
    """Take this frame's input (state, a tankful.game.input.InputState,
    in a window of (width, height) pixels) and advance the Control by
    dt, before the tank steps.  taken(x, y), if given, says whether a
    click there was another control's (the light switch, the factor
    menu), which it leaves alone; keys=False leaves the arrows to
    another control, as if none were down."""
    self._window = window
    for x, y, button in state.clicks():
      if button == 'left' and not (taken is not None and taken(x, y)):
        self.click(x, y, window)
    self.keys = ([k for k in steering.ARROWS if state.is_down(k)]
                 if keys else [])
    self.control.update(dt, self.keys)

  def click(self, x, y, window):
    """Select what the click at window pixel x, y hits, or nothing."""
    cam = self.scene.active_camera
    if cam is None:
      return None
    origin, direction = screen_ray(
      x, y, window, tuple(cam.worldPosition), _rows(cam.worldOrientation, 3),
      _rows(cam.projection_matrix, 4))
    hit = pick(origin, direction, self.fish)
    group = sim_school.group_of(hit) if hit is not None else None
    self.control.select(group)
    log.info('selected %s', getattr(group, 'name', None))
    return hit

  def show(self):
    """Show the current selection on the fish, after they are posed: only
    when it changed."""
    current = self.control.selected
    if current is self._shown:
      return
    self._highlight(self._shown, False)
    self._highlight(current, True)
    self._shown = current

  def _highlight(self, group, on):
    if group is None:
      return
    scale = SELECTED_SCALE if on else 1.0
    members = [f for f in self.fish if sim_school.group_of(f) is group]
    for f in members:
      self.fishes.set_scale(f, scale)
    outline = self.outlines.get(group.name)
    if outline is not None:
      outline.visible = on

  def snapshot(self):
    snap = self.control.snapshot()
    snap['keys'] = list(self.keys)
    snap['outline'] = (self._shown is not None
                       and self._shown.name in self.outlines
                       and bool(self.outlines[self._shown.name].visible))
    snap['screen'] = self.screen_positions()
    return snap

  def screen_positions(self):
    """{fish name: [x, y]}, where each fish is in window pixels, for
    harness scripts to click on; {} before the first frame."""
    cam = self.scene.active_camera
    if cam is None or self._window is None:
      return {}
    w, h = self._window
    out = {}
    for f in self.fish:
      sx, sy = cam.getScreenPosition([f.x, f.y, f.z])
      out[f.name] = [round(sx * w), round(sy * h)]
    return out
