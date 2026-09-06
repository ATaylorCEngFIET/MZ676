"""Regression tests for background polling and foreground command ordering."""
from concurrent.futures import Future
import tkinter as tk
import unittest
from unittest.mock import patch
from gui import App


class ManualExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, job):
        future = Future()
        self.jobs.append((job, future))
        return future

    def finish(self, error=None):
        job, future = self.jobs.pop(0)
        if error:
            future.set_exception(error)
        else:
            future.set_result(job())

    def shutdown(self, **kwargs):
        pass


class PollingTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        with patch.object(App, 'refresh_ports'):
            self.app = App(self.root, demo=True)
        self.app.executor.shutdown(wait=True)
        self.worker = self.app.executor = ManualExecutor()

    def tearDown(self):
        if hasattr(self, 'app'):
            self.app.close()

    def test_background_poll_keeps_controls_enabled(self):
        self.app.poll(background=True)
        self.assertTrue(self.app.busy)
        for button in [*self.app.action_buttons, self.app.connect_button]:
            self.assertFalse(button.instate(['disabled']))
        self.worker.finish()
        self.app.drain()
        self.assertFalse(self.app.busy)
        self.assertIsNotNone(self.app.last_snapshot)

    def test_restart_click_during_poll_runs_once_after_read(self):
        with patch.object(self.app.device, 'start', wraps=self.app.device.start) as start:
            self.app.poll(background=True)
            self.app.start()
            self.app.start()
            self.assertEqual(len(self.worker.jobs), 1)
            self.assertTrue(self.app.action_buttons[0].instate(['disabled']))
            self.worker.finish()
            self.app.drain()
            start.assert_not_called()
            self.assertEqual(len(self.worker.jobs), 1)
            self.worker.finish()
            self.app.drain()
            start.assert_called_once()
            self.assertFalse(self.app.busy)
            self.assertFalse(self.app.action_buttons[0].instate(['disabled']))

    def test_failed_poll_cancels_queued_restart(self):
        with patch.object(self.app.device, 'start') as start, patch('gui.messagebox.showerror') as error:
            self.app.poll(background=True)
            self.app.start()
            self.worker.finish(OSError('UART disconnected'))
            self.app.drain()
            start.assert_not_called()
            self.assertIsNone(self.app.pending_job)
            self.assertIsNone(self.app.device)
            self.assertEqual(len(self.worker.jobs), 1)  # Close the failed connection.
            self.worker.finish()
            start.assert_not_called()
            error.assert_called_once()

    def test_duplicate_background_reads_are_not_queued(self):
        self.app.poll(background=True)
        self.app.poll(background=True)
        self.assertEqual(len(self.worker.jobs), 1)

    def test_disconnect_click_during_poll_is_not_lost(self):
        self.app.poll(background=True)
        self.app.connect()
        self.worker.finish()
        self.app.drain()
        self.worker.finish()
        self.app.drain()
        self.assertIsNone(self.app.device)
        self.assertFalse(self.app.connect_button.instate(['disabled']))
        self.assertTrue(self.app.action_buttons[0].instate(['disabled']))

    def test_polling_can_be_paused(self):
        self.app.poll_enabled.set(False)
        self.app.auto_poll()
        self.assertEqual(self.worker.jobs, [])


if __name__ == '__main__':
    unittest.main()
