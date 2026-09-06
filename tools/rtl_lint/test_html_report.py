import contextlib
import io
import json
from html import escape
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rtl_lint import main, RULES
from html_report import format_html
from recommendations import GUIDANCE
import open_report

class HtmlReportTests(unittest.TestCase):
    def generate(self, directory):
        js, html = Path(directory)/'report.json', Path(directory)/'report.html'
        with contextlib.redirect_stdout(io.StringIO()):
            code = main([str(Path(__file__).parent/'examples'/'placement_wrapper.vhd'), '--json', str(js), '--html-report', str(html)])
        self.assertEqual(code, 0)
        return json.loads(js.read_text()), html.read_text(encoding='utf-8')

    def test_guidance_source_locations_and_architecture_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            data, html = self.generate(d)
            self.assertEqual(set(GUIDANCE), set(RULES))
            self.assertEqual(html.count('class="finding"'), len(data['findings']))
            for f in data['findings']:
                self.assertIn(f'href="#guide-{f["rule"]}"', html)
                self.assertIn(f'id="guide-{f["rule"]}"', html)
                self.assertIn(f'L{f["line"]}:{f["column"]}', html)
                self.assertEqual(data['rule_guidance'][f['rule']]['url'], f['reference'])
                self.assertTrue(any(r['line']==f['line'] for r in f['source_excerpt']))
            self.assertIn('core_i (demo_core)', html)
            self.assertIn('registers on both sides', html)
            self.assertIn('din → in_2', html)
            self.assertIn(data['generated_at'], html)

    def test_source_and_messages_cannot_inject_html(self):
        with tempfile.TemporaryDirectory() as d:
            data, _ = self.generate(d)
            payload = '</pre><script>alert("x")</script><img src=x onerror=alert(1)>'
            data['findings'][0]['message'] = payload
            data['findings'][0]['file'] = payload
            data['findings'][0]['waived'] = payload
            data['findings'][0]['source_excerpt'][0]['text'] = payload
            html = format_html(data)
            self.assertNotIn(payload, html)
            self.assertIn(escape(payload), html)
            self.assertEqual(html.count('<script>'), 1)
            self.assertNotIn('<script src=', html)
            self.assertNotIn('<link ', html)

    def test_errors_unknowns_and_exclusions_visible(self):
        with tempfile.TemporaryDirectory() as d:
            data, _ = self.generate(d)
            data['errors'] = ['Source unavailable']
            data['architectures'][0]['status'] = 'unknown'
            data['sources_not_linted'] = ['vendor.xci']
            html = format_html(data)
            self.assertIn('Source unavailable', html)
            self.assertIn('Pipeline / wrapper status unknown', html)
            self.assertIn('vendor.xci', html)
            self.assertIn('not AMD methodology DRC IDs', html)

    def test_browser_receives_encoded_local_file_uri(self):
        with tempfile.TemporaryDirectory(prefix='lint spaces ') as d:
            p=Path(d)/'results #1.html'
            p.write_text('<html></html>')
            with patch.object(open_report.webbrowser, 'open', return_value=True) as viewer:
                self.assertEqual(open_report.main([str(p)]), 0)
                viewer.assert_called_once_with(p.resolve().as_uri(), new=2)
            with patch.object(open_report.webbrowser, 'open') as viewer, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(open_report.main([str(Path(d)/'missing.html')]), 2)
                viewer.assert_not_called()

if __name__ == '__main__':
    unittest.main()
