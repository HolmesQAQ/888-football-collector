"""Interactive terminal menu; never starts a web server or browser."""
import json
import os
from folders import open_folder
from datetime import date, datetime
from collector import BASE, VERSION, collect
from model import TZ
from verify import verify
from summary import summary_lines
from history import history_targets, clear_history, RUN_NAME


def ask_date():
    while True:
        value = input('销售日 YYYY-MM-DD（回车=今天，0=取消）：').strip()
        if value == '0': return None
        if not value: return datetime.now(TZ).date().isoformat()
        try: return date.fromisoformat(value).isoformat()
        except ValueError: print('日期无效，例如 2026-09-17。')


def show_summary(report):
    print('\n销售日：', report['sale_date'], '  状态：', report['status'])
    for source in report['sources']:
        ms = [m for m in report['matches'] if m['source'] == source['source']]
        print(source['source'], '比赛', len(ms), '场；赔率',
              sum(v['observed_count'] for m in ms for v in m['markets'].values()),
              '项；完赛', sum(m.get('result', {}).get('status') == 'FINISHED' for m in ms), '场')
        print('  ', source.get('error') or source.get('reason') or source.get('results_status') or source['status'])
    print('\n'.join(summary_lines(report)))
    print('待核对不等于没有数据；源站缺项和24维资料未完成仍会保留。')


def choose_archive():
    folders = sorted((BASE / 'data').glob('*/snapshot.json'), reverse=True)[:20]
    if not folders:
        print('暂无采集记录。'); return None
    for i, path in enumerate(folders, 1): print(str(i) + '.', path.parent.name)
    choice = input('选择记录编号（0=取消）：').strip()
    if choice == '0': return None
    if not choice.isdigit() or not 1 <= int(choice) <= len(folders):
        print('编号无效。'); return None
    return folders[int(choice)-1].parent


def main():
    current_folder = None
    while True:
        print('\n=== 888 足球采集器 v' + VERSION + ' · 命令行 ===')
        print('1. 开始采集\n2. 查看历史结果\n3. 校验历史文件')
        print('4. 打开本次采集文件夹' if current_folder else '4. 打开数据总文件夹')
        if current_folder: print('5. 打开数据总文件夹')
        print('6. 清除历史数据\n0. 退出')
        try:
            choice = input('请选择：').strip()
            if choice == '0': return 0
            if choice == '1':
                day = ask_date()
                if day is None: continue
                print('1. 500 + 澳客（默认）\n2. 仅500\n3. 仅澳客\n0. 取消')
                selected = input('选择来源：').strip() or '1'
                if selected == '0': continue
                sources = {'1': ('500','okooo'), '2': ('500',), '3': ('okooo',)}.get(selected)
                if sources is None:
                    print('来源选项无效。'); continue
                folder, report = collect(day, sources=sources)
                current_folder = folder
                show_summary(report)
                print('保存位置：', folder)
                print('优先查看：先看这里.txt、汇总.csv；按4直接打开本次目录。')
            elif choice in ('2','3'):
                folder = choose_archive()
                if folder is None: continue
                if choice == '2': show_summary(json.loads((folder/'snapshot.json').read_text('utf-8')))
                else:
                    errors = verify(folder)
                    print('校验通过' if not errors else '校验失败：' + '；'.join(errors))
            elif choice == '4' or (choice == '5' and current_folder):
                folder = current_folder if choice == '4' and current_folder else BASE / 'data'
                folder.mkdir(parents=True, exist_ok=True)
                open_folder(str(folder))
                print('已请求打开数据文件夹：', folder)
            elif choice == '6':
                targets = history_targets(BASE)
                if not targets:
                    print('没有可清除的历史数据。'); continue
                count = sum(bool(RUN_NAME.fullmatch(p.name)) for p in targets)
                print('将永久删除 '+str(count)+' 轮采集目录（含原始页面、汇总、报告等）及本地历史数据库。')
                print('范围：', BASE/'data')
                print('程序、Python环境、运行日志及其他非采集目录保留。请先停止其他采集程序。')
                if input('输入 CLEAR 确认清除，其他输入取消：').strip() != 'CLEAR':
                    print('已取消，历史数据未改动。'); continue
                try:
                    clear_history(BASE, targets)
                finally:
                    if current_folder and not current_folder.exists(): current_folder = None
                current_folder = None
                print('历史数据已清除，可以重新开始采集。')
            else: print('请输入菜单中的数字。')
        except EOFError: return 0
        except KeyboardInterrupt:
            print('\n已中断当前操作；正在采集的本轮可能未完成归档。返回菜单。')
        except Exception as error:
            print('操作失败：', error, '\n可检查网络或文件路径后重试。')


if __name__ == '__main__':
    raise SystemExit(main())
