"""Private atomic files, JSON serialization and diagnostic redaction."""
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def redact(text: str) -> str:
    for key, value in os.environ.items():
        if re.search(r"TOKEN|SECRET|PASSWORD|CREDENTIAL|API_KEY|PRIVATE_KEY", key, re.I) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{12,}|github_pat_[\w]{12,})", "[REDACTED]", text)
    return re.sub(r"(?i)(authorization\s*:\s*bearer\s+)\S+", r"\1[REDACTED]", text)


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def atomic_write(path: Path, content: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
