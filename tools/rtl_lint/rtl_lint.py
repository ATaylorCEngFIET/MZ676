"""Small VHDL, Verilog and SystemVerilog source-pattern linter. Never elaborates or invokes synthesis.

This is a deliberately limited lexer/structural scanner, not an HDL compiler.
Findings are review suggestions; absence of findings is not design sign-off.
"""
import argparse
import fnmatch
import json
from pathlib import Path
import re
import sys
import boundary_lint
import architecture_lint
import verilog_lint
from text_report import format_report
from html_report import format_html
from recommendations import GUIDANCE, examples_for
from datetime import datetime
from dataclasses import dataclass

GUIDE = "https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/"
RULES = {
    "UF001": ("Asynchronous control", "Synchronous-Reset-vs.-Asynchronous-Reset"),
    "UF002": ("Reset nested under enable", "Reset-and-Clock-Enable-Precedence"),
    "UF003": ("Logic in clock path", "Using-Gated-Clocks"),
    "UF004": ("Multiply with asynchronous control", "Reset-Coding-Example-Multiplier-with-Synchronous-Reset"),
    "UF005": ("Memory array reset", "Inferring-RAM-and-ROM"),
    "UF006": ("Module output registration", "Register-Data-Paths-at-Logical-Boundaries"),
    "UF007": ("Module input registration", "Register-Data-Paths-at-Logical-Boundaries"),
    "UF008": ("Pipeline stage policy", "Pipelining-Considerations"),
    "UF009": ("Placement pipeline SRL extraction", "Coding-Shift-Registers-and-Delay-Lines"),
    "UF010": ("Analysis coverage incomplete", "Running-RTL-DRCs"),
}
DEFAULT = {"reset_pattern": r"(?i)(^|_)(rst|reset|areset)(_n|n)?$",
           "disabled_rules": [], "exclude": [], "waivers": [], "module_policies": [], "automatic_architecture": True}
# Retain strings as single tokens so comments and keywords inside them are inert.
LEX = re.compile(r'--[^\n]*|/\*.*?\*/|"(?:""|[^"])*"|\\[^\\\n]+\\|'
                 r"'(?:[^'\n])'|[a-zA-Z][a-zA-Z0-9_]*|\d+(?:#\w+#)?|"
                 r"<=|:=|=>|/=|>=|\*\*|\S", re.S)


@dataclass
class Token:
    text: str
    offset: int


def lex(source):
    return [Token(m.group().lower() if not m.group().startswith(('"', '\\')) else m.group(),
                  m.start()) for m in LEX.finditer(source)
            if not m.group().startswith(("--", "/*"))]


def pairs(tokens):
    stack, result = [], {}
    for i, t in enumerate(tokens):
        if t.text == "(":
            stack.append(i)
        elif t.text == ")" and stack:
            start = stack.pop()
            result[start] = i
    return result


def edge_names(tokens):
    return {tokens[i+2].text for i, t in enumerate(tokens[:-3])
            if t.text in ("rising_edge", "falling_edge")
            and tokens[i+1].text == "(" and tokens[i+3].text == ")"}


def scan(source, filename, config=None, architecture_reports=None):
    config = {**DEFAULT, **(config or {})}
    if Path(filename).suffix.lower() in (".v", ".sv"):
        return verilog_lint.scan(source, filename, config, architecture_reports)
    reset_re = re.compile(config["reset_pattern"])
    tokens = lex(source)
    findings, coverage = [], []
    source_lines = source.splitlines()

    def emit(rule, tok, message):
        line = source.count("\n", 0, tok.offset) + 1
        item = {"rule": rule, "severity": "warning", "file": str(filename),
                "line": line, "column": tok.offset - source.rfind("\n", 0, tok.offset),
                "message": message, "reference": GUIDE + RULES[rule][1], "language": "VHDL"}
        item["source_excerpt"] = [{"line": n+1, "text": source_lines[n]}
                                  for n in range(max(0, line-3), min(len(source_lines), line+2))]
        if rule in config["disabled_rules"]:
            return
        for waiver in config["waivers"]:
            if (waiver["rule"] == rule and fnmatch.fnmatch(str(filename).replace("\\", "/"),
                                                       waiver["file"])
                    and waiver.get("line", line) == line):
                item["waived"] = waiver["reason"]
        if item not in findings:
            findings.append(item)

    # Analyze each architecture separately; equal signal names in other entities
    # must not supply evidence for a clock driver or local memory declaration.
    starts = [i for i, t in enumerate(tokens[:-3])
              if t.text == "architecture" and tokens[i+2].text == "of"]
    for a, b in zip(starts, starts[1:] + [len(tokens)]):
        ts = tokens[a:b]
        values = [t.text for t in ts]
        parens = pairs(ts)
        array_types = set()
        memories = set()
        for i in range(len(ts)-3):
            if values[i] == "type" and values[i+2:i+4] == ["is", "array"]:
                array_types.add(values[i+1])
        for i, t in enumerate(ts):
            if t.text != "signal":
                continue
            j = i+1
            while j < len(ts) and values[j] not in (":", ";"):
                j += 1
            if j+1 < len(ts) and values[j] == ":" and values[j+1] in array_types:
                memories.update(v for v in values[i+1:j] if v != ",")

        # Separate process bodies from concurrent assignments without flattening
        # their clocks together. Unsupported event-attribute forms are reported.
        process_ranges = []
        i = 0
        while i < len(ts):
            if values[i] == "process" and (i == 0 or values[i-1] != "end"):
                end = next((j for j in range(i+1, len(ts)-1)
                            if values[j:j+2] == ["end", "process"]), None)
                if end is None:
                    coverage.append("Unterminated process; remaining source not checked.")
                    break
                process_ranges.append((i, end+2))
                i = end+2
            else:
                i += 1
        clocks = set()
        for lo, hi in process_ranges:
            pt = ts[lo:hi]
            pv = values[lo:hi]
            clocks.update(edge_names(pt))
            if "event" in pv:
                coverage.append("Clock 'event form is not analyzed; use rising_edge/falling_edge for these checks.")
            if "procedure" in pv or "function" in pv:
                coverage.append("Process with local subprogram is not analyzed.")
                continue
            begin = next((k for k, v in enumerate(pv) if v == "begin"), None)
            if begin is None:
                continue
            stack, assignments, async_controls = [], [], []
            k = begin+1
            while k < len(pt):
                v = pv[k]
                if pv[k:k+2] == ["end", "if"]:
                    if stack:
                        stack.pop()
                    k += 2
                    continue
                if v in ("if", "elsif"):
                    stop = next((j for j in range(k+1, len(pt)) if pv[j] == "then"), None)
                    if stop is None:
                        break
                    if v == "elsif" and stack:
                        stack.pop()
                    cond = pt[k+1:stop]
                    has_edge = any(t.text in ("rising_edge", "falling_edge") for t in cond)
                    has_reset = any(re.fullmatch(r"[a-z][a-z0-9_]*", t.text)
                                    and reset_re.search(t.text) for t in cond)
                    kind = "clock" if has_edge else "reset" if has_reset else "other"
                    if kind == "reset" and "clock" in stack:
                        clock_at = len(stack)-1-stack[::-1].index("clock")
                        if "other" in stack[clock_at+1:]:
                            emit("UF002", pt[k], "Reset-like condition is nested under another condition inside a clocked branch; review reset-over-enable priority.")
                    if has_edge:
                        # Direct expression clocks, e.g. rising_edge(clk and en).
                        for e, t in enumerate(cond[:-1]):
                            if t.text in ("rising_edge", "falling_edge"):
                                cp = pairs(cond)
                                endp = cp.get(e+1)
                                if endp is not None and endp != e+3:
                                    emit("UF003", t, "Clock edge uses an expression or indexed name; review for logic in the clock path.")
                    stack.append(kind)
                    k = stop+1
                    continue
                if v == "else" and stack:
                    stack[-1] = "other"
                # Recognize simple signal assignments, including array elements.
                if re.fullmatch(r"[a-z][a-z0-9_]*", v):
                    j = k+1
                    if j < len(pt) and pv[j] == "(":
                        endp = parens.get(lo+j)
                        j = endp-lo+1 if endp is not None else j
                    if j < len(pt) and pv[j] == "<=":
                        stop = next((x for x in range(j+1, len(pt)) if pv[x] == ";"), len(pt))
                        rhs = pt[j+1:stop]
                        assignments.append((pt[k], list(stack), rhs))
                        if "reset" in stack and "clock" not in stack:
                            async_controls.append(pt[k])
                        if v in memories and "reset" in stack:
                            emit("UF005", pt[k], "Locally declared array is written in a reset-like branch; resetting memory contents can prevent block RAM inference. Review array intent.")
                        k = stop+1
                        continue
                k += 1
            if async_controls and edge_names(pt):
                emit("UF001", async_controls[0], "Assignment under a reset-like condition outside the clock edge; review whether asynchronous control is required (reset synchronizers may be intentional).")
                for lhs, context, rhs in assignments:
                    if "clock" in context and any(t.text == "*" for t in rhs):
                        emit("UF004", lhs, "Multiplication shares a process with asynchronous control; review register resets for DSP packing. Actual DSP inference is not checked.")
        in_process = {i for lo, hi in process_ranges for i in range(lo, hi)}
        for i in range(len(ts)-2):
            if i in in_process or values[i] not in clocks or values[i+1] != "<=":
                continue
            stop = next((j for j in range(i+2, len(ts)) if values[j] == ";"), len(ts))
            if any(v in ("and", "or", "xor", "nand", "nor", "xnor", "not", "when")
                   for v in values[i+2:stop]):
                emit("UF003", ts[i], "A clock used by an edge function is driven by a Boolean/conditional assignment in this architecture; review clock-enable or dedicated clock-buffer options.")
    if not starts:
        coverage.append("No architecture body found; no architecture checks applied (packages/entities alone are not checked).")
    discovered = architecture_lint.discover(tokens, filename, config, emit, coverage)
    if architecture_reports is not None:
        architecture_reports.extend(discovered)
    boundary_lint.check(tokens, filename, config, emit, coverage)
    return findings, sorted(set(coverage))


def load_config(filename):
    config = {**DEFAULT, **(json.loads(Path(filename).read_text(encoding="utf-8-sig")) if filename else {})}
    unknown = set(config) - set(DEFAULT)
    if unknown:
        raise ValueError("Unknown configuration fields: " + ", ".join(sorted(unknown)))
    re.compile(config["reset_pattern"])
    boundary_lint.validate(config["module_policies"])
    if type(config["automatic_architecture"]) is not bool:
        raise ValueError("automatic_architecture must be true or false")
    if any(rule not in RULES for rule in config["disabled_rules"]):
        raise ValueError("Unknown disabled rule")
    for waiver in config["waivers"]:
        if waiver.get("rule") not in RULES or not waiver.get("file") or not waiver.get("reason", "").strip():
            raise ValueError("Each waiver needs a known rule, file glob and nonempty reason")
    return config


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", help="VHDL, Verilog, SystemVerilog files or directories")
    ap.add_argument("--file-list", help="UTF-8 file, one absolute source path per line")
    ap.add_argument("--skipped-file-list", help="UTF-8 paths intentionally omitted by the source adapter; recorded as unreviewed")
    ap.add_argument("--source-scope", default="Supplied files and recursive RTL directory inputs", help="Description of the caller's file selection")
    ap.add_argument("--config")
    ap.add_argument("--json", dest="json_path")
    ap.add_argument("--html-report", help="Write an offline browser report with UltraFast repair guidance")
    ap.add_argument("--text-report", help="Write a formatted report for the Vivado text editor")
    ap.add_argument("--fail-on-warning", action="store_true")
    args = ap.parse_args(argv)
    try:
        config = load_config(args.config)
        skipped_sources = []
        if args.skipped_file_list:
            skipped_sources = sorted(set(line for line in Path(args.skipped_file_list).read_text(encoding="utf-8-sig").splitlines() if line))
        inputs = list(args.paths)
        if args.file_list:
            inputs += Path(args.file_list).read_text(encoding="utf-8-sig").splitlines()
        files = set()
        for name in filter(None, inputs):
            p = Path(name).resolve()
            if p.is_dir():
                files.update(x for x in p.rglob("*") if x.suffix.lower() in (".vhd", ".vhdl", ".v", ".sv"))
            else:
                files.add(p)
        results, coverage, errors, checked, excluded = [], [], [], [], []
        matched_policies = set()
        architectures = []
        for p in sorted(files):
            if any(fnmatch.fnmatch(p.as_posix(), glob) for glob in config["exclude"]):
                excluded.append(str(p))
                continue
            if p.suffix.lower() not in (".vhd", ".vhdl", ".v", ".sv"):
                errors.append(f"Unsupported source language: {p}")
                continue
            try:
                source = p.read_text(encoding="utf-8-sig")
                if p.suffix.lower() in (".v", ".sv"):
                    entities = [unit['name'] for unit in verilog_lint.modules(source)[0]]
                    match_policy = verilog_lint.policy_matches
                else:
                    token_values = [t.text for t in lex(source)]
                    entities = [token_values[i+3] for i in range(len(token_values)-3)
                                if token_values[i] == "architecture" and token_values[i+2] == "of"]
                    match_policy = boundary_lint.policy_matches
                for index, policy in enumerate(config["module_policies"]):
                    if any(match_policy(policy, str(p), e) for e in entities):
                        matched_policies.add(index)
                findings, notes = scan(source, str(p), config, architectures)
                results.extend(findings)
                coverage.extend({"file": str(p), "note": note} for note in notes)
                checked.append(str(p))
            except (OSError, UnicodeError) as exc:
                errors.append(str(exc))
        for index, policy in enumerate(config["module_policies"]):
            if index not in matched_policies:
                errors.append(f'Module policy {index+1} ({policy["entity"]}) matched no scanned architecture')
        if not config["module_policies"]:
            coverage.append({"file": "(policy)", "note": "No explicit module policies: automatic architecture checks run independently when enabled; no required pipeline depth is imposed."})
        if not checked:
            errors.append("No RTL files checked")
        report = {"mode": "source-pattern-review", "files_checked": checked,
                  "files_excluded": excluded, "findings": results,
                  "source_scope": args.source_scope, "sources_not_linted": skipped_sources,
                  "module_policies": config["module_policies"],
                  "automatic_architecture": config["automatic_architecture"],
                  "architectures": architectures,
                  "coverage_notes": coverage, "errors": errors,
                  "limitation": "Limited VHDL/Verilog/SystemVerilog source patterns only; no syntax validation, elaboration, timing, CDC proof, or inference verification."}
        report["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        report["rule_guidance"] = {r: {**GUIDANCE[r], "examples": dict(examples_for(r, results))}
                                   for r in sorted({f["rule"] for f in results})}
        if args.json_path:
            Path(args.json_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.text_report:
            Path(args.text_report).write_text(format_report(report), encoding="utf-8")
        if args.html_report:
            Path(args.html_report).write_text(format_html(report), encoding="utf-8")
        print("Source scope: " + args.source_scope)
        if skipped_sources:
            print(f"COVERAGE: {len(skipped_sources)} source/container entries omitted by the adapter; see sources_not_linted in the JSON report. These entries were not checked.")
        for f in results:
            state = "WAIVED" if "waived" in f else "WARNING"
            print(f'{f["file"]}:{f["line"]}:{f["column"]}: {state} [{f["rule"]}] {f["message"]}')
        for architecture in architectures:
            name = f'{architecture["entity"]}({architecture["architecture"]})'
            print(f'ARCHITECTURE: {name}: {architecture["status"]}; {len(architecture["clocked_signals"])} clocked signals, {len(architecture["pipeline_chains"])} copy pipelines, {len(architecture["wrapper_candidates"])} wrapper candidates')
            for direction in ("inputs", "outputs"):
                if architecture[direction]:
                    print(f'  {direction}: ' + ", ".join(f'{n}={v["status"]}' for n, v in architecture[direction].items()))
            for pipeline in architecture["pipeline_chains"]:
                print(f'  pipeline: {pipeline["from"]} -> {pipeline["to"]}: {pipeline["stage_count"]} stages ({", ".join(pipeline["stages"])})')
            for wrapper in architecture["wrapper_candidates"]:
                print(f'  wrapper: {wrapper["instance"]}: {wrapper["status"]}; directions {wrapper["port_directions"]}; placement intent unknown')
            for note in architecture["notes"]:
                print(f'  note: {note}')
        for note in coverage:
            print(f'COVERAGE: {note["file"]}: {note["note"]}')
        for error in errors:
            print("ERROR: " + error)
        count = sum("waived" not in f for f in results)
        print(f"Source review: {len(checked)} files, {count} warnings, {len(errors)} errors. No elaboration. No sign-off implied.")
        return 2 if errors else 1 if args.fail_on_warning and count else 0
    except (OSError, ValueError, TypeError, KeyError, re.error) as exc:
        print("RTL lint error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

