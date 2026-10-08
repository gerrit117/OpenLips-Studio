"""Explicit local-console bootstrap access, not a network endpoint."""
import argparse
from studio.server_config import load_config
parser = argparse.ArgumentParser()
parser.add_argument('--config', default='/data/server.json')
config = load_config(parser.parse_args().config)
if config.get('lan_open'):
    print(f"Home-network library: http://{config['bind']}:{config['port']}")
    print('No login, access key or certificate required.')
else:
    print(config['api_token'])
    print('Certificate SHA-256:', config.get('certificate_fingerprint', 'localhost HTTP'))
