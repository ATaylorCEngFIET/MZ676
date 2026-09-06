"""Conservative Verilog/SystemVerilog source parser; no preprocessing or elaboration.

Supports ordinary module RTL. Unsupported structural constructs invalidate the
module inventory explicitly; they never silently disappear from a passing model.
"""
from collections import defaultdict
from dataclasses import dataclass
import fnmatch
import re
from boundary_lint import Model, Assignment, Unsupported
import architecture_lint

IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*\Z')
LEX = re.compile(r'//[^\n]*|/\*.*?(?:\*/|\Z)|"(?:\\.|[^"\\])*"|`[^\n]*|'
                 r"\\[^\s]+|(?:\d[\d_]*)?'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|'[01xXzZ]|"
                 r'\d[\d_]*(?:\.\d[\d_]*)?|[A-Za-z_$][A-Za-z0-9_$]*|'
                 r'===|!==|<<<|>>>|<=|>=|==|!=|&&|\|\||<<|>>|\*\*|\+\+|--|::|\+=|-=|\S', re.S)
TYPES = {'wire','reg','logic','bit','tri','signed','unsigned','integer','int','longint','shortint','byte','var'}
DIRECTIONS = {'input':'in','output':'out','inout':'inout'}

@dataclass
class Token:
    text: str
    offset: int


def lex(source):
    return [Token(m.group(),m.start()) for m in LEX.finditer(source)
            if not m.group().startswith(('//','/*'))]


def split(tokens, separator=','):
    groups, start, stack = [], 0, []
    for i,t in enumerate(tokens):
        if t.text in ('(','[','{'): stack.append(t.text)
        elif t.text in (')',']','}'):
            if not stack: raise Unsupported('unbalanced delimiter')
            stack.pop()
        elif t.text == separator and not stack:
            groups.append(tokens[start:i]); start=i+1
    if stack: raise Unsupported('unbalanced delimiter')
    groups.append(tokens[start:])
    return groups


class Cursor:
    def __init__(self,tokens): self.ts=tokens; self.i=0
    def peek(self): return self.ts[self.i].text if self.i<len(self.ts) else ''
    def take(self,expected=None):
        if not self.peek(): raise Unsupported('unexpected end of module')
        tok=self.ts[self.i]
        if expected is not None and tok.text!=expected:
            raise Unsupported(f'expected {expected}, found {tok.text}')
        self.i+=1
        return tok
    def group(self,opening='(',closing=')'):
        self.take(opening); start=self.i; depth=1
        while self.peek():
            tok=self.take()
            if tok.text==opening: depth+=1
            if tok.text==closing: depth-=1
            if depth==0: return self.ts[start:self.i-1]
        raise Unsupported(f'missing {closing}')
    def until(self,end=';'):
        start=self.i; stack=[]
        pairs={')':'(',']':'[','}':'{'}
        while self.peek():
            t=self.peek()
            if t==end and not stack:
                out=self.ts[start:self.i]; self.take(); return out
            if t in ('(','[','{'): stack.append(t)
            elif t in pairs:
                if not stack or stack.pop()!=pairs[t]: raise Unsupported('unbalanced delimiter')
            self.take()
        raise Unsupported(f'missing {end}')


def strip_type(tokens):
    c=Cursor(tokens)
    while c.peek() in TYPES or c.peek()=='[':
        if c.peek()=='[': c.group('[',']')
        else: c.take()
    return c.ts[c.i:]


def declarations(tokens, inherited=None):
    """Return name tokens, direction, suffix; packed dimensions need no evaluation."""
    mode=inherited; result=[]
    for group in split(tokens):
        if not group: raise Unsupported('empty declaration')
        if group[0].text in DIRECTIONS:
            mode=DIRECTIONS[group[0].text]; group=group[1:]
        group=strip_type(group)
        if not group or not IDENT.fullmatch(group[0].text):
            raise Unsupported('typed/interface/structured declaration is not supported')
        result.append((group[0],mode,group[1:]))
    return result


def modules(source):
    tokens=lex(source)
    directives=[t for t in tokens if t.text.startswith('`')]
    unsafe=[t for t in directives if t.text.split()[0] not in ('`timescale','`default_nettype','`resetall')]
    tokens=[t for t in tokens if t not in directives]
    units=[]; i=0
    while i<len(tokens):
        if tokens[i].text!='module': i+=1; continue
        lo=i
        end=next((j for j in range(i+1,len(tokens)) if tokens[j].text=='endmodule'),len(tokens))
        chunk=tokens[lo:end]; c=Cursor(chunk); anchor=c.take('module')
        unit={'name':'(unnamed)', 'anchor':anchor, 'ports':{}, 'params':set(), 'body':[], 'error':None}
        try:
            if c.peek() in ('automatic','static'): c.take()
            name=c.take()
            if not IDENT.fullmatch(name.text): raise Unsupported('escaped or missing module name')
            unit['name']=name.text
            if c.peek()=='#':
                c.take(); params=c.group()
                for g in split(params):
                    if g and g[0].text in ('parameter','localparam'): g=g[1:]
                    for tok,_,suffix in declarations(g): unit['params'].add(tok.text)
            if c.peek()=='(':
                ports=c.group()
                if ports:
                    ansi=any(t.text in DIRECTIONS for t in ports)
                    for tok,mode,suffix in declarations(ports):
                        if suffix: raise Unsupported('unpacked, defaulted or interface port declaration')
                        if ansi and mode is None: raise Unsupported('missing ANSI port direction')
                        if tok.text in unit['ports']: raise Unsupported('duplicate port name')
                        unit['ports'][tok.text]=(mode,tok)
            c.take(';'); unit['body']=chunk[c.i:]
            # Non-ANSI directions are supplied by declarations in the module body.
            bc=Cursor(unit['body'])
            while bc.peek():
                if bc.peek() in DIRECTIONS:
                    for tok,mode,suffix in declarations(bc.until()):
                        if tok.text not in unit['ports']: raise Unsupported('port declaration absent from module header')
                        if suffix: raise Unsupported('unpacked/defaulted port declaration')
                        unit['ports'][tok.text]=(mode,tok)
                else: bc.take()
            if any(mode is None for mode,_ in unit['ports'].values()): raise Unsupported('unresolved non-ANSI port direction')
            if end==len(tokens): raise Unsupported('missing endmodule')
            if unsafe: raise Unsupported('preprocessor macros/includes/conditionals are not expanded; compilation configuration is unknown')
        except Unsupported as exc: unit['error']=str(exc)
        units.append(unit); i=end+1
    return units, unsafe


def wire(tokens):
    return tokens[0].text if len(tokens)==1 and IDENT.fullmatch(tokens[0].text) else None


class VerilogModel(Model):
    ident=IDENT
    wire=staticmethod(wire)

    def __init__(self,unit,reset_pattern):
        if unit['error']: raise Unsupported(unit['error'])
        self.unit=unit; self.c=Cursor(unit['body']); self.reset_re=re.compile(reset_pattern)
        self.assignments=defaultdict(list); self.uses=[]; self.attrs=defaultdict(list)
        self.signals=set(unit['ports']); self.parameters=set(unit['params']); self.memories=set()
        self.instances={}; self.instance_types={}; self.instance_tokens={}; self.owner=0
        self.emit=unit['emit']; self.clock=None; self.async_names=set(); self.saw_async_reset=set()
        self.pending_attrs={}; self.clock_tokens={}
        self.body()
        known=self.signals | self.parameters
        for rows in self.assignments.values():
            for row in rows:
                if row.token.text not in self.signals: raise Unsupported(f'undeclared assignment target {row.token.text}')
                unresolved=[t.text for t in row.rhs if IDENT.fullmatch(t.text) and t.text not in known]
                if unresolved: raise Unsupported('unresolved expression names: '+', '.join(sorted(set(unresolved))))
        for expression, _, _ in self.uses:
            vals=[t.text for t in expression]
            if any(v in ('.','::') or v.startswith('$') for v in vals):
                raise Unsupported('hierarchical/scoped/system-function expression is not traced')
            if any(IDENT.fullmatch(vals[i]) and vals[i+1]=='(' for i in range(len(vals)-1)):
                raise Unsupported('function call in a condition/connection is not traced')
            unresolved=[v for v in vals if IDENT.fullmatch(v) and v not in known]
            if unresolved:
                raise Unsupported('unresolved condition/connection names: '+', '.join(sorted(set(unresolved))))
        for clock,tok in self.clock_tokens.items():
            for row in self.assignments.get(clock,[]):
                if any(t.text in ('&','|','^','~','!','?','&&','||','+','-') for t in row.rhs):
                    self.emit('UF003',row.token,f'{unit["name"]}.{clock}: clock is driven by combinational logic; review a clock enable or dedicated clock buffer.')

    def registered(self,signal,seen=None):
        if signal in getattr(self,'external_drivers',set()): return False
        return super().registered(signal,seen)

    def chain(self,source,target):
        stages,clock=super().chain(source,target)
        if any(s in getattr(self,'external_drivers',set()) for s in stages):
            raise Unsupported('pipeline stage is also driven by a known child output')
        return stages,clock

    def constant(self,tokens):
        return bool(tokens) and all(not IDENT.fullmatch(t.text) or t.text in self.parameters for t in tokens)

    def attributes(self):
        c=self.c; c.take('('); c.take('*'); items=[]
        while c.peek() and not (c.peek()=='*' and c.i+1<len(c.ts) and c.ts[c.i+1].text==')'):
            items.append(c.take())
        c.take('*'); c.take(')')
        for group in split(items):
            if len(group)==3 and group[1].text=='=':
                self.pending_attrs[group[0].text.lower()]=group[2].text.strip('"').lower()

    def body(self):
        c=self.c
        while c.peek():
            v=c.peek()
            if v=='(' and c.i+1<len(c.ts) and c.ts[c.i+1].text=='*': self.attributes(); continue
            attrs=self.pending_attrs; self.pending_attrs={}
            if v in TYPES or v in DIRECTIONS:
                is_net=v in ('wire','tri')
                for tok,mode,suffix in declarations(c.until()):
                    self.signals.add(tok.text)
                    for attr,value in attrs.items(): self.attrs[(tok.text,attr)].append(value)
                    if suffix and suffix[0].text=='[':
                        self.memories.add(tok.text)
                        dim=Cursor(suffix)
                        while dim.peek()=='[': dim.group('[',']')
                        suffix=dim.ts[dim.i:]
                    if suffix:
                        if suffix[0].text!='=': raise Unsupported('unsupported declaration suffix')
                        if is_net: self.assign(tok,suffix[1:],(),False,-1,False)
                        elif not self.constant(suffix[1:]): raise Unsupported('nonconstant variable initializer')
            elif v in ('parameter','localparam'):
                c.take()
                for tok,_,suffix in declarations(c.until()):
                    if not suffix or suffix[0].text!='=': raise Unsupported('parameter without value')
                    self.parameters.add(tok.text)
            elif v=='assign':
                c.take()
                for expr in split(c.until()): self.assignment(expr,(),False,-1)
            elif v in ('always','always_ff','always_comb','always_latch'):
                kind=c.take().text; self.owner+=1; self.clock=None; self.async_names=set(); self.saw_async_reset=set()
                if kind in ('always','always_ff'):
                    c.take('@')
                    event=[c.take()] if c.peek()=='*' else c.group()
                    parts=[]
                    for group in split(event): parts.extend(split(group,'or'))
                    edges=[]
                    for part in parts:
                        if part and part[0].text in ('posedge','negedge'):
                            if len(part)!=2 or not IDENT.fullmatch(part[1].text):
                                self.emit('UF003',part[0],f'{self.unit["name"]}: clock/event expression requires review.')
                                raise Unsupported('complex edge expression')
                            edges.append((part[0].text,part[1].text,part[1]))
                        elif any(t.text in ('posedge','negedge') for t in part): raise Unsupported('complex event control')
                    if edges:
                        if len(edges)!=len(parts): raise Unsupported('mixed edge and level event control')
                        clocks=[e for e in edges if not self.reset_re.search(e[1])]
                        if len(clocks)!=1: raise Unsupported('multiple clocks or ambiguous reset/clock event names')
                        edge,name,tok=clocks[0]; self.clock=(edge,name); self.clock_tokens[name]=tok
                        self.async_names={e[1] for e in edges if e[1]!=name}
                        self.async_levels={e[1]:int(e[0]=='posedge') for e in edges if e[1]!=name}
                    elif kind=='always_ff': raise Unsupported('always_ff without a recognized edge')
                self.statement((),False)
                if self.async_names - self.saw_async_reset: raise Unsupported('async event without a recognized reset branch')
                self.clock=None; self.async_names=set()
            elif v==';': c.take()
            elif IDENT.fullmatch(v) and v not in {'generate','endgenerate','for','if','function','task','initial','typedef','import','export','genvar','assert','class','interface','final','specify'}:
                self.instance()
            else:
                raise Unsupported(f'{v}: unsupported module construct (generate/loops/functions/interfaces are not expanded)')

    def reset_condition(self,condition):
        vals=[t.text for t in condition]
        # Recognize only simple reset tests, never arbitrary reset/data expressions.
        names=[v for v in vals if IDENT.fullmatch(v)]
        if len(names)!=1 or not self.reset_re.search(names[0]): return None
        rest=[v for v in vals if v!=names[0]]
        return names[0] if all(v.lower() in ('!','~','(',')','==','!=','===','!==','0','1',"1'b0","1'b1","'0","'1") for v in rest) else None

    def reset_branch_is_true(self,condition,name):
        level = (self.async_levels[name] if name in self.async_names else
                 int(not name.lower().endswith(('_n', 'rstn', 'resetn'))))
        values=[t.text for t in condition if t.text not in ('(',')')]
        def value(tokens):
            invert=False
            while tokens and tokens[0] in ('!','~'):
                invert=not invert; tokens=tokens[1:]
            if len(tokens)!=1: raise Unsupported('complex reset predicate')
            tok=tokens[0]
            result=level if tok==name else int(tok.lower() in ('1', "1'b1", "'1"))
            return int(not result) if invert else result
        operators=[i for i,v in enumerate(values) if v in ('==','!=','===','!==')]
        if not operators: return bool(value(values))
        if len(operators)!=1: raise Unsupported('complex reset comparison')
        i=operators[0]; equal=value(values[:i])==value(values[i+1:])
        return equal if values[i] in ('==','===') else not equal

    def statement(self,guards,reset):
        c=self.c; v=c.peek()
        if v=='begin':
            c.take()
            if c.peek()==':': c.take(); c.take()
            while c.peek() and c.peek()!='end': self.statement(guards,reset)
            c.take('end')
            if c.peek()==':': c.take(); c.take()
        elif v=='if':
            anchor=c.take(); condition=c.group(); is_reset=self.reset_condition(condition)
            self.uses.append((condition,False,anchor))
            if is_reset and self.clock and guards:
                self.emit('UF002',anchor,f'{self.unit["name"]}: reset-like condition is nested under another condition; review reset-over-enable precedence.')
            if is_reset and self.async_names:
                self.saw_async_reset.add(is_reset)
                self.emit('UF001',anchor,f'{self.unit["name"]}: clocked block has asynchronous reset control; review whether synchronous reset is suitable.')
            signature=tuple(t.text for t in condition)
            yes=guards if is_reset else guards+(('if',signature),)
            no=guards if is_reset else guards+(('else',signature),)
            true_is_reset=self.reset_branch_is_true(condition,is_reset) if is_reset else False
            self.statement(yes,reset or bool(is_reset and true_is_reset))
            if c.peek()=='else':
                c.take(); self.statement(no,reset or bool(is_reset and not true_is_reset))
        elif v in ('case','casez','casex'):
            c.take(); condition=c.group(); self.uses.append((condition,False,condition[0]))
            while c.peek() and c.peek()!='endcase':
                if c.peek()=='default':
                    label=[c.take()]
                    if c.peek()==':': c.take()
                else: label=c.until(':')
                signature=tuple(t.text for t in condition+label)
                self.statement(guards+(('case',signature),),reset)
            c.take('endcase')
        elif v in ('unique','unique0','priority'):
            c.take(); self.statement(guards,reset)
        elif v==';': c.take()
        elif v in ('for','while','repeat','foreach','do','fork','wait','@','#'):
            raise Unsupported(f'{v}: loops or timing controls are not expanded')
        else: self.assignment(c.until(),guards,reset,self.owner)

    def assignment(self,expr,guards,reset,owner):
        if not expr: raise Unsupported('empty assignment')
        lhs=expr[0]
        if not IDENT.fullmatch(lhs.text): raise Unsupported('concatenated/structured assignment target')
        c=Cursor(expr[1:]); indexed=False
        while c.peek()=='[': c.group('[',']'); indexed=True
        op=c.take().text
        if op not in ('=','<='): raise Unsupported('unsupported statement or assignment operator')
        rhs=c.ts[c.i:]
        if indexed:
            if lhs.text in self.memories and reset:
                self.emit('UF005',lhs,f'{self.unit["name"]}.{lhs.text}: memory element written under reset; review RAM inference and validity-based reset.')
            raise Unsupported('indexed/partial assignment target; whole-signal register inventory is unknown')
        if self.clock and op=='=': raise Unsupported('blocking assignment in edge-triggered block; pipeline order is not modeled')
        if owner==-1 and op!='=': raise Unsupported('continuous assignment must use =')
        self.assign(lhs,rhs,guards,reset,owner,op=='<=')

    def assign(self,lhs,rhs,guards,reset,owner,nonblocking):
        if not rhs: raise Unsupported('empty assignment expression')
        vals=[t.text for t in rhs]
        if any(v in ('#','@','++','--','::',"'") for v in vals): raise Unsupported('timed, scoped, cast or side-effecting expression')
        if any(IDENT.fullmatch(vals[i]) and vals[i+1]=='(' for i in range(len(vals)-1)) or any(v.startswith('$') for v in vals):
            raise Unsupported('function/system-function call is not traced')
        if self.async_names and reset and self.clock: clock=None
        else: clock=self.clock if owner!=-1 else None
        self.assignments[lhs.text].append(Assignment(lhs,rhs,clock,guards,reset,owner))
        self.uses.append((rhs,clock is not None,lhs))
        if self.async_names and '*' in vals:
            self.emit('UF004',lhs,f'{self.unit["name"]}.{lhs.text}: multiplication shares a block with asynchronous reset; review DSP register packing.')
        if lhs.text in self.memories and reset:
            self.emit('UF005',lhs,f'{self.unit["name"]}.{lhs.text}: memory contents written under reset; review RAM inference.')

    def instance(self):
        c=self.c; child=c.take().text
        if c.peek()=='#': c.take(); c.group()
        name=c.take()
        if not IDENT.fullmatch(name.text): raise Unsupported('unsupported instance declaration')
        actuals={}
        for group in split(c.group()):
            if not group: continue
            if len(group)<2 or group[0].text!='.' or not IDENT.fullmatch(group[1].text):
                raise Unsupported('positional/wildcard instance connections are not supported')
            formal=group[1].text; pc=Cursor(group[2:])
            actual=pc.group() if pc.peek()=='(' else [group[1]]
            if pc.peek(): raise Unsupported('unexpected instance connection tokens')
            if formal in actuals: raise Unsupported('duplicate named port connection')
            actuals[formal]=actual
            if actual: self.uses.append((actual,False,actual[0]))
        c.take(';')
        if name.text in self.instances: raise Unsupported('duplicate instance name')
        self.instances[name.text]=actuals; self.instance_types[name.text]=child; self.instance_tokens[name.text]=name


def policy_matches(policy,filename,module):
    return fnmatch.fnmatchcase(module,policy['entity']) and fnmatch.fnmatchcase(str(filename).replace('\\','/'),policy.get('file','*'))


def check_policies(unit,model,config,emit,coverage):
    for policy in config.get('module_policies',[]):
        if not policy_matches(policy,unit['file'],unit['name']): continue
        name=unit['name']; ports=unit['ports']; anchor=unit['anchor']
        if isinstance(model,Exception):
            emit('UF010',anchor,f'{name}: module policy could not be checked: {model}.'); continue
        for field,mode,rule in [('registered_inputs','in','UF007'),('registered_outputs','out','UF006')]:
            for pattern in policy.get(field,[]):
                matches=[p for p,(m,_) in ports.items() if m==mode and fnmatch.fnmatchcase(p,pattern)]
                if not matches: emit('UF010',anchor,f'{name}: {field} selector {pattern!r} matched no local port (Verilog names are case-sensitive).')
                for port in matches:
                    uses=[(ts,ok,t) for ts,ok,t in model.uses if any(v.text==port for v in ts)]
                    if mode=='out' and not model.registered(port): emit(rule,ports[port][1],f'{name}.{port}: required output registration was not established.')
                    if mode=='in':
                        if not uses: emit('UF010',ports[port][1],f'{name}.{port}: selected input has no recognized use.')
                        for ts,ok,t in uses:
                            if not ok or wire(ts)!=port or not model.registered(t.text):
                                emit(rule,t,f'{name}.{port}: required direct input capture has raw-input bypass or logic.')
        for pipeline in policy.get('pipelines',[]):
            source,target=pipeline['from'],pipeline['to']
            try:
                stages,clock=model.chain(source,target)
                if source not in model.signals or target not in model.signals: raise Unsupported('undeclared pipeline endpoint')
            except Unsupported as exc:
                emit('UF008',anchor,f'{name}: cannot establish pipeline {source} -> {target}: {exc}.'); continue
            if len(stages)<pipeline['min_stages'] or len(stages)>pipeline.get('max_stages',float('inf')):
                emit('UF008',anchor,f'{name}: {source} -> {target} has {len(stages)} stages; required minimum {pipeline["min_stages"]}, maximum {pipeline.get("max_stages","unspecified")}.')
            if pipeline.get('clock') and (not clock or clock[1]!=pipeline['clock']): emit('UF008',anchor,f'{name}: pipeline clock does not match {pipeline["clock"]}.')
            if pipeline.get('placement'):
                for s in stages:
                    if model.attrs.get((s,'shreg_extract'))!=['no']: emit('UF009',model.assignments[s][0].token,f'{name}.{s}: placement pipeline needs local SHREG_EXTRACT="no" under this policy.')
            if pipeline.get('core_port'):
                instance,formal=pipeline['core_port'].split('.')
                expected=target if pipeline.get('side','input')=='input' else source
                if wire(model.instances.get(instance,{}).get(formal,[]))!=expected:
                    emit('UF010',anchor,f'{name}: expected {instance}.{formal} to connect directly to {expected}.')
            coverage.append(f'{name}: {source} -> {target}: {len(stages)} source register stages; stalled-cycle latency not proven.')


def scan(source,filename,config,architecture_reports=None):
    from recommendations import GUIDANCE
    findings=[]; coverage=[]; lines=source.splitlines()
    def emit(rule,tok,message):
        if rule in config.get('disabled_rules',[]): return
        line=source.count('\n',0,tok.offset)+1
        item={'rule':rule,'severity':'warning','file':str(filename),'line':line,
              'column':tok.offset-source.rfind('\n',0,tok.offset), 'message':message,
              'reference':GUIDANCE[rule]['url'], 'language':'SystemVerilog' if str(filename).lower().endswith('.sv') else 'Verilog',
              'source_excerpt':[{'line':i+1,'text':lines[i]} for i in range(max(0,line-3),min(len(lines),line+2))]}
        for waiver in config.get('waivers',[]):
            if waiver['rule']==rule and fnmatch.fnmatch(str(filename).replace('\\','/'),waiver['file']) and waiver.get('line',line)==line:
                item['waived']=waiver['reason']
        if item not in findings: findings.append(item)
    units,unsafe=modules(source)
    duplicate={u['name'] for u in units if sum(v['name']==u['name'] for v in units)>1}
    declarations_by_name={u['name']:u['ports'] for u in units if not u['error'] and u['name'] not in duplicate}
    payload=[]
    for unit in units:
        unit['emit']=emit; unit['file']=str(filename)
        if unit['name'] in duplicate: unit['error']='duplicate module definitions; configuration is unknown'
        try: model=VerilogModel(unit,config['reset_pattern'])
        except (Unsupported,IndexError) as exc: model=Unsupported(str(exc))
        if not isinstance(model,Exception):
            model.external_drivers=set()
            for instance,actuals in model.instances.items():
                child_ports=declarations_by_name.get(model.instance_types[instance],{})
                for formal,actual in actuals.items():
                    if child_ports.get(formal,(None,))[0] in ('out','inout') and wire(actual):
                        model.external_drivers.add(wire(actual))
        unit['model']=model
        payload.append((unit['name'],'module',unit['anchor'],unit['ports'],unit))
        check_policies(unit,model,config,emit,coverage)
        if isinstance(model,Exception) and not config.get('automatic_architecture',True):
            emit('UF010',unit['anchor'],f'{unit["name"]}: source checks incomplete: {model}.')
    def factory(unit,reset_pattern):
        if isinstance(unit['model'],Exception): raise unit['model']
        return unit['model']
    reports=architecture_lint.review_units(payload,declarations_by_name,factory,filename,config,emit,coverage)
    for report in reports: report['language']='SystemVerilog' if str(filename).lower().endswith('.sv') else 'Verilog'
    if architecture_reports is not None: architecture_reports.extend(reports)
    if not units: coverage.append('No module declaration found; module architecture checks were not applied.')
    if unsafe: coverage.append('Preprocessor directives/macros/includes are not expanded. Affected module results are unknown; headers are not standalone lint targets.')
    coverage.append('Verilog/SystemVerilog source subset only: no preprocessing, hierarchy elaboration, width/type validation, generated-instance expansion or syntax sign-off.')
    return findings,sorted(set(coverage))
