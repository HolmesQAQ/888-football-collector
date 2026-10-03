import json
import unittest
from pathlib import Path
from unittest.mock import Mock
import threading
from extended_history import parse_history,history_url
from team_evidence import for_match,parse_team,enrich
from adapters import parse_500
FIX=Path(__file__).parent/'fixtures'
AT='2026-10-03T16:00:00+08:00'

class ExtendedHistoryTests(unittest.TestCase):
    def data(self,tid='4156'):
        return (FIX/('500-history-'+tid+'.json')).read_bytes()

    def test_real_hundred_records_and_h2h(self):
        p=parse_history(self.data(),'4156',history_url('4156'),AT)
        self.assertEqual(len(p['records']),100)
        m=for_match(p,'2026-09-30T18:30:00+08:00','4143','1495376')
        self.assertEqual(len(m['eligible_prior_records']),5)
        self.assertEqual(len(m['recent_10']),5)
        self.assertEqual(len(m['h2h_records']),0)
        self.assertEqual(m['days_since_last_listed_match'],5)
        self.assertEqual(len(m['previous_10d_match_ids']),2)
        self.assertTrue(all(r['date']<'2026-09-30' and r['fulltime_90'] is None for r in m['eligible_prior_records']))
        self.assertIsNone(m['recent_3'][0]['historical_market_observation']['quoted_at'])

    def test_wrong_identity_and_foreign_rows(self):
        with self.assertRaisesRegex(ValueError,'IDENTITY'):parse_history(self.data(),'4143',history_url('4143'),AT)
        d=json.loads(self.data());d['list'][0]['HOMETEAMID']=1
        with self.assertRaisesRegex(ValueError,'IDENTITY'):parse_history(json.dumps(d).encode(),'4156',history_url('4156'),AT)

    def test_duplicate_and_unsettled(self):
        d=json.loads(self.data());d['list']=d['list'][:3];d['list'][0]['HOMESCORE']=-1
        p=parse_history(json.dumps(d).encode(),'4156',history_url('4156'),AT)
        self.assertEqual(len(p['records']),2);self.assertEqual(len(p['rejected_rows']),1)
        d=json.loads(self.data());d['list']=d['list'][:2];d['list'][1]['FIXTUREID']=d['list'][0]['FIXTUREID']
        with self.assertRaisesRegex(ValueError,'CONFLICTING'):parse_history(json.dumps(d).encode(),'4156',history_url('4156'),AT)

    def test_h2h_agrees_in_both_team_windows(self):
        ids=[]
        for tid,opp in [('4156','4143'),('4143','4156')]:
            p=parse_history(self.data(tid),tid,history_url(tid),AT)
            ids.append({r['source_match_id'] for r in for_match(p,'2026-09-30T18:30:00+08:00',opp,'1495376')['h2h_records']})
        self.assertEqual(ids[0],ids[1])

    def test_schedule_date_scope(self):
        p=parse_team((FIX/'500-team-1640.html').read_bytes(),'1640','https://liansai.500.com/team/1640/',AT)
        m=for_match(p,'2026-09-30T14:00:00+08:00','3947','1495377')
        self.assertEqual([r['date'] for r in m['future_10d_observed_schedule']],['2026-10-03','2026-10-06'])
        self.assertTrue(all(not r['prematch_availability_proven'] for r in m['future_10d_observed_schedule']))

    def test_expansion_failure_keeps_homepage(self):
        ms,_=parse_500((FIX/'500.html').read_bytes(),'2026-09-30','https://trade.500.com/jczq/',AT)
        fetch=Mock();fetch.stop=threading.Event();fetch.attempts=[]
        def get(url):
            if url=='https://liansai.500.com/team/1640/':return (FIX/'500-team-1640.html').read_bytes(),AT
            raise ValueError('HTTP 405')
        fetch.get.side_effect=get
        enrich(ms[:1],fetch,log=lambda _:None)
        t=ms[0]['team_evidence']['teams']['home']
        self.assertEqual(len(t['eligible_prior_records']),3)
        self.assertEqual(t['history_expansion_error'],'HTTP 405')

    def test_calendar_month_boundaries_and_no_backfill(self):
        from copy import deepcopy
        template=parse_history(self.data(),'4156',history_url('4156'),AT)['records'][0]
        for target,start,before in [('2026-03-31','2026-02-28','2026-02-27'),('2024-03-31','2024-02-29','2024-02-28'),('2026-01-31','2025-12-31','2025-12-30')]:
            rows=[]
            for i,day in enumerate((before,start,target)):
                row=deepcopy(template);row.update(date=day,source_match_id=str(i+1));rows.append(row)
            result=for_match({'records':rows},target+'T18:00:00+08:00','4143','999')
            self.assertEqual(result['history_start_inclusive'],start)
            self.assertEqual([r['date'] for r in result['records']],[start])
            self.assertEqual(len(result['recent_5']),1)
            self.assertEqual(len(result['h2h_records']),1)
