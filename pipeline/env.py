"""
Minimal .env loader, no third-party dependency, no network, no surprises.

Reads KEY=VALUE lines from the project-root .env into a dict. Real process
environment variables win over the file, so CI/secret-managers can override
without editing anything on disk.
"""

from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")


def load(path: str = ENV_PATH) -> dict[str, str]:
    """Parse .env. Missing file is fine, returns whatever the OS env has."""
    values: dict[str, str] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                if val:
                    values[key.strip()] = val
    # process env takes precedence
    for key in list(values) + ["HF_TOKEN", "META_ACCESS_TOKEN",
                               "YOUTUBE_API_KEY", "CRAWLER_CONTACT"]:
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def get(key: str, default: str | None = None) -> str | None:
    return load().get(key, default)


def require(key: str) -> str:
    """Fetch a credential or explain precisely how to obtain it."""
    val = get(key)
    if not val:
        raise SystemExit(
            f"\nMissing {key}.\n"
            f"  1. Open {ENV_PATH}\n"
            f"  2. Set {key}=<your value>\n"
            f"  3. See .env.example for where to get it.\n"
        )
    return val


def redact(secret: str) -> str:
    """Safe-to-log form of a credential. Never print a raw token."""
    if not secret:
        return "<unset>"
    return f"{secret[:4]}…{secret[-2:]} ({len(secret)} chars)"
