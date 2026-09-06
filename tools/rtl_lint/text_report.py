"""Human-readable source-lint report for Vivado's text editor."""
from collections import Counter, defaultdict
from recommendations import GUIDANCE, examples_for
from textwrap import wrap
from datetime import datetime


def format_report(report):
    lines = []
    def section(title):
        lines.extend(["", title, "-" * len(title)])
    def path(p):
        clock = " / ".join(p.get("clock", []))
        return (f'{p["from"]} -> {p["to"]}: {p["stage_count"]} stages '
                f'({", ".join(p["stages"])}); clock {clock}')
    findings = report["findings"]
    active = [f for f in findings if "waived" not in f]
    architectures = report["architectures"]
    unknown = sum(a["status"] != "reviewed" for a in architectures)
    lines.extend(["RTL Lint Results", "=" * 80,
                  "Generated: " + (report.get("generated_at") or datetime.now().astimezone().isoformat(timespec="seconds")),
                  "Source review only - no elaboration or synthesis",
                  f'{len(report["files_checked"])} files checked | {len(active)} warnings | '
                  f'{len(findings)-len(active)} waived | {len(report["errors"])} errors',
                  f'{len(architectures)} architectures | {unknown} unknown/unsupported',
                  "Scope: " + report["source_scope"], report["limitation"]])
    lines.append("UF001-UF010 are local linter IDs, not AMD methodology DRC IDs.")
    section("Errors")
    lines.extend(report["errors"] or ["None."])
    section("Findings by rule (unwaived)")
    counts = Counter(f["rule"] for f in active)
    lines.extend([f"{rule}: {count:>4}   {GUIDANCE[rule]["title"]}" for rule, count in sorted(counts.items())] or ["None. This is not a sign-off result; review coverage below."])
    section("Findings by file - line:column")
    groups = defaultdict(list)
    for f in findings:
        groups[f["file"]].append(f)
    for filename, group in sorted(groups.items()):
        lines.extend(["", "FILE: " + filename, "=" * 96])
        for f in sorted(group, key=lambda item:(item["line"], item["column"], item["rule"])):
            state = "WAIVED" if "waived" in f else "REVIEW"
            lines.extend(["", f'{state} [{f["rule"]}] Line {f["line"]}:{f["column"]}',
                          "  Observed: " + f["message"],
                          "  Fix: see " + f["rule"] + " in SUGGESTED FIXES below."])
            for row in f.get("source_excerpt", []):
                marker = ">" if row["line"] == f["line"] else " "
                lines.append(f'  {marker} {row["line"]:5} | {row["text"]}')
            if "waived" in f:
                lines.append("  Waiver: " + f["waived"])
    if not findings:
        lines.append("No findings emitted. See coverage and limitations.")
    section("SUGGESTED FIXES - UltraFast methodology guidance")
    lines.append("Examples are illustrative; adapt names and preserve interface behavior.")
    for rule in sorted({f["rule"] for f in findings}):
        g = GUIDANCE[rule]
        lines.extend(["", rule + " | " + g["title"], "-" * 96,
                      "Suggested change: " + g["action"],
                      "Check before accepting: " + g["verify"],
                      "UltraFast basis: " + g["why"],
                      "AMD UG949: " + g["url"]])
        for language, example in examples_for(rule, findings):
            lines.append("Illustrative " + language + ":")
            lines.extend("    " + row for row in example.splitlines())
    section("Architecture checks")
    if not report["automatic_architecture"]:
        lines.append("Automatic architecture checks are disabled.")
    for a in architectures:
        lines.extend(["", f'{a["entity"]}({a["architecture"]}) - {a["status"].upper()}',
                      "File: " + a["file"]])
        for direction in ("inputs", "outputs"):
            lines.append(direction.title() + ":")
            for port, details in sorted(a[direction].items()):
                captures = details.get("capture_registers", [])
                suffix = "; capture: " + ", ".join(captures) if captures else ""
                lines.append(f'  {port}: {details["status"]}{suffix}')
            if not a[direction]:
                lines.append("  No ports reported.")
        if a["status"] != "reviewed":
            lines.append("Pipeline/wrapper inventory: UNKNOWN; empty results do not prove absence.")
        else:
            lines.append("Clocked signals: " + (", ".join(a["clocked_signals"]) or "None detected."))
            lines.append("Copy pipelines (2+ stages):")
            lines.extend(["  " + path(p) for p in a["pipeline_chains"]] or ["  None detected by supported source patterns."])
            lines.append("Register wrapper candidates:")
            for w in a["wrapper_candidates"]:
                lines.append(f'  {w["instance"]} ({w["entity"]}): {w["status"]}')
                lines.append(f'    Port directions: {w["port_directions"]}; placement intent: unknown')
                for direction in ("input_paths", "output_paths"):
                    for p in w[direction]:
                        lines.append(f'    {direction}: core port {p["core_port"]}: ' + path(p))
                missing = w["missing_shreg_extract_no"]
                if missing:
                    lines.append('    Review SHREG_EXTRACT="no": ' + ", ".join(missing))
            if not a["wrapper_candidates"]:
                lines.append("  None detected by supported source patterns.")
        lines.extend("Note: " + note for note in a["notes"])
    section("Coverage notes")
    lines.extend(f'{n["file"]}: {n["note"]}' for n in report["coverage_notes"])
    section("Files checked")
    lines.extend(report["files_checked"] or ["None."])
    section("Files excluded by configuration")
    lines.extend(report["files_excluded"] or ["None."])
    section("Sources/containers skipped by adapter - NOT CHECKED")
    lines.extend(report["sources_not_linted"] or ["None listed."])
    lines.append("IP/BD interiors excluded by the Vivado adapter are not enumerated here.")
    formatted = []
    for line in lines:
        # Keep URLs, full file paths and code intact; wrap prose for Notepad.
        if line.startswith(("FILE:", "AMD UG949:", "    ", "  >")) or " | " in line:
            formatted.append(line)
        else:
            formatted.extend(wrap(line, width=100, subsequent_indent="  ", break_long_words=False, break_on_hyphens=False) or [""])
    return "\n".join(formatted) + "\n"
