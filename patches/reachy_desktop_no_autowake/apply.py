"""Validate/apply the source patch in an explicitly selected offline Git checkout.

Never builds, installs, starts or stops an application. Dry-run is the default.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.checkout.resolve(strict=True)
    bundle = Path(__file__).resolve().parent
    spec = json.loads((bundle / 'manifest.json').read_text())
    if any(part.lower() in {'program files', 'program files (x86)', 'appdata'} for part in root.parts):
        raise SystemExit('Refusing an installed application directory; use an offline source checkout.')
    if not (root / '.git').exists():
        raise SystemExit('An explicit Git checkout is required.')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    if Path(git('rev-parse', '--show-toplevel')).resolve() != root:
        raise SystemExit('Pass the Git root, not a subdirectory.')
    if git('rev-parse', 'HEAD') != spec['upstream_commit']:
        raise SystemExit('Upstream commit differs; re-review before applying.')
    target = root / spec['path']
    digest = hashlib.sha256(target.read_text(encoding='utf-8').encode()).hexdigest()
    if digest == spec['patched_sha256_lf']:
        print('Already patched; no writes.')
        return
    if digest != spec['original_sha256_lf']:
        raise SystemExit('Source differs; refusing to overwrite local edits.')
    patch = str(bundle / 'no-autowake.patch')
    git('apply', '--check', '--ignore-space-change', patch)
    if args.apply:
        git('apply', '--ignore-space-change', patch)
        actual = hashlib.sha256(target.read_text(encoding='utf-8').encode()).hexdigest()
        if actual != spec['patched_sha256_lf']:
            raise SystemExit('Post-apply hash mismatch; inspect checkout before continuing.')
    print('Source patch applied.' if args.apply else 'Dry-run passed; no writes.')


if __name__ == '__main__':
    main()
