"""Automatic local architecture inventory and advisory register-boundary checks."""
import re
from boundary_lint import Model, Unsupported, entity_ports, IDENT, wire_source


def discover(tokens, filename, config, emit, coverage):
    declarations = entity_ports(tokens)
    values = [t.text for t in tokens]
    starts = [i for i in range(len(tokens)-3)
              if values[i] == 'architecture' and values[i+2] == 'of']
    units = [(values[lo+3], values[lo+1], tokens[lo], declarations.get(values[lo+3], {}),
              tokens[lo:hi]) for lo, hi in zip(starts, starts[1:] + [len(tokens)])]
    return review_units(units, declarations, Model, filename, config, emit, coverage)


def review_units(units, declarations, model_class, filename, config, emit, coverage):
    """Language adapters provide a local assignment model; analysis never elaborates."""
    if not config.get('automatic_architecture', True):
        return []
    reports = []
    reset_re = re.compile(config['reset_pattern'])
    clock_re = re.compile(r'(?i)(^|_)(clk|clock)(_|$)')
    for entity, architecture, anchor, ports, payload in units:
        report = {'file': str(filename), 'entity': entity, 'architecture': architecture,
                  'status': 'reviewed', 'inputs': {}, 'outputs': {},
                  'clocked_signals': [], 'pipeline_chains': [], 'wrapper_candidates': [],
                  'notes': []}
        reports.append(report)
        try:
            model = model_class(payload, config['reset_pattern'])
        except (Unsupported, IndexError) as exc:
            report['status'] = 'unknown'
            report['notes'].append(str(exc))
            for name, (mode, _) in ports.items():
                dest = report['inputs'] if mode == 'in' else report['outputs']
                dest[name] = {'status': 'unknown'}
            emit('UF010', anchor, f'{entity}({architecture}): automatic architecture checks could not finish: {exc}. Pipeline, wrapper and I/O status is unknown.')
            continue
        if not ports:
            report['notes'].append('No local ports found; boundary checks have no port evidence.')
        clocks = {r.clock[1] for rows in model.assignments.values() for r in rows if r.clock}
        known = model.signals | set(ports)
        # Resolve child directions only when the entity declaration is in this file.
        external_drivers = set()
        child_modes = {}
        for instance, actuals in model.instances.items():
            child = declarations.get(model.instance_types[instance], {})
            child_modes[instance] = child
            for formal, actual in actuals.items():
                mode = child.get(formal, (None,))[0]
                if mode in ('out', 'buffer', 'inout') and len(actual) == 1:
                    external_drivers.add(actual[0].text)

        def registered(signal):
            seen = set()
            while signal not in seen:
                seen.add(signal)
                if signal in external_drivers:
                    return False
                rows = model.data_rows(signal)
                if len(rows) == 1 and rows[0].owner == -1 and model.wire(rows[0].rhs):
                    signal = model.wire(rows[0].rhs)
                else:
                    return model.registered(signal)
            return False

        for name, rows in model.assignments.items():
            data = model.data_rows(name)
            if data and all(r.clock for r in data) and registered(name):
                report['clocked_signals'].append(name)
        report['clocked_signals'].sort()
        for port, (mode, tok) in ports.items():
            if mode == 'in':
                if port in clocks or clock_re.search(port) or reset_re.search(port):
                    report['inputs'][port] = {'status': 'clock_or_reset_exempt'}
                    continue
                usages = [(ts, ok, where) for ts, ok, where in model.uses
                          if any(t.text == port for t in ts)]
                captures, bypasses = set(), []
                for ts, ok, where in usages:
                    if ok and [t.text for t in ts] == [port] and registered(where.text):
                        captures.add(where.text)
                    else:
                        bypasses.append(where)
                status = ('unused' if not usages else 'registered' if captures and not bypasses
                          else 'partially_registered' if captures else 'unregistered')
                report['inputs'][port] = {'status': status, 'capture_registers': sorted(captures)}
                if bypasses:
                    emit('UF007', bypasses[0], f'{entity}.{port}: automatic I/O review found raw input use before direct register capture; status {status}. Review whether this boundary should be registered.')
            elif mode in ('out', 'buffer'):
                if registered(port):
                    status = 'registered'
                elif (len(model.assignments.get(port, [])) == 1
                      and model.assignments[port][0].owner == -1
                      and model.constant(model.assignments[port][0].rhs)):
                    status = 'constant'
                elif model.assignments.get(port):
                    status = 'unregistered'
                    emit('UF006', tok, f'{entity}.{port}: automatic I/O review found no local registered output boundary; review combinational logic or bypass at this output.')
                else:
                    status = 'unknown'
                    report['notes'].append(f'{port}: no local assignment; child-driven or unresolved output registration is unknown.')
                report['outputs'][port] = {'status': status}
            else:
                report['outputs'][port] = {'status': 'bidirectional_not_checked'}

        # Trace whole-signal copies backwards without a prescribed source or depth.
        # Expressions end a copy-chain; cycles and ambiguous drivers do not count.
        paths, issues = [], set()
        for target in sorted(known):
            source, seen, possible_stages = target, set(), []
            while source not in seen:
                seen.add(source)
                rows = model.data_rows(source)
                if not rows:
                    break
                signatures = {(tuple(t.text for t in r.rhs), r.clock, r.guards) for r in rows}
                if len(signatures) != 1 or len({r.owner for r in model.assignments[source]}) != 1:
                    break
                rhs, clock, guards = next(iter(signatures))
                if len(rhs) != 1 or not model.ident.fullmatch(rhs[0]) or rhs[0] not in known:
                    break
                if clock:
                    possible_stages.append(source)
                source = rhs[0]
            else:
                continue  # state feedback is not counted as a pipeline
            if not possible_stages:
                continue
            try:
                stages, clock = model.chain(source, target)
                if any(s in external_drivers for s in stages):
                    raise Unsupported('a stage is also connected to a locally known child output')
            except Unsupported as exc:
                if len(possible_stages) >= 2:
                    message = f'{entity}: candidate copy pipeline ending at {target} could not be established: {exc}.'
                    if message not in issues:
                        issues.add(message)
                        emit('UF008', model.assignments[target][0].token, message)
                continue
            if stages:
                paths.append({'from': source, 'to': target, 'stages': stages,
                              'stage_count': len(stages), 'clock': list(clock),
                              'kind': 'whole_signal_copy_chain'})
        # Keep maximal chains, plus distinct branch endpoints. Register count is
        # structural, not a latency or minimum-timing requirement.
        for path in paths:
            if path['stage_count'] < 2:
                continue
            if any(path['stages'] == other['stages'][:len(path['stages'])]
                   and other['stage_count'] > path['stage_count'] for other in paths):
                continue
            if not any(p['stages'] == path['stages'] for p in report['pipeline_chains']):
                report['pipeline_chains'].append(path)

        for instance, actuals in model.instances.items():
            input_paths, output_paths, unknown_modes = [], [], False
            child = child_modes[instance]
            for formal, actual in actuals.items():
                if len(actual) != 1:
                    continue
                signal = actual[0].text
                mode = child.get(formal, (None,))[0]
                incoming = [p for p in paths if p['to'] == signal and p['from'] in report['inputs']
                            and report['inputs'][p['from']]['status'] != 'clock_or_reset_exempt']
                outgoing = [p for p in paths if p['from'] == signal and p['to'] in report['outputs']]
                if mode is None and (incoming or outgoing):
                    unknown_modes = True
                if mode in ('in', None):
                    input_paths.extend({'core_port': formal, **p} for p in incoming)
                if mode in ('out', 'buffer', None):
                    output_paths.extend({'core_port': formal, **p} for p in outgoing)
            if not input_paths and not output_paths:
                continue
            wrapped = bool(input_paths and output_paths)
            stage_names = sorted({s for p in input_paths + output_paths for s in p['stages']})
            missing = [s for s in stage_names if model.attrs.get((s, 'shreg_extract')) != ['no']]
            candidate = {'instance': instance, 'entity': model.instance_types[instance],
                         'status': 'registers_on_both_sides' if wrapped else 'registers_on_one_side',
                         'port_directions': 'inferred_from_local_usage' if unknown_modes else 'declared_in_file',
                         'input_paths': input_paths, 'output_paths': output_paths,
                         'placement_intent': 'unknown', 'missing_shreg_extract_no': missing}
            report['wrapper_candidates'].append(candidate)
            if wrapped and missing:
                emit('UF009', model.instance_tokens[instance], f'{entity}.{instance}: registers detected on both sides of this core; {", ".join(missing)} lack local SHREG_EXTRACT = "no". If this is a placement wrapper, review SRL extraction; ordinary delay pipelines may intentionally use SRLs.')
        report['notes'].append('Pipeline and wrapper absence is informational. Required timing depth, internal child registers and physical placement are not determined.')
    return reports
