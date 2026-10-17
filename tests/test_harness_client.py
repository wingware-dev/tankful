import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
from unittest import mock

from tankful import harness_client
from tankful import harness_protocol as proto
from tankful import launcher
from tests.test_pngstats import write_png


class FakeSocket:
  """Replies to each request with what respond(msg) returns."""

  def __init__(self, respond):
    self.respond = respond
    self.requests = []
    self.inbox = []
    self.closed = False

  def sendall(self, data):
    for line in data.splitlines():
      msg = json.loads(line)
      self.requests.append(msg)
      for reply in self.respond(msg):
        self.inbox.append(proto.encode(reply))

  def settimeout(self, t):
    pass

  def recv(self, n):
    if not self.inbox:
      raise socket.timeout()
    return self.inbox.pop(0)

  def close(self):
    self.closed = True


class ClientTests(unittest.TestCase):

  def test_request_assigns_ids_and_matches_replies(self):
    sock = FakeSocket(lambda m: [{'id': m['id'], 'ok': True, 'echo': m['cmd']}])
    client = harness_client.Client(sock)
    self.assertEqual(client.request({'cmd': 'state'})['echo'], 'state')
    self.assertEqual(client.request({'cmd': 'quit'})['id'], 2)
    self.assertEqual([r['id'] for r in sock.requests], [1, 2])

  def test_reply_split_and_out_of_order(self):
    sock = FakeSocket(lambda m: [])
    client = harness_client.Client(sock, timeout=0.2)
    sock.inbox = [b'{"id": 2, "ok": true}\n{"id"', b': 1, "ok": true}\n']
    self.assertEqual(client.request({'cmd': 'state'})['id'], 1)
    self.assertEqual(client._pending, [{'id': 2, 'ok': True}])

  def test_rejected_message(self):
    sock = FakeSocket(lambda m: [{'id': None, 'ok': False, 'error': 'bad'}])
    with self.assertRaises(harness_client.HarnessError) as cm:
      harness_client.Client(sock).request({'cmd': 'state'})
    self.assertIn('bad', str(cm.exception))

  def test_wait_allows_its_frames_at_min_fps(self):
    for min_fps, msg, want in (
        (60.0, {'cmd': 'wait', 'seconds': 4}, 64.0),
        (60.0, {'cmd': 'wait', 'frames': 600}, 70.0),
        (2.0, {'cmd': 'wait', 'seconds': 4}, 180.0),
        (2.0, {'cmd': 'wait', 'frames': 60}, 90.0),
        (2.0, {'cmd': 'state'}, 60.0)):
      client = harness_client.Client(FakeSocket(lambda m: []), min_fps=min_fps)
      with mock.patch.object(client, '_reply') as reply:
        client.request(msg)
      self.assertEqual(reply.call_args[0][1], want, msg)
    self.assertEqual(harness_client.min_fps('docker'),
                     harness_client.DOCKER_MIN_FPS)
    self.assertEqual(harness_client.min_fps('offscreen'),
                     harness_client.MIN_FPS)

  def test_timeout(self):
    client = harness_client.Client(FakeSocket(lambda m: []), timeout=0.05)
    with self.assertRaises(harness_client.HarnessError):
      client.request({'cmd': 'state'})

  def test_closed_connection(self):
    sock = FakeSocket(lambda m: [])
    sock.recv = lambda n: b''
    with self.assertRaises(harness_client.HarnessError):
      harness_client.Client(sock).request({'cmd': 'state'})

  def test_invalid_request_is_not_sent(self):
    sock = FakeSocket(lambda m: [])
    with self.assertRaises(proto.ProtocolError):
      harness_client.Client(sock).request({'cmd': 'click'})
    self.assertEqual(sock.requests, [])


class ScriptTests(unittest.TestCase):

  def setUp(self):
    self.dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.dir)

  def write(self, data):
    path = os.path.join(self.dir, 's.json')
    with open(path, 'w') as f:
      json.dump(data, f)
    return path

  def test_list_script(self):
    script = harness_client.load_script(self.write(['wait 2f', 'quit']))
    self.assertEqual(script['commands'], [{'cmd': 'wait', 'frames': 2},
                                          {'cmd': 'quit'}])

  def test_object_script(self):
    script = harness_client.load_script(self.write(
      {'backend': 'docker', 'commands': [{'cmd': 'state'}]}))
    self.assertEqual(script['backend'], 'docker')

  def test_bad_scripts(self):
    for data in ({'cmds': []}, 'quit', ['fly']):
      with self.assertRaises(proto.ProtocolError):
        harness_client.load_script(self.write(data))

  def test_git_add_only_under_docs_shots(self):
    self.assertFalse(harness_client.git_add('build/x.png', root=self.dir))
    self.assertFalse(harness_client.git_add('/elsewhere/x.png', root=self.dir))

  def test_run_script_stops_at_failure(self):
    def respond(m):
      return [{'id': m['id'], 'ok': m['cmd'] != 'key', 'error': 'nope'}]
    client = harness_client.Client(FakeSocket(respond))
    lines = []
    results = harness_client.run_script(
      client, [{'cmd': 'state'}, {'cmd': 'key', 'action': 'down', 'name': 'a'},
               {'cmd': 'quit'}], log=lines.append)
    self.assertEqual(len(results), 2)
    self.assertTrue(lines[1].startswith('FAILED key'))


class ReadShotTests(unittest.TestCase):

  def setUp(self):
    self.dir = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.dir)
    self.path = os.path.join(self.dir, 'shot.png')
    full = os.path.join(self.dir, 'full.png')
    write_png(full, 32, 32, lambda x, y: (x * 8, y * 8, 120))
    with open(full, 'rb') as f:
      self.data = f.read()

  def write(self, data):
    with open(self.path, 'wb') as f:
      f.write(data)

  def finish_later(self, delay=0.3):
    timer = threading.Timer(delay, self.write, [self.data])
    timer.start()
    self.addCleanup(timer.join)

  def test_waits_for_truncated_file(self):
    self.write(self.data[:len(self.data) // 2])
    self.finish_later()
    self.assertEqual(harness_client.read_shot(self.path, timeout=5)['width'],
                     32)

  def test_waits_for_missing_file(self):
    self.finish_later()
    self.assertEqual(harness_client.read_shot(self.path, timeout=5)['height'],
                     32)

  def test_gives_up(self):
    self.write(self.data[:-12])
    with self.assertRaises(harness_client.HarnessError) as cm:
      harness_client.read_shot(self.path, timeout=0.2, poll=0.05)
    self.assertIn('incomplete', str(cm.exception))

  def test_run_script_reads_shot_written_after_reply(self):
    rel = os.path.relpath(self.path, launcher.ROOT)
    self.write(self.data[:40])
    self.finish_later()
    client = harness_client.Client(FakeSocket(
      lambda m: [{'id': m['id'], 'ok': True}]))
    lines = []
    results = harness_client.run_script(
      client, [{'cmd': 'screenshot', 'path': rel}, {'cmd': 'quit'}],
      add_shots=False, log=lines.append)
    self.assertEqual(len(results), 2)
    self.assertTrue(results[0][1]['ok'])
    self.assertEqual(results[0][1]['image']['width'], 32)
    self.assertTrue(lines[0].startswith('ok screenshot'), lines)

  def test_run_script_fails_incomplete_shot(self):
    rel = os.path.relpath(self.path, launcher.ROOT)
    self.write(self.data[:-12])
    client = harness_client.Client(FakeSocket(
      lambda m: [{'id': m['id'], 'ok': True}]))
    lines = []
    with mock.patch.object(harness_client, 'SHOT_TIMEOUT', 0.2):
      results = harness_client.run_script(
        client, [{'cmd': 'screenshot', 'path': rel}, {'cmd': 'quit'}],
        add_shots=False, log=lines.append)
    self.assertEqual(len(results), 1)
    self.assertFalse(results[0][1]['ok'])
    self.assertTrue(lines[0].startswith('FAILED screenshot'), lines)


if __name__ == '__main__':
  unittest.main()
