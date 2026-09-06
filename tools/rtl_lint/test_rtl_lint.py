import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from rtl_lint import main, scan as scan_impl


def scan(source, filename, config=None):
    # These tests isolate the original source rules from automatic architecture review.
    return scan_impl(source, filename, {"automatic_architecture": False, **(config or {})})


def design(body, declarations=''):
    return f'architecture rtl of demo is\n{declarations}\nbegin\n{body}\nend architecture;'


def rules(body, declarations='', config=None):
    return {f['rule'] for f in scan(design(body, declarations), 'demo.vhd', config)[0]}


ASYNC = "process(clk,rst) begin if rst='1' then q<='0'; elsif rising_edge(clk) then q<=d; end if; end process;"


class LintTests(unittest.TestCase):
    def test_synchronous_reset_priority(self):
        self.assertEqual(rules("process(clk) begin if rising_edge(clk) then if rst='1' then q<='0'; elsif ce='1' then q<=d; end if; end if; end process;"), set())

    def test_async_multiply(self):
        self.assertEqual(rules(ASYNC.replace('q<=d', 'q<=a*b')), {'UF001', 'UF004'})

    def test_reset_under_enable(self):
        self.assertIn('UF002', rules("process(clk) begin if rising_edge(clk) then if ce='1' then if rst='1' then q<='0'; else q<=d; end if; end if; end if; end process;"))

    def test_separate_processes(self):
        self.assertNotIn('UF004', rules(ASYNC + 'process(clk) begin if rising_edge(clk) then p<=a*b; end if; end process;'))

    def test_comments_strings_and_locations(self):
        src = design('-- rising_edge(clk and en)\nreport "-- rising_edge(clk and en)";\nclk2 <= clk and en;\nprocess(clk2) begin if rising_edge(clk2) then q<=d; end if; end process;')
        findings, _ = scan(src, 'demo.vhd')
        self.assertEqual([f['rule'] for f in findings], ['UF003'])
        self.assertEqual(src.splitlines()[findings[0]['line']-1], 'clk2 <= clk and en;')

    def test_clock_expression(self):
        self.assertIn('UF003', rules('process(clk) begin if rising_edge(clk and en) then q<=d; end if; end process;'))

    def test_memory_reset_and_normal_write(self):
        decl = 'type ram_t is array(0 to 15) of std_logic_vector(7 downto 0); signal mem : ram_t;'
        body = "process(clk) begin if rising_edge(clk) then if rst='1' then for i in 0 to 15 loop mem(i)<=(others=>'0'); end loop; else mem(addr)<=din; end if; end if; end process;"
        self.assertIn('UF005', rules(body, decl))
        self.assertNotIn('UF005', rules(body.replace('rst', 'we'), decl))

    def test_architecture_scoping(self):
        src = design('clk2<=a and b;') + design('process(clk2) begin if rising_edge(clk2) then q<=d; end if; end process;')
        self.assertNotIn('UF003', {f['rule'] for f in scan(src, 'demo.vhd')[0]})

    def test_configuration(self):
        self.assertEqual(rules(ASYNC, config={'disabled_rules':['UF001']}), set())
        found, _ = scan(design(ASYNC), 'demo.vhd', {'waivers':[{'rule':'UF001', 'file':'demo.vhd', 'reason':'Reset synchronizer'}]})
        self.assertEqual(found[0]['waived'], 'Reset synchronizer')
        self.assertNotIn('UF001', rules(ASYNC.replace('rst', 'clear')))
        self.assertIn('UF001', rules(ASYNC.replace('rst', 'clear'), config={'reset_pattern':'^clear$'}))

    def test_reset_counter_is_not_reset(self):
        self.assertNotIn('UF001', rules(ASYNC.replace('rst', 'reset_count')))
        self.assertNotIn('UF002', rules("process(clk) begin if rising_edge(clk) then if rst='1' then q<='0'; else if reset_count /= 0 then reset_count <= reset_count - 1; end if; end if; end if; end process;"))

    def test_coverage(self):
        _, notes = scan(design("process(clk) begin if clk'event and clk='1' then q<=d; end if; end process;"), 'demo.vhd')
        self.assertTrue(any("'event" in n for n in notes))

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            folder = Path(tmp)
            src, report = folder/'with spaces.vhd', folder/'report.json'
            src.write_text(design(ASYNC))
            self.assertEqual(main([str(src), '--json', str(report), '--fail-on-warning']), 1)
            self.assertEqual(len(json.loads(report.read_text())['files_checked']), 1)
            self.assertEqual(main([str(folder/'missing.vhd')]), 2)
            self.assertEqual(main([str(folder/'unsupported.sv')]), 2)
            self.assertEqual(main([]), 2)

if __name__ == '__main__':
    unittest.main()

