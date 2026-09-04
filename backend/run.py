#!/usr/bin/env python3
"""Entrypoint for the Cherubyte panel service (port 1001 by default).

The panel holds the database and the UI and scans nothing — discovery is the
agent's job, in its own program (github.com/Cherubyte/cherubyte-agent). So the
only privilege this process needs is to bind the privileged port 1001:

  * systemd (recommended, persistent):  ./scripts/setup.sh --service
      (already set up and just want the unit (re)installed on its own:
      ./scripts/install-service.sh)
  * capability on the venv python:
        sudo setcap 'cap_net_bind_service+eip' \\
          "$(readlink -f backend/.venv/bin/python)"
  * a high port:  CHERUBYTE_PORT=8001 backend/.venv/bin/python backend/run.py
"""

from __future__ import annotations

import sys

import uvicorn

from app.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload="--reload" in sys.argv,
    )
