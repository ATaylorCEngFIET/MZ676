# Automatic architecture checks, no module policy and no persistent GUI changes.
set addon [file dirname [file normalize [info script]]]
source [file join $addon vivado.tcl]
create_project -in_memory -part xc7s50csga324-1
add_files [file join $addon examples placement_wrapper.vhd]
set report [::rtl_lint::run]
exec {*}$::rtl_lint::python -c {import json,sys; r=json.load(open(sys.argv[1])); assert not r['errors']; assert r['automatic_architecture']; assert not r['module_policies']; w=next(a for a in r['architectures'] if a['entity']=='placement_wrapper'); assert w['inputs']['din']['status']=='registered'; assert w['outputs']['dout']['status']=='registered'; assert sorted(p['stage_count'] for p in w['pipeline_chains'])==[2,2]; assert w['wrapper_candidates'][0]['status']=='registers_on_both_sides'; assert all('demo_core.' in f['message'] and f['rule'] in ('UF006','UF007') for f in r['findings'])} $report
set text_report [file join [file dirname $report] RTL_Lint_Results.rpt]
if {![file exists $text_report] || [file size $text_report] == 0} { error "Missing formatted report" }
set html_report [file join [file dirname $report] RTL_Lint_Results.html]
if {![file exists $html_report] || [file size $html_report] == 0} { error "Missing HTML report" }
if {[llength [get_designs -quiet]]} { error "Unexpected elaborated design" }
puts "RTL_LINT_AUTO_SMOKE_PASS: automatic architecture checks without policy or elaboration"
close_project
exit
