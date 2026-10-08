"""Check the internal HTTP port without reading legacy server.json."""
import json
import os
import urllib.request

port = int(os.environ.get('OPENLIPS_PORT', '8765'))
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(f'http://127.0.0.1:{port}/api/v1/status', timeout=4) as response:
    status = json.load(response)
if status.get('protocol') != 1 or status.get('auth_required'):
    raise SystemExit(1)
