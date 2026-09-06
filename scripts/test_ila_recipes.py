"""Exercise Tcl recipes using the shipped LTX and a fake hardware command boundary.
These tests do not simulate an ILA or validate a physical JTAG connection.
"""
import json
from pathlib import Path
import tkinter
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.tcl = tkinter.Tcl()
        cores = json.loads((ROOT/'prebuilt/arty_s7_50/debug_lab.ltx').read_text())['ltx_root']['ltx_data']
        for entry in cores:
            for core in entry.get('debug_cores', []):
                if core['name'] == 'dbg_hub':
                    continue
                name = core['name']
                probes = []
                for pin in core['pins']:
                    probe = pin['nets'][0]['name']
                    probes.append(probe)
                    self.tcl.setvar(f'props({probe},NAME)', probe)
                    self.tcl.setvar(f'widths({probe})', abs(pin['leftIndex']-pin['rightIndex'])+1)
                self.tcl.setvar(f'probes({name})', tuple(probes))
                self.tcl.setvar(f'props({name},CELL_NAME)', name)
        self.tcl.eval('''
            set armed {}
            proc current_hw_device {args} {return device}
            proc get_hw_ilas {args} {return [array names ::probes]}
            proc get_hw_probes {args} {return $::probes([lindex $args end])}
            proc get_property {key object} {return $::props($object,$key)}
            proc set_property {key value object} {
                if {$key eq "TRIGGER_COMPARE_VALUE"} {
                    if {![regexp {^eq([0-9]+)'b([X01]+)$} $value _ width bits]} {error "Bad mask"}
                    if {$width != $::widths($object) || [string length $bits] != $width} {error "Width mismatch"}
                }
                set ::props($object,$key) $value
            }
            proc reset_hw_ila {ila} {
                foreach p $::probes($ila) {unset -nocomplain ::props($p,TRIGGER_COMPARE_VALUE)}
                set ::props($ila,RESET_CALLED) 1
            }
            proc run_hw_ila {ila} {lappend ::armed $ila}
        ''')
        self.tcl.call('source', str(ROOT/'scripts/ila_recipes.tcl').replace('\\','/'))

    def prop(self, object, key):
        return self.tcl.getvar(f'props({object},{key})')

    def check_core(self, suffix, position):
        core = self.tcl.call('lab_ila', suffix)
        self.assertIn(core, self.tcl.splitlist(self.tcl.getvar('armed')))
        self.assertEqual(self.prop(core, 'CONTROL.CAPTURE_MODE'), 'ALWAYS')
        self.assertEqual(int(self.prop(core, 'CONTROL.TRIGGER_POSITION')), position)
        self.assertEqual(self.prop(core, 'CONTROL.TRIGGER_CONDITION'), 'AND')
        self.assertEqual(int(self.prop(core, 'RESET_CALLED')), 1)
        return core

    def test_all_fault_event_and_sticky_masks(self):
        for mode, event in {1:14, 2:13, 3:15, 4:12, 5:16, 6:17}.items():
            for kind in ('event', 'sticky'):
                self.tcl.call('lab_arm_fault', mode, kind)
                self.check_core('ila_fast', 768)
                mask = self.prop('debug_system_i/experiment_native0','TRIGGER_COMPARE_VALUE').split("'b")[1]
                self.assertEqual(mask[31-(event + (8 if kind == 'sticky' else 0))], '1')
                self.assertEqual(mask[20:24], f'{mode:04b}')
                self.assertEqual(mask.count('X'), 27)

    def test_cdc_done_mask(self):
        self.tcl.call('lab_arm_cdc_slow')
        self.check_core('ila_slow', 768)
        value = self.prop('debug_system_i/experiment_slow_debug','TRIGGER_COMPARE_VALUE')
        self.assertEqual(value, "eq64'b" + 'X'*24 + '1' + 'X'*39)

    def test_system_recipes(self):
        cases = {
            'source_stall': (256, {'net_slot_0_axis_tvalid':"eq1'b1", 'net_slot_0_axis_tready':"eq1'b0"}),
            'source_violation': (768, {'net_slot_0_apc_pc_asserted':"eq1'b1"}),
            'sink_last': (768, {f'net_slot_1_axis_{s}':"eq1'b1" for s in ('tvalid','tready','tlast')}),
            'axi_address': (32, {'net_slot_2_axi_aw_ctrl':"eq2'bX1"}),
            'axi_data': (32, {'net_slot_2_axi_w_ctrl':"eq2'bX1"}),
        }
        for recipe, (position, terms) in cases.items():
            self.tcl.call('lab_arm_system', recipe)
            self.check_core('system_ila', position)
            for probe, value in terms.items():
                self.assertEqual(self.prop('debug_system_i/system_ila/U0/'+probe, 'TRIGGER_COMPARE_VALUE'), value)

    def test_invalid_recipe_does_not_arm(self):
        for args in [('lab_arm_fault',0), ('lab_arm_fault',7), ('lab_arm_fault',5,'wrong'), ('lab_arm_system','wrong')]:
            with self.assertRaises(tkinter.TclError):
                self.tcl.call(*args)
        self.assertFalse(self.tcl.getvar('armed'))

    def test_missing_probe_does_not_arm(self):
        core = self.tcl.call('lab_ila','ila_fast')
        self.tcl.setvar(f'probes({core})', ())
        with self.assertRaises(tkinter.TclError):
            self.tcl.call('lab_arm_fault',5)
        self.assertFalse(self.tcl.getvar('armed'))


if __name__ == '__main__':
    unittest.main()
