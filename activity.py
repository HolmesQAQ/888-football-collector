"""Cross-process exclusion for collection and history deletion."""
from contextlib import contextmanager
import os
from pathlib import Path


@contextmanager
def data_lock(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    f=(root/'.activity.lock').open('a+b')
    locked=False
    try:
        if f.seek(0,2)==0: f.write(b'0');f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            locked=True
        except OSError as error:
            raise RuntimeError('其他窗口正在采集或清理，请等待完成后重试。') from error
        yield
    finally:
        if locked:
            f.seek(0)
            if os.name=='nt': msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(f.fileno(),fcntl.LOCK_UN)
        f.close()
