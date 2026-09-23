"""Installer writes must not modify other environments sharing uv hardlinks."""
import ast
import os
from pathlib import Path
import tempfile
import unittest


class InstallIsolationTests(unittest.TestCase):
    def test_replace_does_not_modify_shared_cache_inode(self):
        # Load only the writer: importing install.py would modify a real SDK.
        tree = ast.parse(Path(__file__).with_name('install.py').read_text())
        writer = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                      and n.name == 'atomic_write')
        namespace = {'os': os, 'tempfile': tempfile}
        exec(compile(ast.Module(body=[writer], type_ignores=[]), '<writer>', 'exec'), namespace)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'cache.py'
            router = Path(directory) / 'move.py'
            sibling = Path(directory) / 'sibling.py'
            cache.write_bytes(b'original')
            os.link(cache, router)
            os.link(cache, sibling)
            namespace['atomic_write'](router, b'patched')
            self.assertEqual(router.read_bytes(), b'patched')
            self.assertEqual(cache.read_bytes(), b'original')
            self.assertEqual(sibling.read_bytes(), b'original')
            namespace['atomic_write'](router, b'original')
            self.assertEqual(router.read_bytes(), b'original')
            self.assertEqual(len(list(Path(directory).iterdir())), 3)


if __name__ == '__main__':
    unittest.main()
