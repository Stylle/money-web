"""Called only after both managed services stop; never touch a shared database."""
import os
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
os.environ['DATA_DIR'] = str(root/'data')
from app.db import engine
if engine.url.get_backend_name() != 'sqlite' or Path(engine.url.database).resolve() != (root/'data'/'invest.db').resolve():
    print('Shared database detected; leases retained.')
    raise SystemExit(0)
from app.services import release
for key in ('worker','refresh','news'):
    release(key)
print('Released local task leases after stopping services.')
