import json
import os
import shutil
import tempfile
import unittest

from tankful import harness_protocol as proto
from tankful.game import harness_channel
from tankful.game.input import InputState


class FakeClock:

  def __init__(self):
    self.now = 100.0

  def __call__(self):
    return self.now


class FakeGame:
  """The engine side the processor talks to."""

  def __init__(self, root):
    self.root = root
    self.shots = []
    self.quit_called = 0
    self.files = {}
    self.input = InputState()
    self.clock = FakeClock()

  def screenshot(self, path):
    self.shots.append(path)

  def file_size(self, path):
    return self.files.get(path)

  def get_state(self):
    return {'frame': 1}

  def request_quit(self):
    self.quit_called += 1

  def processor(self):
    return harness_channel.CommandProcessor(
      self.input, self.screenshot, self.get_state, self.request_quit,
      self.root, clock=self.clock, file_size=self.file_size)


class CommandProcessorTests(unittest.TestCase):

  def setUp(self):
    self.root = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.root)
    self.game = FakeGame(self.root)
    self.proc = self.game.processor()

  def test_immediate_commands_reply_in_order(self):
    self.proc.submit({'cmd': 'click', 'x': 5, 'y': 6, 'id': 1})
    self.proc.submit({'cmd': 'key', 'action': 'down', 'name': 'LEFTARROWKEY',
                      'id': 2})
    self.proc.submit({'cmd': 'state', 'id': 3})
    out = self.proc.tick()
    self.assertEqual([r['id'] for r in out], [1, 2, 3])
    self.assertTrue(all(r['ok'] for r in out))
    self.assertEqual(out[2]['state'], {'frame': 1})
    self.assertEqual(self.game.input.clicks(), [(5, 6, 'left')])
    self.assertTrue(self.game.input.is_down('left'))

  def test_key_up(self):
    self.game.input.key_down('l')
    self.proc.submit({'cmd': 'key', 'action': 'up', 'name': 'L', 'id': 1})
    self.proc.tick()
    self.assertFalse(self.game.input.is_down('l'))
    self.assertTrue(self.game.input.was_released('l'))

  def test_wait_frames_holds_later_commands(self):
    self.proc.submit({'cmd': 'wait', 'frames': 3, 'id': 1})
    self.proc.submit({'cmd': 'state', 'id': 2})
    self.assertEqual(self.proc.tick(), [])
    self.assertEqual(self.proc.tick(), [])
    self.assertEqual(self.proc.tick(), [])
    self.assertEqual([r['id'] for r in self.proc.tick()], [1, 2])

  def test_wait_zero_frames_is_immediate(self):
    self.proc.submit({'cmd': 'wait', 'frames': 0, 'id': 1})
    self.assertEqual([r['id'] for r in self.proc.tick()], [1])

  def test_wait_seconds(self):
    self.proc.submit({'cmd': 'wait', 'seconds': 1.5, 'id': 1})
    self.assertEqual(self.proc.tick(), [])
    self.game.clock.now += 1.0
    self.assertEqual(self.proc.tick(), [])
    self.game.clock.now += 0.6
    self.assertEqual(self.proc.tick(), [{'id': 1, 'ok': True}])

  def test_wait_seconds_counts_frames_with_fixed_step(self):
    proc = harness_channel.CommandProcessor(
      self.game.input, self.game.screenshot, self.game.get_state,
      self.game.request_quit, self.root, clock=self.game.clock,
      file_size=self.game.file_size, frame_dt=0.25)
    proc.submit({'cmd': 'wait', 'seconds': 1.0, 'id': 1})
    proc.submit({'cmd': 'state', 'id': 2})
    for _ in range(4):
      self.game.clock.now += 10.0    # real time doesn't count
      self.assertEqual(proc.tick(), [])
      self.assertTrue(proc.waiting)
    self.assertEqual([r['id'] for r in proc.tick()], [1, 2])
    self.assertFalse(proc.waiting)

  def test_waiting_only_for_wait_commands(self):
    self.assertFalse(self.proc.waiting)
    self.proc.submit({'cmd': 'screenshot', 'path': 'x.png', 'id': 1})
    self.proc.tick()
    self.assertFalse(self.proc.waiting)

  def test_screenshot_waits_for_file_to_settle(self):
    self.proc.submit({'cmd': 'screenshot', 'path': 'docs/shots/01-a.png',
                      'id': 7})
    self.assertEqual(self.proc.tick(), [])
    full = os.path.join(self.root, 'docs', 'shots', '01-a.png')
    self.assertEqual(self.game.shots, [full])
    self.assertTrue(os.path.isdir(os.path.dirname(full)))
    self.game.files[full] = 100
    self.assertEqual(self.proc.tick(), [])
    self.game.files[full] = 200
    self.assertEqual(self.proc.tick(), [])
    out = self.proc.tick()
    self.assertEqual(out, [{'id': 7, 'ok': True, 'path': 'docs/shots/01-a.png',
                            'bytes': 200}])

  def test_screenshot_removes_an_old_file_first(self):
    full = os.path.join(self.root, 'old.png')
    with open(full, 'wb') as f:
      f.write(b'x')
    self.proc._file_size = harness_channel._file_size
    self.proc.submit({'cmd': 'screenshot', 'path': full, 'id': 1})
    self.proc.tick()
    self.assertFalse(os.path.exists(full))

  def test_screenshot_times_out(self):
    self.proc.submit({'cmd': 'screenshot', 'path': 'x.png', 'id': 1})
    self.proc.tick()
    self.game.clock.now += harness_channel.SCREENSHOT_TIMEOUT + 1
    out = self.proc.tick()
    self.assertFalse(out[0]['ok'])
    self.assertIn('not written', out[0]['error'])

  def test_invalid_command_gets_error_and_queue_goes_on(self):
    self.proc.submit({'cmd': 'fly', 'id': 1})
    self.proc.submit({'cmd': 'click', 'id': 2})
    self.proc.submit({'cmd': 'state', 'id': 3})
    out = self.proc.tick()
    self.assertEqual([(r['id'], r['ok']) for r in out],
                     [(1, False), (2, False), (3, True)])
    self.assertIn('fly', out[0]['error'])

  def test_quit_stops_the_queue_and_quits_on_finish(self):
    self.proc.submit({'cmd': 'quit', 'id': 1})
    self.proc.submit({'cmd': 'state', 'id': 2})
    out = self.proc.tick()
    self.assertEqual(out, [{'id': 1, 'ok': True}])
    self.assertTrue(self.proc.quitting)
    self.assertEqual(self.game.quit_called, 0)
    self.proc.finish()
    self.proc.finish()
    self.assertEqual(self.game.quit_called, 1)


class FakeConn:

  def __init__(self, chunks=()):
    self.incoming = list(chunks)
    self.sent = b''
    self.closed = False
    self.send_limit = None
    self.buffer_full = False
    self.blocking = None

  def setblocking(self, flag):
    self.blocking = flag

  def recv(self, n):
    # The channel reads once per poll before sending: a new poll, so the
    # send buffer has room again
    self.buffer_full = False
    if not self.incoming:
      raise BlockingIOError()
    item = self.incoming.pop(0)
    if isinstance(item, Exception):
      raise item
    return item

  def send(self, data):
    if self.send_limit is not None:
      # Model a small send buffer: one partial send per poll
      if self.buffer_full:
        raise BlockingIOError()
      data = data[:self.send_limit]
      self.buffer_full = True
    self.sent += data
    return len(data)

  def close(self):
    self.closed = True

  def replies(self):
    return [json.loads(l) for l in self.sent.decode().splitlines()]


class FakeListener:

  def __init__(self):
    self.pending = []
    self.closed = False

  def setblocking(self, flag):
    pass

  def accept(self):
    if not self.pending:
      raise BlockingIOError()
    return self.pending.pop(0), ('127.0.0.1', 1234)

  def close(self):
    self.closed = True


class HarnessChannelTests(unittest.TestCase):

  def setUp(self):
    self.game = FakeGame(tempfile.gettempdir())
    self.listener = FakeListener()
    self.channel = harness_channel.HarnessChannel(
      self.game.processor(), port=0, listener=self.listener)

  def connect(self, *chunks):
    conn = FakeConn(chunks)
    self.listener.pending.append(conn)
    return conn

  def test_idle_without_client(self):
    self.channel.poll()
    self.channel.poll()

  def test_request_split_across_reads(self):
    data = proto.encode({'cmd': 'state', 'id': 1})
    conn = self.connect(data[:5], data[5:])
    self.channel.poll()
    self.assertFalse(conn.blocking)
    self.assertEqual(conn.replies(), [{'id': 1, 'ok': True,
                                       'state': {'frame': 1}}])

  def test_bad_json_gets_error_reply(self):
    conn = self.connect(b'not json\n' + proto.encode({'cmd': 'state', 'id': 2}))
    self.channel.poll()
    replies = conn.replies()
    self.assertEqual(replies[0]['id'], None)
    self.assertFalse(replies[0]['ok'])
    self.assertEqual(replies[1]['id'], 2)

  def test_partial_sends_finish_on_later_polls(self):
    conn = self.connect(proto.encode({'cmd': 'state', 'id': 1}))
    conn.send_limit = 4
    self.channel.poll()
    self.assertEqual(len(conn.sent), 4)
    for _ in range(20):
      self.channel.poll()
    self.assertEqual(conn.replies()[0]['id'], 1)

  def test_quit_after_reply_is_sent(self):
    conn = self.connect(proto.encode({'cmd': 'quit', 'id': 9}))
    conn.send_limit = 3
    self.channel.poll()
    self.assertEqual(self.game.quit_called, 0, 'reply not yet fully sent')
    for _ in range(10):
      self.channel.poll()
    self.assertEqual(conn.replies(), [{'id': 9, 'ok': True}])
    self.assertEqual(self.game.quit_called, 1)

  def test_disconnect_then_new_client(self):
    first = self.connect(b'')
    self.channel.poll()
    self.assertTrue(first.closed)
    second = self.connect(proto.encode({'cmd': 'state', 'id': 1}))
    self.channel.poll()
    self.assertEqual(second.replies()[0]['id'], 1)

  def test_reset_connection_is_dropped(self):
    conn = self.connect(ConnectionResetError())
    self.channel.poll()
    self.assertTrue(conn.closed)

  def test_close(self):
    conn = self.connect()
    self.channel.poll()
    self.channel.close()
    self.assertTrue(conn.closed)
    self.assertTrue(self.listener.closed)


if __name__ == '__main__':
  unittest.main()
