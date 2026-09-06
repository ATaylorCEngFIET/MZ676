"""Run: python host/gui.py [--demo]. UART hardware control with a Tkinter front end."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import json
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from protocol import Device, PreviewDevice, Settings, MODES, NOTES, ERRORS


class App:
    def __init__(self, root, demo=False):
        self.root, self.demo = root, demo
        self.device = PreviewDevice() if demo else None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='uart')
        self.results = queue.Queue()
        self.busy = False
        self.foreground_busy = False
        self.pending_job = None
        self.closed = False
        self.last_snapshot = None
        self.active_settings = None
        self.root.title('MicroZed Chronicles | Spartan-7 Debug Laboratory')
        self.root.geometry('940x760')
        self.root.minsize(840, 690)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('Title.TLabel', font=('Segoe UI', 19, 'bold'))
        style.configure('TLabel', font=('Segoe UI', 10))
        style.configure('TButton', padding=7)
        outer = ttk.Frame(root, padding=22)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Spartan-7 Debug Laboratory', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Six selectable RTL faults · VHDL · ILA + System ILA').pack(anchor='w', pady=(3, 15))
        self.banner = tk.StringVar(value='PREVIEW — illustrative data, no FPGA connection' if demo else 'Disconnected — select the FPGA UART COM port')
        ttk.Label(outer, textvariable=self.banner, foreground='#9b5200' if demo else '#174d74').pack(anchor='w', pady=(0, 10))
        connection = ttk.Frame(outer)
        connection.pack(fill='x')
        self.port = tk.StringVar()
        self.ports = ttk.Combobox(connection, textvariable=self.port, width=22)
        self.ports.pack(side='left')
        ttk.Button(connection, text='Refresh ports', command=self.refresh_ports).pack(side='left', padx=6)
        self.connect_button = ttk.Button(connection, text='Disconnect' if demo else 'Connect', command=self.connect)
        self.connect_button.pack(side='left')
        self.poll_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(connection, text='Auto-read status', variable=self.poll_enabled).pack(side='right')
        self.refresh_ports()
        settings = ttk.LabelFrame(outer, text='Experiment', padding=14)
        settings.pack(fill='x', pady=14)
        self.mode = tk.StringVar(value=MODES[0])
        choice = ttk.Combobox(settings, textvariable=self.mode, values=MODES, state='readonly', width=45)
        choice.grid(row=0, column=0, columnspan=4, sticky='ew', pady=(0, 10))
        choice.bind('<<ComboboxSelected>>', self.mode_changed)
        self.fields = {}
        for i, (key, label, value) in enumerate((('packet_words','Words per packet',16), ('stall_cycles','Stall cycles',48),
                ('stall_period','Stall period',64), ('rare_packet','Rare packet (zero-based)',10000), ('axi_skew','AXI skew (cycles)',16))):
            row, col = 1 + i // 3, (i % 3) * 2
            ttk.Label(settings, text=label).grid(row=row, column=col, sticky='w', padx=(0, 6), pady=5)
            var = tk.StringVar(value=str(value))
            ttk.Entry(settings, textvariable=var, width=10).grid(row=row, column=col+1, sticky='w', padx=(0, 15))
            self.fields[key] = var
        self.note = tk.StringVar(value=NOTES[0])
        ttk.Label(settings, textvariable=self.note, wraplength=830).grid(row=3, column=0, columnspan=6, sticky='w', pady=(12, 0))
        actions = ttk.Frame(outer)
        actions.pack(fill='x')
        self.action_buttons = []
        for label, command in (('Apply + restart', self.start), ('Stop', lambda: self.action('stop')),
                               ('Clear + stop', lambda: self.action('clear')), ('Read status', self.poll)):
            button = ttk.Button(actions, text=label, command=command)
            button.pack(side='left', padx=(0, 7))
            self.action_buttons.append(button)
        ttk.Button(actions, text='Export snapshot', command=self.export).pack(side='right')
        ttk.Label(outer, text='UART controls the experiment. Arm and view captures separately in Vivado: Clear + stop → arm ILA → Apply + restart.', wraplength=850).pack(anchor='w', pady=(8, 12))
        self.status = tk.StringVar(value='No experiment data yet')
        ttk.Label(outer, textvariable=self.status, font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        self.error_text = tk.StringVar(value='No errors recorded')
        ttk.Label(outer, textvariable=self.error_text, wraplength=850).pack(anchor='w', pady=7)
        self.table = ttk.Treeview(outer, columns=('value',), show='tree headings', height=9)
        self.table.heading('#0', text='Measurement'); self.table.heading('value', text='Captured value')
        self.table.column('#0', width=370); self.table.column('value', width=370)
        self.table.pack(fill='both', expand=True)
        for key, label in (('words','Accepted stream words'), ('packets','Checked packets'), ('axi_completed','AXI completed writes'),
                ('cdc','CDC events sent / received'), ('first_packet','First error: packet'), ('first_cycle','First error: cycle'),
                ('first_expected','First error: expected stream word'), ('first_actual','First error: observed stream word'), ('cycles','Experiment cycles')):
            self.table.insert('', 'end', iid=key, text=label, values=('—',))
        ttk.Label(outer, text='First-error stream fields are meaningful for data/TLAST faults; use ILA probes for AXI, CDC and occupancy causes.', wraplength=860).pack(anchor='w', pady=(8,0))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(50, self.drain)
        self.root.after(500, self.auto_poll)
        self.set_busy(False)

    def refresh_ports(self):
        try:
            from serial.tools import list_ports
            ports = [p.device for p in list_ports.comports()]
        except ImportError:
            ports = []
        self.ports['values'] = ports
        if ports and not self.port.get(): self.port.set(ports[0])

    def set_busy(self, busy, *, foreground=None):
        self.busy = busy
        if foreground is not None:
            self.foreground_busy = foreground
        # Background reads must not flash controls or discard a user's click.
        for button in self.action_buttons:
            disabled = self.foreground_busy or self.device is None
            if button.instate(['disabled']) != disabled:
                button.state(['disabled'] if disabled else ['!disabled'])
        if self.connect_button.instate(['disabled']) != self.foreground_busy:
            self.connect_button.state(['disabled'] if self.foreground_busy else ['!disabled'])

    def submit(self, job, callback, *, background=False):
        if self.closed or self.foreground_busy:
            return False
        if self.busy:
            if background:
                return False
            # Keep one foreground command until the read has succeeded. Do not
            # queue it directly on the worker: a failed read must cancel it.
            self.pending_job = (job, callback)
            self.set_busy(True, foreground=True)
        else:
            self.dispatch(job, callback, background=background)
        return True

    def dispatch(self, job, callback, *, background=False):
        self.set_busy(True, foreground=not background)
        future = self.executor.submit(job)
        future.add_done_callback(lambda f: self.results.put((f, callback)))

    def drain(self):
        if self.closed: return
        try:
            future, callback = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            try:
                callback(future.result())
            except Exception as exc:
                self.pending_job = None
                self.banner.set(f'Connection / operation error: {exc}')
                device, self.device = self.device, None
                if device: self.executor.submit(device.close)
                self.connect_button['text'] = 'Connect'
                self.set_busy(False, foreground=False)
                messagebox.showerror('Debug laboratory', str(exc), parent=self.root)
            else:
                if self.pending_job is not None:
                    job, callback = self.pending_job
                    self.pending_job = None
                    self.dispatch(job, callback)
                else:
                    self.set_busy(False, foreground=False)
        self.root.after(50, self.drain)

    def connect(self):
        if self.device:
            device = self.device
            def disconnected(_):
                self.device = None
                self.connect_button['text'] = 'Connect'
                self.banner.set('Disconnected')
            self.submit(device.close, disconnected)
        else:
            port = self.port.get().strip()
            if not self.demo and not port:
                messagebox.showerror('UART port', 'Select or type a COM port.', parent=self.root)
                return
            def connected(device):
                self.device = device
                self.connect_button['text'] = 'Disconnect'
                self.banner.set('PREVIEW — illustrative data, no FPGA connection' if self.demo else f'Connected to {port} · 115200 baud · FPGA identity verified')
            self.submit(lambda: PreviewDevice() if self.demo else Device(port), connected)

    def mode_changed(self, _=None):
        self.note.set(NOTES[MODES.index(self.mode.get())])

    def start(self):
        if self.device is None or self.foreground_busy: return
        try:
            settings = Settings(mode=MODES.index(self.mode.get()), **{k:int(v.get(), 0) for k,v in self.fields.items()}).validate()
        except ValueError as exc:
            messagebox.showerror('Experiment settings', str(exc), parent=self.root)
            return
        device = self.device
        def started(result):
            self.active_settings = asdict(settings)
            self.show_snapshot(result)
        self.submit(lambda: device.start(settings), started)

    def action(self, name):
        if self.device: self.submit(getattr(self.device, name), self.show_snapshot)

    def poll(self, *, background=False):
        if self.device: self.submit(self.device.snapshot, self.show_snapshot, background=background)

    def auto_poll(self):
        if self.closed: return
        if self.poll_enabled.get() and not self.busy and self.device: self.poll(background=True)
        self.root.after(700, self.auto_poll)

    def show_snapshot(self, state):
        self.last_snapshot = state
        mode = state['active_mode']
        mode_name = MODES[mode] if 0 <= mode < len(MODES) else f'Unknown mode {mode}'
        status = f'{"Running" if state["status"] & 1 else "Stopped"} · {mode_name}'
        if self.status.get() != status: self.status.set(status)
        errors = [label for i,label in enumerate(ERRORS) if state['errors'] & (1 << i)]
        error_text = ' | '.join(errors) if errors else 'No errors recorded'
        if self.error_text.get() != error_text: self.error_text.set(error_text)
        for key in self.table.get_children():
            if key == 'cdc': value = f'{state["cdc_sent"]} / {state["cdc_received"]}'
            elif key.startswith('first_') and not state['errors']: value = '—'
            elif key in ('first_expected','first_actual'): value = f'0x{state[key]:08X}'
            else: value = f'{state[key]:,}'
            if self.table.set(key, 'value') != value:
                self.table.set(key, 'value', value)

    def export(self):
        if self.last_snapshot is None:
            messagebox.showinfo('Export', 'Read an experiment snapshot first.', parent=self.root)
            return
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON','*.json')], parent=self.root)
        if path:
            payload = {'captured_utc':datetime.now(timezone.utc).isoformat(), 'source':'illustrative preview' if self.demo else 'FPGA UART',
                       'settings_started_in_this_session':self.active_settings, 'snapshot':self.last_snapshot}
            try:
                with open(path, 'w', encoding='utf-8') as output: json.dump(payload, output, indent=2)
            except OSError as exc: messagebox.showerror('Export failed', str(exc), parent=self.root)

    def close(self):
        self.closed = True
        self.pending_job = None
        if self.device: self.executor.submit(self.device.close)
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='Illustrative preview without hardware; not RTL simulation')
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = tk.Tk()
    app = App(root, demo=args.demo)
    if args.smoke_test:
        root.after(100, app.start)
        root.after(1500, app.close)
    root.mainloop()

if __name__ == '__main__': main()
