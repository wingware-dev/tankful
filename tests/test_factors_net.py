import io
import sys
import unittest
from unittest import mock

from tankful.factors import net


class FakeContext:

  def __init__(self, cas):
    self.cas = cas
    self.loaded = []

  def cert_store_stats(self):
    return {'crl': 0, 'x509': self.cas, 'x509_ca': self.cas}

  def load_verify_locations(self, cafile=None):
    self.loaded.append(cafile)


class FakeOpener:
  """Stands in for urlopen: returns a canned body; records the requests."""

  def __init__(self, body=b'{"ok": 1}'):
    self.body = body
    self.calls = []

  def __call__(self, request, timeout=None):
    self.calls.append((request, timeout))
    return io.BytesIO(self.body)


class SslTests(unittest.TestCase):

  def setUp(self):
    patcher = mock.patch.object(net, '_context', None)
    patcher.start()
    self.addCleanup(patcher.stop)
    # Without certifi, as in python.org's Python
    patcher = mock.patch.dict(sys.modules, {'certifi': None})
    patcher.start()
    self.addCleanup(patcher.stop)

  def test_bundle_is_first_that_exists(self):
    self.assertEqual(net.ca_bundle(lambda p: p.startswith('/etc/pki')),
                     '/etc/pki/tls/certs/ca-bundle.crt')
    self.assertIsNone(net.ca_bundle(lambda p: False))

  def test_certifi_preferred(self):
    certifi = mock.Mock(where=lambda: '/x/cacert.pem')
    with mock.patch.dict(sys.modules, {'certifi': certifi}):
      self.assertEqual(net.ca_bundle(lambda p: True), '/x/cacert.pem')

  def test_defaults_kept_when_they_have_cas(self):
    context = FakeContext(cas=140)
    with mock.patch('ssl.create_default_context', return_value=context):
      self.assertIs(net.ssl_context(), context)
    self.assertEqual(context.loaded, [])

  def test_bundle_loaded_when_defaults_empty(self):
    # As under UPBGE's Python, whose OpenSSL looks for CAs in /dev/null
    context = FakeContext(cas=0)
    with mock.patch('ssl.create_default_context', return_value=context), \
         mock.patch.object(net, 'ca_bundle', return_value='/b.pem'), \
         self.assertLogs('tankful.factors', 'INFO'):
      self.assertIs(net.ssl_context(), context)
      self.assertIs(net.ssl_context(), context)
    self.assertEqual(context.loaded, ['/b.pem'])

  def test_warns_with_no_bundle(self):
    context = FakeContext(cas=0)
    with mock.patch('ssl.create_default_context', return_value=context), \
         mock.patch.object(net, 'ca_bundle', return_value=None), \
         self.assertLogs('tankful.factors', 'WARNING'):
      net.ssl_context()
    self.assertEqual(context.loaded, [])

  def test_urlopen_uses_context(self):
    context = FakeContext(cas=1)
    with mock.patch.object(net, '_context', context), \
         mock.patch('urllib.request.urlopen') as urlopen:
      net.urlopen('request', timeout=3)
    urlopen.assert_called_once_with('request', timeout=3, context=context)

  def test_urlopen_default_timeout(self):
    with mock.patch.object(net, '_context', FakeContext(cas=1)), \
         mock.patch('urllib.request.urlopen') as urlopen:
      net.urlopen('request')
    self.assertEqual(urlopen.call_args[1]['timeout'], net.TIMEOUT)


class FetchJsonTests(unittest.TestCase):

  def test_parses_and_sends_app_user_agent(self):
    opener = FakeOpener()
    self.assertEqual(net.fetch_json('https://example.test/x', opener=opener),
                     {'ok': 1})
    request, timeout = opener.calls[0]
    self.assertEqual(request.full_url, 'https://example.test/x')
    # Yahoo answers 429 to a spoofed browser User-Agent
    self.assertEqual(request.get_header('User-agent'),
                     'tankful/0.1 (+desktop aquarium)')
    self.assertEqual(request.get_header('Accept'), 'application/json')
    self.assertEqual(timeout, net.TIMEOUT)

  def test_timeout(self):
    opener = FakeOpener()
    net.fetch_json('http://example.test/', timeout=2, opener=opener)
    self.assertEqual(opener.calls[0][1], 2)

  def test_default_opener_is_urlopen(self):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = b'[1]'
    with mock.patch.object(net, '_context', FakeContext(cas=1)), \
         mock.patch('urllib.request.urlopen',
                    return_value=response) as urlopen:
      self.assertEqual(net.fetch_json('https://example.test/'), [1])
    urlopen.assert_called_once()

  def test_bad_json_raises(self):
    with self.assertRaises(ValueError):
      net.fetch_json('http://example.test/', opener=FakeOpener(b'<html>'))

  def test_opener_errors_propagate(self):
    def opener(request, timeout):
      raise OSError('no route to host')
    with self.assertRaises(OSError):
      net.fetch_json('http://example.test/', opener=opener)


if __name__ == '__main__':
  unittest.main()
