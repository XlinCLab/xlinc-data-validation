"""Background thread for running the LSL monitor without blocking the GUI."""

import threading

from PyQt6.QtCore import QThread

from lsl_monitor.lsl_monitor import monitor


class MonitorWorker(QThread):
    """Runs monitor() on a background thread until stop() is called (or the process
    running monitor()'s stream loop exits on its own). Log output is not passed through
    this worker directly -- monitor() logs via the module logger, which the GUI attaches
    its own handler to independently of this thread."""

    def __init__(
            self,
            logfile: str = None,
            interval: float = 1.0,
            wait_time: float = 2.0,
            max_buflen: int = 360,
            recover: bool = False,
            time_correction_timeout: float = 0.5,
            lag_threshold_periods: float = 10.0,
            startup_grace_period: float = 5.0,
            parent=None,
        ):
        super().__init__(parent)
        self.kwargs = dict(
            logfile=logfile,
            interval=interval,
            wait_time=wait_time,
            max_buflen=max_buflen,
            recover=recover,
            time_correction_timeout=time_correction_timeout,
            lag_threshold_periods=lag_threshold_periods,
            startup_grace_period=startup_grace_period,
        )
        self.stop_event = threading.Event()

    def stop(self) -> None:
        """Request a clean stop. Takes effect within one polling interval."""
        self.stop_event.set()

    def run(self) -> None:
        monitor(stop_event=self.stop_event, **self.kwargs)
