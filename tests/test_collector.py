import copy
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from contextlib import closing
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters import parse_500,parse_500_live,parse_okooo,parse_okooo_more
from collector import collect,Fetcher
from model import OUTCOMES,DIMENSIONS,new_match,set_quote,finish_match,compare,price
from verify import verify
from results import attach_results

FIXTURES=Path(__file__).parent/'fixtures'
AT='2026-10-03T12:00:00+08:00'


class Tests(unittest.TestCase):
    def test_500_public_score_real_history(self):
        matches,state=parse_500_live((FIXTURES/'500-live-20260930.html').read_bytes(),'2026-09-30','https://live.500.com/jczq.php?e=2026-09-30',AT)
        self.assertEqual(state['status'],'PARSED')
        self.assertEqual(len(matches),2)
        for m in matches:
            self.assertEqual(m['sale_status'],'CLOSED')
            self.assertEqual(m['markets']['SPF']['observed_count'],3)
            self.assertEqual(m['markets']['RQSPF']['observed_count'],3)
            self.assertEqual(m['markets']['BF']['observed_count'],0)
            self.assertEqual(m['markets']['JQS']['observed_count'],0)
        self.assertEqual(matches[0]['markets']['SPF']['options']['胜']['value'],'1.17')
        self.assertEqual(matches[0]['handicap'],'-1')
        self.assertEqual(matches[1]['handicap'],'1')
        wrong,state=parse_500_live((FIXTURES/'500-live-20260930.html').read_bytes(),'2026-09-29','https://live.500.com/',AT)
        self.assertEqual(wrong,[])
        self.assertEqual(state['status'],'DATE_MISMATCH')

    def test_market_closure_is_not_scraper_error(self):
        with tempfile.TemporaryDirectory() as d,patch.object(Fetcher,'get',side_effect=AssertionError('network should not run')):
            p,r=collect('2026-10-03',d,log=lambda s:None)
            self.assertEqual(r['status'],'MARKET_CLOSED')
            self.assertEqual(r['matches'],[])
            self.assertEqual(r['attempts'],[])
            self.assertEqual(r['market_calendar_note']['source'],'USER_PROVIDED_2026-10-03')
            self.assertEqual(verify(p),[])

    def test_500_online_route_collects_all_five_plays(self):
        with tempfile.TemporaryDirectory() as d,patch.object(Fetcher,'get',side_effect=[((FIXTURES/'500.html').read_bytes(),AT),((FIXTURES/'500-live-20260930.html').read_bytes(),AT)]) as get:
            p,r=collect('2026-09-30',d,sources=('500',),log=lambda s:None)
            self.assertEqual(get.call_count,6)  # main, results, four unique team pages
            self.assertTrue(all(m['team_evidence']['status']=='UNAVAILABLE' for m in r['matches']))
            self.assertEqual(len(r['matches']),2)
            self.assertEqual(r['status'],'COLLECTED_NOT_INDEPENDENTLY_VERIFIED')
            for m in r['matches']:
                self.assertEqual(sum(v['observed_count'] for v in m['markets'].values()),54)
                self.assertEqual(m['result']['status'],'FINISHED')
            self.assertEqual(verify(p),[])
            self.assertTrue((p/'results.csv').exists())

    def test_results_90_minutes_excludes_penalty_shootout(self):
        matches=self.five()
        body=(FIXTURES/'500-live-20260930.html').read_bytes()
        attach_results(body,matches,'2026-09-30','https://live.500.com/?e=2026-09-30',AT)
        cup=next(m for m in matches if m['source_match_id']=='1495376')['result']
        self.assertEqual(cup['fulltime_90'],[1,1])
        self.assertEqual(cup['halftime'],[1,0])
        self.assertEqual(cup['actual_events']['SPF'],'平')
        self.assertEqual(cup['actual_events']['BQC'],'胜/平')
        self.assertIn('8-9',cup['extra_time_note'])
        with self.assertRaisesRegex(ValueError,'销售日不匹配'):
            attach_results(body,self.five(),'2026-09-17','https://live.500.com/',AT)

    def five(self):
        return parse_500((FIXTURES/'500.html').read_bytes(),'2026-09-30','https://trade.500.com/jczq/?date=2026-09-30',AT)[0]

    def test_real_500_all_54_labels(self):
        matches=self.five()
        self.assertEqual(len(matches),2)
        for m in matches:
            self.assertEqual(sum(v['observed_count'] for v in m['markets'].values()),54)
            self.assertEqual(m['sale_status'],'CLOSED')
            self.assertEqual(set(m['coverage_draft']),set(DIMENSIONS))
            self.assertFalse(m['ready_for_analysis'])
            self.assertIsNone(m['coverage_draft']['injuries_suspensions']['evidence_status'])
        self.assertEqual(matches[0]['markets']['BF']['options']['胜其他']['value'],'35')

    def test_wrong_sales_date_rejected(self):
        m,s=parse_okooo((FIXTURES/'okooo.html').read_bytes(),'2026-10-03','https://www.okooo.com/jingcai/',AT)
        self.assertEqual(m,[]);self.assertEqual(s['status'],'DATE_MISMATCH')
        m,s=parse_500((FIXTURES/'500.html').read_bytes(),'2026-10-03','https://trade.500.com/',AT)
        self.assertEqual(m,[]);self.assertEqual(s['status'],'DATE_MISMATCH')

    def test_okooo_display_not_zero_attribute(self):
        m,_=parse_okooo((FIXTURES/'okooo.html').read_bytes(),'2026-09-30','https://www.okooo.com/jingcai/2026-09-30/',AT)
        self.assertEqual(len(m),2)
        for row in m:
            parse_okooo_more((FIXTURES/('okooo-more-'+row['match_order']+'.html')).read_bytes(),row,'https://www.okooo.com/jingcai/?action=more',AT)
            self.assertEqual(sum(v['observed_count'] for v in row['markets'].values()),54)
            self.assertEqual(row['result']['status'],'FINISHED')
            self.assertEqual(row['result']['source'],'okooo')
            self.assertIsNone(row['result']['halftime'])
            self.assertTrue(row['result']['gaps'])
        q=m[0]['markets']['SPF']['options']['平']
        self.assertEqual(q['raw_attribute'],'0');self.assertIsNotNone(q['value'])
        q=m[1]['markets']['BQC']['options']['胜/平']
        self.assertEqual(q['value'],'17')
        self.assertEqual(m[1]['markets']['BQC']['options']['平/胜']['value'],'14.5')
        self.assertEqual(m[0]['result']['fulltime_90'],[2,1])
        self.assertEqual(m[1]['result']['fulltime_90'],[1,1])
        self.assertEqual(m[1]['result']['actual_events']['BQC'],'胜/平')

    def test_okooo_closed_or_conflicting_result_is_not_finished(self):
        from results import okooo_result_more
        from dom import Tree
        m,_=parse_okooo((FIXTURES/'okooo.html').read_bytes(),'2026-09-30','https://www.okooo.com/jingcai/2026-09-30/',AT)
        self.assertEqual(m[0]['result']['status'],'UNKNOWN')
        okooo_result_more(Tree('<div>已截止</div>').root,m[0],'https://www.okooo.com/',AT)
        self.assertEqual(m[0]['result']['status'],'UNKNOWN')
        m[0]['result']['displayed_score']=[9,9]
        parse_okooo_more((FIXTURES/'okooo-more-3001.html').read_bytes(),m[0],'https://www.okooo.com/',AT)
        self.assertEqual(m[0]['result']['status'],'CONFLICT')
        self.assertIsNone(m[0]['result']['fulltime_90'])

    def test_identity_does_not_merge_alias_guess(self):
        a=self.five()[0];b=copy.deepcopy(a);b['source']='okooo';b['source_match_id']='other';b['home_team']='韩国U23'
        self.assertEqual(compare([a,b])[0]['identity_status'],'NEEDS_REVIEW')
        aliases=[dict(league=a['league'],names=[a['home_team'],b['home_team']],canonical='confirmed-team',evidence_url='https://example.com/verified')]
        self.assertEqual(compare([a,b],aliases)[0]['identity_status'],'MATCHED')
        b['away_team']='different'
        self.assertEqual(compare([a,b],aliases)[0]['identity_status'],'NEEDS_REVIEW')

    def test_conflict_and_missing(self):
        m=self.five()[0]
        set_quote(m,'SPF','胜','1.7','1.8','https://example.com',AT)
        self.assertEqual(m['markets']['SPF']['options']['胜']['status'],'CONFLICT')
        self.assertIsNone(m['markets']['SPF']['options']['胜']['value'])
        for value in ['0','NaN','-1','--','inf']:self.assertIsNone(price(value))

    def test_robot_blank_line_does_not_disable_rules(self):
        with tempfile.TemporaryDirectory() as d:
            f=Fetcher(Path(d),1)
            calls=[]
            def raw(url):
                calls.append(url)
                return b'User-agent: *\n\nDisallow: /private/\n',AT
            f.raw=raw
            with self.assertRaisesRegex(ValueError,'ROBOTS_DISALLOW'):
                f.get('https://trade.500.com/private/')
            self.assertEqual(len(calls),1)

    def test_500_robot_notice_does_not_hide_real_http_failure(self):
        with tempfile.TemporaryDirectory() as d:
            f=Fetcher(Path(d),1)
            def raw(url):
                if url.endswith('robots.txt'):return b'User-agent: *\n\nDisallow: /jczq/?\n',AT
                raise ValueError('HTTP 403')
            f.raw=raw
            with self.assertRaisesRegex(ValueError,'HTTP 403'):
                f.get('https://trade.500.com/jczq/?playid=312')
            self.assertEqual(f.attempts[0]['status'],'ROBOTS_NOTICE')

    def test_immutable_runs_database_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            imports={'500':str(FIXTURES/'500.html'),'okooo':str(FIXTURES)}
            p,r=collect('2026-09-30',d,imports=imports,log=lambda s:None)
            before=(p/'snapshot.json').read_bytes()
            p2,r2=collect('2026-09-30',d,imports=imports,log=lambda s:None)
            self.assertNotEqual(p,p2);self.assertEqual(before,(p/'snapshot.json').read_bytes())
            self.assertEqual(verify(p),[])
            with closing(sqlite3.connect(Path(d)/'archive.sqlite3')) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM runs').fetchone()[0],2)
                self.assertEqual(c.execute('SELECT count(*) FROM odds').fetchone()[0],432)
                self.assertEqual(c.execute('SELECT count(*) FROM coverage').fetchone()[0],192)
            (p/'odds.csv').write_text('changed')
            self.assertIn('FILE_HASH_MISMATCH:odds.csv',verify(p))

    def test_stop_persists_run(self):
        with tempfile.TemporaryDirectory() as d:
            stop=threading.Event();stop.set()
            p,r=collect('2026-09-30',d,stop=stop,log=lambda s:None)
            self.assertEqual(r['status'],'STOPPED');self.assertEqual(verify(p),[])


if __name__=='__main__':unittest.main()
