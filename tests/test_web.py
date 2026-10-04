import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit,quote
from urllib.request import Request,urlopen
import app
from activity import data_lock
from history import history_targets,clear_history


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.patch=patch.object(app,'BASE',self.base);self.patch.start()
        self.server,self.url,self.state,self.stop=app.create_server()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        parts=urlsplit(self.url);self.origin=parts.scheme+'://'+parts.netloc;self.query=parts.query

    def tearDown(self):
        self.stop.set()
        self.server.shutdown();self.thread.join();self.server.server_close()
        self.patch.stop();self.temp.cleanup()

    def api(self,path,data=None,authorized=True,origin=None):
        url=self.origin+quote(path)+('?' + self.query if authorized else '')
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        with urlopen(Request(url,data=json.dumps(data).encode() if data is not None else None,headers=headers),timeout=5) as response:
            return response.read()

    def collect(self):
        fixtures=Path(__file__).parent/'fixtures'
        self.api('/api/start',dict(date='2026-09-30',source='both',import500=str(fixtures/'500.html'),importokooo=str(fixtures)))
        for _ in range(100):
            if not self.state['running']:break
            time.sleep(.02)
        self.assertFalse(self.state['running'])
        self.assertIsNotNone(self.state['current_run'])
        return self.state['current_run']

    def test_web_full_flow_and_confirmed_cleanup(self):
        run=self.collect()
        self.assertIn(run,json.loads(self.api('/api/history'))['runs'])
        self.assertIn('汇总',self.api('/api/view',{'run_id':run}).decode())
        self.assertEqual(json.loads(self.api('/api/verify',{'run_id':run}))['errors'],[])
        self.assertFalse(json.loads(self.api('/data/'+run+'/ai_input.json'))['ready_for_analysis'])
        self.assertIn('销售日',self.api('/data/'+run+'/汇总.csv').decode('utf-8-sig'))
        with patch.object(app,'open_folder') as opened:
            self.api('/api/open',{'scope':'current'})
            self.api('/api/open',{'scope':'root'})
            self.api('/api/open',{'scope':'selected','run_id':run})
            self.assertEqual(Path(opened.call_args_list[0].args[0]).resolve(),(self.base/'data'/run).resolve())
        preview=json.loads(self.api('/api/clear-preview',{}))
        with self.assertRaises(HTTPError):self.api('/api/clear',{'token':preview['token'],'confirmation':'no'})
        self.assertTrue((self.base/'data'/run).exists())
        self.api('/api/clear',{'token':preview['token'],'confirmation':'CLEAR'})
        self.assertFalse((self.base/'data'/run).exists())
        self.assertIsNone(self.state['current_run'])
        self.assertEqual(json.loads(self.api('/api/history'))['runs'],[])
        self.collect()  # Database and outputs remain usable after cleanup.

    def test_access_origin_and_path_checks(self):
        for path,data,auth,origin in [('/api/status',None,False,None),('/api/clear-preview',{},True,'https://example.com'),('/api/view',{'run_id':'../../elsewhere'},True,None),('/api/clear',{'confirmation':'CLEAR'},True,None)]:
            with self.assertRaises(HTTPError):self.api(path,data,auth,origin)
        self.state['running']=True
        with self.assertRaises(HTTPError) as caught:self.api('/api/clear-preview',{})
        self.assertEqual(caught.exception.code,409)
        self.state['running']=False

    def test_other_process_activity_blocks_clear(self):
        self.collect();targets=history_targets(self.base)
        with data_lock(self.base/'data'):
            with self.assertRaisesRegex(RuntimeError,'其他窗口'):clear_history(self.base,targets)
        self.assertTrue((self.base/'data'/self.state['current_run']).exists())
