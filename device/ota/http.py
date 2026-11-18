"""Bounded HTTP/1.0 over TLS without CA verification, raw.githubusercontent.com only.
No redirects, chunking, gzip or credentials. Fail closed on unsupported framing.
"""
import socket
import ssl
import time

HOST = 'raw.githubusercontent.com'

def line(stream, limit=1024):
    data = bytearray()
    while len(data) < limit:
        b = stream.read(1)
        if not b:
            raise OSError('truncated HTTP header')
        data.extend(b)
        if data[-2:] == b'\r\n':
            return bytes(data[:-2])
    raise ValueError('HTTP header line too long')

def headers(stream, maximum):
    status = line(stream)
    parts = status.split(b' ')
    if len(parts) < 2 or parts[0] not in (b'HTTP/1.0', b'HTTP/1.1') or parts[1] != b'200':
        raise OSError('HTTP response: ' + status.decode())
    fields, total = {}, len(status)
    while True:
        b = line(stream)
        total += len(b) + 2
        if total > 8192:
            raise ValueError('HTTP headers too large')
        if not b:
            break
        k, v = b.split(b':', 1)
        k = k.strip().lower()
        if k in fields:
            raise ValueError('duplicate HTTP header')
        fields[k] = v.strip()
    if b'transfer-encoding' in fields or fields.get(b'content-encoding', b'identity') != b'identity':
        raise ValueError('unsupported HTTP encoding')
    if b'content-length' not in fields:
        raise ValueError('Content-Length required')
    n = int(fields[b'content-length'])
    if not 0 < n <= maximum:
        raise ValueError('HTTP body size')
    return n

class GitHub:
    def __init__(self, config, feed=lambda: None):
        self.c, self.feed = config, feed
        for value in (config.GITHUB_OWNER, config.GITHUB_REPO, config.GITHUB_REF):
            if not value or not all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.' for c in value) or value in ('.', '..'):
                raise ValueError('invalid GitHub coordinate')
        self.base = '/%s/%s/%s/' % (config.GITHUB_OWNER, config.GITHUB_REPO, config.GITHUB_REF)

    def fetch(self, path, maximum, sink):
        if path.startswith('/') or '..' in path or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./-' for c in path):
            raise ValueError('invalid URL path')
        raw = wrapped = None
        try:
            self.feed()
            addr = socket.getaddrinfo(HOST, 443, 0, socket.SOCK_STREAM)[0][-1]
            raw = socket.socket()
            raw.settimeout(self.c.SOCKET_TIMEOUT_S)
            raw.connect(addr)
            # Transport encryption only. Authenticity comes from the mandatory
            # signed manifest and SHA-256 verification of every payload file.
            # Do not install any content unless both checks pass.
            wrapped = ssl.wrap_socket(raw, server_hostname=HOST, cert_reqs=ssl.CERT_NONE)
            request = ('GET ' + self.base + path + ' HTTP/1.0\r\nHost: ' + HOST +
                       '\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n').encode()
            offset = 0
            while offset < len(request):
                count = wrapped.write(request[offset:])
                if not count:
                    raise OSError('short request write')
                offset += count
            remaining = headers(wrapped, maximum)
            started = time.ticks_ms()
            while remaining:
                if time.ticks_diff(time.ticks_ms(), started) > self.c.DOWNLOAD_TIMEOUT_MS:
                    raise OSError('download deadline')
                data = wrapped.read(min(1024, remaining))
                if not data:
                    raise OSError('truncated HTTP body')
                sink(data)
                remaining -= len(data)
                self.feed()
        finally:
            if wrapped:
                wrapped.close()
            if raw:
                raw.close()

    def get(self, path, maximum):
        data = bytearray()
        self.fetch(path, maximum, data.extend)
        return bytes(data)
