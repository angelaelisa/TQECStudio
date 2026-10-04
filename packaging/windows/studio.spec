# Build on Windows using: python -m PyInstaller packaging/windows/studio.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).resolve().parents[1]
datas = [(str(root / name), '.') for name in ('LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md')]
binaries = []
# Stim's native sampler imports NumPy's compatibility modules dynamically.
hiddenimports = ['numpy.core.multiarray', 'numpy.core._multiarray_umath']
for name in ('studio', 'tqec', 'tqecd', 'stim', 'sinter', 'pymatching', 'pyzx', 'defusedxml'):
    data, binary, hidden = collect_all(name)
    datas += data
    binaries += binary
    hiddenimports += hidden
for name in ('tqec', 'stim', 'sinter', 'flask', 'matplotlib', 'pymatching'):
    datas += copy_metadata(name, recursive=True)

a = Analysis([str(root / 'packaging/windows/launch.py')], pathex=[str(root)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=['pytest', 'IPython', 'notebook'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TQEC Studio',
    debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TQEC Studio')
