"""Reversible camera/motion isolation for official conversation 1.0.1 on Windows."""
import argparse,hashlib,importlib.util
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--rollback',action='store_true');args=p.parse_args()
spec=importlib.util.find_spec('reachy_mini_conversation_app')
assert spec and spec.origin
main=Path(spec.origin).with_name('main.py')
backup=main.with_suffix('.py.haifeng-original')
original=backup.read_bytes() if backup.exists() else main.read_bytes()
assert hashlib.sha256(original).hexdigest()=='04a917971ff766cd33df49542a6e094d861660e1cbc6677d9283cd9f7b8158f1', 'Unexpected upstream main.py'
source=original.decode('utf-8')
replacements={
 '    app_lifecycle.wake_up_if_sleeping(robot, logger)':
 '    # Haifeng voice-only adaptation: no camera or automatic motor commands.\n    args.no_camera = True\n    robot.media._init_audio("INFO")',
 '    movement_manager.start()':'    logger.info("Haifeng voice-only: movement loop is disabled")',
 '    robot.enable_wobbling()':'    logger.info("Haifeng voice-only: speech wobbling is disabled")',
 '    dont_start_webserver = False':'    dont_start_webserver = False\n    request_media_backend = "no_media"',
}
for old,new in replacements.items():
 assert source.count(old)==1,old
 source=source.replace(old,new)
patched=source.encode('utf-8')
assert main.read_bytes() in (original,patched), 'Independent changes detected; refusing overwrite'
compile(patched,str(main),'exec')
if args.rollback:main.write_bytes(original)
else:
 if not backup.exists():backup.write_bytes(original)
 main.write_bytes(patched)
print('Voice-only adaptation:', 'rolled back' if args.rollback else 'installed')
print('sha256:',hashlib.sha256(main.read_bytes()).hexdigest())
