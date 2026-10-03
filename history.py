"""Clear only collector-owned historical runs and the aggregate archive."""
import os
from pathlib import Path
import re
import shutil
import stat
from activity import data_lock

RUN_NAME = re.compile(r'\d{8}T\d{6}-[0-9a-f]{8}')
DATABASES = ('archive.sqlite3', 'archive.sqlite3-wal', 'archive.sqlite3-shm', 'archive.sqlite3-journal')


def check_path(path, root):
    if path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
        raise ValueError('拒绝清理链接或重定向目录：' + str(path))
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError('清理路径超出数据目录：' + str(path))


def history_targets(base):
    base = Path(base).resolve()
    root = base / 'data'
    if not root.exists(): return []
    check_path(root, base)
    root = root.resolve()
    folders = [p for p in root.iterdir() if RUN_NAME.fullmatch(p.name)]
    targets = [root/n for n in DATABASES if (root/n).exists()] + sorted(folders)
    for path in targets:
        check_path(path, root)
        if path.is_dir():
            for parent, dirs, files in os.walk(path, followlinks=False):
                for name in dirs + files: check_path(Path(parent)/name, root)
    return targets


def clear_history(base, expected):
    with data_lock(Path(base)/'data'):
        return _clear_history(base,expected)


def _clear_history(base, expected):
    targets = history_targets(base)
    if targets != expected:
        raise RuntimeError('历史目录已变化，请重新选择清除。请先停止其他正在运行的采集程序。')
    root = (Path(base).resolve()/'data').resolve()
    deleted = []
    for path in targets:
        check_path(path, root)
        try:
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
        except OSError as error:
            raise RuntimeError('清除未全部完成，已处理 '+str(len(deleted))+' 项；无法删除 '+str(path)+'。请关闭占用文件的程序后重试。') from error
        deleted.append(path)
    return len(deleted)
