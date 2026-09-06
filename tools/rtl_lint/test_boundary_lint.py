import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from rtl_lint import main, scan, load_config
from boundary_lint import validate

HERE = Path(__file__).parent
SOURCE = (HERE/'examples/placement_wrapper.vhd').read_text(encoding='utf-8-sig')
POLICY = json.loads((HERE/'examples/placement_policy.json').read_text(encoding='utf-8-sig'))


def check(source=SOURCE, policy=None):
    config = deepcopy(POLICY if policy is None else policy)
    config['automatic_architecture'] = False
    findings, _ = scan(source, 'wrapper.vhd', config)
    return [f for f in findings if f['rule'] >= 'UF006']


def ids(source=SOURCE, policy=None):
    return {f['rule'] for f in check(source, policy)}


class BoundaryTests(unittest.TestCase):
    def test_two_sided_wrapper(self):
        self.assertEqual(check(), [])

    def test_combinational_output(self):
        self.assertIn('UF006', ids(SOURCE.replace('dout <= out_2;', 'dout <= not out_2;')))

    def test_output_wire_alias_is_allowed(self):
        src = SOURCE.replace('signal in_1,', 'signal alias_q, in_1,').replace('dout <= out_2;', 'alias_q <= out_2; dout <= alias_q;')
        self.assertEqual(check(src), [])

    def test_combinational_reset_after_register_is_not_registered_output(self):
        src = SOURCE.replace('dout <= out_2;', "process(all) begin if rst='1' then dout <= (others=>'0'); else dout <= out_2; end if; end process;")
        self.assertTrue({'UF006', 'UF008'} <= ids(src))

    def test_last_write_hold_cannot_supply_pipeline_stage(self):
        src = SOURCE.replace('in_2 <= in_1;', 'in_2 <= in_1; in_2 <= in_2;')
        self.assertIn('UF008', ids(src))

    def test_raw_input_into_core(self):
        found = ids(SOURCE.replace('d => in_2', 'd => din'))
        self.assertTrue({'UF007', 'UF010'} <= found)

    def test_logic_before_input_capture(self):
        self.assertIn('UF007', ids(SOURCE.replace('in_1 <= din;', 'in_1 <= not din;')))

    def test_input_as_control(self):
        self.assertIn('UF007', ids(SOURCE.replace('in_1 <= din;', "if din(0)='1' then in_1 <= din; end if;")))

    def test_too_few_stages(self):
        self.assertIn('UF008', ids(SOURCE.replace('in_2 <= in_1;', 'in_2 <= din;')))

    def test_exact_depth(self):
        cfg = deepcopy(POLICY)
        cfg['module_policies'][0]['pipelines'][0]['min_stages'] = 1
        cfg['module_policies'][0]['pipelines'][0]['max_stages'] = 1
        self.assertIn('UF008', ids(policy=cfg))

    def test_no_srl_attribute(self):
        src = SOURCE.replace('attribute shreg_extract of in_1, in_2, out_1, out_2 : signal is "no";', '')
        found = [f for f in check(src) if f['rule'] == 'UF009']
        self.assertEqual(len(found), 4)

    def test_unrelated_srl_attribute_does_not_count(self):
        src = SOURCE.replace('of in_1, in_2, out_1, out_2', 'of core_q')
        self.assertEqual(sum(f['rule']=='UF009' for f in check(src)), 4)

    def test_comments_do_not_supply_attribute(self):
        src = SOURCE.replace('  attribute shreg_extract of', '  -- attribute shreg_extract of')
        self.assertIn('UF009', ids(src))

    def test_nonplacement_pipeline_does_not_require_attribute(self):
        cfg = deepcopy(POLICY)
        for path in cfg['module_policies'][0]['pipelines']:
            path['placement'] = False
        self.assertNotIn('UF009', ids(SOURCE.replace('signal is "no";', 'signal is "yes";'), cfg))

    def test_missing_endpoint_and_port(self):
        cfg = deepcopy(POLICY)
        cfg['module_policies'][0]['pipelines'][0]['to'] = 'missing'
        cfg['module_policies'][0]['registered_inputs'] = ['typo']
        self.assertIn('UF010', ids(policy=cfg))

    def test_missing_entity_ports(self):
        src = SOURCE[SOURCE.index('architecture rtl of placement_wrapper'):]
        self.assertIn('UF010', ids(src))

    def test_different_clock_rejected(self):
        src = SOURCE.replace('      in_2 <= in_1;', '').replace('  core_i :', '  process(clk) begin if falling_edge(clk) then in_2 <= in_1; end if; end process;\n  core_i :')
        self.assertIn('UF008', ids(src))

    def test_expected_clock(self):
        cfg = deepcopy(POLICY)
        cfg['module_policies'][0]['pipelines'][0]['clock'] = 'other_clk'
        self.assertIn('UF008', ids(policy=cfg))

    def test_mixed_enables_rejected(self):
        src = SOURCE.replace('in_2 <= in_1;', "if ce='1' then in_2 <= in_1; end if;")
        self.assertIn('UF008', ids(src))

    def test_shared_enable_and_reset_supported(self):
        src = SOURCE.replace('    if rising_edge(clk) then', "    if rst='1' then in_1 <= (others=>'0'); in_2 <= (others=>'0'); out_1 <= (others=>'0'); out_2 <= (others=>'0');\n    elsif rising_edge(clk) then if ce='1' then").replace('    end if;\n  end process;', '    end if; end if;\n  end process;')
        self.assertEqual(check(src), [])

    def test_alternate_bypass_rejected(self):
        src = SOURCE.replace('in_2 <= in_1;', "if bypass='1' then in_2 <= din; else in_2 <= in_1; end if;")
        self.assertIn('UF008', ids(src))

    def test_multiple_process_drivers_rejected(self):
        src = SOURCE.replace('  core_i :', '  process(clk) begin if rising_edge(clk) then in_2 <= in_1; end if; end process;\n  core_i :')
        self.assertIn('UF008', ids(src))

    def test_generate_requires_review(self):
        src = SOURCE.replace('  process(clk)', '  gen : if true generate\n  process(clk)').replace('  end process;', '  end process;\n  end generate;')
        self.assertIn('UF010', ids(src))

    def test_sliced_assignment_requires_review(self):
        self.assertIn('UF010', ids(SOURCE.replace('in_2 <= in_1;', 'in_2(7 downto 0) <= in_1;')))

    def test_clock_expression_requires_review(self):
        self.assertIn('UF010', ids(SOURCE.replace('rising_edge(clk)', 'rising_edge(clk and ce)')))

    def test_waiver_applies_to_new_rules(self):
        cfg = deepcopy(POLICY)
        cfg['waivers'] = [{'rule':'UF009', 'file':'wrapper.vhd', 'reason':'Attribute supplied by reviewed external constraint'}]
        src = SOURCE.replace('signal is "no";', 'signal is "yes";')
        found = [f for f in check(src, cfg) if f['rule']=='UF009']
        self.assertTrue(found and all('waived' in f for f in found))

    def test_invalid_policy(self):
        for update in ({'min_stages':0}, {'min_stages':True}, {'max_stages':1}, {'core_port':'bad'}, {'to':'in_2(0)'}, {'placement':'yes'}):
            cfg = deepcopy(POLICY)
            cfg['module_policies'][0]['pipelines'][0].update(update)
            with self.assertRaises(ValueError):
                validate(cfg['module_policies'])

    def test_missing_module_is_cli_error(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            p = Path(tmp)
            src, cfg, report = p/'wrapper.vhd', p/'config.json', p/'report.json'
            src.write_text(SOURCE)
            config = deepcopy(POLICY)
            config['module_policies'][0]['entity'] = 'missing_entity'
            cfg.write_text(json.dumps(config))
            self.assertEqual(main([str(src), '--config', str(cfg), '--json', str(report)]), 2)
            self.assertTrue(any('matched no' in e for e in json.loads(report.read_text())['errors']))

    def test_pipeline_warning_fails_cli(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            src = Path(tmp)/'bad.vhd'
            src.write_text(SOURCE.replace('in_2 <= in_1;', 'in_2 <= din;'))
            self.assertEqual(main([str(src), '--config', str(HERE/'examples/placement_policy.json'), '--fail-on-warning']), 1)


if __name__ == '__main__':
    unittest.main()
