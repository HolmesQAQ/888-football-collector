"""Open a data directory through Windows Explorer, without invoking a shell."""
import os
import subprocess
import threading
from pathlib import Path


def open_folder(folder):
    path=Path(folder).resolve(strict=True)
    if not path.is_dir():raise ValueError('打开目标不是文件夹')
    if os.name!='nt':raise RuntimeError('当前系统不支持打开Windows文件夹，请复制保存路径')
    explorer=Path(os.environ.get('WINDIR',r'C:\Windows'))/'explorer.exe'
    process=subprocess.Popen([str(explorer),'/n,',str(path)],shell=False)
    threading.Thread(target=process.wait,daemon=True).start()
    return str(path)
