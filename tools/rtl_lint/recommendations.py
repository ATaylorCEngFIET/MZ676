"""Review guidance mapped to AMD UG949; UF IDs are local linter IDs, not AMD DRC IDs."""
GUIDE = 'https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/'

def entry(title, topic, why, action, verify, example=''):
    return dict(title=title, topic=topic, url=GUIDE+topic, why=why,
                action=action, verify=verify, example=example)

GUIDANCE = {
 'UF001': entry('Asynchronous control', 'Synchronous-Reset-vs.-Asynchronous-Reset',
  'UG949 recommends synchronous reset when a reset is needed, allowing more flexible mapping to dedicated resources.',
  'For ordinary synchronous datapath registers, consider moving reset handling inside rising_edge(clk). Keep asynchronous assertion where the reset specification requires it; do not blindly change reset synchronizers.',
  'Check reset polarity, clock availability during reset, and release behavior. Simulate startup and reset recovery.',
  "process(clk)\nbegin\n  if rising_edge(clk) then\n    if rst = '1' then\n      q <= (others => '0');\n    else\n      q <= d;\n    end if;\n  end if;\nend process;"),
 'UF002': entry('Reset under clock enable', 'Reset-and-Clock-Enable-Precedence',
  'UG949 describes reset priority over enable as the native register behavior; reversing it can put extra logic in the data path.',
  'Where the functional reset specification permits, make reset the first branch inside the clock edge, then use elsif for enable. This changes behavior when reset and enable are asserted together.',
  'Simulate all reset/enable combinations, especially reset asserted with enable low.',
  "if rising_edge(clk) then\n  if rst = '1' then\n    q <= (others => '0');\n  elsif en = '1' then\n    q <= d;\n  end if;\nend if;"),
 'UF003': entry('Logic in a clock path', 'Using-Gated-Clocks',
  'UG949 recommends clock enables instead of fine-grained HDL clock gating to preserve dedicated clock routing.',
  'Drive the process from the original clock and place the enable condition inside the clocked branch. If a whole clock domain must stop, review a device-supported clock buffer with enable.',
  'Check enable timing, reset behavior and clock constraints. A mux or divider in the clock path needs a clocking review, not a mechanical rewrite.',
  "-- Replace a Boolean gated clock only after checking its intent.\nif rising_edge(clk) then\n  if en = '1' then\n    q <= d;\n  end if;\nend if;"),
 'UF004': entry('Multiplier reset and DSP packing', 'Reset-Coding-Example-Multiplier-with-Synchronous-Reset',
  'UG949 demonstrates packing multiplier pipeline registers into DSP resources with synchronous reset.',
  'Review operand and product registers for synchronous reset, or omit datapath reset only when validity control makes their startup values irrelevant. Preserve required multiplier latency.',
  'Simulate reset and valid/data alignment, then inspect DSP inference and pipeline packing after synthesis. This scan cannot prove DSP mapping.'),
 'UF005': entry('Memory contents reset', 'Inferring-RAM-and-ROM',
  'UG949 recommends RAM inference templates and notes that asynchronous reset can interfere with RAM inference.',
  'If the array is intended as RAM, use the appropriate RAM template. Consider resetting validity/control state instead of clearing every element. If runtime clearing is required, consider a sequential write sweep with explicit busy/valid handling.',
  'Check read-during-write behavior, reset semantics and when data becomes valid; inspect actual RAM inference after synthesis. A register bank may intentionally reset all elements.'),
 'UF006': entry('Unregistered module output', 'Register-Data-Paths-at-Logical-Boundaries',
  'UG949 recommends registering outputs at logical boundaries to keep timing paths local and easier to analyze.',
  'For a timing-sensitive boundary, move output combinational logic before an existing output register or add an output register. Keep a deliberate combinational adapter unchanged when latency must remain zero, and document that decision with a targeted waiver.',
  'Align data, valid and sideband signals. For ready/valid or AXI interfaces use a protocol-correct register slice or skid-buffer design; never delay ready/valid independently. Check latency in simulation.',
  "-- Example for a simple synchronous datapath, not an AXI slice.\nprocess(clk)\nbegin\n  if rising_edge(clk) then\n    result_q <= result_comb;\n  end if;\nend process;\nresult_out <= result_q;"),
 'UF007': entry('Raw input used before capture', 'Register-Data-Paths-at-Logical-Boundaries',
  'UG949 suggests considering registered inputs as well as outputs at hierarchical boundaries.',
  'If the interface permits an added cycle, capture the synchronous input into a local register and route its internal consumers through that register. Remove unintended raw-input bypasses. A combinational pass-through or monitor may intentionally remain unregistered.',
  'A single input register is not a CDC solution. Preserve handshake and sideband alignment; confirm latency and stall behavior before changing the boundary.',
  "-- Example for a same-clock data input with one-cycle latency.\nprocess(clk)\nbegin\n  if rising_edge(clk) then\n    input_q <= input_data;\n  end if;\nend process;\n-- Use input_q in downstream logic; review any input_data bypass."),
 'UF008': entry('Pipeline structure needs review', 'Pipelining-Considerations',
  'UG949 explains that pipelining trades added latency and control overhead for shorter per-cycle datapaths.',
  'Inspect the named stages, clock and enable conditions. If a required depth is reported, reconcile it with the intended latency; otherwise establish why the candidate is not one consistent pipeline. Do not insert stages just because this limited scanner cannot trace a path.',
  'Align parallel paths and valid/control signals, and simulate stalls and reset. Choose depth using timing requirements; this scan does not prove the number of cycles under stalls.'),
 'UF009': entry('Placement registers may become SRLs', 'Coding-Shift-Registers-and-Delay-Lines',
  'UG949 recommends disabling SRL inference when registers are intended to provide placement flexibility.',
  'If this is deliberately a placement wrapper, apply SHREG_EXTRACT="no" to the listed pipeline signals in the architecture declaration. For ordinary delay storage, SRL inference may be preferable.',
  'Confirm placement intent first, then inspect the synthesized cells and physical placement. The attribute alone does not constrain register locations.',
  'attribute SHREG_EXTRACT : string;\nattribute SHREG_EXTRACT of in_1, in_2, out_1, out_2 : signal is "no";'),
 'UF010': entry('Analysis coverage incomplete', 'Running-RTL-DRCs',
  'This is a linter coverage limitation, not evidence of an AMD methodology violation. UG949 describes elaborated RTL DRCs as a later validation step.',
  'Review the reported unsupported construct, missing local declaration, selector or binding. Correct a mistaken policy selector if applicable; otherwise review the architecture manually. Do not rewrite valid RTL merely to satisfy the scanner.',
  'Treat pipeline, wrapper and I/O results as unknown for the affected analysis. Run elaborated RTL DRCs separately when needed; this lint button still performs no elaboration.')
}


VERILOG_EXAMPLES = {
 'UF001': "always @(posedge clk) begin\n  if (rst) q <= 0;\n  else     q <= d;\nend",
 'UF002': "always @(posedge clk) begin\n  if (rst)     q <= 0;\n  else if (en) q <= d;\nend",
 'UF003': "// Replace a Boolean gated clock after checking intent.\nalways @(posedge clk) begin\n  if (en) q <= d;\nend",
 'UF006': "// Simple datapath example; not an AXI register slice.\nalways @(posedge clk) result_q <= result_comb;\nassign result_out = result_q;",
 'UF007': "// Same-clock input; adds a cycle of latency.\nalways @(posedge clk) input_q <= input_data;\n// Use input_q downstream; review raw input_data bypasses.",
 'UF009': '(* SHREG_EXTRACT = "no" *) reg [WIDTH-1:0] in_1, in_2, out_1, out_2;'
}


def examples_for(rule, findings):
    """Show only the languages represented by this rule's findings."""
    related = [f for f in findings if f['rule'] == rule]
    examples = []
    if any(str(f['file']).lower().endswith(('.vhd', '.vhdl')) for f in related):
        if GUIDANCE[rule]['example']:
            examples.append(('VHDL', GUIDANCE[rule]['example']))
    if any(str(f['file']).lower().endswith(('.v', '.sv')) for f in related):
        if rule in VERILOG_EXAMPLES:
            examples.append(('Verilog / SystemVerilog', VERILOG_EXAMPLES[rule]))
    return examples
