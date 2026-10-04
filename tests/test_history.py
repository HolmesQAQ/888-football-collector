import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import console
from history import history_targets, clear_history


class HistoryTests(unittest.TestCase):
    def setup_files(self, base):
        run=base/'data'/'20261003T120000-abcd1234'
        (run/'raw').mkdir(parents=True)
        (run/'raw'/'sample.html').write_text('sample')
        (base/'data'/'archive.sqlite3').write_bytes(b'archive')
        (base/'data'/'runtime').mkdir()
        (base/'data'/'runtime'/'keep.log').write_text('keep')
        (base/'keep.py').write_text('keep')
        return run

    def test_scope_preserves_program_and_unrelated_data(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);run=self.setup_files(base)
            clear_history(base,history_targets(base))
            self.assertFalse(run.exists())
            self.assertFalse((base/'data'/'archive.sqlite3').exists())
            self.assertTrue((base/'data'/'runtime'/'keep.log').exists())
            self.assertTrue((base/'keep.py').exists())
            self.assertEqual(history_targets(base),[])

    def test_cancel_keeps_history(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);run=self.setup_files(base)
            with patch.object(console,'BASE',base),patch('builtins.input',side_effect=['6','','0']),contextlib.redirect_stdout(io.StringIO()):
                console.main()
            self.assertTrue(run.exists())
            self.assertTrue((base/'data'/'archive.sqlite3').exists())

    def test_changed_inventory_refuses_clear(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);run=self.setup_files(base);targets=history_targets(base)
            (base/'data'/'20261003T120001-abcd1234').mkdir()
            with self.assertRaisesRegex(RuntimeError,'已变化'):clear_history(base,targets)
            self.assertTrue(run.exists())

    def test_clear_resets_current_folder(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);run=self.setup_files(base)
            report={'sale_date':'2026-10-03','status':'MARKET_CLOSED','sources':[],'matches':[]}
            with patch.object(console,'BASE',base),patch.object(console,'collect',return_value=(run,report)),patch('builtins.input',side_effect=['1','2026-10-03','1','6','CLEAR','4','0']),patch.object(console,'open_folder') as opened,contextlib.redirect_stdout(io.StringIO()):
                console.main()
            opened.assert_called_once_with(str(base/'data'))
