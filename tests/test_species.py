import os
import unittest

from tankful import launcher
from tankful.sim import species
from tankful.sim import swim
from tankful.sim.species.base import Species
from tankful.sim.tank import Tank

DT = 1 / 60.0


class RegistryTests(unittest.TestCase):

  def test_each_species_has_its_modules(self):
    self.assertEqual(len(set(species.NAMES)), len(species.NAMES))
    for name in species.NAMES:
      mod = species.module(name)
      self.assertIsInstance(mod.SPECIES, Species)
      # Its Species names its module, which is how the game finds its pose
      self.assertEqual(mod.SPECIES.name, name)
      self.assertIs(species.of(mod.SPECIES), mod)
      for attr in ('BONES', 'pose', 'scales', 'stock'):
        self.assertTrue(hasattr(mod, attr), '%s.%s' % (name, attr))
      # Every rig has the spine chain the swim wave drives
      self.assertEqual(tuple(mod.BONES[:5]), ('Head',) + swim.SPINE, name)
      builder = os.path.join(launcher.ROOT, 'tools', 'species', name + '.py')
      self.assertTrue(os.path.isfile(builder), builder)

  def test_stock_in_registry_order(self):
    tank = Tank()
    fish = species.stock(tank)
    self.assertIs(fish, tank.fish)
    names = [f.species.name for f in tank.fish]
    # Each species' fish together, in the order of NAMES
    order = [n for i, n in enumerate(names) if i == 0 or names[i - 1] != n]
    self.assertEqual(order, list(species.NAMES))
    self.assertEqual(len({f.name for f in tank.fish}), len(tank.fish))
    self.assertEqual([s.name for s in tank.schools], ['NeonTetras'])

  def test_the_tank_as_before(self):
    # The stocking the game did before the registry: the angelfish, the
    # school, then the pleco
    tank = Tank()
    species.stock(tank)
    self.assertEqual([f.name for f in tank.fish[:2]],
                     ['Angelfish.0', 'Angelfish.1'])
    self.assertEqual([f.name for f in tank.fish[2:17]],
                     ['NeonTetra.%02d' % i for i in range(15)])
    self.assertEqual([f.name for f in tank.fish[17:]], ['Pleco'])

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

  def test_scene_sources_have_every_species(self):
    sources = set(launcher.SCENE_SOURCES)
    for name in species.NAMES:
      self.assertIn(os.path.join(launcher.ROOT, 'tools', 'species',
                                 name + '.py'), sources)
      self.assertIn(os.path.join(launcher.ROOT, 'tankful', 'sim', 'species',
                                 name + '.py'), sources)

  def test_species_sources(self):
    self.assertEqual(
      launcher.species_sources(('guppy',)),
      (os.path.join(launcher.ROOT, 'tools', 'species', 'guppy.py'),
       os.path.join(launcher.ROOT, 'tankful', 'sim', 'species', 'guppy.py')))


if __name__ == '__main__':
  unittest.main()
