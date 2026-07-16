#!/usr/bin/env python3
"""Plot one or more streams from an XDF file on a synchronized time axis.

Irregularly-sampled streams (e.g. markers) are rendered as event ticks rather than a
continuous waveform, since there is no meaningful value to connect between them.
Multi-channel regular streams (e.g. EEG) are drawn as stacked, vertically-offset traces
so a dropout affecting only some channels stays visible rather than being hidden behind
a single representative trace. Every panel shares one time axis but each panel keeps 
its own independent, labeled Y-axis.

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
from xdf_validator.xdf_utils import XDFFile, XDFStream

# Percentile-based per-channel amplitude estimate used to size the vertical offset between
# stacked traces, so spacing looks reasonable regardless of the stream's physical units.
CHANNEL_OFFSET_PERCENTILE = 95.0
CHANNEL_OFFSET_SPACING = 4.0
GAP_HIGHLIGHT_ALPHA = 80  # 0-255


def _channel_scale(channel: np.ndarray) -> float:
    """Robust per-channel amplitude estimate (median-centered percentile), used to size
    the vertical spacing between stacked traces."""
    scale = float(np.percentile(np.abs(channel - np.median(channel)), CHANNEL_OFFSET_PERCENTILE))
    return scale if scale > 0 else 1.0


def _axis_label(name: str, unit: str, scale: float = None) -> str:
    """Build a Y-axis label combining a name, its unit (if known), and -- for stacked
    multi-channel panels -- the real-world scale one channel's stacking offset
    represents, so the axis conveys actual values/units rather than just an identity."""
    text = f"{name} ({unit})" if unit else name
    if scale is not None:
        text += f"  [~{scale:.3g} {unit or 'units'} per channel division]"
    return text


def _plot_regular_stream(plot_item, stream: XDFStream, t: np.ndarray, stream_offset: float):
    """Draw a regularly-sampled stream, stacking multiple channels with a vertical offset
    (Y-axis ticks labeled per channel, axis label giving the unit and the real-world
    scale that offset represents) and shading any detected gaps."""
    time_series = stream.time_series
    labels = stream.channel_labels
    units = stream.channel_units
    unit = next((u for u in units if u), "")
    n_channels = stream.n_channels

    offsets = []
    scales = []
    running_offset = 0.0
    for ch in range(n_channels):
        channel_data = time_series[:, ch].astype(np.float64)
        centered = channel_data - np.median(channel_data)
        plot_item.plot(
            t, centered + running_offset,
            pen=pg.intColor(ch, hues=max(n_channels, 1)),
            autoDownsample=True,
        )
        offsets.append(running_offset)
        scale = _channel_scale(channel_data)
        scales.append(scale)
        running_offset += scale * CHANNEL_OFFSET_SPACING

    if n_channels > 1:
        plot_item.getAxis('left').setTicks([list(zip(offsets, labels))])
        plot_item.setLabel('left', _axis_label(stream.name, unit, scale=float(np.median(scales))))
    else:
        plot_item.setLabel('left', _axis_label(labels[0] if labels else stream.name, unit))

    # locate_gaps() reports gap times relative to this stream's own start; shift by
    # stream_offset (this stream's start relative to the plot's shared time origin) so
    # the shaded regions land in the right place on the shared axis.
    gap_color = QColor(COLOR_FAIL)
    gap_color.setAlpha(GAP_HIGHLIGHT_ALPHA)
    for gap in stream.locate_gaps():
        region = pg.LinearRegionItem(
            values=(gap["start"] + stream_offset, gap["end"] + stream_offset),
            movable=False, brush=pg.mkBrush(gap_color), pen=pg.mkPen(None),
        )
        plot_item.addItem(region)


def _plot_irregular_stream(plot_item, stream: XDFStream, t: np.ndarray):
    """Draw an irregularly-sampled stream (e.g. markers) as event ticks."""
    plot_item.plot(
        t, np.zeros_like(t),
        pen=None, symbol='|', symbolSize=20, symbolPen=pg.mkPen(width=1.5),
    )
    plot_item.getAxis('left').setTicks([[(0, 'event')]])


def build_stream_plot(streams: list[XDFStream]) -> pg.GraphicsLayoutWidget:
    """Build a multi-panel plot of the given streams: one row per stream, all sharing a
    single synchronized time axis but each keeping its own labeled Y-axis."""
    if not streams:
        raise ValueError("No streams to plot")

    t0_candidates = [s.time_stamps[0] for s in streams if s.n_samples > 0]
    if not t0_candidates:
        raise ValueError("None of the selected streams contain any samples")
    t0 = min(t0_candidates)

    widget = pg.GraphicsLayoutWidget()
    first_plot_item = None
    for i, stream in enumerate(streams):
        plot_item = widget.addPlot(row=i, col=0)
        if first_plot_item is None:
            first_plot_item = plot_item
        else:
            plot_item.setXLink(first_plot_item)

        if i == len(streams) - 1:
            plot_item.setLabel('bottom', 'Time (s)')
        else:
            plot_item.getAxis('bottom').setStyle(showValues=False)

        plot_item.setTitle(f"{stream.name} ({stream.type})")

        t = stream.time_stamps - t0
        stream_offset = (stream.time_stamps[0] - t0) if stream.n_samples > 0 else 0.0
        if stream.is_regular:
            _plot_regular_stream(plot_item, stream, t, stream_offset)
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
