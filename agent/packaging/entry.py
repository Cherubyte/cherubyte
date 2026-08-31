"""PyInstaller entry point.

On Windows the binary is a service and must speak the Service Control Manager
protocol. Everywhere else it is an ordinary foreground process, because systemd
and launchd supervise a normal process and want it to stay in the foreground.
"""

import sys


def main() -> None:
    if sys.platform == "win32":
        from netscan_agent.winservice import main as service_main

        service_main()
        return

    import uvicorn

    from netscan_agent.config import settings

    uvicorn.run(
        "netscan_agent.main:app", host=settings.health_host, port=settings.health_port
    )


if __name__ == "__main__":
    main()
