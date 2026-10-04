import contextlib
import io
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import console


class ConsoleTests(unittest.TestCase):
    def test_open_folder_switches_to_successful_run_and_keeps_total_option(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);current=base/'data'/'run'
            report={'sale_date':'2026-09-17','status':'NEEDS_REVIEW','sources':[],'matches':[]}
            with patch.object(console,'BASE',base), patch('builtins.input',side_effect=['4','1','2026-09-17','1','4','5','0']), patch.object(console,'collect',return_value=(current,report)), patch.object(console,'open_folder') as opened, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(console.main(),0)
                self.assertEqual([c.args[0] for c in opened.call_args_list],[str(base/'data'),str(current),str(base/'data')])

    def test_invalid_date_retries_and_cancel_does_not_collect(self):
        with patch('builtins.input',side_effect=['1','bad-date','0','0']), patch.object(console,'collect') as collect, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(console.main(),0)
            collect.assert_not_called()
            self.assertIn('日期无效',output.getvalue())

    def test_source_choice_and_summary(self):
        report={'sale_date':'2026-09-17','status':'NEEDS_REVIEW','sources':[{'source':'okooo','status':'PARSED'}],'matches':[]}
        with patch('builtins.input',side_effect=['1','2026-09-17','3','0']), patch.object(console,'collect',return_value=(Path('data/test'),report)) as collect, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(console.main(),0)
            collect.assert_called_once_with('2026-09-17',sources=('okooo',))

    def test_failed_operation_returns_to_menu(self):
        with patch('builtins.input',side_effect=['1','2026-09-17','2','0']), patch.object(console,'collect',side_effect=OSError('network unavailable')), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(console.main(),0)
            self.assertIn('操作失败',output.getvalue())


if __name__=='__main__': unittest.main()
