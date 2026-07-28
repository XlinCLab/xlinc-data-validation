"""Main window for the XDF validation desktop GUI."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QMainWindow, QMessageBox,
                             QPushButton, QSplitter, QStatusBar, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from xdf_validator.gui.clock_offsets_window import ClockOffsetsWindow
from xdf_validator.gui.constants import (DEFAULT_REPORT_FILENAME,
                                         RESULT_COLUMNS, VERDICT_COLOR_FAIL,
                                         VERDICT_COLOR_OK, VERDICT_COLOR_WARN,
                                         WARN_SUBSTRINGS, WINDOW_HEIGHT,
                                         WINDOW_TITLE, WINDOW_WIDTH,
                                         XDF_FILE_FILTER)
from xdf_validator.gui.plot_window import PlotWindow
from xdf_validator.gui.worker import ValidationWorker
from xdf_validator.validate_xdf import format_report
from xdf_validator.xdf_utils import FAIL_PREFIXES

VERDICT_COLUMN = len(RESULT_COLUMNS) - 1


class MainWindow(QMainWindow):
    """Lets the user pick one or more .xdf files, run the same validation checks as
    validate_xdf.py against them, and browse/save the results."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.xdf_files: list[str] = []
        self.results: list[dict] = []
        self.worker: ValidationWorker = None
        self.plot_window: PlotWindow = None
        self.clock_offsets_window: ClockOffsetsWindow = None
        self._cancel_requested = False

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addLayout(self._build_file_controls())
        layout.addLayout(self._build_filter_controls())

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, stretch=1)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        splitter.addWidget(self.file_list)

        self.results_tree = QTreeWidget()
        self.results_tree.setColumnCount(len(RESULT_COLUMNS))
        self.results_tree.setHeaderLabels(RESULT_COLUMNS)
        splitter.addWidget(self.results_tree)
        splitter.setSizes([120, 480])

        layout.addLayout(self._build_run_controls())

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _build_file_controls(self) -> QHBoxLayout:
        file_controls = QHBoxLayout()
        self.add_button = QPushButton("Add XDF Files...")
        self.add_button.clicked.connect(self._on_add_files)
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._on_remove_selected)
        self.clear_button = QPushButton("Clear All")
        self.clear_button.clicked.connect(self._on_clear_files)
        self.plot_streams_button = QPushButton("Plot Streams...")
        self.plot_streams_button.clicked.connect(self._on_plot_streams)
        self.clock_offsets_button = QPushButton("Clock Offsets...")
        self.clock_offsets_button.clicked.connect(self._on_clock_offsets)
        file_controls.addWidget(self.add_button)
        file_controls.addWidget(self.remove_button)
        file_controls.addWidget(self.clear_button)
        file_controls.addWidget(self.plot_streams_button)
        file_controls.addWidget(self.clock_offsets_button)
        file_controls.addStretch()
        return file_controls

    def _on_plot_streams(self):
        # A new window each click, so that the user can have more
        # than one open at a time, e.g. to compare two files side by side.
        self.plot_window = PlotWindow(self, available_files=list(self.xdf_files))
        self.plot_window.show()
        self.plot_window.raise_()
        self.plot_window.activateWindow()

    def _on_clock_offsets(self):
        self.clock_offsets_window = ClockOffsetsWindow(self, available_files=list(self.xdf_files))
        self.clock_offsets_window.show()
        self.clock_offsets_window.raise_()
        self.clock_offsets_window.activateWindow()

    def _build_filter_controls(self) -> QHBoxLayout:
        filter_controls = QHBoxLayout()
        filter_controls.addWidget(QLabel("Stream type filter:"))
        self.stream_type_input = QLineEdit()
        self.stream_type_input.setPlaceholderText("e.g. EEG (leave blank for all)")
        filter_controls.addWidget(self.stream_type_input)
        filter_controls.addWidget(QLabel("Exclude stream name containing:"))
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText("e.g. Impedance")
        filter_controls.addWidget(self.exclude_input)
        return filter_controls

    def _build_run_controls(self) -> QHBoxLayout:
        run_controls = QHBoxLayout()
        self.validate_button = QPushButton("Validate")
        self.validate_button.clicked.connect(self._on_validate)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        self.cancel_button.setEnabled(False)
        self.save_button = QPushButton("Save Report...")
        self.save_button.clicked.connect(self._on_save_report)
        self.save_button.setEnabled(False)
        run_controls.addWidget(self.validate_button)
        run_controls.addWidget(self.cancel_button)
        run_controls.addWidget(self.save_button)
        run_controls.addStretch()
        return run_controls

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select XDF Files", "", XDF_FILE_FILTER)
        for path in paths:
            if path not in self.xdf_files:
                self.xdf_files.append(path)
                self.file_list.addItem(path)

    def _on_remove_selected(self):
        for item in self.file_list.selectedItems():
            path = item.text()
            if path in self.xdf_files:
                self.xdf_files.remove(path)
            self.file_list.takeItem(self.file_list.row(item))

    def _on_clear_files(self):
        self.xdf_files.clear()
        self.file_list.clear()
        self.results_tree.clear()
        self.results.clear()
        self.save_button.setEnabled(False)

    def _on_validate(self):
        if not self.xdf_files:
            QMessageBox.warning(self, "No files selected", "Add one or more .xdf files first.")
            return

        self.results = []
        self.results_tree.clear()
        self._cancel_requested = False
        self._set_running(True)
        self.status_bar.showMessage(f"Validating 0/{len(self.xdf_files)} file(s)...")

        self.worker = ValidationWorker(
            list(self.xdf_files),
            stream_type=self.stream_type_input.text().strip() or None,
            exclude_name_substring=self.exclude_input.text().strip() or None,
        )
        self.worker.file_validated.connect(self._on_file_validated)
        self.worker.finished.connect(self._on_validation_finished)
        self.worker.start()

    def _on_cancel(self):
        if self.worker is not None and self.worker.isRunning():
            self._cancel_requested = True
            self.worker.stop()
            self.cancel_button.setEnabled(False)
            self.status_bar.showMessage("Cancelling after the current file finishes...")

    def _set_running(self, running: bool):
        """Toggle controls between "validation in progress" and "idle" states. File-list
        editing is disabled while running since the worker already took its own snapshot
        of the file list at start time."""
        self.validate_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.add_button.setEnabled(not running)
        self.remove_button.setEnabled(not running)
        self.clear_button.setEnabled(not running)
        if running:
            self.save_button.setEnabled(False)

    def _on_file_validated(self, result: dict):
        self.results.append(result)
        self.status_bar.showMessage(f"Validating {len(self.results)}/{len(self.xdf_files)} file(s)...")
        self._add_result_to_tree(result)

    def _add_result_to_tree(self, result: dict):
        file_item = QTreeWidgetItem([os.path.basename(result["file"])])
        file_item.setToolTip(0, result["file"])

        if result["error"]:
            file_item.setText(VERDICT_COLUMN, f"FAILED: {result['error']}")
            file_item.setForeground(VERDICT_COLUMN, QColor(VERDICT_COLOR_FAIL))
        else:
            status = "PASS" if result["passed"] else "FAIL"
            color = VERDICT_COLOR_OK if result["passed"] else VERDICT_COLOR_FAIL
            file_item.setText(VERDICT_COLUMN, status)
            file_item.setForeground(VERDICT_COLUMN, QColor(color))

            for row in result["streams"]:
                stream_item = QTreeWidgetItem([
                    row["name"],
                    row["type"],
                    row["hostname"],
                    str(row["n_samples"]),
                    f"{row['duration']:.1f}",
                    f"{row['effective_srate']:.1f}",
                    str(row["n_gaps"]),
                    str(row["total_missing"]),
                    f"{row['jitter_pct']:.2f}",
                    row["verdict"],
                ])
                stream_item.setForeground(VERDICT_COLUMN, QColor(self._verdict_color(row["verdict"])))
                file_item.addChild(stream_item)

        self.results_tree.addTopLevelItem(file_item)
        file_item.setExpanded(True)

    @staticmethod
    def _verdict_color(verdict: str) -> str:
        if verdict.startswith(FAIL_PREFIXES):
            return VERDICT_COLOR_FAIL
        if any(substring in verdict for substring in WARN_SUBSTRINGS):
            return VERDICT_COLOR_WARN
        return VERDICT_COLOR_OK

    def _on_validation_finished(self):
        n_passed = sum(1 for r in self.results if r["passed"])

        self._set_running(False)
        self.save_button.setEnabled(bool(self.results))

        if self._cancel_requested:
            self.status_bar.showMessage(
                f"Cancelled after {len(self.results)}/{len(self.xdf_files)} file(s) "
                f"({n_passed} passed)"
            )
        else:
            self.status_bar.showMessage(f"Done: {n_passed}/{len(self.results)} file(s) passed validation")

    def _on_save_report(self):
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Validation Report", DEFAULT_REPORT_FILENAME, "Text files (*.txt)"
        )
        if not path:
            return
        with open(path, "w") as f:
            f.write(format_report(self.results) + "\n")
        self.status_bar.showMessage(f"Report saved to {path}")
