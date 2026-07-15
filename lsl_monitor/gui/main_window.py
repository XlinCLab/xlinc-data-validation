"""Main window for the LSL monitor desktop GUI."""

import html
import logging

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QHBoxLayout, QLineEdit, QMainWindow,
                             QPushButton, QSpinBox, QStatusBar, QTextEdit,
                             QVBoxLayout, QWidget)

from lsl_monitor.gui.constants import (CONSOLE_BACKGROUND, DEFAULT_LEVEL_COLOR,
                                       LEVEL_COLORS, WINDOW_HEIGHT,
                                       WINDOW_TITLE, WINDOW_WIDTH)
from lsl_monitor.gui.log_handler import QtLogHandler
from lsl_monitor.gui.worker import MonitorWorker
from lsl_monitor.lsl_monitor import logger as monitor_logger


class MainWindow(QMainWindow):
    """Lets the user configure and start/stop lsl_monitor.monitor() as a background
    thread, with its log output (the same messages that would print to a terminal)
    shown live in an in-window console."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.worker: MonitorWorker = None

        # Attach once, for the life of the window, independently of how many times
        # monitor() itself is started/stopped -- configure_logging() only replaces the
        # file/console handlers it manages, so this one keeps receiving every record.
        self._log_handler = QtLogHandler()
        self._log_handler.setLevel(logging.INFO)
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        self._log_handler.log_record.connect(self._on_log_record)
        monitor_logger.addHandler(self._log_handler)

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addLayout(self._build_settings())
        layout.addLayout(self._build_run_controls())

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.console.setFont(font)
        self.console.setStyleSheet(
            f"QTextEdit {{ background-color: {CONSOLE_BACKGROUND}; color: {DEFAULT_LEVEL_COLOR}; }}"
        )
        layout.addWidget(self.console, stretch=1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Idle")

    def _build_settings(self) -> QFormLayout:
        form = QFormLayout()

        logfile_row = QHBoxLayout()
        self.logfile_input = QLineEdit()
        self.logfile_input.setPlaceholderText("auto: logs/lsl_watchdog_<timestamp>.log")
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_logfile)
        logfile_row.addWidget(self.logfile_input)
        logfile_row.addWidget(browse_button)
        form.addRow("Log file:", logfile_row)

        self.interval_input = QDoubleSpinBox()
        self.interval_input.setRange(0.1, 60.0)
        self.interval_input.setSingleStep(0.5)
        self.interval_input.setValue(1.0)
        self.interval_input.setSuffix(" s")
        form.addRow("Tick interval:", self.interval_input)

        self.wait_time_input = QDoubleSpinBox()
        self.wait_time_input.setRange(0.5, 30.0)
        self.wait_time_input.setValue(2.0)
        self.wait_time_input.setSuffix(" s")
        form.addRow("Stream discovery wait:", self.wait_time_input)

        self.max_buflen_input = QSpinBox()
        self.max_buflen_input.setRange(1, 3600)
        self.max_buflen_input.setValue(360)
        self.max_buflen_input.setSuffix(" s")
        form.addRow("Max inlet buffer:", self.max_buflen_input)

        self.time_correction_timeout_input = QDoubleSpinBox()
        self.time_correction_timeout_input.setRange(0.1, 10.0)
        self.time_correction_timeout_input.setValue(0.5)
        self.time_correction_timeout_input.setSuffix(" s")
        form.addRow("Time-correction timeout:", self.time_correction_timeout_input)

        self.lag_threshold_input = QDoubleSpinBox()
        self.lag_threshold_input.setRange(1.0, 1000.0)
        self.lag_threshold_input.setValue(10.0)
        self.lag_threshold_input.setSuffix(" nominal periods")
        form.addRow("Lag warning threshold:", self.lag_threshold_input)

        self.startup_grace_input = QDoubleSpinBox()
        self.startup_grace_input.setRange(0.0, 120.0)
        self.startup_grace_input.setValue(5.0)
        self.startup_grace_input.setSuffix(" s")
        form.addRow("Startup grace period:", self.startup_grace_input)

        self.recover_input = QCheckBox("Attempt stream recovery")
        form.addRow(self.recover_input)

        return form

    def _build_run_controls(self) -> QHBoxLayout:
        run_controls = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._on_start)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._on_stop)
        self.stop_button.setEnabled(False)
        run_controls.addWidget(self.start_button)
        run_controls.addWidget(self.stop_button)
        run_controls.addStretch()
        return run_controls

    def _on_browse_logfile(self):
        path, _ = QFileDialog.getSaveFileName(self, "Choose Log File", "", "Log files (*.log);;All files (*)")
        if path:
            self.logfile_input.setText(path)

    def _on_start(self):
        if self.worker is not None and self.worker.isRunning():
            return

        self.console.clear()
        self._set_running(True)
        self.status_bar.showMessage("Resolving streams...")

        self.worker = MonitorWorker(
            logfile=self.logfile_input.text().strip() or None,
            interval=self.interval_input.value(),
            wait_time=self.wait_time_input.value(),
            max_buflen=self.max_buflen_input.value(),
            recover=self.recover_input.isChecked(),
            time_correction_timeout=self.time_correction_timeout_input.value(),
            lag_threshold_periods=self.lag_threshold_input.value(),
            startup_grace_period=self.startup_grace_input.value(),
        )
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()
        self.status_bar.showMessage("Monitoring...")

    def _on_stop(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.status_bar.showMessage("Stopping...")

    def _set_running(self, running: bool):
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        for widget in (self.logfile_input, self.interval_input, self.wait_time_input,
                       self.max_buflen_input, self.recover_input,
                       self.time_correction_timeout_input, self.lag_threshold_input,
                       self.startup_grace_input):
            widget.setEnabled(not running)

    def _on_worker_finished(self):
        self._set_running(False)
        self.status_bar.showMessage("Idle")

    def _on_log_record(self, message: str, levelno: int):
        color = LEVEL_COLORS.get(levelno, DEFAULT_LEVEL_COLOR)
        self.console.append(f'<span style="color:{color};">{html.escape(message)}</span>')

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        monitor_logger.removeHandler(self._log_handler)
        super().closeEvent(event)
