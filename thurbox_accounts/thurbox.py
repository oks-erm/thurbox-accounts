"""Bounded transport for the public Thurbox JSON CLI."""
import json
from pathlib import Path
from .runtime import execute


def strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"invalid JSON constant: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


class Thurbox:
    def __init__(self, command=None, *, timeout=30):
        self.command = command or ['thurbox-cli']
        self.timeout = timeout

    def call(self, *args: str, timeout: float | None = None) -> dict:
        argv = list(args)
        argv.insert(argv.index('--') if '--' in argv else len(argv),'--json')
        result = execute([*self.command, *argv], Path.cwd(), timeout=timeout or self.timeout,
                         limit=2_000_000)
        if result["status"] == "TIMEOUT":
            raise TimeoutError(f"Thurbox {' '.join(args[:2])} exceeded its deadline")
        if result["status"] != "PASS" or result["truncated"]:
            detail = result["stderr"]
            try:
                failure = strict_json(result["stdout"])
                if isinstance(failure, dict) and isinstance(failure.get("error"), str):
                    detail = failure["error"]
            except ValueError:
                pass
            raise RuntimeError(f"Thurbox {' '.join(args[:2])} failed ({result['status']}): "
                               f"{detail[:1000] or 'no diagnostic returned'}")
        value = strict_json(result["stdout"])
        if args[:2] == ('session','list') and isinstance(value,list) and all(isinstance(row,dict) for row in value):
            value = dict(sessions=value)
        if not isinstance(value, dict) or value.get("ok") is False:
            raise ValueError("Thurbox returned invalid or unsuccessful JSON")
        return value
