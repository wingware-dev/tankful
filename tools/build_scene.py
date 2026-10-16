"""Generate build/tankful.blend procedurally.

Runs inside UPBGE's Blender, not the venv:

  blender -b --factory-startup --python tools/build_scene.py -- [--output PATH]

run_tankful.py does this for you when the scene is missing or older than
its sources.  Run directly with the venv's Python (as Wing's build-scene
entry point does), it finds UPBGE and re-runs itself under Blender.

Coordinates match tankful.sim.tank.Tank: meters, origin at the center of
the tank floor, x to the viewer's right, y away from the viewer (the
camera is at -y, looking along +y) and z up.
"""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT = os.path.join(ROOT, 'build', 'tankful.blend')

# The scene reads its layout from the sim, and scene_env sits beside us
for _path in (ROOT, os.path.dirname(os.path.abspath(__file__))):
  if _path not in sys.path:
    sys.path.insert(0, _path)

from tankful.sim.environment import (  # noqa: E402
  TANK_W, TANK_D, TANK_H, GLASS, WATER_LEVEL)

TRIM = 0.012
WINDOW = (1280, 720)

# The game's entry: run every frame by an Always sensor.  TANKFUL_ROOT is
# set by run_tankful.py; the fallback is the parent of the .blend's dir.
BOOT_SCRIPT = '''\
import os, sys
import bge
_root = os.environ.get('TANKFUL_ROOT') or os.path.normpath(
  bge.logic.expandPath('//..'))
if _root not in sys.path:
  sys.path.insert(0, _root)
from tankful.game import main
main.update(bge.logic.getCurrentController())
'''


def build(output):
  import bpy

  # Clear the factory startup scene by hand: after wm.read_factory_settings
  # the logic brick operators crash Blender in their undo push
  for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                     bpy.data.cameras, bpy.data.lights, bpy.data.worlds):
    for block in list(collection):
      collection.remove(block)
  scene = bpy.context.scene
  scene.name = 'Tank'
  scene.unit_settings.system = 'METRIC'
  setup_render(scene)
  setup_world(scene)

  mats = {
    'glass': material('Glass', (0.85, 0.95, 0.95, 1.0), alpha=0.12,
                      roughness=0.02, specular=0.9),
    'water': material('Water', (0.08, 0.32, 0.36, 1.0), alpha=0.07,
                      roughness=0.1),
    'trim': material('Trim', (0.02, 0.02, 0.02, 1.0), roughness=0.4),
    'stand': material('Stand', (0.09, 0.055, 0.035, 1.0), roughness=0.6),
    'wall': material('Wall', (0.10, 0.11, 0.13, 1.0), roughness=0.9),
  }

  tank = bpy.data.objects.new('Tank', None)
  scene.collection.objects.link(tank)
  import scene_env
  import scene_fish
  scene_env.build_environment(scene, tank, mats)
  scene_fish.build_fish(scene)
  build_glass(scene, tank, mats)
  build_trim(scene, tank, mats['trim'])
  box(scene, 'Water', (0, 0, WATER_LEVEL / 2 + GLASS / 2),
      (TANK_W - 2 * GLASS - 0.002, TANK_D - 2 * GLASS - 0.002,
       WATER_LEVEL - GLASS), mats['water'], parent=tank, shadow=False)
  box(scene, 'Stand', (0, 0, -0.04), (TANK_W + 0.3, TANK_D + 0.2, 0.08),
      mats['stand'])
  box(scene, 'BackWall', (0, TANK_D / 2 + 0.35, 0.6), (6.0, 0.02, 3.0),
      mats['wall'])

  setup_camera(scene)
  setup_light(scene)
  setup_logic(scene)

  os.makedirs(os.path.dirname(output), exist_ok=True)
  bpy.ops.wm.save_as_mainfile(filepath=output, compress=True)
  print('Wrote %s' % output)


def setup_render(scene):
  gs = scene.game_settings
  gs.resolution_x, gs.resolution_y = WINDOW
  gs.use_desktop = False
  gs.show_fullscreen = False
  gs.vsync = 'ON'
  gs.show_mouse = True
  gs.use_auto_start = False
  gs.exit_key = 'ESC'
  scene.render.resolution_x, scene.render.resolution_y = WINDOW
  ee = scene.eevee
  # The player accumulates samples over frames (TAA), which is what makes
  # soft shadows clean: two shadow rays and eight steps per frame, plus the
  # light's filter (setup_light), converge without grain and hold 60 fps.
  # One ray leaves the shadows grainy; four halve the frame rate.  The
  # same accumulation smears shading that changes fast, which is why the
  # caustics evolve slowly (tankful/game/scenery.py)
  for attr, value in (('taa_render_samples', 16), ('taa_samples', 8),
                      ('use_taa_reprojection', True), ('use_shadows', True),
                      ('shadow_ray_count', 2), ('shadow_step_count', 8)):
    if hasattr(ee, attr):
      setattr(ee, attr, value)


def setup_world(scene):
  import bpy
  world = bpy.data.worlds.new('Room')
  world.use_nodes = True
  bg = world.node_tree.nodes['Background']
  bg.inputs['Color'].default_value = (0.05, 0.06, 0.08, 1.0)
  bg.inputs['Strength'].default_value = 1.0
  scene.world = world


def material(name, color, alpha=1.0, roughness=0.5, specular=0.5):
  import bpy
  mat = bpy.data.materials.new(name)
  mat.use_nodes = True
  bsdf = mat.node_tree.nodes['Principled BSDF']
  bsdf.inputs['Base Color'].default_value = color
  bsdf.inputs['Roughness'].default_value = roughness
  bsdf.inputs['Alpha'].default_value = alpha
  if 'Specular IOR Level' in bsdf.inputs:
    bsdf.inputs['Specular IOR Level'].default_value = specular
  mat.diffuse_color = color[:3] + (alpha,)
  if alpha < 1.0:
    if hasattr(mat, 'surface_render_method'):
      mat.surface_render_method = 'BLENDED'
    else:
      mat.blend_method = 'BLEND'
    if hasattr(mat, 'use_transparency_overlap'):
      mat.use_transparency_overlap = True
    mat.use_backface_culling = False
  return mat


def box(scene, name, center, size, mat, parent=None, shadow=True):
  import bpy
  import bmesh
  mesh = bpy.data.meshes.new(name)
  bm = bmesh.new()
  bmesh.ops.create_cube(bm, size=1.0)
  bmesh.ops.scale(bm, vec=size, verts=bm.verts)
  bm.to_mesh(mesh)
  bm.free()
  mesh.materials.append(mat)
  obj = bpy.data.objects.new(name, mesh)
  obj.location = center
  obj.game.physics_type = 'NO_COLLISION'
  obj.visible_shadow = shadow
  scene.collection.objects.link(obj)
  if parent is not None:
    obj.parent = parent
  return obj


def build_glass(scene, tank, mats):
  w, d, h, g = TANK_W, TANK_D, TANK_H, GLASS
  panes = {
    'GlassFront': ((0, -d / 2 + g / 2, h / 2), (w, g, h)),
    'GlassBack': ((0, d / 2 - g / 2, h / 2), (w, g, h)),
    'GlassLeft': ((-w / 2 + g / 2, 0, h / 2), (g, d - 2 * g, h)),
    'GlassRight': ((w / 2 - g / 2, 0, h / 2), (g, d - 2 * g, h)),
    'GlassBottom': ((0, 0, g / 2), (w - 2 * g, d - 2 * g, g)),
  }
  for name, (center, size) in panes.items():
    # The front pane, the one the viewer looks through, catches sheens
    mat = mats['glass_front'] if name == 'GlassFront' else mats['glass']
    box(scene, name, center, size, mat, parent=tank, shadow=False)


def build_trim(scene, tank, mat):
  """Black edge trim around the top and bottom rims and the corners."""
  w, d, h, t = TANK_W, TANK_D, TANK_H, TRIM
  for z in (t / 2, h - t / 2):
    for y in (-d / 2, d / 2):
      box(scene, 'Trim', (0, y, z), (w + t, t, t), mat, parent=tank)
    for x in (-w / 2, w / 2):
      box(scene, 'Trim', (x, 0, z), (t, d + t, t), mat, parent=tank)
  for x in (-w / 2, w / 2):
    for y in (-d / 2, d / 2):
      box(scene, 'Trim', (x, y, h / 2), (t, t, h), mat, parent=tank)


def setup_camera(scene):
  import bpy
  cam_data = bpy.data.cameras.new('Camera')
  cam_data.lens = 35
  cam_data.clip_start = 0.05
  cam_data.clip_end = 50
  cam = bpy.data.objects.new('Camera', cam_data)
  cam.location = (0, -TANK_D / 2 - 1.25, TANK_H * 0.55)
  # Looking along +y at the front glass, tilted down slightly, so +x is
  # to the right of the screen
  cam.rotation_euler = (math.radians(87), 0, 0)
  scene.collection.objects.link(cam)
  scene.camera = cam
  # The 0.50 player renders through the saved 3D viewport (as its
  # __default__cam__) unless that viewport looks through the camera
  for screen in bpy.data.screens:
    for area in screen.areas:
      for space in area.spaces:
        if space.type == 'VIEW_3D':
          space.region_3d.view_perspective = 'CAMERA'


def setup_light(scene):
  import bpy
  data = bpy.data.lights.new('TankLight', 'AREA')
  data.shape = 'RECTANGLE'
  data.size, data.size_y = TANK_W * 0.9, TANK_D * 0.6
  data.energy = 20
  data.color = (1.0, 0.97, 0.9)
  data.use_shadow = True
  # Blurs the shadow map lookups, which hides the remaining noise of the
  # soft shadow's few rays (see setup_render)
  data.shadow_filter_radius = 4.0
  light = bpy.data.objects.new('TankLight', data)
  light.location = (0, 0, TANK_H + 0.35)
  scene.collection.objects.link(light)


def setup_logic(scene):
  """An empty whose Always sensor runs the boot script every frame."""
  import bpy
  text = bpy.data.texts.new('tankful_boot.py')
  text.from_string(BOOT_SCRIPT)
  ctl = bpy.data.objects.new('Controller', None)
  scene.collection.objects.link(ctl)
  # The logic operators insist on an active object even when given one,
  # and in background mode crash in their own undo push unless the undo
  # stack already has a step (UPBGE 0.50)
  bpy.ops.ed.undo_push(message='build_scene')
  with bpy.context.temp_override(object=ctl, active_object=ctl):
    bpy.ops.logic.sensor_add(type='ALWAYS', name='EveryFrame',
                             object=ctl.name)
    bpy.ops.logic.controller_add(type='PYTHON', name='Boot', object=ctl.name)
  sensor = ctl.game.sensors['EveryFrame']
  sensor.use_pulse_true_level = True
  if hasattr(sensor, 'tick_skip'):
    sensor.tick_skip = 0
  controller = ctl.game.controllers['Boot']
  controller.mode = 'SCRIPT'
  controller.text = text
  controller.link(sensor=sensor)


def blender_argv():
  argv = sys.argv
  return argv[argv.index('--') + 1:] if '--' in argv else []


def parse_args(argv):
  import argparse
  parser = argparse.ArgumentParser(prog='build_scene.py')
  parser.add_argument('--output', default=DEFAULT_OUTPUT)
  return parser.parse_args(argv)


def main_in_blender():
  args = parse_args(blender_argv())
  build(os.path.abspath(args.output))


def main_outside_blender(argv=None):
  # Accept the in-Blender form's '--' too, so both command lines work
  argv = sys.argv[1:] if argv is None else argv
  args = parse_args(argv[1:] if argv[:1] == ['--'] else argv)
  sys.path.insert(0, ROOT)
  from tankful import launcher
  return launcher.build_scene(launcher.find_upbge(), force=True,
                              output=os.path.abspath(args.output))


if __name__ == '__main__':
  try:
    import bpy  # noqa: F401
  except ImportError:
    sys.exit(main_outside_blender())
  main_in_blender()
