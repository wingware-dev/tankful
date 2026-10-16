"""HTTP(S) fetches for the network factors (weather, stock).

A Python that ships its own OpenSSL can start with no CA certificates, and
then every HTTPS fetch fails verification: UPBGE's has none but ships
certifi, and python.org's macOS builds have neither until their Install
Certificates step.  So when Python's defaults hold no CAs, ssl_context()
loads certifi's bundle, else the system's.

Requests carry tankful's own User-Agent: Yahoo serves a plain app one, but
answers 429 to a browser one that doesn't really come from that browser.
"""

import json
import logging
import os
import ssl
import urllib.request

log = logging.getLogger('tankful.factors.net')

USER_AGENT = 'tankful/0.1 (+desktop aquarium)'
TIMEOUT = 10.0

CA_BUNDLES = (
  '/etc/ssl/cert.pem',                     # macOS, some BSDs and Linuxes
  '/etc/ssl/certs/ca-certificates.crt',    # Debian, Ubuntu, Arch
  '/etc/pki/tls/certs/ca-bundle.crt',      # Fedora, RHEL
)

_context = None


def ca_bundle(exists=os.path.exists):
  """A CA bundle file to load when Python's defaults have none, or None."""
  try:
    import certifi
    return certifi.where()
  except ImportError:
    pass
  for path in CA_BUNDLES:
    if exists(path):
      return path
  return None


def ssl_context():
  """The verifying SSL context for fetches, made once."""
  global _context
  if _context is None:
    context = ssl.create_default_context()
    if not context.cert_store_stats().get('x509_ca'):
      path = ca_bundle()
      if path is None:
        log.warning('No CA certificates found; HTTPS fetches will fail')
      else:
        log.info('Loading CA certificates from %s', path)
        context.load_verify_locations(cafile=path)
    _context = context
  return _context


def urlopen(request, timeout=TIMEOUT):
  """urllib's urlopen with the verifying context (unused for http:)."""
  return urllib.request.urlopen(request, timeout=timeout,
                                context=ssl_context())


def fetch_json(url, timeout=TIMEOUT, opener=urlopen):
  """GET url and parse it as JSON; raises on any failure.

  opener(request, timeout) returns a file-like response; the tests pass a
  stand-in so nothing touches the network.
  """
  request = urllib.request.Request(
    url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
  with opener(request, timeout=timeout) as response:
    return json.loads(response.read().decode('utf-8'))
