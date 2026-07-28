"""Clock-offsets window for the XDF validation desktop GUI: select a file and streams,
then view each stream's raw clock-offset calibration measurements to map every
stream in XDF file onto one shared clock."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from xdf_validator.gui.constants import (CLOCK_OFFSETS_COLUMNS,
                                         CLOCK_OFFSETS_WINDOW_HEIGHT,
                                         CLOCK_OFFSETS_WINDOW_TITLE,
                                         CLOCK_OFFSETS_WINDOW_WIDTH,
                                         XDF_FILE_FILTER)
from xdf_validator.gui.worker import StreamLoadWorker, StreamResolveWorker
from xdf_validator.xdf_utils import XDFStream

STREAM_ID_ROLE = Qt.ItemDataRole.UserRole
PANEL_MAX_WIDTH = 280


class ClockOffsetsWindow(QDialog):
    """Lets the user pick an XDF file (seeded from the main window's file list, or
    browse for a new one) and which of its streams to inspect, then shows each stream's
    raw clock-offset calibration measurements plus a summary (count, mean, drift)."""

    def __init__(self, parent=None, available_files: list[str] = None):
        super().__init__(parent)
        self.setWindowTitle(CLOCK_OFFSETS_WINDOW_TITLE)
        self.resize(CLOCK_OFFSETS_WINDOW_WIDTH, CLOCK_OFFSETS_WINDOW_HEIGHT)

        self.resolve_worker: StreamResolveWorker = None
        self.load_worker: StreamLoadWorker = None

        self._build_ui()

        # Populating the combo box already triggers _on_file_changed for the first item
        # via currentTextChanged (its current index moves from -1 to 0), so no separate
        # call is needed to kick off the initial resolve.
        for path in available_files or []:
            self.file_combo.addItem(path)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        file_controls = QHBoxLayout()
        file_controls.addWidget(QLabel("File:"))
        self.file_combo = QComboBox()
        self.file_combo.currentTextChanged.connect(self._on_file_changed)
        file_controls.addWidget(self.file_combo, stretch=1)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._on_browse)
        file_controls.addWidget(self.browse_button)
        layout.addLayout(file_controls)

        content = QHBoxLayout()
        layout.addLayout(content, stretch=1)
        content.addWidget(self._build_stream_panel())

        self.offsets_tree = QTreeWidget()
        self.offsets_tree.setColumnCount(len(CLOCK_OFFSETS_COLUMNS))
        self.offsets_tree.setHeaderLabels(CLOCK_OFFSETS_COLUMNS)
        content.addWidget(self.offsets_tree, stretch=1)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    def _build_stream_panel(self) -> QWidget:
        stream_panel = QVBoxLayout()
        stream_panel.addWidget(QLabel("Streams:"))
        self.stream_list = QListWidget()
        stream_panel.addWidget(self.stream_list)
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self._on_load_clicked)
        self.load_button.setEnabled(False)
        stream_panel.addWidget(self.load_button)

        widget = QWidget()
        widget.setLayout(stream_panel)
        widget.setMaximumWidth(PANEL_MAX_WIDTH)
        return widget

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select an XDF File", "", XDF_FILE_FILTER)
        if not path:
            return
        if self.file_combo.findText(path) < 0:
            self.file_combo.addItem(path)
        self.file_combo.setCurrentText(path)

    def _on_file_changed(self, path: str):
        if not path:
            return

        self.stream_list.clear()
        self.offsets_tree.clear()
        self.load_button.setEnabled(False)
        self.status_label.setText(f"Resolving streams in {path}...")

        self.resolve_worker = StreamResolveWorker(path)
        self.resolve_worker.resolved.connect(self._on_streams_resolved)
        self.resolve_worker.failed.connect(self._on_resolve_failed)
        self.resolve_worker.start()

    def _on_streams_resolved(self, streams: list[dict]):
        for stream_info in streams:
            name = stream_info.get("name") or "(unnamed)"
            stype = stream_info.get("type") or "?"
            hostname = stream_info.get("hostname") or "-"
            item = QListWidgetItem(f"{name} ({stype}, {hostname})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(STREAM_ID_ROLE, stream_info["stream_id"])
            self.stream_list.addItem(item)

        self.load_button.setEnabled(self.stream_list.count() > 0)
        self.status_label.setText(f"{self.stream_list.count()} stream(s) found")

    def _on_resolve_failed(self, error: str):
        self.status_label.setText(f"Failed to read streams: {error}")

    def _on_load_clicked(self):
        stream_ids = [
            self.stream_list.item(i).data(STREAM_ID_ROLE)
            for i in range(self.stream_list.count())
            if self.stream_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        if not stream_ids:
            QMessageBox.warning(self, "No streams selected", "Check one or more streams to load.")
            return

        self.load_button.setEnabled(False)
        self.offsets_tree.clear()
        self.status_label.setText(f"Loading {len(stream_ids)} stream(s)...")

        self.load_worker = StreamLoadWorker(self.file_combo.currentText(), stream_ids)
        self.load_worker.loaded.connect(self._on_streams_loaded)
        self.load_worker.failed.connect(self._on_load_failed)
        self.load_worker.start()

    def _on_streams_loaded(self, streams: list[XDFStream]):
        self.load_button.setEnabled(True)
        self.offsets_tree.clear()

        for stream in streams:
            summary = stream.summarize_clock_offsets()
            stream_item = QTreeWidgetItem([
                f"{stream.name} ({stream.type})",
                f"{summary['n_measurements']} measurements",
                f"mean={summary['mean_offset']:.6f}, drift={summary['drift']:.6f}",
            ])
            stream_item.setFlags(stream_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)

            for i, (t, v) in enumerate(zip(stream.clock_times, stream.clock_values)):
                stream_item.addChild(QTreeWidgetItem([f"#{i}", f"{t:.6f}", f"{v:.6f}"]))

            self.offsets_tree.addTopLevelItem(stream_item)
            stream_item.setExpanded(True)

        for col in range(len(CLOCK_OFFSETS_COLUMNS)):
            self.offsets_tree.resizeColumnToContents(col)

        self.status_label.setText(f"Loaded clock-offset measurements for {len(streams)} stream(s)")

    def _on_load_failed(self, error: str):
        self.load_button.setEnabled(True)
        self.status_label.setText(f"Failed to load streams: {error}")
