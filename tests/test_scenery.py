import ast
import os
import unittest
from unittest import mock

from tankful import launcher
from tankful.game import scenery


class FakeObjects(list):
  """A scene's objects, as the player's CListValue: a list with get."""

  def get(self, name):
    for obj in self:
      if obj.name == name:
        return obj
    return None


class FakeObject:

  def __init__(self, name, groups=(), position=(0.0, 0.0, 0.0)):
    self.name = name
    self.worldPosition = list(position)
    self.color = (1.0, 1.0, 1.0, 1.0)
    slots = []
    for group in groups:
      node = mock.Mock(bl_idname='ShaderNodeGroup')
      node.node_tree.name = group
      material = mock.Mock()
      material.node_tree.nodes = [mock.Mock(bl_idname='ShaderNodeBsdfPrincipled'),
                                  node]
      slots.append(mock.Mock(material=material))
    if groups:
      self.blenderObject = mock.Mock(material_slots=slots)


def make_scenery(objects):
  pool = mock.Mock(capacity=0)
  with mock.patch.object(scenery.log, 'warning'):
    return scenery.Scenery(mock.Mock(objects=FakeObjects(objects)), pool)


class ReadsGroupTest(unittest.TestCase):

  def test_finds_group_in_any_slot(self):
    obj = FakeObject('Fish', groups=('Other', scenery.FISH_CAUSTIC))
    self.assertTrue(scenery.reads_group(obj, scenery.FISH_CAUSTIC))

  def test_other_groups_do_not_count(self):
    obj = FakeObject('Sand', groups=('CausticProjection',))
    self.assertFalse(scenery.reads_group(obj, scenery.FISH_CAUSTIC))

  def test_object_without_blender_object(self):
    self.assertFalse(scenery.reads_group(FakeObject('Empty'),
                                         scenery.FISH_CAUSTIC))

  def test_empty_slot_and_material_without_nodes(self):
    no_nodes = mock.Mock()
    no_nodes.node_tree = None
    obj = FakeObject('Fish')
    obj.blenderObject = mock.Mock(material_slots=[
      mock.Mock(material=None), mock.Mock(material=no_nodes)])
    self.assertFalse(scenery.reads_group(obj, scenery.FISH_CAUSTIC))


class CausticFollowersTest(unittest.TestCase):

  HOME = (0.0, 0.0, 0.62)

  def setUp(self):
    self.projector = FakeObject(scenery.PROJECTOR, position=self.HOME)
    self.fish = FakeObject('Angelfish.0', groups=(scenery.FISH_CAUSTIC,))
    self.sand = FakeObject('Sand', groups=('CausticProjection',))
    self.scenery = make_scenery([self.projector, self.fish, self.sand])

  def test_only_fish_caustic_readers_follow(self):
    self.assertEqual(self.scenery.caustic_followers, [self.fish])
    self.assertEqual(self.scenery.snapshot()['caustic_followers'], 1)

  def test_color_gives_the_projector_place(self):
    # The fish group reads the projector at home + (r - bias, g - bias, -b)
    # (tools/scene_env.py, caustic_group)
    for t in (0.0, 3.5, 60.0, 3600.0):
      self.scenery._move_projector(t)
      r, g, b, a = self.fish.color
      bias = scenery.CAUSTIC_BIAS
      place = (self.HOME[0] + r - bias, self.HOME[1] + g - bias,
               self.HOME[2] - b)
      for got, want in zip(place, self.projector.worldPosition):
        self.assertAlmostEqual(got, want)
      # The player's object color is never negative
      self.assertTrue(min(r, g, b) >= 0.0, (t, self.fish.color))
      self.assertEqual(a, 1.0)

  def test_others_keep_their_color(self):
    self.scenery._move_projector(10.0)
    self.assertEqual(self.sand.color, (1.0, 1.0, 1.0, 1.0))


class SharedConstantsTest(unittest.TestCase):

  def test_scene_builder_agrees(self):
    # tools/scene_env.py needs bpy, so read its constants from the source
    path = os.path.join(launcher.ROOT, 'tools', 'scene_env.py')
    with open(path) as f:
      tree = ast.parse(f.read())
    values = {}
    for node in tree.body:
      if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
          try:
            values[target.id] = ast.literal_eval(node.value)
          except ValueError:
            pass
    self.assertEqual(values['FISH_CAUSTIC'], scenery.FISH_CAUSTIC)
    self.assertEqual(values['CAUSTIC_BIAS'], scenery.CAUSTIC_BIAS)
    self.assertEqual(values['PROJECTOR'], scenery.PROJECTOR)


if __name__ == '__main__':
  unittest.main()
