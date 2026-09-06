# Optional module policies

Automatic architecture checks run independently of `module_policies`. These optional
policies add explicit port selections, required stage counts, and placement intent. The
required boundary ports and pipeline depths are design intent, not something the
linter can infer from a module name. Select data ports explicitly; clocks, resets,
handshake signals and bidirectional ports should not automatically be registered.

`examples/placement_wrapper.vhd` demonstrates a core with two register stages on
its input and two on its output. `examples/placement_policy.json` selects the
ports and paths and checks their connections to the wrapped core. The example
files are separate from the application's RTL and are not added to your project.

```powershell
python tools/rtl_lint/rtl_lint.py tools/rtl_lint/examples/placement_wrapper.vhd --config tools/rtl_lint/examples/placement_policy.json --fail-on-warning
```

Example policy for your own wrapper (merge this field into your existing config):

```json
{
  "module_policies": [
    {
      "entity": "placement_wrapper",
      "registered_inputs": ["din"],
      "registered_outputs": ["dout"],
      "pipelines": [
        {"from": "din", "to": "in_2", "min_stages": 2, "max_stages": 2,
         "clock": "clk", "placement": true,
         "core_port": "core_i.d", "side": "input"},
        {"from": "core_q", "to": "dout", "min_stages": 2, "max_stages": 2,
         "clock": "clk", "placement": true,
         "core_port": "core_i.q", "side": "output"}
      ]
    }
  ]
}
```

- Entity names and port selectors accept globs. An optional `file` glob selects
  absolute source paths using forward slashes. VHDL names are case insensitive;
  Verilog/SystemVerilog names and all file globs are case sensitive. The `entity`
  field selects a module name for Verilog/SystemVerilog. Policies apply to every
  matching architecture/module.
- `min_stages` is required. `max_stages` is optional; use equal values to require
  an exact count. Plain concurrent wire aliases add zero stages.
- `clock` optionally requires a clock signal name. All traced stages must use
  the same clock name and edge; enable guards must match textually. The tool
  does not prove logical equivalence of different guard expressions.
- `placement: true` checks each recognized register stage for an explicit local
  signal attribute, for example `attribute shreg_extract of in_1, in_2 : signal
  is "no";`. An unrelated attribute or comment does not satisfy this rule.
- `core_port` is an optional `instance.port` binding. For `side: "input"`, that
  port must connect to `to`; for `side: "output"`, it must connect to `from`.
  This checks local wiring only, not the child entity's actual port direction,
  internal behavior, clock domain or driver ownership.
- Policy selectors matching no ports produce UF010; a module policy matching no
  scanned architecture is an input error. Existing exclusions and waivers apply.

The Vivado command accepts a policy path:

```tcl
::rtl_lint::run C:/path/to/rtl_lint.json
```

With no argument, it uses `rtl_lint.json` in the open project's directory if
present, otherwise the bundled `config.json`. The menu uses the same lookup.
Source reports include the configured policies and recognized stage counts.
The example's two-stage choice is illustrative, not a universal AMD requirement.

For Verilog/SystemVerilog, use `(* SHREG_EXTRACT = "no" *)` on the pipeline signal
declarations and preserve the exact case of module, port, instance and signal names.
See the [language support notes](README.md#verilog-and-systemverilog-support) for
constructs that produce unknown results.

The VHDL boundary/pipeline model intentionally supports a narrower subset than a VHDL
compiler: entity ports declared in the same file, whole scalar/vector signal
assignments, simple edge functions, if/elsif/else, local signal attributes and
direct entity instances with named port maps. It supports constant reset writes
and consistent enable guards. Arrays/slices on assignment targets, generated loops,
local subprograms, component instances and other
unsupported statements produce UF010 for selected architectures. Registers inside
child instances are not followed. Port/signal types and widths are not resolved.
Explicit self-hold assignments and combinational-process aliases on pipeline paths
require review; use clock enables with implicit holds for recognized pipelines.
A pipeline is a chain of whole-signal copies; arithmetic between stages is reported
as a path that cannot be established. Registered output checks do allow arithmetic
before the output's clocked assignment. Direct input capture is a strict policy;
even an input wire alias before capture requires review.

The checks count source register stages, not guaranteed cycle latency under stalls,
reset behavior, sideband alignment, protocol correctness, post-synthesis surviving
registers or physical distance. They do not add registers or constraints to RTL.
To inspect the Tcl integration without elaboration, run:

```powershell
vivado -mode batch -nolog -nojournal -source tools/rtl_lint/test_vivado.tcl
```

