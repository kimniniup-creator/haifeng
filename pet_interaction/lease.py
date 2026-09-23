"""Process lease shared by all ports/checkouts; released by OS on process exit."""
import os
from pathlib import Path
import tempfile


class ProcessLease:
    def __enter__(self):
        self.file = (Path(tempfile.gettempdir()) / "haifeng-pet-interaction.lock").open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError("pet_interaction_already_running") from exc
        return self

    def __exit__(self, *args):
        self.file.close()
