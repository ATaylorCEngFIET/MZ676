# Real Vivado source selection and mixed-language lint; no elaboration.
set addon [file dirname [file normalize [info script]]]
source [file join $addon vivado.tcl]
create_project -in_memory -part xc7s50csga324-1
add_files [file join $addon examples placement_wrapper.vhd]
add_files [file join $addon examples placement_wrapper.sv]
add_files [file join $addon examples legacy_pipeline.v]
set report [::rtl_lint::run]
exec {*}$::rtl_lint::python -c {import json,sys; from pathlib import Path; r=json.load(open(sys.argv[1])); assert not r['errors']; assert {Path(p).suffix for p in r['files_checked']}=={'.vhd','.v','.sv'}; sv=next(a for a in r['architectures'] if a['entity']=='placement_wrapper_sv'); v=next(a for a in r['architectures'] if a['entity']=='legacy_pipeline'); assert sv['status']=='reviewed'; assert sv['inputs']['din']['status']=='registered'; assert sv['outputs']['dout']['status']=='registered'; assert sorted(p['stage_count'] for p in sv['pipeline_chains'])==[2,2]; assert sv['wrapper_candidates'][0]['status']=='registers_on_both_sides'; assert v['outputs']['Q']['status']=='registered'; assert v['pipeline_chains'][0]['stages']==['Stage1','Stage2']; html=Path(sys.argv[1]).with_name('RTL_Lint_Results.html').read_text(encoding='utf-8'); assert 'Illustrative Verilog / SystemVerilog' in html; assert 'Illustrative VHDL' in html} $report
if {[llength [get_designs -quiet]]} {error "Unexpected elaborated design"}
puts "RTL_LINT_MIXED_SMOKE_PASS: VHDL, Verilog, SystemVerilog and HTML guidance; no elaboration"
close_project
exit
