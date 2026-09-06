import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from rtl_lint import main

class ScopeTests(unittest.TestCase):
    def test_mixed_source_metadata_is_not_claimed_checked(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp)
            source = folder/'example.vhd'
            source.write_text('entity e is end; architecture a of e is begin end;')
            skipped = folder/'skipped.txt'
            omitted = str(folder/'generated core with spaces.v')
            skipped.write_text(omitted+'\n'+omitted+'\n')
            report = folder/'report.json'
            self.assertEqual(main([str(source), '--skipped-file-list', str(skipped), '--source-scope', 'direct VHDL', '--json', str(report)]), 0)
            data=json.loads(report.read_text())
            self.assertEqual(data['sources_not_linted'], [omitted])
            self.assertEqual(data['source_scope'], 'direct VHDL')
            self.assertNotIn(omitted,data['files_checked'])

    def test_missing_skipped_manifest_is_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--skipped-file-list','no_such_scope_manifest_4729.txt']), 2)

if __name__=='__main__':
    unittest.main()
