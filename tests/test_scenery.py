import ast
import os
import unittest
from unittest import mock

from tankful import launcher
from tankful.game import scenery
from tankful.sim import bubbles
from tankful.sim.bubbles import RIPPLE_TIME


class FakeObjects(list):
  """A scene's objects, as the player's CListValue: a list with get."""

  def get(self, name):
    for obj in self:
      if obj.name == name:
        return obj
    return None


class FakeTree:
  """A node tree: its name and nodes, groups among them for the names in
  groups.  A group given as a tuple (outer, inner, ...) nests: outer's
  tree uses inner."""

  def __init__(self, name, groups=()):
    self.name = name
    self.nodes = [mock.Mock(bl_idname='ShaderNodeBsdfPrincipled')]
    for group in groups:
      path = (group,) if isinstance(group, str) else group
      inner = FakeTree(path[0], [path[1:]] if len(path) > 1 else [])
      self.nodes.append(mock.Mock(bl_idname='ShaderNodeGroup',
                                  node_tree=inner))


class FakeObject:

  def __init__(self, name, groups=(), position=(0.0, 0.0, 0.0)):
    """groups: for each material slot, the groups its tree uses
    (FakeTree)."""
    self.name = name
    self.worldPosition = list(position)
    self.color = (1.0, 1.0, 1.0, 1.0)
    if groups:
      self.blenderObject = mock.Mock(material_slots=[
        mock.Mock(material=mock.Mock(node_tree=FakeTree('Material', slot)))
        for slot in groups])


# A material reading the caustics, as tools/scene_env.py builds them
CAUSTIC = [(('CausticProjection', scenery.PROJECTOR_SPACE),)]


def make_scenery(objects):
  pool = mock.Mock(capacity=0)
  with mock.patch.object(scenery.log, 'warning'):
    return scenery.Scenery(mock.Mock(objects=FakeObjects(objects)), pool)


class ReadsGroupTest(unittest.TestCase):

  def test_finds_group_in_any_slot(self):
    obj = FakeObject('GodRay.0', groups=[('Other',), (scenery.PROJECTOR_SPACE,)])
    self.assertTrue(scenery.reads_group(obj, scenery.PROJECTOR_SPACE))

  def test_finds_group_nested_in_another(self):
    obj = FakeObject('Sand', groups=[(('Outer', 'CausticProjection',
                                       scenery.PROJECTOR_SPACE),)])
    self.assertTrue(scenery.reads_group(obj, scenery.PROJECTOR_SPACE))

  def test_other_groups_do_not_count(self):
    obj = FakeObject('Leaf', groups=[(('Other', 'Inner'), 'Third')])
    self.assertFalse(scenery.reads_group(obj, scenery.PROJECTOR_SPACE))

  def test_group_used_twice_is_looked_through_once(self):
    shared = FakeTree('Shared')
    tree = FakeTree('Material')
    tree.nodes += [mock.Mock(bl_idname='ShaderNodeGroup', node_tree=shared)
                   for _ in range(2)]
    seen = set()
    with mock.patch.object(scenery, 'tree_uses',
                           wraps=scenery.tree_uses) as uses:
      self.assertFalse(scenery.tree_uses(tree, scenery.PROJECTOR_SPACE, seen))
    self.assertEqual(seen, {'Shared'})
    self.assertEqual(uses.call_count, 2)

  def test_object_without_blender_object(self):
    self.assertFalse(scenery.reads_group(FakeObject('Empty'),
                                         scenery.PROJECTOR_SPACE))

  def test_empty_slot_material_without_nodes_and_empty_group(self):
    no_nodes = mock.Mock()
    no_nodes.node_tree = None
    empty_group = FakeTree('Material')
    empty_group.nodes.append(mock.Mock(bl_idname='ShaderNodeGroup',
                                       node_tree=None))
    obj = FakeObject('Fish')
    obj.blenderObject = mock.Mock(material_slots=[
      mock.Mock(material=None), mock.Mock(material=no_nodes),
      mock.Mock(material=mock.Mock(node_tree=empty_group))])
    self.assertFalse(scenery.reads_group(obj, scenery.PROJECTOR_SPACE))


class CausticFollowersTest(unittest.TestCase):

  HOME = (0.0, 0.0, 0.62)

  def setUp(self):
    self.projector = FakeObject(scenery.PROJECTOR, position=self.HOME)
    self.fish = FakeObject('Angelfish.0', groups=CAUSTIC)
    self.sand = FakeObject('Sand', groups=CAUSTIC)
    self.ray = FakeObject('GodRay.0', groups=[(scenery.PROJECTOR_SPACE,)])
    self.tetras = FakeObject('NeonTetras', groups=[('Other',)])
    self.scenery = make_scenery([self.projector, self.fish, self.sand,
                                 self.ray, self.tetras])

  def test_only_projector_space_readers_follow(self):
    self.assertEqual(self.scenery.caustic_followers,
                     [self.fish, self.sand, self.ray])
    self.assertEqual(self.scenery.snapshot()['caustic_followers'], 3)

  def test_color_gives_the_projector_place(self):
    # ProjectorSpace reads the projector at home + (r - bias, g - bias, -b)
    # (tools/scene_env.py, projector_space_group)
    for t in (0.0, 3.5, 60.0, 3600.0):
      self.scenery._move_projector(t)
      for obj in (self.fish, self.sand, self.ray):
        r, g, b, a = obj.color
        bias = scenery.CAUSTIC_BIAS
        place = (self.HOME[0] + r - bias, self.HOME[1] + g - bias,
                 self.HOME[2] - b)
        for got, want in zip(place, self.projector.worldPosition):
          self.assertAlmostEqual(got, want)
        # The player's object color is never negative
        self.assertTrue(min(r, g, b) >= 0.0, (t, obj.color))
        self.assertEqual(a, 1.0)

  def test_others_keep_their_color(self):
    self.scenery._move_projector(10.0)
    self.assertEqual(self.tetras.color, (1.0, 1.0, 1.0, 1.0))


class RipplesTest(unittest.TestCase):

  def setUp(self):
    self.disc = FakeObject(scenery.RIPPLES)
    self.disc.color = (1.0, 1.0, 1.0, 1.0)
    self.pool = mock.Mock(capacity=0, bubbles=[], pop_events=[])
    with mock.patch.object(scenery.log, 'warning'):
      self.scenery = scenery.Scenery(
        mock.Mock(objects=FakeObjects([self.disc])), self.pool)

  def update(self, dt=0.1, pops=()):
    self.pool.pop_events = list(pops)
    self.scenery.update(1.0, dt)

  def test_pops_start_ripples_shown_in_the_color(self):
    self.update(pops=[(0.3, 0.16, 0.004)])
    self.assertEqual(self.disc.color, (0.0, 1.0, 1.0, 1.0))
    self.update(pops=[(0.31, 0.16, 0.003)])
    r, g, b, a = self.disc.color
    self.assertAlmostEqual(r, 0.1 / RIPPLE_TIME)
    self.assertEqual((g, b, a), (0.0, 1.0, 1.0))
    # Two pops at once fill the last slot, and the one after has none
    self.update(pops=[(0.3, 0.16, 0.004)] * 2)
    self.assertEqual(self.disc.color[2], 0.0)
    snap = self.scenery.snapshot()['ripples']
    self.assertEqual((snap['started'], snap['skipped']), (3, 1))

  def test_spent_ripples_go_dark_and_writes_stop(self):
    self.update(pops=[(0.3, 0.16, 0.004)])
    for _ in range(int(RIPPLE_TIME / 0.1) + 1):
      self.update()
    self.assertEqual(self.disc.color, (1.0, 1.0, 1.0, 1.0))
    # Nothing changes now, so the color is not set again
    self.disc.color = 'untouched'
    self.update()
    self.assertEqual(self.disc.color, 'untouched')

  def test_scene_without_the_disc(self):
    pool = mock.Mock(capacity=0, bubbles=[], pop_events=[(0.3, 0.16, 0.004)])
    with mock.patch.object(scenery.log, 'warning') as warning:
      s = scenery.Scenery(mock.Mock(objects=FakeObjects([])), pool)
    self.assertTrue(any(scenery.RIPPLES in str(c) for c in
                        warning.call_args_list))
    s.update(1.0, 0.1)
    self.assertEqual(s.snapshot()['ripples']['started'], 1)

  def test_disc_draws_at_most_three(self):
    with mock.patch.object(scenery.log, 'warning'), \
         self.assertRaises(ValueError):
      scenery.Scenery(mock.Mock(objects=FakeObjects([self.disc])),
                      self.pool, bubbles.RipplePool(capacity=4))


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
    self.assertEqual(values['PROJECTOR_SPACE'], scenery.PROJECTOR_SPACE)
    self.assertEqual(values['CAUSTIC_BIAS'], scenery.CAUSTIC_BIAS)
    self.assertEqual(values['PROJECTOR'], scenery.PROJECTOR)


if __name__ == '__main__':
  unittest.main()
