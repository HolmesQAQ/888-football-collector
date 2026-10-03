"""Local browser UI; listens only on 127.0.0.1, no third-party packages."""
import argparse
import json
import secrets
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from collector import collect, BASE
from model import TZ

PAGE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>888 足球数据采集器</title>
<style>body{margin:0;background:#edf2f8;color:#17243b;font:15px/1.65 system-ui}main{max-width:1050px;margin:36px auto;padding:0 24px}h1{font-size:30px}small{color:#52647a}.card{background:white;padding:24px;border-radius:14px;margin:18px 0;box-shadow:0 3px 14px #1a305510}label{display:block;margin:14px 0 5px}input,select,button{font:inherit;padding:9px 12px;border:1px solid #c9d4e2;border-radius:7px}input[type=text]{width:90%}button{background:#145ec0;color:white;cursor:pointer;margin-right:10px}button:disabled{opacity:.5;cursor:default}.row{display:flex;gap:24px;flex-wrap:wrap}pre{white-space:pre-wrap;max-height:340px;overflow:auto;background:#122139;color:#dceaff;padding:18px;border-radius:8px}.notice{background:#fff3d8;padding:12px;border-radius:8px}a{color:#145ec0}</style>
<main><small>888 · 本地数据基础 / 第一阶段</small><h1>足球数据采集器</h1><p>按销售日保存比赛、五玩法赔率和来源证据。每轮独立归档，可导出 CSV、JSON 和浏览报告。</p>
<div class="card"><div class="row"><div><label>北京时间销售日</label><input id="date" type="date" value="TODAY"></div><div><label>数据来源</label><select id="source"><option value="both">500 + 澳客</option><option value="okooo">仅澳客</option><option value="500">仅500</option></select></div></div>
<details><summary>本地页面导入（可选）</summary><label>500 HTML文件完整路径</label><input id="import500" type="text" placeholder="C:\\...\\500.html"><label>澳客导入目录</label><input id="importokooo" type="text" placeholder="含 okooo.html 和 okooo-more-3001.html 等文件"><p><small>导入不会请求对应网站；保留导入时间，原采集时间未知，不作为当前在售依据。</small></p></details>
<p class="notice">五玩法赔率共54个选项。未开售、已截止、未知和采集缺失分别记录。24维基本面尚未采集，当前结果不标记为完整分析数据包。</p>
<button id="start" onclick="startRun()">开始采集</button><button id="stop" onclick="stopRun()" disabled>停止</button><small>停止会等待当前网络请求结束。</small></div>
<div class="card"><h2 id="status">等待开始</h2><p id="summary"></p><p id="report"></p><pre id="logs">日志将在这里显示。</pre></div>
<small>500在线读取公开混合过关页的五玩法，robots提示单独记录；403、429或验证页会停止。2026年10月1—4日按用户提供日历标记休市。数据保存在程序data目录，新运行不覆盖历史。</small></main>
<script>
async function api(path,data){let r=await fetch(path,{method:data?'POST':'GET',headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});if(!r.ok)throw Error(await r.text());return r.json()}
async function startRun(){try{await api('/api/start',{date:document.querySelector('#date').value,source:document.querySelector('#source').value,import500:document.querySelector('#import500').value,importokooo:document.querySelector('#importokooo').value});await poll()}catch(e){document.querySelector('#status').textContent=e.message}}
async function stopRun(){await api('/api/stop',{})}
async function poll(){try{let s=await api('/api/status');document.querySelector('#start').disabled=s.running;document.querySelector('#stop').disabled=!s.running;document.querySelector('#status').textContent=s.running?'正在采集…':s.status;document.querySelector('#logs').textContent=s.logs.join('\n')||'日志将在这里显示。';document.querySelector('#summary').textContent=s.summary||'';let d=document.querySelector('#report');d.replaceChildren();if(s.report){let a=document.createElement('a');a.href=s.report;a.target='_blank';a.textContent='打开本轮报告与下载文件';d.appendChild(a)}}catch(e){document.querySelector('#status').textContent='无法连接本地程序：'+e.message}}
setInterval(poll,1200);poll();
</script></html>'''


def serve(port=0, open_browser=True):
    token=secrets.token_urlsafe(32)
    state=dict(running=False,status='等待开始',logs=[],report=None,summary='')
    lock=threading.Lock();stop=threading.Event()
    def log(msg):
        with lock:state['logs'].append(msg)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def authorized(self):
            cookie=self.headers.get('Cookie','')
            return ('session='+token) in cookie.split('; ') or parse_qs(urlsplit(self.path).query).get('token')==[token]
        def send(self,body,kind='application/json; charset=utf-8',status=200):
            self.send_response(status);self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            if self.authorized():
                self.send_header('Set-Cookie','session='+token+'; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers();self.wfile.write(body if isinstance(body,bytes) else body.encode('utf-8'))
        def do_GET(self):
            if not self.authorized():
                self.send('本地会话未授权',status=403);return
            path=unquote(urlsplit(self.path).path)
            if path=='/':
                self.send(PAGE.replace('TODAY',datetime.now(TZ).date().isoformat()),'text/html; charset=utf-8')
            elif path=='/api/status':
                with lock:payload=json.dumps(state,ensure_ascii=False)
                self.send(payload)
            elif path.startswith('/data/'):
                root=(BASE/'data').resolve();f=(BASE/path.lstrip('/')).resolve()
                if not f.is_relative_to(root) or f.name not in ('report.html','snapshot.json','odds.csv','results.csv','quality.json','manifest.json') or not f.is_file():
                    self.send('Not found',status=404);return
                kind={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.csv':'text/csv; charset=utf-8'}[f.suffix]
                self.send(f.read_bytes(),kind)
            else:self.send('Not found',status=404)
        def do_POST(self):
            if not self.authorized():self.send('Forbidden',status=403);return
            origin=self.headers.get('Origin')
            if origin and origin != 'http://127.0.0.1:'+str(self.server.server_port):
                self.send('Forbidden origin',status=403);return
            path=urlsplit(self.path).path
            if path=='/api/stop':stop.set();self.send('{}');return
            if path!='/api/start':self.send('Not found',status=404);return
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<10000:raise ValueError('无效请求大小')
                args=json.loads(self.rfile.read(length))
                datetime.strptime(args['date'],'%Y-%m-%d')
                if args['source'] not in ('500','okooo','both'):raise ValueError('来源无效')
                imports={k:args[v].strip() for k,v in [('500','import500'),('okooo','importokooo')] if args.get(v,'').strip()}
                for value in imports.values():
                    if not Path(value).exists():raise ValueError('导入路径不存在：'+value)
            except (ValueError,KeyError,TypeError) as e:self.send(str(e),status=400);return
            with lock:
                if state['running']:self.send('正在运行',status=409);return
                state.update(running=True,status='正在采集',logs=[],report=None,summary='')
            stop.clear()
            def worker():
                try:
                    folder,r=collect(args['date'],sources=('500','okooo') if args['source']=='both' else (args['source'],),imports=imports,stop=stop,log=log)
                    label={'MARKET_CLOSED':'目标销售日休市 · 正常无销售数据','NEEDS_REVIEW':'采集完成 · 存在待核对项','NO_USABLE_MATCHES':'本轮未取得目标日期的可用比赛','STOPPED':'已停止并保存','COLLECTED_NOT_INDEPENDENTLY_VERIFIED':'采集完成 · 尚未独立核验'}[r['status']]
                    counts=[]
                    for source in ('500','okooo'):
                        ms=[m for m in r['matches'] if m['source']==source]
                        if any(s['source']==source for s in r['sources']):
                            counts.append(source+'：'+str(len(ms))+' 场，'+str(sum(v['observed_count'] for m in ms for v in m['markets'].values()))+' 个赔率值，'+str(sum(m.get('result',{}).get('status')=='FINISHED' for m in ms))+' 场已取得完赛结果')
                    with lock:state.update(status=label,report='/data/'+folder.name+'/report.html',summary='；'.join(counts))
                except Exception as e:
                    log('运行失败：'+str(e))
                    with lock:state['status']='运行失败，请检查日志'
                finally:
                    with lock:state['running']=False
            threading.Thread(target=worker,daemon=True).start();self.send('{}')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    url='http://127.0.0.1:'+str(server.server_port)+'/?token='+token
    print(url,flush=True)
    if open_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:stop.set()
    finally:server.server_close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=0);p.add_argument('--no-browser',action='store_true')
    a=p.parse_args();serve(a.port,not a.no_browser)
