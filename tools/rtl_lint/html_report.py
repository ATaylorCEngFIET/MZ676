"""Standalone, offline HTML presentation of the same source-lint results."""
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from recommendations import GUIDANCE, examples_for


def h(value):
    return escape(str(value), quote=True)


def table(headers, rows):
    return ('<div class="table-wrap"><table><thead><tr>' + ''.join('<th>'+h(x)+'</th>' for x in headers)
            + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+x+'</td>' for x in row)+'</tr>' for row in rows)
            + '</tbody></table></div>')


def badge(value):
    return '<span class="badge">'+h(value.replace('_', ' '))+'</span>'


def format_html(report):
    findings = report['findings']
    active = [f for f in findings if 'waived' not in f]
    unknown = sum(a['status'] != 'reviewed' for a in report['architectures'])
    counts = Counter(f['rule'] for f in active)
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>RTL Lint Results</title><style>',
           (Path(__file__).parent/'report.css').read_text(encoding='utf-8'),
           '</style></head><body><main>',
           '<header><div class="eyebrow">RTL SOURCE REVIEW / ULTRAFAST GUIDANCE</div>',
           '<h1>RTL Lint Results</h1><p class="muted">Generated '+h(report.get('generated_at') or datetime.now().astimezone().isoformat(timespec='seconds'))+'</p>',
           '<p>Pipeline stages, register wrappers and registered I/O — with repair guidance linked to AMD UG949.</p></header>',
           '<nav><a href="#findings">Findings</a><a href="#guidance">Suggested fixes</a><a href="#architecture">Architecture</a><a href="#coverage">Coverage</a><button id="print">Print / save PDF</button></nav>',
           '<section class="stats">']
    for value, label in [(len(report['files_checked']), 'Files checked'), (len(active), 'Unwaived warnings'), (unknown, 'Unknown architectures'), (len(report['errors']), 'Scan errors')]:
        out.append('<div><strong>'+h(value)+'</strong><span>'+h(label)+'</span></div>')
    out.append('</section><p class="notice">Review suggestions, not sign-off. UF001–UF010 are this add-in’s rule IDs, not AMD methodology DRC IDs. Unknown means not established. No elaboration or synthesis was run.</p>')
    if report['errors']:
        out.append('<section class="errors"><h2>Scan errors — results may be incomplete</h2><ul>'+''.join('<li>'+h(e)+'</li>' for e in report['errors'])+'</ul></section>')
    out.append('<section><h2>Review overview</h2>')
    out.append(table(['Rule', 'Review area', 'Unwaived'], [[f'<a href="#guide-{h(rule)}">{h(rule)}</a>', h(GUIDANCE[rule]['title']), str(n)] for rule, n in sorted(counts.items())]))
    out.append('<p class="muted">'+str(len(findings)-len(active))+' waived findings remain visible. Zero findings do not imply complete coverage.</p></section>')
    out.append('<section id="findings"><h2>Findings by file</h2><p>Expand a finding for the source excerpt. Follow its fix link for a suggested change, validation steps and UltraFast reference.</p>')
    out.append('<div class="filters"><label>Search<input id="search" type="search" placeholder="File, signal, rule or message"></label><label>Rule<select id="rule"><option value="">All rules</option>')
    out.extend('<option>'+h(r)+'</option>' for r in sorted({f['rule'] for f in findings}))
    out.append('</select></label><label>Status<select id="state"><option value="">All statuses</option><option value="active">Unwaived</option><option value="waived">Waived</option></select></label><button id="expand">Expand visible</button><button id="collapse">Collapse visible</button></div><p id="visible-count" aria-live="polite"></p><p id="no-match" hidden>No findings match these filters.</p>')
    groups = defaultdict(list)
    for f in findings:
        groups[f['file']].append(f)
    for filename, group in sorted(groups.items()):
        basename = filename.replace('\\', '/').rsplit('/', 1)[-1]
        out.append('<article class="file-group"><h3>'+h(basename)+' <span class="muted">'+str(len(group))+' findings</span></h3><p class="path">'+h(filename)+'</p>')
        for f in sorted(group, key=lambda x:(x['line'], x['column'], x['rule'])):
            rule = f['rule']
            state = 'waived' if 'waived' in f else 'active'
            out.append('<details class="finding" data-rule="'+h(rule)+'" data-state="'+state+'"><summary><span class="location">L'+h(f['line'])+':'+h(f['column'])+'</span>'+badge(rule)+'<span class="finding-message">'+h(f['message'])+'</span>'+badge('waived' if state=='waived' else 'review')+'</summary><div class="finding-body">')
            if 'waived' in f:
                out.append('<p><b>Waiver:</b> '+h(f['waived'])+'</p>')
            if f.get('source_excerpt'):
                out.append('<p class="muted">Source at scan time; highlighted line is the reported location.</p><pre class="source">')
                for row in f['source_excerpt']:
                    tag = 'mark' if row['line']==f['line'] else 'span'
                    out.append('<'+tag+'>'+h(f"{row['line']:>5}  {row['text']}")+'</'+tag+'>\n')
                out.append('</pre>')
            else:
                out.append('<p class="muted">No source excerpt in this saved report. Rerun lint to capture it.</p>')
            out.append('<a class="fix-link" href="#guide-'+h(rule)+'">Suggested fix &amp; UltraFast basis: '+h(GUIDANCE[rule]['title'])+' →</a></div></details>')
        out.append('</article>')
    if not findings:
        out.append('<p>No findings emitted. Check coverage and errors before drawing conclusions.</p>')
    out.append('</section><section id="guidance"><h2>Suggested fixes &amp; UltraFast basis</h2><p>Apply these patterns only where they preserve the interface contract. Examples use placeholder signal names and are not automatic patches.</p>')
    for rule in sorted({f['rule'] for f in findings}):
        g = GUIDANCE[rule]
        out.append('<article class="guide" id="guide-'+h(rule)+'"><h3>'+badge(rule)+' '+h(g['title'])+'</h3><div class="guide-grid"><div><h4>Suggested change</h4><p>'+h(g['action'])+'</p><h4>Before accepting the change</h4><p>'+h(g['verify'])+'</p></div><div><h4>Why this relates to UltraFast</h4><p>'+h(g['why'])+'</p><a href="'+h(g['url'])+'" target="_blank" rel="noopener noreferrer">AMD UG949: '+h(g['topic'].replace('-', ' '))+' ↗</a>')
        for language, example in examples_for(rule, findings):
            out.append('<h4>Illustrative '+h(language)+' - adapt to your design</h4><pre>'+h(example)+'</pre>')
        out.append('</div></div><a href="#findings">Back to findings ↑</a></article>')
    out.append('</section><section id="architecture"><h2>Architecture inventory</h2><p>Counts describe detected source structures, not physical register counts or proven timing closure.</p>')
    if not report['automatic_architecture']:
        out.append('<p class="notice">Automatic architecture checks are disabled.</p>')
    for a in report['architectures']:
        reviewed = a['status']=='reviewed'
        out.append('<details class="architecture"><summary><b>'+h(a['entity']+' ('+a['architecture']+')')+'</b> '+badge(a['status'])+'<span class="muted">'+(f"{len(a['pipeline_chains'])} copy pipelines · {len(a['wrapper_candidates'])} wrapper candidates" if reviewed else 'Pipeline / wrapper status unknown')+'</span></summary><div class="finding-body"><p class="path">'+h(a['file'])+'</p>')
        rows=[]
        for direction in ('inputs','outputs'):
            for port, data in sorted(a[direction].items()):
                rows.append([h(direction[:-1]), h(port), badge(data['status']), h(', '.join(data.get('capture_registers',[])))])
        out.append(table(['Direction','Port','Status','Capture registers'], rows))
        if reviewed:
            out.append('<h4>Clocked signals</h4><p>'+h(', '.join(a['clocked_signals']) or 'None detected.')+'</p><h4>Copy pipelines (2+ stages)</h4>')
            out.append(table(['Path','Stages','Registers','Clock'], [[h(p['from']+' → '+p['to']),h(p['stage_count']),h(', '.join(p['stages'])),h(' / '.join(p.get('clock') or []))] for p in a['pipeline_chains']]) if a['pipeline_chains'] else '<p>None detected by supported patterns.</p>')
            out.append('<h4>Register wrappers</h4>')
            for w in a['wrapper_candidates']:
                out.append('<p><b>'+h(w['instance']+' ('+w['entity']+')')+'</b> '+badge(w['status'])+'</p><p>Port directions: '+h(w['port_directions'])+'; placement intent: unknown.</p>')
                rows=[]
                for direction in ('input_paths','output_paths'):
                    for p in w[direction]:
                        rows.append([h(direction.replace('_',' ')),h(p['core_port']),h(p['from']+' → '+p['to']),h(p['stage_count']),h(', '.join(p['stages']))])
                out.append(table(['Side','Core port','Path','Depth','Registers'],rows))
                if w['missing_shreg_extract_no']:
                    out.append('<p>Review SHREG_EXTRACT="no": '+h(', '.join(w['missing_shreg_extract_no']))+'</p>')
            if not a['wrapper_candidates']:
                out.append('<p>None detected by supported patterns.</p>')
        else:
            out.append('<p class="notice">Inventory is unknown. Empty results do not prove missing registers, pipelines or wrappers.</p>')
        out.extend('<p class="muted">'+h(n)+'</p>' for n in a['notes'])
        out.append('</div></details>')
    out.append('</section><section id="coverage"><h2>Scope &amp; coverage</h2><p>'+h(report['source_scope'])+'</p><p>'+h(report['limitation'])+'</p>')
    for key, label in [('files_checked','Files checked'),('files_excluded','Configuration exclusions'),('sources_not_linted','Skipped sources / containers — NOT CHECKED')]:
        out.append('<details><summary>'+h(label)+' ('+str(len(report[key]))+')</summary><ul class="path">'+''.join('<li>'+h(p)+'</li>' for p in report[key])+'</ul></details>')
    out.append('<details><summary>Coverage notes ('+str(len(report['coverage_notes']))+')</summary><ul>')
    out.extend('<li><span class="path">'+h(n['file'])+'</span><br>'+h(n['note'])+'</li>' for n in report['coverage_notes'])
    out.append('</ul></details></section><footer>Saved source review · No RTL modified · Findings require engineering review</footer></main><script>')
    out.append((Path(__file__).parent/'report.js').read_text(encoding='utf-8'))
    out.append('</script></body></html>')
    return ''.join(out)
