import json
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import Mock
from team_evidence import parse_team,for_match,enrich
from collector import collect
from adapters import parse_500,decode
from verify import verify

FIX=Path(__file__).parent/'fixtures'
AT='2026-10-03T12:00:00+08:00'
URL='https://liansai.500.com/team/1640/'

class TeamEvidenceTests(unittest.TestCase):
    def page(self):
        return parse_team((FIX/'500-team-1640.html').read_bytes(),'1640',URL,AT)

    def test_real_page_and_time_cutoff(self):
        p=self.page()
        self.assertEqual(len(p['records']),10)
        self.assertEqual(p['records'][0]['source_match_id'],'1495377')
        self.assertEqual(p['records'][0]['displayed_score'],'2:1 (1:1)')
        self.assertIsNone(p['records'][0]['fulltime_90'])
        x=for_match(p,'2026-09-30T23:00:00+08:00','3947','1495377')
        self.assertTrue(all(r['date']<'2026-09-30' for r in x['eligible_prior_records']))
        self.assertEqual(x['recent_3'][0]['date'],'2026-09-25')
        self.assertFalse(x['prematch_availability_proven'])
        old=for_match(p,'2020-01-01T00:00:00+08:00','3947','1')
        self.assertEqual(old['recent_5'],[])
        self.assertEqual(old['completeness'],'PARTIAL_WINDOW_NOT_FULL_HISTORY')

    def test_identity_and_changed_schema(self):
        b=(FIX/'500-team-1640.html').read_bytes()
        with self.assertRaisesRegex(ValueError,'IDENTITY'):parse_team(b,'673','https://liansai.500.com/team/673/',AT)
        s=decode(b).replace('比赛时间','未知列')
        with self.assertRaisesRegex(ValueError,'HEADERS'):parse_team(s.encode(),'1640',URL,AT)

    def test_undated_current_rank(self):
        p=parse_team((FIX/'500-team-673.html').read_bytes(),'673','https://liansai.500.com/team/673/',AT)
        self.assertEqual(p['standings']['rank'],3)
        self.assertEqual(p['standings']['points'],16)
        self.assertFalse(p['standings']['historical_prematch_eligible'])
        self.assertIsNone(p['standings']['as_of'])
        self.assertIsNone(self.page()['standings'])

    def test_wrong_row_score_and_duplicate_rejected(self):
        s=decode((FIX/'500-team-1640.html').read_bytes())
        s=s.replace('shuju-1495167.shtml','shuju-1495377.shtml')
        with self.assertRaisesRegex(ValueError,'CONFLICTING'):parse_team(s.encode(),'1640',URL,AT)
        s=decode((FIX/'500-team-1640.html').read_bytes()).replace('<span class="lred">2</span>:1','加时2:1')
        p=parse_team(s.encode(),'1640',URL,AT)
        self.assertTrue(p['rejected_rows'])
        self.assertFalse(any(r['source_match_id']=='1495377' for r in p['records']))

    def test_missing_blocked_and_cache(self):
        ms,_=parse_500((FIX/'500.html').read_bytes(),'2026-09-30','https://trade.500.com/jczq/',AT)
        fetch=Mock();fetch.stop=threading.Event();fetch.attempts=[]
        fetch.get.side_effect=ValueError('HTTP 403')
        enrich([ms[0],ms[0]],fetch,log=lambda _:None)
        self.assertEqual(fetch.get.call_count,2)
        self.assertEqual(ms[0]['team_evidence']['status'],'UNAVAILABLE')
        self.assertTrue(ms[0]['team_evidence']['gaps'])

    def test_import_ai_export_manifest_and_database(self):
        with tempfile.TemporaryDirectory() as d:
            folder,report=collect('2026-09-30',d,('500',),{'500':str(FIX/'500.html')},log=lambda _:None)
            ai=json.loads((folder/'ai_input.json').read_text('utf-8'))
            self.assertFalse(ai['ready_for_analysis'])
            self.assertEqual(ai['matches'][0]['team_evidence']['gaps'],['LOCAL_IMPORT_NO_TEAM_PAGE'])
            self.assertEqual(verify(folder),[])
            import sqlite3
            with closing(sqlite3.connect(Path(d)/'archive.sqlite3')) as db:
                self.assertEqual(db.execute('select count(*) from fact_evidence').fetchone()[0],len(report['matches']))

    def test_ai_excludes_future_and_groups_reference_unique_records(self):
        from ai_export import ai_matches
        ms,_=parse_500((FIX/'500.html').read_bytes(),'2026-09-30','https://trade.500.com/jczq/',AT)
        ms[0]['team_evidence']=dict(status='PARTIAL',teams={'home':for_match(self.page(),ms[0]['kickoff_at'],'3947',ms[0]['source_match_id'])})
        ai=ai_matches(ms[:1])[0]['team_evidence']['teams']['home']
        self.assertNotIn('records',ai)
        ids={r['source_match_id'] for r in ai['eligible_prior_records']}
        self.assertNotIn('1495377',ids)
        self.assertTrue(set(ai['recent_3_ids']) <= ids)
        self.assertEqual(len(ai['recent_5_ids']),5)
