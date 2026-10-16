"""The species registry: every kind of fish in the tank, one line each.

Each species has its own modules (docs/species.md):

- tankful/sim/species/<name>.py: its Species (tankful.sim.species.base),
  who of it lives in the tank and how they move, and its rig's pose;
- tools/species/<name>.py: its model.

The sim (stock), the game's fish driver (tankful.game.fishes), the scene
builder (tools/scene_fish.py) and the launcher's scene sources all go
through NAMES, so adding a species is adding its modules and its line
here.  The tank is stocked, and the scene built, in this order.
"""

import importlib

NAMES = (
  'angelfish',
  'neon_tetra',
  'pleco',
)


def module(name):
  """The sim module of the species name."""
  return importlib.import_module('tankful.sim.species.' + name)


def modules():
  return [module(name) for name in NAMES]


def of(species):
  """The sim module of species (a Species): its BONES, pose and scales."""
  return module(species.name)


def stock(tank):
  """Add every species' fish to tank."""
  for mod in modules():
    mod.stock(tank)
  return tank.fish
