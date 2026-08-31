# PyInstaller spec for the Windows agent. One file, no Python needed on the box.
#
# win32timezone is imported lazily by pywin32 at service start and PyInstaller
# cannot see that, so it has to be named. Without it the service installs and
# then fails on start, which is the least helpful moment to find out.

block_cipher = None

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "win32timezone",
        "cherubyte_agent.main",
        "cherubyte_protocol",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="cherubyte-agent",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
