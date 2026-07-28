"""Plot window for the XDF validation desktop GUI: select a file, select streams and channels to plot, and view them on a synchronized time axis."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from xdf_validator.gui.constants import (PLOT_WINDOW_HEIGHT, PLOT_WINDOW_TITLE,
                                         PLOT_WINDOW_WIDTH, XDF_FILE_FILTER)
from xdf_validator.gui.worker import PlotLoadWorker, StreamResolveWorker
from xdf_validator.plot_xdf_streams import build_stream_plot
from xdf_validator.xdf_utils import XDFStream

STREAM_ID_ROLE = Qt.ItemDataRole.UserRole
CHANNEL_INDEX_ROLE = Qt.ItemDataRole.UserRole
PANEL_MAX_WIDTH = 280


class PlotWindow(QDialog):
    """Lets the user pick an XDF file (seeded from the main window's file list, or
    browse for a new one), pick which of its streams to load via a lightweight
    metadata-only scan, then pick which channels of those streams to plot."""

    def __init__(self, parent=None, available_files: list[str] = None):
        super().__init__(parent)
        self.setWindowTitle(PLOT_WINDOW_TITLE)
        self.resize(PLOT_WINDOW_WIDTH, PLOT_WINDOW_HEIGHT)

        self.resolve_worker: StreamResolveWorker = None
        self.load_worker: PlotLoadWorker = None
        self.plot_widget: QWidget = None
        self.loaded_streams: list[XDFStream] = []

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
        content.addWidget(self._build_channel_panel())

        self.plot_container = QVBoxLayout()
        content.addLayout(self.plot_container, stretch=1)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

    def _build_stream_panel(self) -> QWidget:
        stream_panel = QVBoxLayout()
        stream_panel.addWidget(QLabel("Streams:"))
        self.stream_list = QListWidget()
        stream_panel.addWidget(self.stream_list)
        self.load_button = QPushButton("Load Streams")
        self.load_button.clicked.connect(self._on_load_clicked)
        self.load_button.setEnabled(False)
        stream_panel.addWidget(self.load_button)

        widget = QWidget()
        widget.setLayout(stream_panel)
        widget.setMaximumWidth(PANEL_MAX_WIDTH)
        return widget

    def _build_channel_panel(self) -> QWidget:
        channel_panel = QVBoxLayout()
        channel_panel.addWidget(QLabel("Channels:"))
        self.channel_tree = QTreeWidget()
        self.channel_tree.setHeaderHidden(True)
        channel_panel.addWidget(self.channel_tree)

        select_controls = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(lambda: self._set_all_channels_checked(True))
        self.deselect_all_button = QPushButton("Deselect All")
        self.deselect_all_button.clicked.connect(lambda: self._set_all_channels_checked(False))
        select_controls.addWidget(self.select_all_button)
        select_controls.addWidget(self.deselect_all_button)
        channel_panel.addLayout(select_controls)

        self.plot_button = QPushButton("Plot")
        self.plot_button.clicked.connect(self._on_plot_clicked)
        self.plot_button.setEnabled(False)
        channel_panel.addWidget(self.plot_button)

        widget = QWidget()
        widget.setLayout(channel_panel)
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
        self.channel_tree.clear()
        self.loaded_streams = []
        self.load_button.setEnabled(False)
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
        self.plot_button.setEnabled(False)
        self.channel_tree.clear()
        self.status_label.setText(f"Loading {len(stream_ids)} stream(s)...")

        self.load_worker = PlotLoadWorker(self.file_combo.currentText(), stream_ids)
        self.load_worker.loaded.connect(self._on_streams_loaded)
        self.load_worker.failed.connect(self._on_load_failed)
        self.load_worker.start()

    def _on_streams_loaded(self, streams: list[XDFStream]):
        self.load_button.setEnabled(True)
        self.loaded_streams = streams
        self.channel_tree.clear()

        for stream in streams:
            stream_item = QTreeWidgetItem([f"{stream.name} ({stream.type})"])
            stream_item.setFlags(stream_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            if stream.is_regular:
                for ch_idx, label in enumerate(stream.channel_labels):
                    channel_item = QTreeWidgetItem([label])
                    channel_item.setFlags(channel_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    channel_item.setCheckState(0, Qt.CheckState.Checked)
                    channel_item.setData(0, CHANNEL_INDEX_ROLE, ch_idx)
                    stream_item.addChild(channel_item)
            else:
                note_item = QTreeWidgetItem(["(irregular stream, shown as event ticks)"])
                note_item.setFlags(note_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                stream_item.addChild(note_item)
            self.channel_tree.addTopLevelItem(stream_item)
            stream_item.setExpanded(True)

        self.plot_button.setEnabled(len(streams) > 0)
        self.status_label.setText(f"Loaded {len(streams)} stream(s) -- select channels, then Plot")

    def _on_load_failed(self, error: str):
        self.load_button.setEnabled(True)
        self.status_label.setText(f"Failed to load streams: {error}")

    def _set_all_channels_checked(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.channel_tree.topLevelItemCount()):
            stream_item = self.channel_tree.topLevelItem(i)
            for c in range(stream_item.childCount()):
                channel_item = stream_item.child(c)
                if channel_item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    channel_item.setCheckState(0, state)

    def _on_plot_clicked(self):
        streams_to_plot = []
        channel_selections = []
        for i, stream in enumerate(self.loaded_streams):
            stream_item = self.channel_tree.topLevelItem(i)
            if not stream.is_regular:
                streams_to_plot.append(stream)
                channel_selections.append(None)
                continue

            checked_indices = [
                stream_item.child(c).data(0, CHANNEL_INDEX_ROLE)
                for c in range(stream_item.childCount())
                if stream_item.child(c).checkState(0) == Qt.CheckState.Checked
            ]
            if not checked_indices:
                continue  # no channels selected for this stream -- omit it entirely
            streams_to_plot.append(stream)
            channel_selections.append(checked_indices)

        if not streams_to_plot:
            QMessageBox.warning(self, "Nothing to plot", "Check at least one channel to plot.")
            return

        try:
            widget = build_stream_plot(streams_to_plot, channel_selections=channel_selections)
        except Exception as exc:
            self.status_label.setText(f"Failed to build plot: {exc}")
            return

        if self.plot_widget is not None:
            self.plot_container.removeWidget(self.plot_widget)
            self.plot_widget.deleteLater()
        self.plot_widget = widget
        self.plot_container.addWidget(self.plot_widget)
        self.status_label.setText(f"Plotted {len(streams_to_plot)} stream(s)")
