import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters import parse_500
from model import compare
from summary import compact_rows


class SummaryTests(unittest.TestCase):
    def pair(self):
        a=parse_500((Path(__file__).parent/'fixtures'/'500.html').read_bytes(),'2026-09-30','https://trade.500.com/jczq/','2026-10-03T12:00:00+08:00')[0][0]
        b=copy.deepcopy(a); b.update(source='okooo',source_match_id='other')
        return a,b

    def test_equal_values_display_once_without_modifying_evidence(self):
        a,b=self.pair(); report={'matches':[a,b],'comparisons':compare([a,b])}; before=copy.deepcopy(report)
        rows=compact_rows(report)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['身份核对'],'同场已匹配')
        self.assertEqual(rows[0]['SPF_胜'],a['markets']['SPF']['options']['胜']['value'])
        self.assertEqual(report,before)

    def test_differences_and_missing_keep_source(self):
        a,b=self.pair();b['markets']['SPF']['options']['胜']['value']='9.99'
        a['result']={'halftime':[1,0]}
        row=compact_rows({'matches':[a,b]})[0]
        self.assertIn('okooo=9.99',row['SPF_胜'])
        self.assertEqual(row['赔率差异项数'],1)
        self.assertEqual(row['半场比分'],'500=1:0 / okooo=未取得')

    def test_alias_candidate_is_not_confirmed_identity(self):
        a,b=self.pair();b['home_team']='不同名称';b['league']='赛事简称'
        row=compact_rows({'matches':[a,b]})[0]
        self.assertEqual(row['身份核对'],'候选对照：名称待核对')
        self.assertIn('不同名称',row['主队'])
        self.assertIn('赛事简称',row['赛事'])

    def test_same_number_different_time_and_duplicates_stay_separate(self):
        a,b=self.pair();b['kickoff_at']='2026-09-30T22:00:00+08:00'
        self.assertEqual(len(compact_rows({'matches':[a,b]})),2)
        b['kickoff_at']=a['kickoff_at']
        self.assertEqual(len(compact_rows({'matches':[a,b,copy.deepcopy(b)]})),3)
