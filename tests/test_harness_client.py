import json
import os
import shutil
import socket
import tempfile
import unittest

from tankful import harness_client
from tankful import harness_protocol as proto


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


if __name__ == '__main__':
  unittest.main()
