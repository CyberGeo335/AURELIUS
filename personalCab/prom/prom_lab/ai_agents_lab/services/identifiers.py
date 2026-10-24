"""Deterministic hashes for idempotent application commands."""
import hashlib
import json


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


