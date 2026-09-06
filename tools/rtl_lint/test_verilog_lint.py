import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from rtl_lint import scan, main


def check(source,config=None,filename='test.sv'):
    reports=[]
    findings,notes=scan(source,filename,config,reports)
    return findings,reports,notes


def module(body, ports='input logic clk, input logic rst_n, input logic en, input logic D, output logic Q',decl='logic S1, S2;'):
    return f'module DUT ({ports}); {decl} {body} endmodule'


class VerilogTests(unittest.TestCase):
    def test_sv_wrapper_named_parameter_binding(self):
        source=(Path(__file__).parent/'examples'/'placement_wrapper.sv').read_text()
        f,r,_=check(source)
        w=r[1]
        self.assertEqual(w['status'],'reviewed')
        self.assertEqual(w['inputs']['din']['status'],'registered')
        self.assertEqual(w['outputs']['dout']['status'],'registered')
        self.assertEqual(sorted(p['stage_count'] for p in w['pipeline_chains']),[2,2])
        self.assertEqual(w['wrapper_candidates'][0]['status'],'registers_on_both_sides')
        self.assertEqual(w['wrapper_candidates'][0]['missing_shreg_extract_no'],[])
        self.assertEqual({x['rule'] for x in f},{'UF006','UF007'})

    def test_async_active_low_reset_in_else_branch(self):
        f,r,_=check(module("always @(posedge clk or negedge rst_n) if(rst_n) begin S1<=D; S2<=S1; end else begin S1<=0; S2<=0; end assign Q=S2;"))
        self.assertEqual(r[0]['outputs']['Q']['status'],'registered')
        self.assertEqual(r[0]['pipeline_chains'][0]['stage_count'],2)

    def test_every_async_event_requires_reset_handling(self):
        f,r,_=check(module("always @(posedge clk or negedge rst_n or posedge reset) if(!rst_n) Q<=0; else Q<=D;",ports='input clk,rst_n,reset,D, output reg Q'))
        self.assertEqual(r[0]['status'],'unknown')
        self.assertIn('UF010',[x['rule'] for x in f])

    def test_policy_endpoints_can_differ_only_by_case(self):
        cfg={'module_policies':[{'entity':'DUT','pipelines':[{'from':'D','to':'d','min_stages':1}]}]}
        f,r,_=check(module('always @(posedge clk) d<=D; assign Q=d;',decl='reg d;'),cfg)
        self.assertNotIn('UF008',[x['rule'] for x in f])

    def test_verilog_non_ansi_ports(self):
        f,r,_=check('module Old(CLK,D,Q); input CLK; input [7:0] D; output [7:0] Q; reg [7:0] A,B; always @(posedge CLK) begin A<=D; B<=A; end assign Q=B; endmodule',filename='test.v')
        self.assertFalse(f)
        self.assertEqual(r[0]['pipeline_chains'][0]['stages'],['A','B'])
        self.assertEqual(r[0]['outputs']['Q']['status'],'registered')

    def test_case_sensitive_names_not_merged(self):
        f,r,_=check(module('always_ff @(posedge clk) Q <= D; assign d = en;',decl='wire d;'))
        self.assertEqual(r[0]['inputs']['D']['status'],'registered')
        self.assertEqual(r[0]['inputs']['en']['status'],'unregistered')
        self.assertEqual(r[0]['outputs']['Q']['status'],'registered')

    def test_async_reset_constants_do_not_break_chain(self):
        f,r,_=check(module("always_ff @(posedge clk or negedge rst_n) begin if (!rst_n) begin S1 <= 1'b0; S2 <= '0; end else begin S1<=D; S2<=S1; end end assign Q=S2;"))
        self.assertEqual([x['rule'] for x in f],['UF001'])
        self.assertEqual(r[0]['pipeline_chains'][0]['stages'],['S1','S2'])

    def test_sync_reset_precedes_enable(self):
        f,r,_=check(module("always @(posedge clk) begin if(!rst_n) begin S1<=0; S2<=0; end else if(en) begin S1<=D; S2<=S1; end end assign Q=S2;"))
        self.assertNotIn('UF002',[x['rule'] for x in f])
        self.assertEqual(r[0]['pipeline_chains'][0]['stage_count'],2)

    def test_reset_under_enable_warns(self):
        f,r,_=check(module("always_ff @(posedge clk) if(en) begin if(!rst_n) Q<=0; else Q<=D; end"))
        self.assertIn('UF002',[x['rule'] for x in f])

    def test_gated_clock_and_async_multiply(self):
        f,_,_=check(module("wire gated; assign gated=clk & en; always @(posedge gated or negedge rst_n) if(!rst_n) Q<=0; else Q<=D*D;"))
        self.assertTrue({'UF001','UF003','UF004'} <= {x['rule'] for x in f})

    def test_memory_reset_is_flagged_before_partial_write_unknown(self):
        f,r,_=check(module("always @(posedge clk) if(!rst_n) mem[0]<=0;",decl='reg [7:0] mem[0:15];'))
        self.assertTrue({'UF005','UF010'} <= {x['rule'] for x in f})
        self.assertEqual(r[0]['status'],'unknown')

    def test_combinational_blocks_do_not_count_as_registers(self):
        for body in ['always_comb Q = D;', 'always @* Q = D;', 'always @(D or en) Q = D & en;', 'always_latch if(en) Q <= D;']:
            with self.subTest(body=body):
                f,r,_=check(module(body))
                self.assertEqual(r[0]['status'],'reviewed')
                self.assertEqual(r[0]['outputs']['Q']['status'],'unregistered')
                self.assertFalse(r[0]['pipeline_chains'])

    def test_raw_input_bypass_is_partial_registration(self):
        _,r,_=check(module('always_ff @(posedge clk) S1<=D; assign Q=S1 & D;'))
        self.assertEqual(r[0]['inputs']['D']['status'],'partially_registered')
        self.assertEqual(r[0]['outputs']['Q']['status'],'unregistered')

    def test_case_and_single_statement_branches(self):
        _,r,_=check(module("always @(posedge clk) case(en) 1'b0: Q<=D; default: Q<=S1; endcase"))
        self.assertEqual(r[0]['status'],'reviewed')
        self.assertEqual(r[0]['outputs']['Q']['status'],'registered')

    def test_mixed_clocks_or_enables_not_counted_as_pipeline(self):
        for body,ports in [('always @(posedge clk) S1<=D; always @(negedge clk) S2<=S1;',None),
                           ('always @(posedge clk) if(en) S1<=D; always @(posedge clk) S2<=S1;',None)]:
            f,r,_=check(module(body+' assign Q=S2;'))
            self.assertIn('UF008',[x['rule'] for x in f])
            self.assertFalse(r[0]['pipeline_chains'])

    def test_feedback_not_reported_as_pipeline(self):
        _,r,_=check(module('always @(posedge clk) begin S1<=S2; S2<=S1; end assign Q=S2;'))
        self.assertFalse(r[0]['pipeline_chains'])

    def test_multiple_drivers_do_not_prove_registration(self):
        _,r,_=check(module('always @(posedge clk) Q<=D; always @(posedge clk) Q<=en;'))
        self.assertEqual(r[0]['outputs']['Q']['status'],'unregistered')
        self.assertNotIn('Q',r[0]['clocked_signals'])

    def test_child_output_driver_invalidates_local_register_policy(self):
        source='module Child(output wire q); assign q=0; endmodule '+module('always @(posedge clk) Q<=D; Child child(.q(Q));')
        f,r,_=check(source,{'module_policies':[{'entity':'DUT','registered_outputs':['Q']}]})
        self.assertEqual(r[1]['outputs']['Q']['status'],'unregistered')
        self.assertIn('UF006',[x['rule'] for x in f])

    def test_blocking_sequential_stages_are_unknown(self):
        f,r,_=check(module('always @(posedge clk) begin S1=D; S2=S1; Q=S2; end'))
        self.assertIn('UF010',[x['rule'] for x in f])
        self.assertEqual(r[0]['status'],'unknown')
        self.assertFalse(r[0]['pipeline_chains'])

    def test_unsupported_constructs_never_silently_pass(self):
        bodies=['generate if(1) begin assign Q=D; end endgenerate',
                'always @(posedge clk) Q[0]<=D;', 'initial Q=0;',
                'foo child(D,Q);','foo child(.*);',
                'always @(posedge clk) Q<=func(D);',
                'always @(posedge clk) if(func(D)) Q<=D;',
                'always @(posedge clk) if(missing_enable) Q<=D;',
                'always @(posedge clk) for(integer i=0;i<2;i=i+1) Q<=D;',
                'typedef struct packed {logic a;} T;',
                'always @(posedge clk) Q<=missing_signal;',
                'always_ff @(posedge clk or posedge other) Q<=D;']
        for body in bodies:
            with self.subTest(body=body):
                f,r,_=check(module(body))
                self.assertIn('UF010',[x['rule'] for x in f])
                self.assertEqual(r[0]['status'],'unknown')

    def test_macros_include_conditionals_unknown(self):
        for directive in ['`include "defs.svh"','`define WIDTH 8','`ifdef USE_FEATURE']:
            f,r,n=check(directive+'\n'+module('always @(posedge clk) Q<=D;'))
            self.assertEqual(r[0]['status'],'unknown')
            self.assertIn('UF010',[x['rule'] for x in f])

    def test_timescale_and_comments_safe_and_locations_preserved(self):
        source='`timescale 1ns/1ps\n// always @(posedge fake) x<=y;\n'+module('assign Q=D;')
        f,r,_=check(source)
        self.assertEqual(r[0]['status'],'reviewed')
        self.assertTrue(all(x['line']==3 for x in f))
        self.assertTrue(all(any(t['line']==3 for t in x['source_excerpt']) for x in f))

    def test_waivers_and_disabled_rules(self):
        f,_,_=check(module('assign Q=D;'),{'disabled_rules':['UF007'],'waivers':[{'rule':'UF006','file':'*.sv','reason':'Intentional adapter'}]})
        self.assertEqual(len(f),1)
        self.assertEqual(f[0]['waived'],'Intentional adapter')

    def test_case_sensitive_pipeline_policy(self):
        cfg={'module_policies':[{'entity':'DUT','registered_outputs':['Q'],'pipelines':[{'from':'D','to':'Q','min_stages':3,'clock':'clk'}]}]}
        f,r,_=check(module('always @(posedge clk) begin S1<=D; S2<=S1; end assign Q=S2;'),cfg)
        self.assertIn('UF008',[x['rule'] for x in f])
        self.assertEqual(r[0]['pipeline_chains'][0]['stage_count'],2)

    def test_attribute_absence_warns_on_wrapper(self):
        source=(Path(__file__).parent/'examples'/'placement_wrapper.sv').read_text().replace('(* SHREG_EXTRACT = "no" *)','')
        f,r,_=check(source)
        self.assertIn('UF009',[x['rule'] for x in f])
        self.assertEqual(len(r[1]['wrapper_candidates'][0]['missing_shreg_extract_no']),4)

    def test_duplicate_module_definitions_unknown(self):
        f,r,_=check(module('assign Q=D;')+'\n'+module('assign Q=D;'))
        self.assertTrue(all(a['status']=='unknown' for a in r))

    def test_html_guidance_selects_verilog_examples(self):
        from html_report import format_html
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            folder=Path(d)
            source=folder/'example.sv'
            source.write_text(module('assign Q=D;'))
            js=folder/'report.json'; html=folder/'report.html'
            self.assertEqual(main([str(source),'--json',str(js),'--html-report',str(html)]),0)
            text=html.read_text(encoding='utf-8')
            self.assertIn('Illustrative Verilog / SystemVerilog',text)
            self.assertNotIn('Illustrative VHDL',text)
            self.assertIn('always @(posedge clk)',text)
            report=json.loads(js.read_text())
            self.assertIn('Verilog / SystemVerilog',report['rule_guidance']['UF006']['examples'])

    def test_mixed_language_directory_and_fail_on_warning(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            folder=Path(d)
            (folder/'a.v').write_text('module A(input D, output Q); assign Q=D; endmodule')
            (folder/'b.sv').write_text('module B(input logic clk,D, output logic Q); always_ff @(posedge clk) Q<=D; endmodule')
            (folder/'c.vhd').write_text('entity C is end; architecture rtl of C is begin end;')
            js=folder/'report.json'
            self.assertEqual(main([d,'--json',str(js),'--fail-on-warning']),1)
            report=json.loads(js.read_text())
            self.assertEqual(len(report['files_checked']),3)
            self.assertFalse(report['errors'])
            self.assertEqual(len(report['architectures']),3)

if __name__=='__main__': unittest.main()
