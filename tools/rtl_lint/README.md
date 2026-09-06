# Automatic RTL architecture lint for Vivado

A Python 3 VHDL, Verilog and SystemVerilog source linter with a Vivado Tcl command.
It automatically inspects supported architectures/modules in the supplied files for pipeline registers, register wrappers,
and registered I/O. **No module list, pipeline endpoints or policy file is required.**
It reads saved source only and never invokes elaboration, synthesis or implementation.

## Run

In the Vivado Tcl console with a project open:

```tcl
source C:/hdl_projects/debugging_advanced/tools/rtl_lint/vivado.tcl
::rtl_lint::run
```

To install **Run RTL Lint** and **Open RTL Lint Report** toolbar buttons, paste this into the Vivado Tcl console (run it again to add the new report button):

```tcl
source C:/hdl_projects/debugging_advanced/tools/rtl_lint/install.tcl
```

Look for the **chip with a green check mark** in the main toolbar. Hover text is
"Run RTL Lint". Clicking it immediately scans the open project's saved RTL;
there are no command arguments or setup dialogs on each run. The command is also
available under Tools > Custom Commands > Run RTL Lint. Vivado saves custom buttons
for subsequent sessions of that version. Keep this folder at its installed path.
Re-sourcing the installer refreshes both entries without adding duplicates.
The **blue document** button, **Open RTL Lint Report**, opens the active project's
last `RTL_Lint_Results.html` in your default browser. The report is a local file;
it is not uploaded and does not require an internet connection to view. AMD reference
links require internet access when clicked. It does not rerun lint. If no
report exists for that project, it asks you to run lint first. Each click reads
the active project, so switching projects also switches which report is opened.
Both commands are available under Tools > Custom Commands.

The command scans direct synthesis-enabled VHDL, Verilog and SystemVerilog in the active source fileset. It prints
findings and architecture summaries in the Tcl console and saves these files in
`rtl_lint_reports` under the open project's directory:

- `RTL_Lint_Results.html`: summary cards, rule counts, searchable findings grouped
  by file, saved source excerpts, linked fix guidance, language-appropriate examples and architecture
  tables. Filter by rule or waiver status and print/save as PDF from the browser.
- `RTL_Lint_Results.rpt`: a wrapped text fallback with file groups, code excerpts,
  fix guidance and AMD links. It also includes warning counts, file/line locations,
  registered I/O, pipeline stages, wrapper candidates, errors and coverage notes.
- `report.json`: the same scan results in machine-readable form.

Click **Run RTL Lint**, then **Open RTL Lint Report** to use the new browser report.
Existing buttons pick up the new behavior automatically; re-source the installer
if you want to refresh an older tooltip mentioning Notepad. An old text-only report
requires one lint run to generate the HTML version.

The fix guidance maps local UF rule IDs to AMD UG949 topics; these IDs are not
AMD methodology DRC IDs. Suggestions are conditional and do not modify RTL.
UF010 describes incomplete analysis, not a proven RTL violation. For example,
boundary-register suggestions explicitly require latency and handshake review,
and allow intentional combinational adapters to remain unchanged. Source excerpts
are saved at scan time; rerun after editing RTL.

To view the text fallback in a Vivado tab, use **File > Text Editor > Open File**
and select `RTL_Lint_Results.rpt`. The Tcl console prints its full path after each
run. This uses Vivado's text editor; automatic opening is not implemented because
no suitable supported Tcl API was verified. `open_report` loads native RPX reports,
not this plain-text report. Each run replaces the report files and manifests. If
an open editor tab retains old contents, close it without saving and reopen the
report. The lint button re-sources the add-in on every click. Run the installer above
once to add the separate report-opening button to an existing installation.

Python 3 must be on Vivado's PATH; no packages
are needed. To specify an executable, set `::rtl_lint::python` to a Tcl list before
running, or edit its default in `vivado.tcl` for persistent menu use.

The adapter queries direct files using `get_files -norecurse`. Generated IP/BD
internals are not expanded. Verilog and SystemVerilog files added directly to the
source fileset are scanned along with VHDL. Header files (`.vh`/`.svh`), unsupported
source types and IP/BD containers are skipped and listed in
`sources_not_linted` in the JSON report and `skipped_sources.txt`. The report records
its `source_scope`; skipped entries are not claimed to have been checked. A generated
RTL wrapper added directly to the fileset is still included. A project with no direct
RTL files produces an explicit error. Simulation filesets are not scanned.
The standalone CLI still rejects unsupported files explicitly passed as inputs.

From a shell, inspect a file or directory directly:

```powershell
python tools/rtl_lint/rtl_lint.py rtl --json build/rtl_lint_report.json --text-report build/RTL_Lint_Results.rpt --html-report build/RTL_Lint_Results.html
python tools/rtl_lint/rtl_lint.py C:/path/to/block.vhd
```

Directories are searched recursively for `.vhd`, `.vhdl`, `.v` and `.sv` files. Exit codes:
0 = review completed; 1 = unwaived warnings when using `--fail-on-warning`;
2 = input/configuration/tool error. Empty scans are errors.

## Verilog and SystemVerilog support

The source parser supports ANSI and non-ANSI module ports, `wire`/`reg`/`logic`/`bit`
declarations, packed vectors, parameterized module headers and named parameter/port
connections, continuous assignments, `always` edge blocks, `always_ff`, `always_comb`,
`always_latch`, combinational sensitivity lists, `begin`/`end`, `if`/`else`, and
`case`/`casez`/`casex`. Module, port and signal names remain **case-sensitive**.
The same UF001–UF010 checks, waivers, HTML/text reports and optional module policies
apply. The policy field remains named `entity`; for Verilog it selects a module.

The architecture scan recognizes whole-signal **nonblocking** register assignments,
wire aliases, copy chains, enable differences, mixed clocks and named register
wrappers. `(* SHREG_EXTRACT = "no" *)` on signal declarations is recognized. Blocking
assignments in combinational blocks do not count as registers. Edge-triggered
blocking assignments make the module unknown because execution order is not modeled.

This is a limited structural source parser, not a compiler. Preprocessor macros,
includes and conditionals are **not expanded**; affected modules are marked unknown.
`timescale`, `default_nettype` and `resetall` directives are accepted. Generate blocks,
loops, functions/tasks, packages/interfaces/structs, positional or wildcard instance
connections, indexed/partial writes and unresolved expressions also produce UF010
instead of a claimed passing architecture. Supported memory reset writes can emit
UF005 before the partial-write limitation is reported. Header files are not scanned
as standalone design units. Widths, parameter values, binding across files, inferred
hardware and syntax validity are not proved; no elaboration is invoked.

```powershell
python tools/rtl_lint/rtl_lint.py tools/rtl_lint/examples/placement_wrapper.sv --html-report build/sv_report.html
```

## Automatic architecture report

| Item | What the checker reports |
|---|---|
| Clocked signals | Whole signals assigned in recognized clocked branches; this is not a count of physical flip-flops |
| Pipeline chains | Automatically discovered chains of at least two whole-signal copy registers, with names, clock and stage count |
| Input registration | Registered, partially registered (capture plus bypass), unregistered, unused, or clock/reset exempt |
| Output registration | Registered, unregistered, constant, unknown, or bidirectional/not checked |
| Register wrappers | Child instances with input-side and/or output-side register paths connected to the parent entity's ports |
| SRL extraction | Advisory warning when a wrapper has registers on both sides but stages lack local `SHREG_EXTRACT = "no"` |
| Unknown source | Explicit unknown status and UF010 if the architecture uses an unsupported structural construct |

Example of automatically detected structure:

```text
ARCHITECTURE: placement_wrapper(rtl): reviewed; 4 clocked signals, 2 copy pipelines, 1 wrapper candidates
  inputs: clk=clock_or_reset_exempt, din=registered
  outputs: dout=registered
  pipeline: din -> in_2: 2 stages (in_1, in_2)
  pipeline: core_q -> dout: 2 stages (out_1, out_2)
  wrapper: core_i: registers_on_both_sides; directions declared_in_file; placement intent unknown
```

Detection uses assignments and connections, not module or signal names. Simple
clock/reset names and observed clocks are exempt from input-registration advice.
Other control and handshake ports are reported; their unregistered status may be
intentional. Warnings prompt review and never instruct the tool to insert registers.

Output wire aliases and standard `std_logic_vector`/`unsigned`/`signed` casts can
preserve registered status. Arithmetic, conditional logic or inversion after an
output register triggers review. Input registration currently requires direct
whole-signal capture; expressions, control use and child-port bypasses are flagged.

A single capture register appears in the clocked-signal inventory and wrapper
paths. A copy pipeline is reported from two stages onward. Ordinary arithmetic
registers appear in the inventory, but the tool does not count arithmetic or
variable-dependent paths as copy pipelines. Feedback loops are not pipelines.

A wrapper is a **structural candidate**. The checker cannot establish physical
placement intent from source alone. Child port directions are resolved from entity
declarations in the same file; otherwise directions are labelled as inferred from
local use. Child internal registers are not traced. Register wrappers do not have
to be present in every architecture, and a missing pipeline is informational.

## Rules

| Rule | Check |
|---|---|
| UF001 | Reset-like assignment outside the clock edge: review asynchronous control |
| UF002 | Reset nested below another condition in a clocked branch: review priority |
| UF003 | Boolean/conditional clock driver or non-simple edge argument |
| UF004 | Multiplication shares a process with detected asynchronous control |
| UF005 | Locally declared array written inside a reset-like branch |
| UF006 | Unregistered local output boundary |
| UF007 | Raw input use before direct register capture, including bypasses |
| UF008 | Detected candidate copy pipeline cannot be established, e.g. mixed clocks/edges or enable guards; optional policies can also check required depth |
| UF009 | Possible placement-wrapper stages lack explicit local no-SRL attributes; optional placement policies make this an explicit requirement |
| UF010 | Architecture analysis is unknown, or an optional policy cannot be established |

IDs are local to this tool, not AMD methodology check IDs. Every finding has a file,
line, column and reference. Reports include structured `architectures` records as
well as findings; raw pipeline counts alone do not constitute timing sign-off.

## Optional settings

Automatic checks are **on by default**, including without `--config`. Set
`automatic_architecture` to false only to disable the automatic inventory/advice.
`config.json` can adjust reset-name recognition, disable rules, exclude files or
waive warnings with reasons. Vivado uses `rtl_lint.json` in the project directory
when present, otherwise its bundled `config.json`. CLI settings are passed with
`--config`. A specific configuration can also be passed to `::rtl_lint::run`.

`module_policies` are optional additional requirements, not prerequisites for
automatic checks. See [POLICIES.md](POLICIES.md) to enforce a particular depth,
clock, set of boundary ports or placement intent. No depth is imposed automatically.

## Coverage and validation

This is a limited structural source checker, not a compiler. It supports ordinary
entity/architecture declarations, whole-signal assignments, simple edge functions,
if/elsif/else and case branches, process variables (not variable-dependent pipeline
tracing), local attributes and direct entity instances with named port maps.
Comments and strings do not create fake register or attribute evidence.

Indexed/sliced assignment targets, generate loops, component/positional instances,
local subprograms and other unsupported constructs yield an unknown architecture
result. Entity ports must be declared in the same file for I/O classification.
Types, widths, overloads, aliases, shadowing, generics, hierarchy and XDC attributes
are not resolved. A module driven only by a child has unknown output registration.
Unrelated variable operations do not add pipeline stages.

Unknown status is not the same as no registers or no wrappers. Recognized stages
are source structures, not guaranteed surviving registers or fixed cycle latency
under stalls. Reset correctness, valid/data alignment, protocol correctness, CDC,
required pipeline depth, timing and physical placement still need later checks.
Warnings can describe intentional designs; review or waive them with a reason.

```powershell
python -m unittest discover -s tools/rtl_lint -p "test_*.py"
vivado -mode batch -nolog -nojournal -source tools/rtl_lint/test_vivado.tcl
vivado -mode batch -nolog -nojournal -source tools/rtl_lint/test_vivado_mixed.tcl
```

The Vivado smoke tests use in-memory projects and check automatic discovery
without an elaborated design. The mixed test exercises VHDL, Verilog, SystemVerilog
and language-appropriate HTML repair examples. It does not install GUI commands or edit application RTL.

## References

- [AMD: Register Data Paths at Logical Boundaries](https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/Register-Data-Paths-at-Logical-Boundaries?contentId=rAQuq~ABtJ9ZH4g4n2_O8w)
- [AMD: Placement registers and SRL extraction](https://docs.amd.com/r/en-US/ug1387-acap-hardware-ip-platform-dev-methodology/Coding-Shift-Registers-and-Delay-Lines)
- [AMD: Pipeline depth and SRL tradeoffs](https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/Balance-Pipeline-Depth-and-SRL-Usage)
