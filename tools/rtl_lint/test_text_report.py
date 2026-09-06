import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from rtl_lint import main
from text_report import format_report

class TextReportTests(unittest.TestCase):
    def run_lint(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return main(list(args))

    def test_example_report_matches_json(self):
        with tempfile.TemporaryDirectory() as d:
            rpt, js = Path(d)/'results.rpt', Path(d)/'results.json'
            source = Path(__file__).parent/'examples'/'placement_wrapper.vhd'
            self.assertEqual(self.run_lint(str(source), '--json', str(js), '--text-report', str(rpt)), 0)
            data = json.loads(js.read_text())
            text = rpt.read_text()
            self.assertIn('1 files checked | 2 warnings | 0 waived | 0 errors', text)
            self.assertIn('din: registered', text)
            self.assertIn('dout: registered', text)
            self.assertIn('core_i (demo_core): registers_on_both_sides', text)
            self.assertIn('din -> in_2: 2 stages (in_1, in_2)', text)
            for f in data['findings']:
                self.assertIn("FILE: " + f["file"], text)
                self.assertIn(f'Line {f["line"]}:{f["column"]}', text)
                self.assertIn("Fix: see " + f["rule"], text)

    def test_unknown_waivers_and_skips_are_visible(self):
        with tempfile.TemporaryDirectory() as d:
            js = Path(d)/'report.json'
            self.run_lint(str(Path(__file__).parent/'examples'/'placement_wrapper.vhd'), '--json', str(js))
            r = json.loads(js.read_text())
            r['findings'][0]['waived'] = 'Intentional combinational core'
            r['architectures'][0]['status'] = 'unknown'
            r['sources_not_linted'] = ['generated_ip.xci']
            r['errors'] = ['Unreadable source']
            text = format_report(r)
            self.assertIn('1 warnings | 1 waived | 1 errors', text)
            self.assertIn('1 unknown/unsupported', text)
            self.assertIn('inventory: UNKNOWN; empty results do not prove absence', text)
            self.assertIn('Waiver: Intentional combinational core', text)
            self.assertIn('generated_ip.xci', text)
            self.assertIn('Unreadable source', text)

    def test_failed_scan_still_writes_error_report(self):
        with tempfile.TemporaryDirectory() as d:
            rpt = Path(d)/'results.rpt'
            self.assertEqual(self.run_lint(str(Path(d)/'missing.vhd'), '--text-report', str(rpt)), 2)
            self.assertIn('0 files checked | 0 warnings | 0 waived | 2 errors', rpt.read_text())

if __name__ == '__main__':
    unittest.main()
