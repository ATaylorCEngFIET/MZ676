"""Conservative, opt-in VHDL module-boundary and placement-pipeline checks.

Only a small structural subset is supported. Unsupported constructs in a selected
architecture produce UF010, never an implied successful policy check.
"""
from collections import defaultdict
from dataclasses import dataclass
import fnmatch
import re

IDENT = re.compile(r'[a-z][a-z0-9_]*\Z')
POLICY_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*\Z')


class Unsupported(ValueError):
    pass


def names(values):
    return [v for v in values if IDENT.fullmatch(v)]


def wire_source(tokens):
    """Recognize a wire or standard vector type conversion, without resizing."""
    vs = [t.text for t in tokens]
    while len(vs) >= 4 and vs[0] in ('std_logic_vector', 'unsigned', 'signed') and vs[1] == '(' and vs[-1] == ')':
        depth = 0
        balanced = True
        for i, value in enumerate(vs[1:]):
            depth += (value == '(') - (value == ')')
            if depth == 0 and i != len(vs)-2:
                balanced = False
        if not balanced:
            break
        vs = vs[2:-1]
    return vs[0] if len(vs) == 1 and IDENT.fullmatch(vs[0]) else None


def split_top(tokens, separator):
    groups, start, depth = [], 0, 0
    for i, tok in enumerate(tokens):
        depth += (tok.text == '(') - (tok.text == ')')
        if depth == 0 and tok.text == separator:
            groups.append(tokens[start:i])
            start = i + 1
    groups.append(tokens[start:])
    return groups


@dataclass
class Assignment:
    token: object
    rhs: list
    clock: object
    guards: tuple
    reset: bool
    owner: int


class Model:
    ident = IDENT
    wire = staticmethod(wire_source)

    def constant(self, tokens):
        return all(not self.ident.fullmatch(t.text) or t.text == 'others' for t in tokens)

    def __init__(self, tokens, reset_pattern):
        self.ts = tokens
        self.v = [t.text for t in tokens]
        self.i = 0
        self.reset_re = re.compile(reset_pattern)
        self.assignments = defaultdict(list)
        self.uses = []
        self.signals = set()
        self.attrs = defaultdict(list)
        self.instances = {}
        self.instance_types = {}
        self.instance_tokens = {}
        self.owner = 0
        self.body()

    def take(self, expected=None):
        if self.i >= len(self.v):
            raise Unsupported('unexpected end of architecture')
        tok = self.ts[self.i]
        if expected is not None and tok.text != expected:
            raise Unsupported(f'expected {expected}, found {tok.text}')
        self.i += 1
        return tok

    def until(self, end):
        start, depth = self.i, 0
        while self.i < len(self.v):
            v = self.v[self.i]
            if depth == 0 and v == end:
                result = self.ts[start:self.i]
                self.i += 1
                return result
            depth += (v == '(') - (v == ')')
            self.i += 1
        raise Unsupported(f'missing {end}')

    def body(self):
        # Caller supplies one architecture, starting at architecture ... is.
        self.until('is')
        while self.i < len(self.v) and self.v[self.i] != 'begin':
            kind = self.take().text
            if kind not in ('signal', 'attribute', 'constant', 'type', 'subtype'):
                raise Unsupported(f'declaration {kind} (local subprograms/components are not supported)')
            decl = self.until(';')
            vals = [t.text for t in decl]
            if kind == 'signal' and ':' in vals:
                self.signals.update(names(vals[:vals.index(':')]))
            if kind == 'type' and 'record' in vals:
                raise Unsupported('record declaration')
            if kind == 'attribute' and 'of' in vals:
                if ':' not in vals or 'is' not in vals:
                    raise Unsupported('attribute specification')
                attr, colon, value_at = vals[0], vals.index(':'), vals.index('is')
                if vals[colon+1] != 'signal' or value_at+2 != len(vals):
                    continue
                for signal in names(vals[vals.index('of')+1:colon]):
                    self.attrs[(signal, attr)].append(vals[value_at+1].strip('"').lower())
        self.take('begin')
        self.statements((), False)
        self.take('end')
        # Stop at this architecture's terminator. Other design units are ignored.
        self.until(';')

    def statements(self, context, sequential):
        while self.i < len(self.v) and self.v[self.i] not in ('end', 'elsif', 'else', 'when'):
            # Optional process/instance labels.
            label = None
            if self.i+1 < len(self.v) and self.v[self.i+1] == ':':
                label = self.take().text
                self.take(':')
            v = self.v[self.i]
            if v == 'process' and not sequential:
                self.take()
                if self.v[self.i] == '(':
                    self.take()
                    self.until(')')
                if self.v[self.i] == 'is':
                    self.take()
                while self.v[self.i] in ('variable', 'constant'):
                    self.take()
                    decl = self.until(';')
                    # Variable-dependent data paths are not traced as register chains.
                    self.uses.append((decl, False, decl[0]))
                self.take('begin')
                self.owner += 1
                self.statements((), True)
                self.take('end')
                self.take('process')
                self.until(';')
            elif v == 'if' and sequential:
                self.take()
                self.if_branches(context)
                self.take('end')
                self.take('if')
                self.take(';')
            elif v == 'case' and sequential:
                self.take()
                expr = self.until('is')
                self.uses.append((expr, False, expr[0]))
                while self.v[self.i] == 'when':
                    self.take()
                    choice = self.until('=>')
                    guard = ('guard', tuple(t.text for t in expr + choice), True)
                    self.statements(context + (guard,), True)
                self.take('end')
                self.take('case')
                self.take(';')
            elif IDENT.fullmatch(v) and self.i+1 < len(self.v) and self.v[self.i+1] == ':=' and sequential:
                lhs = self.take()
                self.take(':=')
                rhs = self.until(';')
                self.uses.append((rhs, False, lhs))
            elif v == 'null' and sequential:
                self.take()
                self.take(';')
            elif v == 'entity' and not sequential and label:
                self.instance(label)
            elif IDENT.fullmatch(v) and self.i+1 < len(self.v) and self.v[self.i+1] == '<=':
                lhs = self.take()
                self.take('<=')
                rhs = self.until(';')
                if any(t.text in ('after', 'transport', 'reject') for t in rhs):
                    raise Unsupported('timed assignment')
                clocks = [x[1] for x in context if x[0] == 'clock']
                clock = clocks[0] if len(clocks) == 1 else None
                if any(x[0] == 'clock_else' for x in context):
                    raise Unsupported('assignment in the non-edge branch of a clock condition')
                guards = tuple(x for x in context if x[0] == 'guard')
                reset = any(x[0] == 'reset' and x[2] for x in context)
                row = Assignment(lhs, rhs, clock, guards, reset, self.owner if sequential else -1)
                self.assignments[lhs.text].append(row)
                self.uses.append((rhs, clock is not None and len(rhs) == 1, lhs))
            else:
                raise Unsupported(f'{v} statement (only whole-signal assignments, if branches and direct entity instances are supported)')

    def condition(self, tokens):
        vs = [t.text for t in tokens]
        self.uses.append((tokens, False, tokens[0]))
        if len(vs) == 4 and vs[0] in ('rising_edge', 'falling_edge') and vs[1] == '(' and vs[3] == ')' and IDENT.fullmatch(vs[2]):
            return ('clock', (vs[0], vs[2]), True)
        if any(v in ('rising_edge', 'falling_edge', 'event') for v in vs):
            raise Unsupported('non-simple clock condition')
        if any(self.reset_re.search(v) for v in names(vs)):
            return ('reset', tuple(vs), True)
        return ('guard', tuple(vs), True)

    def if_branches(self, outer):
        prior = []
        while True:
            cond = self.condition(self.until('then'))
            self.statements(outer + tuple(prior) + (cond,), True)
            kind, expr, _ = cond
            prior.append(('clock_else' if kind == 'clock' else kind, expr, False))
            if self.v[self.i] == 'elsif':
                self.take()
                continue
            if self.v[self.i] == 'else':
                self.take()
                self.statements(outer + tuple(prior), True)
            break

    def instance(self, label):
        self.instance_tokens[label] = self.take('entity')
        header = self.until('port')
        header_values = [t.text for t in header]
        self.instance_types[label] = header_values[2] if len(header_values) >= 3 and header_values[1] == '.' else (header_values[0] if header_values else '')
        #  # generics are opaque; port actuals are checked below
        self.take('map')
        self.take('(')
        mappings = split_top(self.until(')'), ',')
        actuals = {}
        for group in mappings:
            vals = [t.text for t in group]
            if len(vals) < 3 or vals[1] != '=>' or not IDENT.fullmatch(vals[0]):
                raise Unsupported('positional/complex port association')
            actuals[vals[0]] = group[2:]
            self.uses.append((group[2:], False, group[0]))
        if label in self.instances:
            raise Unsupported('duplicate instance label')
        self.instances[label] = actuals
        self.take(';')

    def data_rows(self, signal):
        rows = self.assignments.get(signal, [])
        # Ignore only explicit constant reset writes, never arbitrary reset data.
        result = []
        for row in rows:
            vals = [t.text for t in row.rhs]
            constant = self.constant(row.rhs)
            if row.reset and constant:
                continue
            result.append(row)
        return result

    def registered(self, signal, seen=None):
        seen = set() if seen is None else set(seen)
        if signal in seen:
            return False
        seen.add(signal)
        rows = self.data_rows(signal)
        all_rows = self.assignments.get(signal, [])
        if not rows or len({r.owner for r in all_rows}) != 1:
            return False
        if all(r.clock is not None for r in rows) and len({r.clock for r in rows}) == 1:
            return True
        if len(rows) == 1 and len(all_rows) == 1 and rows[0].owner == -1 and self.wire(rows[0].rhs):
            return self.registered(self.wire(rows[0].rhs), seen)
        return False

    def chain(self, source, target):
        stages, seen, clock, guards = [], set(), None, None
        while target != source:
            if target in seen:
                raise Unsupported('feedback/cycle on configured pipeline path')
            seen.add(target)
            rows = self.data_rows(target)
            if not rows or len({r.owner for r in self.assignments.get(target, [])}) != 1:
                raise Unsupported(f'{target}: missing or multiple drivers')
            signatures = {(tuple(t.text for t in r.rhs), r.clock, r.guards) for r in rows}
            if len(signatures) != 1:
                raise Unsupported(f'{target}: alternate data/enable paths')
            rhs, row_clock, row_guards = next(iter(signatures))
            if row_clock is None and (rows[0].owner != -1 or len(rows) != 1):
                raise Unsupported(f'{target}: combinational process cannot be treated as a wire-only alias')
            if len(rhs) != 1 or not self.ident.fullmatch(rhs[0]):
                raise Unsupported(f'{target}: expression, slice or aggregate between pipeline stages')
            if row_clock is not None:
                if clock is not None and clock != row_clock:
                    raise Unsupported('mixed clock names or edges on configured pipeline path')
                if guards is not None and guards != row_guards:
                    raise Unsupported('different enable conditions on configured pipeline stages')
                clock, guards = row_clock, row_guards
                stages.append(target)
            target = rhs[0]
        return list(reversed(stages)), clock


def entity_ports(tokens):
    """Find entity declarations and their simple port names in the same file."""
    from rtl_lint import pairs
    result = {}
    vs = [t.text for t in tokens]
    ps = pairs(tokens)
    for i in range(len(tokens)-2):
        if vs[i] != 'entity' or vs[i+2] != 'is':
            continue
        end = next((j for j in range(i+3, len(tokens)) if vs[j] == 'end'), len(tokens))
        port_at = next((j for j in range(i+3, end-1) if vs[j:j+2] == ['port', '(']), None)
        if port_at is None or port_at+1 not in ps:
            continue
        ports = {}
        for group in split_top(tokens[port_at+2:ps[port_at+1]], ';'):
            vals = [t.text for t in group]
            if ':' not in vals:
                continue
            colon = vals.index(':')
            if colon+1 >= len(vals):
                continue
            mode = vals[colon+1] if vals[colon+1] in ('in', 'out', 'buffer', 'inout') else 'in'
            for tok in group[:colon]:
                if IDENT.fullmatch(tok.text) and tok.text != 'signal':
                    ports[tok.text] = (mode, tok)
        result[vs[i+1]] = ports
    return result


def policy_matches(policy, filename, entity):
    return fnmatch.fnmatchcase(entity, policy['entity'].lower()) and fnmatch.fnmatchcase(str(filename).replace('\\', '/'), policy.get('file', '*'))


def check(tokens, filename, config, emit, coverage):
    policies = config.get('module_policies', [])
    if not policies:
        return
    ports_by_entity = entity_ports(tokens)
    vs = [t.text for t in tokens]
    starts = [i for i in range(len(tokens)-3) if vs[i] == 'architecture' and vs[i+2] == 'of']
    for lo, hi in zip(starts, starts[1:] + [len(tokens)]):
        entity = vs[lo+3]
        selected = [p for p in policies if policy_matches(p, filename, entity)]
        if not selected:
            continue
        anchor = tokens[lo]
        try:
            model = Model(tokens[lo:hi], config['reset_pattern'])
        except (Unsupported, IndexError) as exc:
            emit('UF010', anchor, f'{entity}: module/pipeline policy could not be checked: {exc}.')
            continue
        ports = ports_by_entity.get(entity, {})
        for policy in selected:
            for field, mode, rule in [('registered_outputs', 'out', 'UF006'), ('registered_inputs', 'in', 'UF007')]:
                for pattern in policy.get(field, []):
                    matches = [n for n, (m, _) in ports.items() if m == mode and fnmatch.fnmatchcase(n, pattern.lower())]
                    if not matches:
                        emit('UF010', anchor, f'{entity}: {field} selector {pattern!r} matched no local {mode} port; entity declarations must be in the same file.')
                    for port in matches:
                        tok = ports[port][1]
                        if mode == 'out' and not model.registered(port):
                            emit(rule, tok, f'{entity}.{port}: no exclusive local clocked driver or wire-only alias to one was established; review output registration.')
                        if mode == 'in':
                            usages = [(ts, ok, where) for ts, ok, where in model.uses if any(t.text == port for t in ts)]
                            if not usages:
                                emit('UF010', tok, f'{entity}.{port}: selected input has no recognized use.')
                            for ts, ok, where in usages:
                                if not ok or [t.text for t in ts] != [port] or not model.registered(where.text):
                                    emit(rule, where, f'{entity}.{port}: raw input is used before a direct local register capture (logic, control, alias or child port connection).')
            for pipeline in policy.get('pipelines', []):
                source, target = pipeline['from'].lower(), pipeline['to'].lower()
                location = next((t for t in tokens[lo:hi] if t.text == target), anchor)
                known = model.signals | set(ports)
                if source not in known or target not in known:
                    emit('UF010', location, f'{entity}: pipeline endpoint {source} or {target} is not a declared local signal/port.')
                    continue
                try:
                    stages, clock = model.chain(source, target)
                except Unsupported as exc:
                    emit('UF008', location, f'{entity}: cannot establish pipeline {source} -> {target}: {exc}.')
                    continue
                coverage.append(f'{entity}: {source} -> {target}: {len(stages)} recognized stages [{", ".join(stages)}], clock {clock}; source structure only.')
                minimum = pipeline['min_stages']
                maximum = pipeline.get('max_stages')
                if len(stages) < minimum or (maximum is not None and len(stages) > maximum):
                    emit('UF008', location, f'{entity}: {source} -> {target} has {len(stages)} recognized register stages; required minimum {minimum}' + (f', maximum {maximum}.' if maximum is not None else '.'))
                if pipeline.get('clock') and (clock is None or clock[1] != pipeline['clock'].lower()):
                    emit('UF008', location, f'{entity}: pipeline clock does not match {pipeline["clock"]}.')
                if pipeline.get('placement', False):
                    for signal in stages:
                        if model.attrs.get((signal, 'shreg_extract')) != ['no']:
                            emit('UF009', model.assignments[signal][0].token, f'{entity}.{signal}: placement pipeline register needs an explicit local SHREG_EXTRACT = "no" signal attribute under this policy.')
                # Optional binding ensures the selected endpoint is actually wired
                # to the named wrapped core port, without inspecting core internals.
                if pipeline.get('core_port'):
                    instance, formal = pipeline['core_port'].lower().split('.')
                    actual = model.instances.get(instance, {}).get(formal, [])
                    expected = target if pipeline.get('side', 'input') == 'input' else source
                    if [t.text for t in actual] != [expected]:
                        emit('UF010', location, f'{entity}: expected {instance}.{formal} to connect directly to {expected}; binding missing or different.')
            coverage.append(f'{entity}: selected module/pipeline policies reviewed using a limited local source model; inferred hardware and latency under stalls are not verified.')


def validate(policies):
    if not isinstance(policies, list):
        raise ValueError('module_policies must be a list')
    for p in policies:
        if not isinstance(p, dict) or not isinstance(p.get('entity'), str) or not p['entity']:
            raise ValueError('Each module policy needs an entity name or glob')
        if set(p) - {'entity', 'file', 'registered_inputs', 'registered_outputs', 'pipelines'}:
            raise ValueError('Unknown module policy field')
        if not isinstance(p.get('file', '*'), str):
            raise ValueError('Module policy file must be a glob string')
        for field in ('registered_inputs', 'registered_outputs'):
            if not isinstance(p.get(field, []), list) or any(not isinstance(x, str) or not x for x in p.get(field, [])):
                raise ValueError(field + ' must contain port names/globs')
        if not isinstance(p.get('pipelines', []), list):
            raise ValueError('pipelines must be a list')
        for pipe in p.get('pipelines', []):
            if not isinstance(pipe, dict) or set(pipe) - {'from', 'to', 'min_stages', 'max_stages', 'placement', 'clock', 'core_port', 'side'}:
                raise ValueError('Invalid pipeline fields')
            for field in ('from', 'to'):
                if not isinstance(pipe.get(field), str) or not POLICY_IDENT.fullmatch(pipe[field]):
                    raise ValueError('Pipeline endpoints must be simple signal names')
            if pipe['from'] == pipe['to']:
                raise ValueError('Pipeline endpoints must be distinct')
            if type(pipe.get('min_stages')) is not int or pipe['min_stages'] < 1:
                raise ValueError('min_stages must be a positive integer')
            if 'max_stages' in pipe and (type(pipe['max_stages']) is not int or pipe['max_stages'] < pipe['min_stages']):
                raise ValueError('max_stages must be an integer >= min_stages')
            if type(pipe.get('placement', False)) is not bool:
                raise ValueError('placement must be true or false')
            if 'clock' in pipe and (not isinstance(pipe['clock'], str) or not POLICY_IDENT.fullmatch(pipe['clock'])):
                raise ValueError('clock must be a simple signal name')
            if pipe.get('side', 'input') not in ('input', 'output'):
                raise ValueError('side must be input or output')
            if 'core_port' in pipe and (not isinstance(pipe['core_port'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*', pipe['core_port'])):
                raise ValueError('core_port must be instance.port')
