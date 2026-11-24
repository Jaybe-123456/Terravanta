import struct

import pytest

from app.config import settings
from app import evidence_storage
from app.evidence_storage import EvidenceMalwareDetected, EvidenceScannerUnavailable, scan_evidence


class FakeClamdConnection:
    def __init__(self, verdict: bytes):
        self.verdict = verdict + b"\0"
        self.sent = bytearray()
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, value):
        self.sent.extend(value)

    def recv(self, _size):
        verdict, self.verdict = self.verdict, b""
        return verdict


def fake_scanner(monkeypatch, verdict: bytes):
    connection = FakeClamdConnection(verdict)
    monkeypatch.setattr(settings, "evidence_scanner_host", "clamd.private")
    monkeypatch.setattr(settings, "evidence_scanner_port", 3310)
    monkeypatch.setattr(settings, "evidence_scanner_timeout_seconds", 2)
    monkeypatch.setattr(evidence_storage.socket, "create_connection", lambda *_args, **_kwargs: connection)
    return connection


def unpack_instream(connection: FakeClamdConnection) -> bytes:
    assert connection.sent.startswith(b"zINSTREAM\0")
    offset = len(b"zINSTREAM\0")
    payload = bytearray()
    while True:
        size = struct.unpack("!I", connection.sent[offset:offset + 4])[0]
        offset += 4
        if size == 0:
            break
        payload.extend(connection.sent[offset:offset + size])
        offset += size
    assert offset == len(connection.sent)
    return bytes(payload)


def test_clamd_instream_accepts_clean_file(monkeypatch):
    payload = b"cooperative statement sample"
    connection = fake_scanner(monkeypatch, b"stream: OK")
    scan_evidence(payload)
    assert unpack_instream(connection) == payload


def test_clamd_instream_rejects_malware(monkeypatch):
    payload = b"test signature"
    fake_scanner(monkeypatch, b"stream: Eicar-Signature FOUND")
    with pytest.raises(EvidenceMalwareDetected):
        scan_evidence(payload)


def test_scanning_fails_closed_when_scanner_is_missing(monkeypatch):
    monkeypatch.setattr(settings, "evidence_scanner_host", "")
    with pytest.raises(EvidenceScannerUnavailable):
        scan_evidence(b"evidence")
