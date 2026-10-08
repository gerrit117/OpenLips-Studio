"""Local certificates and owner-approved per-device library credentials."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import ssl
import threading
import time
import uuid


def create_certificate(folder, bind='127.0.0.1'):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, timezone
    import ipaddress
    folder = Path(folder)
    key_path, cert_path = folder / 'library-key.pem', folder / 'library-cert.pem'
    if key_path.exists() or cert_path.exists():
        raise FileExistsError('Library certificate already exists')
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'OpenLips Library')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),
            *[x509.IPAddress(ipaddress.ip_address(value)) for value in sorted({'127.0.0.1', bind})]]), critical=False)
        .sign(key, hashes.SHA256()))
    for path, data in [(key_path, key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())),
            (cert_path, cert.public_bytes(serialization.Encoding.PEM))]:
        with path.open('xb') as stream:
            if os.name != 'nt':
                os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
    return str(cert_path), str(key_path)


def certificate_fingerprint(path):
    der = ssl.PEM_cert_to_DER_cert(Path(path).read_text(encoding='ascii'))
    return hashlib.sha256(der).hexdigest()


class DeviceAuth:
    def __init__(self, library, config, authorizer=None):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.exceptions import InvalidTag
        self.library, self.config, self.authorizer = library, config, authorizer
        self.cipher = AESGCM(hashlib.sha256(('openlips-device-v1:' + config['api_token']).encode()).digest())
        self.lock = threading.Lock()
        self.pair_code, self.expires, self.attempts = None, 0, 0
        with library.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY,
                name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, ftp_secret TEXT NOT NULL,
                created REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)''')
            rows = db.execute('SELECT * FROM devices WHERE revoked=0').fetchall()
        for row in rows:
            try:
                credential = self.decrypt(row['ftp_secret'])
            except (ValueError, InvalidTag):
                # Rotating the owner secret invalidates old device credentials.
                with library.connect() as db:
                    db.execute('UPDATE devices SET revoked=1 WHERE id=?', (row['id'],))
                continue
            if authorizer:
                authorizer.add_user(credential['username'], credential['password'],
                    str(library.root / 'publish'), perm='elr')

    def encrypt(self, data):
        nonce = secrets.token_bytes(12)
        return base64.b64encode(nonce + self.cipher.encrypt(nonce, json.dumps(data).encode(), b'OpenLips device')).decode()

    def decrypt(self, value):
        raw = base64.b64decode(value, validate=True)
        return json.loads(self.cipher.decrypt(raw[:12], raw[12:], b'OpenLips device'))

    def is_master(self, token):
        return hmac.compare_digest(token.encode(), self.config['api_token'].encode())

    def valid(self, token):
        if self.is_master(token):
            return True
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.library.connect() as db:
            return db.execute('SELECT 1 FROM devices WHERE token_hash=? AND revoked=0', (digest,)).fetchone() is not None

    def begin_pairing(self):
        with self.lock:
            self.pair_code = secrets.token_hex(4).upper()
            self.expires = time.monotonic() + 300
            self.attempts = 0
            return dict(code=self.pair_code, expires_in=300)

    def pair(self, code, name):
        if not isinstance(code, str) or not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Invalid pairing request')
        with self.lock:
            self.attempts += 1
            if (not self.pair_code or time.monotonic() > self.expires or self.attempts > 5
                    or not hmac.compare_digest(code.strip().upper().encode(), self.pair_code.encode())):
                raise ValueError('Pairing code invalid or expired')
            with self.library.connect() as db:
                if db.execute('SELECT count(*) FROM devices WHERE revoked=0').fetchone()[0] >= 128:
                    raise ValueError('Too many paired devices')
                identifier, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
                ftp = dict(username='device-' + identifier, password=secrets.token_urlsafe(24))
                db.execute('INSERT INTO devices VALUES (?,?,?,?,?,0)',
                    (identifier, name.strip(), hashlib.sha256(token.encode()).hexdigest(), self.encrypt(ftp), time.time()))
            if self.authorizer:
                self.authorizer.add_user(ftp['username'], ftp['password'], str(self.library.root / 'publish'), perm='elr')
            self.pair_code = None
            return dict(device_id=identifier, api_token=token, ftp=ftp)

    def devices(self):
        with self.library.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,name,created,revoked FROM devices ORDER BY created DESC')]

    def revoke(self, identifier):
        with self.library.connect() as db:
            row = db.execute('SELECT ftp_secret FROM devices WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise KeyError('Unknown device')
            db.execute('UPDATE devices SET revoked=1 WHERE id=?', (identifier,))
        if self.authorizer:
            username = self.decrypt(row['ftp_secret'])['username']
            if self.authorizer.has_user(username):
                self.authorizer.remove_user(username)
