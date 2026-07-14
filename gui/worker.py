"""Background thread for running XDF validation without blocking the GUI."""

from PyQt6.QtCore import QThread, pyqtSignal

from validate_xdf import validate_xdf_file


class ValidationWorker(QThread):
    """Runs validate_xdf_file() for a batch of paths on a background thread, emitting one
    result dict at a time (file_validated) so the GUI can update incrementally. Emits the
    inherited QThread.finished signal once every file has been processed."""

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

    def run(self):
        for xdf_file in self.xdf_files:
            result = validate_xdf_file(
                xdf_file,
                stream_type=self.stream_type,
                exclude_name_substring=self.exclude_name_substring,
            )
            self.file_validated.emit(result)
