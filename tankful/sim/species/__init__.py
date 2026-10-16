"""The species registry: every kind of fish in the tank, one line each.

Each species has its own modules (docs/species.md):

- tankful/sim/species/<name>.py: its Species (tankful.sim.species.base),
  who of it lives in the tank and how they move, and its rig's pose;
- tools/species/<name>.py: its model.

The sim (stock), the game's fish driver (tankful.game.fishes), the scene
builder (tools/scene_fish.py) and the launcher's scene sources all go
through present(), the names in NAMES whose two modules both exist.  A
species is listed here before its modules are written, so the tasks
that write them don't all edit this file: until both exist it is
skipped, and logged once.  The tank is stocked, and the scene built, in
this order.
"""

import importlib
import logging
import os

log = logging.getLogger('tankful.species')

NAMES = (
  'angelfish',
  'neon_tetra',
  'pleco',
  'corydoras',
  'guppy',
  'honey_gourami',
  'cherry_shrimp',
)

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SIM_DIR)))
MODEL_DIR = os.path.join(ROOT, 'tools', 'species')

_skipped = set()


def sim_path(name):
  return os.path.join(SIM_DIR, name + '.py')


def model_path(name):
  return os.path.join(MODEL_DIR, name + '.py')


def missing(name):
  """The paths of name's modules that don't exist yet."""
  return [p for p in (sim_path(name), model_path(name))
          if not os.path.isfile(p)]


def present(names=None):
  """The names (by default NAMES) whose sim and model modules both
  exist, in order.  Each one skipped is logged, once per process."""
  out = []
  for name in NAMES if names is None else names:
    gone = missing(name)
    if not gone:
      out.append(name)
    elif name not in _skipped:
      _skipped.add(name)
      log.info('skipping species %s: no %s', name,
               ', '.join(os.path.relpath(p, ROOT) for p in gone))
  return out


def module(name):
  """The sim module of the species name."""
  return importlib.import_module('tankful.sim.species.' + name)


def modules():
  return [module(name) for name in present()]


def of(species):
  """The sim module of species (a Species): its BONES, pose and scales."""
  return module(species.name)


def stock(tank):
  """Add every present species' fish to tank."""
  for mod in modules():
    mod.stock(tank)
  return tank.fish
