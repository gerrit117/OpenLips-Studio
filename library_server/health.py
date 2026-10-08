from studio.server_config import load_config
from studio.library_client import LibraryClient
config = load_config('/data/server.json')
scheme = 'https' if config.get('tls_cert') else 'http'
LibraryClient(f"{scheme}://{config['bind']}:{config['port']}", config['api_token'],
              config.get('certificate_fingerprint', '')).request('GET', '/api/v1/status')
