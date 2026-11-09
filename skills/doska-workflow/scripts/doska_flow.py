#!/usr/bin/env python3
"""CLI entrypoint; importing does not activate tracking."""
from doska_flow.cli import main
if __name__ == '__main__':
    raise SystemExit(main())
