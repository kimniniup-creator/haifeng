import importlib.util
import os
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / "patches/reachy_motion_telemetry/install.py"
spec = importlib.util.spec_from_file_location("telemetry_installer", path)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def fixture(tmp_path):
    site = tmp_path / "site"
    state = site / "reachy_mini/daemon/app/routers/state.py"
    state.parent.mkdir(parents=True)
    state.write_text('router = APIRouter(prefix="/state")\nget_backend = None\n', encoding="utf-8")
    helper = tmp_path / "helper.py"
    helper.write_text("def make_router(get_backend): return None\n", encoding="utf-8")
    return site, state, helper, tmp_path / "backup"


def test_install_is_idempotent_breaks_hardlink_and_rolls_back(tmp_path):
    site, state, helper, backup = fixture(tmp_path)
    cache = tmp_path / "uv-cache-file"
    os.link(state, cache)
    original = cache.read_bytes()
    assert installer.install(site, backup, helper) == "installed"
    assert cache.read_bytes() == original
    assert not os.path.samefile(state, cache)
    assert installer.install(site, backup, helper) == "already_installed"
    assert installer.rollback(backup) == "restored"
    assert state.read_bytes() == original
    assert not (site / "haifeng_motion_telemetry.py").exists()


def test_rollback_does_not_overwrite_later_changes(tmp_path):
    site, state, helper, backup = fixture(tmp_path)
    installer.install(site, backup, helper)
    state.write_bytes(state.read_bytes() + b"# unrelated change\n")
    with pytest.raises(RuntimeError, match="unrelated"):
        installer.rollback(backup)
