from pathlib import Path
from copy import deepcopy
import contextlib
import io
import json
import tempfile
import unittest
from rtl_lint import scan, main

HERE = Path(__file__).parent
SOURCE = (HERE/'examples/placement_wrapper.vhd').read_text(encoding='utf-8-sig')


def analyze(source=SOURCE, config=None):
    architectures = []
    findings, _ = scan(source, 'auto.vhd', config, architectures)
    return architectures, findings


def wrapper(source=SOURCE):
    return next(a for a in analyze(source)[0] if a['entity'] == 'placement_wrapper')


class AutomaticTests(unittest.TestCase):
    def test_default_no_policy_detects_architecture(self):
        report = wrapper()
        self.assertEqual(report['status'], 'reviewed')
        self.assertEqual(report['inputs']['din']['status'], 'registered')
        self.assertEqual(report['outputs']['dout']['status'], 'registered')
        self.assertEqual(report['inputs']['clk']['status'], 'clock_or_reset_exempt')
        self.assertEqual(sorted(p['stage_count'] for p in report['pipeline_chains']), [2, 2])
        self.assertEqual(len(report['clocked_signals']), 4)
        self.assertEqual(report['wrapper_candidates'][0]['status'], 'registers_on_both_sides')

    def test_arbitrary_names(self):
        report = wrapper(SOURCE.replace('core_i', 'u42').replace('in_1', 'apple').replace('in_2', 'pear'))
        self.assertEqual(report['wrapper_candidates'][0]['instance'], 'u42')
        self.assertIn('apple', report['clocked_signals'])

    def test_combinational_core_io_flagged(self):
        reports, findings = analyze()
        core = reports[0]
        self.assertEqual(core['outputs']['q']['status'], 'unregistered')
        self.assertTrue({'UF006', 'UF007'} <= {f['rule'] for f in findings})
        self.assertEqual(core['pipeline_chains'], [])

    def test_missing_srl_attribute_is_advisory(self):
        src = SOURCE.replace('  attribute shreg_extract of', '  -- attribute shreg_extract of')
        self.assertTrue(any(f['rule']=='UF009' and 'If this is a placement wrapper' in f['message'] for f in analyze(src)[1]))

    def test_wrapper_name_alone_does_not_establish_structure(self):
        src = SOURCE.replace('in_1 <= din;', 'in_1 <= not din;')
        report = wrapper(src)
        self.assertFalse(any(w['status']=='registers_on_both_sides' for w in report['wrapper_candidates']))

    def test_external_child_direction_uncertain(self):
        src = SOURCE[SOURCE.index('library ieee;', 10):]
        report = wrapper(src)
        self.assertEqual(report['wrapper_candidates'][0]['port_directions'], 'inferred_from_local_usage')
        self.assertEqual(report['wrapper_candidates'][0]['placement_intent'], 'unknown')

    def test_bypass_input_reported(self):
        src = SOURCE.replace('d => in_2', 'd => din')
        self.assertEqual(wrapper(src)['inputs']['din']['status'], 'partially_registered')

    def test_output_combinational_logic(self):
        self.assertEqual(wrapper(SOURCE.replace('dout <= out_2;', 'dout <= not out_2;'))['outputs']['dout']['status'], 'unregistered')

    def test_standard_vector_cast_preserves_registration(self):
        src = SOURCE.replace('dout <= out_2;', 'dout <= std_logic_vector(unsigned(out_2));')
        self.assertEqual(wrapper(src)['outputs']['dout']['status'], 'registered')

    def test_cast_with_operation_does_not_preserve_registration(self):
        src = SOURCE.replace('dout <= out_2;', 'dout <= std_logic_vector(unsigned(out_2) + 1);')
        self.assertEqual(wrapper(src)['outputs']['dout']['status'], 'unregistered')

    def test_constant_output(self):
        self.assertEqual(wrapper(SOURCE.replace('dout <= out_2;', "dout <= (others => '0');"))['outputs']['dout']['status'], 'constant')

    def test_mixed_clock_pipeline_reported(self):
        src = SOURCE.replace('      in_2 <= in_1;', '').replace('  core_i :', '  process(clk) begin if falling_edge(clk) then in_2 <= in_1; end if; end process;\n  core_i :')
        self.assertTrue(any(f['rule']=='UF008' for f in analyze(src)[1]))

    def test_cycles_not_pipelines(self):
        src = SOURCE.replace('in_1 <= din;', 'in_1 <= in_2;')
        self.assertFalse(any('in_1' in p['stages'] for p in wrapper(src)['pipeline_chains']))

    def test_one_stage_is_inventory_not_two_stage_pipeline(self):
        src = SOURCE.replace('in_2 <= in_1;', 'in_2 <= din;')
        report = wrapper(src)
        self.assertFalse(any(p['from']=='din' for p in report['pipeline_chains']))
        self.assertEqual(report['wrapper_candidates'][0]['input_paths'][0]['stage_count'], 1)

    def test_unknown_syntax_not_absent_or_clean(self):
        report = wrapper(SOURCE.replace('in_2 <= in_1;', 'in_2(7 downto 0) <= in_1;'))
        self.assertEqual(report['status'], 'unknown')
        self.assertEqual(report['outputs']['dout']['status'], 'unknown')

    def test_cases_and_variables(self):
        src = SOURCE.replace('process(clk) begin', 'process(clk) variable x : integer; begin').replace('in_1 <= din;', 'case x is when 0 => in_1 <= din; when others => in_1 <= din; end case;')
        self.assertEqual(wrapper(src)['status'], 'reviewed')
        self.assertEqual(wrapper(src)['inputs']['din']['status'], 'registered')

    def test_known_child_output_cannot_double_drive_register(self):
        src = SOURCE.replace('q => core_q', 'q => out_2')
        self.assertEqual(wrapper(src)['outputs']['dout']['status'], 'unregistered')

    def test_disable_automatic_inventory(self):
        reports, findings = analyze(config={'automatic_architecture':False})
        self.assertEqual(reports, [])
        self.assertEqual(findings, [])

    def test_cli_no_policy_writes_inventory(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            report = Path(tmp)/'report.json'
            self.assertEqual(main([str(HERE/'examples/placement_wrapper.vhd'), '--json', str(report)]), 0)
            data = json.loads(report.read_text())
            self.assertTrue(data['automatic_architecture'])
            self.assertEqual(data['module_policies'], [])
            self.assertEqual(len(data['architectures']), 2)

    def test_waiver_applies(self):
        _, findings = analyze(config={'waivers':[{'file':'auto.vhd','rule':'UF006','reason':'Intentional combinational core'}]})
        self.assertTrue(all('waived' in f for f in findings if f['rule']=='UF006'))


if __name__ == '__main__':
    unittest.main()
