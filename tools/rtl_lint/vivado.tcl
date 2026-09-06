# Source from the Vivado Tcl console; no design opening/elaboration is needed.
namespace eval ::rtl_lint {
    variable home [file dirname [file normalize [info script]]]
    variable python [list python]
}

proc ::rtl_lint::run {{config ""}} {
    variable home
    variable python
    set project [current_project -quiet]
    if {$project eq ""} { error "Open a Vivado project before running RTL source lint." }
    set sources [get_files -quiet -norecurse -of_objects [current_fileset] -filter {USED_IN_SYNTHESIS == 1}]
    set files {}
    set skipped {}
    foreach obj $sources {
        set type [get_property FILE_TYPE $obj]
        set name [get_property NAME $obj]
        if {[string match "VHDL*" $type] || $type eq "Verilog" || $type eq "SystemVerilog"} {
            lappend files [file normalize $name]
        } else {
            # Composite IP/BD sources and other HDL languages are outside this
            # RTL pass. Record them instead of aborting the whole project.
            lappend skipped [file normalize $name]
        }
    }
    if {![llength $files]} { error "No direct synthesis-enabled VHDL, Verilog or SystemVerilog files in the active source fileset. IP/BD internals and header files are not linted independently." }
    if {$config eq ""} {
        set config [file join [get_property DIRECTORY $project] rtl_lint.json]
        if {![file exists $config]} { set config [file join $home config.json] }
    }
    set config [file normalize $config]
    puts "RTL source lint policy: $config"
    set output [file join [get_property DIRECTORY $project] rtl_lint_reports]
    file mkdir $output
    set manifest [file join $output sources.txt]
    set fp [open $manifest w]
    fconfigure $fp -encoding utf-8
    foreach name [lsort -unique $files] { puts $fp $name }
    close $fp
    set skipped_manifest [file join $output skipped_sources.txt]
    set fp [open $skipped_manifest w]
    fconfigure $fp -encoding utf-8
    foreach name [lsort -unique $skipped] { puts $fp $name }
    close $fp
    set report [file join $output report.json]
    set text_report [file join $output RTL_Lint_Results.rpt]
    set html_report [file join $output RTL_Lint_Results.html]
    # Remove only our generated reports so a failed invocation cannot show stale results.
    foreach generated [list $report $text_report $html_report] {
        if {[file exists $generated]} { file delete -- $generated }
    }
    set command [concat $python [list [file join $home rtl_lint.py] \
        --file-list $manifest --config $config --json $report --text-report $text_report --html-report $html_report \
        --skipped-file-list $skipped_manifest \
        --source-scope {Vivado direct synthesis-enabled VHDL/Verilog/SystemVerilog sources; IP and block-design contents are not expanded}]]
    puts "RTL source lint: [llength [lsort -unique $files]] direct RTL files; [llength [lsort -unique $skipped]] other source/container entries skipped. Generated IP interiors are not expanded."
    set failed [catch {exec {*}$command 2>@1} result options]
    puts $result
    if {[file exists $text_report]} {
        puts "RTL lint browser report: $html_report"
        puts "RTL lint text report: $text_report"
        puts "Click Open RTL Lint Report to view the formatted browser report; for a Vivado tab use File > Text Editor > Open File."
    }
    if {[file exists $report]} { puts "RTL source lint JSON: $report" }
    if {$failed} { return -options $options $result }
    return $report
}

# View the last report for the active project; this does not run lint again.
proc ::rtl_lint::open_report {} {
    variable home
    variable python
    set project [current_project -quiet]
    if {$project eq ""} { error "Open a Vivado project before opening its RTL lint report." }
    set report [file normalize [file join [get_property DIRECTORY $project] rtl_lint_reports RTL_Lint_Results.html]]
    if {![file isfile $report]} {
        error "No formatted RTL lint report for this project. Click Run RTL Lint first. Expected: $report"
    }
    # Python uses the OS browser association; no shell-built command or file upload.
    if {[catch {exec {*}$python [file join $home open_report.py] $report 2>@1} result]} {
        error "Could not open the RTL lint browser report: $result. Report: $report"
    }
    puts "Opened saved RTL lint browser report: $report"
    return $report
}

proc ::rtl_lint::install {} {
    variable home
    set buttons [list \
        [list rtl_source_lint "Run RTL Lint" \
            "Run RTL Lint: check saved RTL, pipeline stages, wrappers and registered I/O" run.tcl lint_button.png] \
        [list rtl_source_lint_report "Open RTL Lint Report" \
            "Open the current project's formatted RTL lint report in a browser" open_report.tcl report_button.png]]
    # Validate all assets before updating either entry.
    foreach button $buttons {
        lassign $button name label description script icon
        foreach asset [list $script $icon] {
            set path [file join $home $asset]
            if {![file exists $path]} { error "RTL lint installation file missing: $path" }
        }
    }
    foreach button $buttons {
        lassign $button name label description script icon
        if {[llength [get_gui_custom_commands -quiet $name]]} {
            remove_gui_custom_commands $name
        }
        create_gui_custom_command -name $name -menu_name $label \
            -description $description -tcl_file [file join $home $script] \
            -toolbar_icon [file join $home $icon] -show_on_toolbar
    }
    puts "RTL lint toolbar buttons installed: Run RTL Lint (chip/check) and Open RTL Lint Report (blue document)."
}
