"""Plot window for the XDF validation desktop GUI: pick a file, pick which of its
streams to plot, and view them on a synchronized time axis."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from xdf_validator.gui.constants import (PLOT_WINDOW_HEIGHT, PLOT_WINDOW_TITLE,
                                         PLOT_WINDOW_WIDTH, XDF_FILE_FILTER)
from xdf_validator.gui.worker import PlotLoadWorker, StreamResolveWorker
from xdf_validator.plot_xdf_streams import build_stream_plot

STREAM_ID_ROLE = Qt.ItemDataRole.UserRole


class PlotWindow(QDialog):
    """Lets the user pick an XDF file (seeded from the main window's file list, or
    browse for a new one), pick which of its streams to plot via a lightweight
    metadata-only scan, then loads and plots only those streams."""

    def __init__(self, parent=None, available_files: list[str] = None):
        super().__init__(parent)
        self.setWindowTitle(PLOT_WINDOW_TITLE)
        self.resize(PLOT_WINDOW_WIDTH, PLOT_WINDOW_HEIGHT)

        self.resolve_worker: StreamResolveWorker = None
        self.load_worker: PlotLoadWorker = None
        self.plot_widget: QWidget = None

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

        stream_panel = QVBoxLayout()
        stream_panel.addWidget(QLabel("Streams:"))
        self.stream_list = QListWidget()
        stream_panel.addWidget(self.stream_list)
        self.plot_button = QPushButton("Plot")
        self.plot_button.clicked.connect(self._on_plot_clicked)
        self.plot_button.setEnabled(False)
        stream_panel.addWidget(self.plot_button)
        stream_panel_widget = QWidget()
        stream_panel_widget.setLayout(stream_panel)
        stream_panel_widget.setMaximumWidth(320)
        content.addWidget(stream_panel_widget)

        self.plot_container = QVBoxLayout()
        content.addLayout(self.plot_container, stretch=1)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

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
        self.plot_button.setEnabled(False)
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

        self.plot_button.setEnabled(self.stream_list.count() > 0)
        self.status_label.setText(f"{self.stream_list.count()} stream(s) found")

    def _on_resolve_failed(self, error: str):
        self.status_label.setText(f"Failed to read streams: {error}")

    def _on_plot_clicked(self):
        stream_ids = [
            self.stream_list.item(i).data(STREAM_ID_ROLE)
            for i in range(self.stream_list.count())
            if self.stream_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        if not stream_ids:
            QMessageBox.warning(self, "No streams selected", "Check one or more streams to plot.")
            return

        self.plot_button.setEnabled(False)
        self.status_label.setText(f"Loading {len(stream_ids)} stream(s)...")

        self.load_worker = PlotLoadWorker(self.file_combo.currentText(), stream_ids)
        self.load_worker.loaded.connect(self._on_streams_loaded)
        self.load_worker.failed.connect(self._on_load_failed)
        self.load_worker.start()

    def _on_streams_loaded(self, streams: list):
        self.plot_button.setEnabled(True)
        try:
            widget = build_stream_plot(streams)
        except Exception as exc:
            self.status_label.setText(f"Failed to build plot: {exc}")
            return

        if self.plot_widget is not None:
            self.plot_container.removeWidget(self.plot_widget)
            self.plot_widget.deleteLater()
        self.plot_widget = widget
        self.plot_container.addWidget(self.plot_widget)
        self.status_label.setText(f"Plotted {len(streams)} stream(s)")

    def _on_load_failed(self, error: str):
        self.plot_button.setEnabled(True)
        self.status_label.setText(f"Failed to load streams: {error}")
