"""Install/undo the version-pinned official-client expression patch with daemon stopped."""
import argparse
import hashlib
import importlib.metadata
from pathlib import Path
import shutil
import socket
import sys

ORIGINAL='ca18dbc85041a49b784b17b0bb09c06a7c6eec82bcd8f1dd2a23d64275a18943'
p=argparse.ArgumentParser();p.add_argument('--rollback',action='store_true');args=p.parse_args()
if importlib.metadata.version('reachy-mini') not in ('1.8.0', '1.11.0'):
    sys.exit('Only verified SDK 1.8.0/1.11.0 routers are supported; no files changed.')
with socket.socket() as s:
    s.settimeout(1)
    if s.connect_ex(('127.0.0.1',8000))==0:
        sys.exit('Close Reachy Mini Control first; daemon still listening on 8000.')
site=Path(sys.prefix)/'Lib'/'site-packages'
router=site/'reachy_mini/daemon/app/routers/move.py'
helper=site/'haifeng_expression_guard.py'
backup=router.with_suffix('.py.haifeng-original')
original=backup.read_bytes() if backup.exists() else router.read_bytes()
if hashlib.sha256(original).hexdigest()!=ORIGINAL:
    sys.exit('Unexpected original router hash; no files changed.')
source=original.decode('utf-8')
anchor='    return create_move_task(backend.play_move(move))'
assert source.count(anchor)==1
patched=source.replace('from reachy_mini.motion.recorded_move import RecordedMoves',
 'from reachy_mini.motion.recorded_move import RecordedMoves\nfrom haifeng_expression_guard import start_expression')
patched=patched.replace(anchor,'    return start_expression(backend, move, create_move_task, move_tasks)').encode('utf-8')
if router.read_bytes() not in (original,patched):
    sys.exit('Router changed independently; refusing to overwrite.')
if args.rollback:
    router.write_bytes(original)
    print('Original router restored. Helper retained but unused.')
else:
    compile(patched,str(router),'exec')
    helper_source=Path(__file__).with_name('haifeng_expression_guard.py').read_bytes()
    compile(helper_source,str(helper),'exec')
    if not backup.exists(): backup.write_bytes(original)
    helper.write_bytes(helper_source)
    router.write_bytes(patched)
    print('Installed expression return/overlap guard in verified official SDK.')
print('router sha256:',hashlib.sha256(router.read_bytes()).hexdigest())
