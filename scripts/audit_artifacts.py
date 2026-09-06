"""Audit generated bitstreams, LTX interface maps and routed timing reports."""
import argparse
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--board', choices=('arty_s7_50','sp701'), help='Audit one board instead of both')
args = parser.parse_args()
manifest = {}
for board, part in [('arty_s7_50','7s50csga324'), ('sp701','7s100fgga676')]:
    if args.board and board != args.board:
        continue
    folder = root/'build'/f'ipi_{board}'
    bd = json.loads((folder/'debug_lab.srcs/sources_1/bd/debug_system/debug_system.bd').read_text())['design']
    for cell, ip in {'clocks':'clk_wiz', 'reset_controller':'proc_sys_reset', 'uart':'axi_uartlite',
                     'stream_fifo':'axis_data_fifo', 'system_ila':'system_ila', 'ila_fast':'ila',
                     'ila_slow':'ila', 'heartbeat':'c_counter_binary'}.items():
        assert f':ip:{ip}:' in bd['components'][cell]['vlnv'], f'{board}: missing AMD {ip}'
    assert (folder/'debug_lab.gen/sources_1/bd/debug_system/hdl/debug_system_wrapper.vhd').exists()
    assert all(p.suffix == '.vhd' for directory in ('rtl','sim') for p in (root/directory).iterdir() if p.is_file())
    bit = folder/'debug_lab.bit'
    ltx = folder/'debug_lab.ltx'
    assert part.encode() in bit.read_bytes()[:512], f'{board}: bitstream part mismatch'
    data = json.loads(ltx.read_text())
    cores = [c for entry in data['ltx_root']['ltx_data'] for c in entry.get('debug_cores',[])]
    fast = next(c for c in cores if c['name'].endswith('/ila_fast'))
    slow = next(c for c in cores if c['name'].endswith('/ila_slow'))
    system = next(c for c in cores if 'system_ila' in c['name'])
    assert len(fast['pins']) == 6
    assert all(abs(p['leftIndex']-p['rightIndex'])+1 == 32 for p in fast['pins'])
    assert abs(slow['pins'][0]['leftIndex']-slow['pins'][0]['rightIndex'])+1 == 64
    interfaces = {b['name']:b for b in system['bus_interfaces']}
    pins = {p['id']:p for p in system['pins']}
    assert set(interfaces) == {'SLOT_0_AXIS','SLOT_1_AXIS','SLOT_2_AXI'}
    for name, bus in interfaces.items():
        mappings = {p['logical_port']:p['physical_pin'] for p in bus['port_maps']}
        required = {'TDATA','TVALID','TREADY','TLAST'} if name.endswith('AXIS') else {
            'AWADDR','AWPROT','AWVALID','AWREADY','WDATA','WSTRB','WVALID','WREADY','BRESP','BVALID','BREADY',
            'ARADDR','ARPROT','ARVALID','ARREADY','RDATA','RRESP','RVALID','RREADY'}
        assert required <= mappings.keys(), f'{board}: missing interface signals'
        for signal, mapping in mappings.items():
            assert mapping['id'] in pins
            width = abs(pins[mapping['id']]['leftIndex']-pins[mapping['id']]['rightIndex'])+1
            assert mapping['leftBit']+mapping['width'] <= width
        assert mappings['TDATA' if name.endswith('AXIS') else 'WDATA']['width'] == 32
    assert interfaces['SLOT_2_AXI']['protocol'] == 'AXI4LITE'
    timing = (folder/'debug_lab.runs/impl_1/debug_system_wrapper_timing_summary_routed.rpt').read_text()
    assert 'All user specified timing constraints are met.' in timing
    assert 'unconstrained_internal_endpoints (0)' in timing
    skew = (folder/'bus_skew.rpt').read_text()
    assert 'VIOLATED' not in skew and 'Slack (MET)' in skew
    clocks = (folder/'debug_clocks.rpt').read_text()
    for pin, period in {'dbg_hub/clk':20.0, 'debug_system_i/ila_fast/clk':20.0,
                        'debug_system_i/ila_slow/clk':80.0}.items():
        match = re.search(r'^' + re.escape(pin) + r' period_ns=([0-9.]+)', clocks, re.M)
        assert match and abs(float(match[1])-period) < 0.01, f'{board}: wrong debug clock: {pin}'
    manifest[board] = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (bit,ltx)}
    print(f'PASS {board}: AMD IP block design, VHDL sources/wrapper, part, 3 ILAs, complete interface maps, timing, bus skew and debug clocks')
(root/'build'/('artifact_sha256_'+args.board+'.json' if args.board else 'artifact_sha256.json')).write_text(json.dumps(manifest,indent=2),encoding='utf-8')
