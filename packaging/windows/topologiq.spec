# Build with the separately installed Topologiq environment.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).resolve().parents[1]
datas = collect_data_files('topologiq')
for package in ('topologiq', 'pyzx', 'numpy', 'networkx', 'matplotlib', 'imageio'):
    datas += copy_metadata(package)

a = Analysis([str(root / 'studio/topologiq_worker.py')],
    pathex=[str(root)], datas=datas, binaries=[],
    hiddenimports=['numpy.core.multiarray', 'numpy.core._multiarray_umath'],
    hooksconfig={'matplotlib': {'backends': ['Agg']}},
    excludes=['PySide6', 'qbraid', 'qiskit', 'IPython', 'notebook', 'pytest'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Topologiq',
    debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TopologiqEngine')
