import ast
import os
import types
import unittest
from unittest import mock

from tankful import launcher
from tankful.game.fishes import Fishes
from tankful.sim import species
from tankful.sim import swim
from tankful.sim.species import angelfish
from tankful.sim.species.base import Species
from tankful.sim.tank import Tank

DT = 1 / 60.0
# The species written so far, which must stay present
WRITTEN = ('angelfish', 'neon_tetra', 'pleco')


class RegistryTests(unittest.TestCase):

  def test_names(self):
    self.assertEqual(len(set(species.NAMES)), len(species.NAMES))
    self.assertEqual(species.NAMES[:3], WRITTEN)
    for name in WRITTEN:
      self.assertIn(name, species.present())

  def test_each_sim_module_written_is_complete(self):
    # A species may be listed before its modules are written, but a sim
    # module that exists must have everything the registry's readers use
    for name in species.NAMES:
      if not os.path.isfile(species.sim_path(name)):
        continue
      mod = species.module(name)
      self.assertIsInstance(mod.SPECIES, Species)
      # Its Species names its module, which is how the game finds its pose
      self.assertEqual(mod.SPECIES.name, name)
      self.assertIs(species.of(mod.SPECIES), mod)
      for attr in ('pose', 'scales', 'stock'):
        self.assertTrue(callable(getattr(mod, attr, None)),
                        '%s.%s' % (name, attr))
      # Every rig has the spine chain the swim wave drives
      self.assertEqual(tuple(mod.BONES[:5]), ('Head',) + swim.SPINE, name)

  def test_each_model_module_written_has_build(self):
    # Model modules run only under Blender, so read them without importing
    for name in species.NAMES:
      path = species.model_path(name)
      if not os.path.isfile(path):
        continue
      with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), path)
      builds = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == 'build']
      self.assertEqual(len(builds), 1, path)
      self.assertEqual(builds[0].args.args[0].arg, 'scene', path)

  def test_stock_in_registry_order(self):
    tank = Tank()
    fish = species.stock(tank)
    self.assertIs(fish, tank.fish)
    names = [f.species.name for f in tank.fish]
    # Each species' fish together, in the order of NAMES
    order = [n for i, n in enumerate(names) if i == 0 or names[i - 1] != n]
    self.assertEqual(order, species.present())
    self.assertEqual(len({f.name for f in tank.fish}), len(tank.fish))
    self.assertIn('NeonTetras', [s.name for s in tank.schools])

  def test_the_tank_as_before(self):
    # The stocking the game did before the registry: the angelfish, the
    # school, then the pleco, ahead of any species added since
    tank = Tank()
    species.stock(tank)
    self.assertEqual([f.name for f in tank.fish[:2]],
                     ['Angelfish.0', 'Angelfish.1'])
    self.assertEqual([f.name for f in tank.fish[2:17]],
                     ['NeonTetra.%02d' % i for i in range(15)])
    self.assertEqual(tank.fish[17].name, 'Pleco')

  def test_poses_cover_the_bones(self):
    tank = Tank()
    species.stock(tank)
    for _ in range(30):
      tank.step(DT)
    for f in tank.fish:
      mod = species.of(f.species)
      pose = mod.pose(f)
      for bone in mod.BONES:
        self.assertEqual(len(pose[bone]), 3, '%s %s' % (f.name, bone))
      self.assertLessEqual(set(mod.scales(f)), set(mod.BONES))

  def test_scene_sources_have_every_present_species(self):
    sources = set(launcher.SCENE_SOURCES)
    for name in species.present():
      self.assertIn(os.path.join(launcher.ROOT, 'tools', 'species',
                                 name + '.py'), sources)
      self.assertIn(os.path.join(launcher.ROOT, 'tankful', 'sim', 'species',
                                 name + '.py'), sources)
    # and nothing missing, which would fail every launch
    for path in sources:
      self.assertTrue(os.path.isfile(path), path)


class MissingSpeciesTests(unittest.TestCase):
  """A species listed before its modules are written is skipped."""

  def setUp(self):
    # Each test sees the skip logged afresh
    patcher = mock.patch.object(species, '_skipped', set())
    patcher.start()
    self.addCleanup(patcher.stop)

  def test_paths(self):
    self.assertEqual(species.sim_path('guppy'),
                     os.path.join(launcher.ROOT, 'tankful', 'sim', 'species',
                                  'guppy.py'))
    self.assertEqual(species.model_path('guppy'),
                     os.path.join(launcher.ROOT, 'tools', 'species',
                                  'guppy.py'))
    self.assertEqual(species.missing('pleco'), [])
    self.assertEqual(species.missing('no_such_fish'),
                     [species.sim_path('no_such_fish'),
                      species.model_path('no_such_fish')])

  def test_present_skips_and_logs_once(self):
    names = ('no_such_fish', 'angelfish')
    with self.assertLogs('tankful.species', 'INFO') as logs:
      self.assertEqual(species.present(names), ['angelfish'])
    self.assertEqual(len(logs.output), 1)
    self.assertIn('no_such_fish', logs.output[0])
    self.assertIn(os.path.join('tools', 'species', 'no_such_fish.py'),
                  logs.output[0])
    with self.assertNoLogs('tankful.species'):
      self.assertEqual(species.present(names), ['angelfish'])

  def test_a_species_needs_both_modules(self):
    # Its sim module alone (or model alone) is not enough
    def isfile(path):
      return path != species.model_path('pleco') and os.path.exists(path)
    with mock.patch('os.path.isfile', isfile):
      with self.assertLogs('tankful.species', 'INFO'):
        self.assertEqual(species.present(WRITTEN), ['angelfish',
                                                    'neon_tetra'])

  def test_stock_skips(self):
    with mock.patch.object(species, 'NAMES', ('no_such_fish', 'angelfish')):
      with self.assertLogs('tankful.species', 'INFO'):
        tank = Tank()
        species.stock(tank)
    self.assertEqual([f.name for f in tank.fish],
                     ['Angelfish.0', 'Angelfish.1'])

  def test_species_sources_skip(self):
    with self.assertLogs('tankful.species', 'INFO'):
      sources = launcher.species_sources(('no_such_fish', 'pleco'))
    self.assertEqual(sources, (species.model_path('pleco'),
                               species.sim_path('pleco')))

  def test_fishes_skip(self):
    # A fish of a species not present gets no rig, and no warning for it
    ghost = types.SimpleNamespace(
      name='Ghost', school=None,
      species=angelfish.SPECIES._replace(name='no_such_fish'))
    scene = types.SimpleNamespace(objects={})
    with mock.patch.object(species, 'NAMES', WRITTEN + ('no_such_fish',)), \
         self.assertLogs('tankful.species', 'INFO'):
      with self.assertNoLogs('tankful.fishes'):
        fishes = Fishes(scene, [ghost])
    self.assertEqual(fishes.snapshot(), {'rigs': [], 'school_rigs': [],
                                         'members': 0})


if __name__ == '__main__':
  unittest.main()
