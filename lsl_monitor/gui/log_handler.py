"""Bridges Python's logging module into Qt so log records can be shown in a GUI widget."""

import logging

from PyQt6.QtCore import QObject, pyqtSignal


class QtLogHandler(logging.Handler, QObject):
    """A logging.Handler that re-emits each record as a Qt signal instead of writing it
    anywhere itself. monitor() runs on a background QThread, but Qt automatically queues
    a signal emitted from one thread to a slot owned by another, so connecting
    log_record to a slot on the GUI thread is safe without any extra locking."""

    log_record = pyqtSignal(str, int)  # formatted message, levelno

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, record: logging.LogRecord) -> None:
        self.log_record.emit(self.format(record), record.levelno)
