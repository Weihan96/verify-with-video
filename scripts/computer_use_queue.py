#!/usr/bin/env python3
"""Compatibility entry point preserving the original importable API."""
from pathlib import Path
_source = Path(__file__).with_name("desktop_queue.py")
exec(compile(_source.read_text(), str(_source), "exec"), globals())
