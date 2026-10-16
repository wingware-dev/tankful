import unittest

from tankful import harness_protocol as proto


class ParseCommandTests(unittest.TestCase):

  def test_text_commands(self):
    cases = {
      'click 100 200': {'cmd': 'click', 'x': 100, 'y': 200},
      'click 1.5 2 right': {'cmd': 'click', 'x': 1.5, 'y': 2,
                            'button': 'right'},
      'key down LEFT': {'cmd': 'key', 'action': 'down', 'name': 'LEFT'},
      'key UP l': {'cmd': 'key', 'action': 'up', 'name': 'l'},
      'wait 2': {'cmd': 'wait', 'seconds': 2.0},
      'wait 0.25s': {'cmd': 'wait', 'seconds': 0.25},
      'wait 30f': {'cmd': 'wait', 'frames': 30},
      'wait 30 frames': {'cmd': 'wait', 'frames': 30},
      'wait 3 seconds': {'cmd': 'wait', 'seconds': 3.0},
      'screenshot docs/shots/01-x.png': {'cmd': 'screenshot',
                                         'path': 'docs/shots/01-x.png'},
      'state': {'cmd': 'state'},
      'QUIT': {'cmd': 'quit'},
    }
    for text, want in cases.items():
      self.assertEqual(proto.parse_command(text), want, text)

  def test_list_and_dict_forms(self):
    self.assertEqual(proto.parse_command(['click', 3, 4]),
                     {'cmd': 'click', 'x': 3, 'y': 4})
    msg = {'cmd': 'wait', 'frames': 5}
    self.assertEqual(proto.parse_command(msg), msg)
    self.assertIsNot(proto.parse_command(msg), msg)

  def test_bad_commands(self):
    for bad in ('', 'jump', 'click 1', 'click a b', 'key sideways x',
                'key down', 'wait', 'wait 3 parsecs', 'wait xf',
                'screenshot', 'state now', {'cmd': 'wait'},
                {'cmd': 'wait', 'seconds': 1, 'frames': 2},
                {'cmd': 'wait', 'seconds': -1}, {'cmd': 'click', 'x': True,
                                                 'y': 1},
                {'cmd': 'screenshot', 'path': ''}, {'x': 1}):
      with self.assertRaises(proto.ProtocolError, msg=repr(bad)):
        proto.parse_command(bad)


class WireTests(unittest.TestCase):

  def test_round_trip(self):
    msg = {'cmd': 'state', 'id': 3}
    data = proto.encode(msg)
    self.assertTrue(data.endswith(b'\n'))
    self.assertEqual(data.count(b'\n'), 1)
    self.assertEqual(proto.decode(data.strip()), msg)

  def test_decode_errors(self):
    for bad in (b'{nope', b'[1, 2]', b'\xff\xfe'):
      with self.assertRaises(proto.ProtocolError):
        proto.decode(bad)

  def test_line_buffer_joins_split_lines(self):
    buf = proto.LineBuffer()
    self.assertEqual(buf.feed(b'{"a":'), [])
    self.assertEqual(buf.feed(b'1}\n{"b":2}\n\n{"c"'), [b'{"a":1}', b'{"b":2}'])
    self.assertEqual(buf.feed(b':3}\n'), [b'{"c":3}'])


if __name__ == '__main__':
  unittest.main()
