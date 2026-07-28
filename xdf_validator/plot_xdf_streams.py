#!/usr/bin/env python3
"""Plot one or more streams from an XDF file on a synchronized time axis.

Irregularly-sampled streams (e.g. markers) are rendered as event ticks rather than a
continuous waveform, since there is no meaningful value to connect between them.
Multi-channel regular streams (e.g. EEG) get one subplot per channel rather than being
stacked into a single shared axis, so each channel keeps its own independently
auto-ranged Y-axis with real tick values -- overlaying channels with very different
amplitude ranges (e.g. a 2-channel audio stream) in one axis makes them unreadable.
Every panel shares one time axis, linked across the whole plot regardless of how many
channels a given stream contributes.

Usage:
    python3 -m xdf_validator.plot_xdf_streams recording.xdf
    python3 -m xdf_validator.plot_xdf_streams recording.xdf --streams "CGX Mobile-128 M128-DEMO" audio
    python3 -m xdf_validator.plot_xdf_streams recording.xdf --stream-type EEG --exclude-name-substring Impedance
"""

import argparse
import sys

import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from shared.colors import COLOR_FAIL
from xdf_validator.constants import UNIT_ABBREVIATIONS
from xdf_validator.xdf_utils import XDFFile, XDFStream

GAP_HIGHLIGHT_ALPHA = 80  # 0-255


def _format_unit(unit: str) -> str:
    """Abbreviate a unit string for compact axis labels."""
    if not unit:
        return ""
    return UNIT_ABBREVIATIONS.get(unit.lower(), unit)


def _shade_gaps(plot_item, gaps: list[dict], stream_offset: float):
    """Shade detected gaps on a plot. locate_gaps() reports gap times relative to the
    stream's own start; shift by stream_offset (that stream's start relative to the
    plot's shared time origin) so the shaded regions land in the right place."""
    gap_color = QColor(COLOR_FAIL)
    gap_color.setAlpha(GAP_HIGHLIGHT_ALPHA)
    for gap in gaps:
        region = pg.LinearRegionItem(
            values=(gap["start"] + stream_offset, gap["end"] + stream_offset),
            movable=False, brush=pg.mkBrush(gap_color), pen=pg.mkPen(None),
        )
        plot_item.addItem(region)


def _plot_channel(
        plot_item, stream: XDFStream, channel_idx: int, t: np.ndarray,
        stream_offset: float, gaps: list[dict],
    ):
    """Draw a single channel of a regularly-sampled stream in its own subplot: a real,
    independently auto-ranged Y-axis (actual tick values) labeled with just the unit,
    channel identity in the title, and any detected gaps shaded."""
    label = stream.channel_labels[channel_idx]
    units = stream.channel_units
    unit = _format_unit(units[channel_idx] if channel_idx < len(units) else "")

    channel_data = stream.time_series[:, channel_idx].astype(np.float64)
    centered = channel_data - np.median(channel_data)
    plot_item.plot(t, centered, autoDownsample=True)

    plot_item.setTitle(f"{stream.name} - {label}")
    plot_item.setLabel('left', unit)

    _shade_gaps(plot_item, gaps, stream_offset)


def _plot_irregular_stream(plot_item, stream: XDFStream, t: np.ndarray):
    """Draw an irregularly-sampled stream (e.g. markers) as event ticks."""
    plot_item.plot(
        t, np.zeros_like(t),
        pen=None, symbol='|', symbolSize=20, symbolPen=pg.mkPen(width=1.5),
    )
    plot_item.setTitle(f"{stream.name} ({stream.type})")
    plot_item.getAxis('left').setTicks([[(0, 'event')]])


def build_stream_plot(
        streams: list[XDFStream],
        channel_selections: list[list[int]] = None,
    ) -> pg.GraphicsLayoutWidget:
    """Build a plot of the given streams: one subplot per selected channel for each
    regularly-sampled stream (all of its channels if channel_selections is None), one
    subplot per irregularly-sampled stream, all sharing a single synchronized time axis.

    channel_selections, if given, must be the same length as streams: each entry is
    either None (plot all of that stream's channels) or a list of channel indices to
    plot for that stream. Only relevant for regularly-sampled streams."""
    if not streams:
        raise ValueError("No streams to plot")
    if channel_selections is None:
        channel_selections = [None] * len(streams)

    t0_candidates = [s.time_stamps[0] for s in streams if s.n_samples > 0]
    if not t0_candidates:
        raise ValueError("None of the selected streams contain any samples")
    t0 = min(t0_candidates)

    # Flatten to one row per selected channel (regular streams) or one row per stream
    # (irregular streams), computing each stream's gaps only once regardless of how many
    # of its channels get their own row.
    rows = []
    for stream, selection in zip(streams, channel_selections):
        if stream.is_regular:
            indices = selection if selection is not None else list(range(stream.n_channels))
            gaps = stream.locate_gaps()
            rows.extend((stream, ch, gaps) for ch in indices)
        else:
            rows.append((stream, None, None))

    widget = pg.GraphicsLayoutWidget()
    first_plot_item = None
    for row_idx, (stream, channel_idx, gaps) in enumerate(rows):
        plot_item = widget.addPlot(row=row_idx, col=0)
        if first_plot_item is None:
            first_plot_item = plot_item
        else:
            plot_item.setXLink(first_plot_item)

        if row_idx == len(rows) - 1:
            plot_item.setLabel('bottom', 'Time (s)')
        else:
            plot_item.getAxis('bottom').setStyle(showValues=False)

        t = stream.time_stamps - t0
        stream_offset = (stream.time_stamps[0] - t0) if stream.n_samples > 0 else 0.0
        if channel_idx is not None:
            _plot_channel(plot_item, stream, channel_idx, t, stream_offset, gaps)
        else:
            _plot_irregular_stream(plot_item, stream, t)

    return widget


def plot_xdf_file(
        path: str,
        stream_names: list[str] = None,
        stream_type: str = None,
        exclude_name_substring: str = None,
    ) -> pg.GraphicsLayoutWidget:
    """Load an XDF file and build a synchronized multi-panel plot of its streams,
    optionally filtered by explicit name, type, and/or an excluded name substring."""
    xdf = XDFFile(path, synchronize_clocks=True, verbose=False)
    streams = xdf.streams_by_type(stream_type=stream_type, exclude_name_substring=exclude_name_substring)
    if stream_names is not None:
        streams = [s for s in streams if s.name in stream_names]
    return build_stream_plot(streams)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plot one or more streams from an XDF file on a synchronized time axis."
    )
    parser.add_argument("xdf_file", help="Path to a single .xdf file to plot")
    parser.add_argument("--streams", nargs="+", default=None,
                         help="Only plot streams with these exact names. Default: all matching streams")
    parser.add_argument("--stream-type", default=None,
                         help="Only plot streams of this type (e.g. EEG). Default: all types")
    parser.add_argument("--exclude-name-substring", default=None,
                         help="Exclude streams whose name contains this substring (e.g. impedance checks)")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    widget = plot_xdf_file(
        args.xdf_file,
        stream_names=args.streams,
        stream_type=args.stream_type,
        exclude_name_substring=args.exclude_name_substring,
    )
    widget.setWindowTitle(f"XDF Streams - {args.xdf_file}")
    widget.resize(1100, 700)
    widget.show()
    return app.exec()


if __name__ == "__main__":
    main()
