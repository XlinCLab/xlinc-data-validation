"""Background threads for running XDF validation and stream plotting without blocking
the GUI."""

from PyQt6.QtCore import QThread, pyqtSignal
from pyxdf import resolve_streams

from xdf_validator.validate_xdf import validate_xdf_file
from xdf_validator.xdf_utils import XDFFile


class ValidationWorker(QThread):
    """Runs validate_xdf_file() for a batch of paths on a background thread, emitting one
    result dict at a time (file_validated) so the GUI can update incrementally.
    Emits the inherited QThread.finished signal once processing stops, whether because 
    every file was processed or because cancellation was requested (see stop())."""

    file_validated = pyqtSignal(dict)

    def __init__(
            self,
            xdf_files: list[str],
            stream_type: str = None,
            exclude_name_substring: str = None,
            parent=None,
        ):
        super().__init__(parent)
        self.xdf_files = xdf_files
        self.stream_type = stream_type
        self.exclude_name_substring = exclude_name_substring

    def stop(self):
        """Request cancellation. Takes effect after the file currently being validated
        finishes; does not interrupt an in-progress load_xdf() call."""
        self.requestInterruption()

    def run(self):
        for xdf_file in self.xdf_files:
            if self.isInterruptionRequested():
                break
            result = validate_xdf_file(
                xdf_file,
                stream_type=self.stream_type,
                exclude_name_substring=self.exclude_name_substring,
            )
            self.file_validated.emit(result)


class StreamResolveWorker(QThread):
    """Resolves an XDF file's stream metadata (name/type/hostname/rate/stream_id) on a
    background thread without loading any sample data, via pyxdf.resolve_streams()."""

    resolved = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            streams = resolve_streams(self.path)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.resolved.emit(streams)


class StreamLoadWorker(QThread):
    """Loads only selected streams' full sample data on a background thread."""

    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, path: str, stream_ids: list[int], parent=None):
        super().__init__(parent)
        self.path = path
        self.stream_ids = stream_ids

    def run(self):
        try:
            xdf = XDFFile(
                path=self.path,
                select_streams=self.stream_ids,
                synchronize_clocks=True,
                verbose=False,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.loaded.emit(xdf.streams)
