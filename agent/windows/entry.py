"""PyInstaller entry point: the Windows service wrapper."""

from netscan_agent.winservice import main

if __name__ == "__main__":
    main()
