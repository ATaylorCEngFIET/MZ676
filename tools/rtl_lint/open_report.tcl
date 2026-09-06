# Toolbar action: open the active project's saved report without rerunning lint.
source [file join [file dirname [file normalize [info script]]] vivado.tcl]
::rtl_lint::open_report
