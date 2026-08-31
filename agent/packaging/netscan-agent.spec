# PyInstaller spec shared by all three platforms.
#
# One binary, no Python on the target. The Windows build additionally needs the
# pywin32 service framework, which is imported lazily and therefore invisible to
# PyInstaller's analysis — without naming it the service installs and then fails
# to start, which is the least helpful moment to find out.

import sys

WINDOWS = sys.platform == "win32"

hidden = [
    "netscan_agent.main",
    "netscan_protocol",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]
if WINDOWS:
    hidden += ["win32timezone", "netscan_agent.winservice"]

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="netscan-agent",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
