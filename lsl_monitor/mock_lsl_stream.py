#!/usr/bin/env python3
"""Emit fake LSL streams for locally testing lsl_monitor.py without real hardware.

Starts a regularly-sampled stream (e.g. a fake EEG stream) and, optionally, an
irregularly-sampled marker/event stream, and pushes synthetic samples to them in real
time over loopback so lsl_monitor.py (or any other LSL tool) can discover and monitor
them exactly as it would a real device. Runs until interrupted (Ctrl+C).

Usage:
    # plain, well-behaved stream
    python3 -m lsl_monitor.mock_lsl_stream

    # inject dropouts and jitter to see lsl_monitor.py react to bad data
    python3 -m lsl_monitor.mock_lsl_stream --srate 500 --n-channels 16 --dropout-prob 0.01 --jitter 0.01
"""

import argparse
import random
import threading
import time

import numpy as np
import pylsl


def run_regular_stream(
        name: str,
        stype: str,
        n_channels: int,
        srate: float,
        dropout_prob: float,
        gap_size: int,
        jitter: float,
    ) -> None:
    """Push random samples to a regularly-sampled outlet at `srate` Hz forever. On each
    tick, with probability `dropout_prob`, skip `gap_size` consecutive samples instead of
    pushing (simulating a dropout/gap); otherwise push a sample, optionally jittering its
    timing by up to +/- `jitter` seconds (simulating unstable buffering)."""
    info = pylsl.StreamInfo(name, stype, n_channels, srate, "float32", f"mock_{name}")
    outlet = pylsl.StreamOutlet(info)
    print(f"streaming: {name} ({n_channels} ch @ {srate} Hz)")

    period = 1.0 / srate
    start = pylsl.local_clock()
    tick = 0
    while True:
        if dropout_prob > 0 and random.random() < dropout_prob:
            tick += gap_size
            continue

        outlet.push_sample(np.random.randn(n_channels).tolist())
        tick += 1
        target = start + tick * period
        if jitter:
            target += random.uniform(-jitter, jitter)

        sleep_time = target - pylsl.local_clock()
        if sleep_time > 0:
            time.sleep(sleep_time)


def run_marker_stream(name: str, min_interval: float, max_interval: float) -> None:
    """Push an incrementing string marker at random intervals, forever."""
    info = pylsl.StreamInfo(name, "Markers", 1, pylsl.IRREGULAR_RATE, "string", f"mock_{name}")
    outlet = pylsl.StreamOutlet(info)
    print(f"streaming: {name} (markers)")

    i = 0
    while True:
        time.sleep(random.uniform(min_interval, max_interval))
        i += 1
        outlet.push_sample([f"event_{i}"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Emit fake LSL streams for locally testing lsl_monitor.py (or other "
                     "LSL tools) without real hardware."
    )
    parser.add_argument("--name", default="MockEEG", help="Name of the regularly-sampled stream. Default: MockEEG")
    parser.add_argument("--type", default="EEG", help="Type of the regularly-sampled stream. Default: EEG")
    parser.add_argument("--n-channels", type=int, default=8, help="Channel count. Default: 8")
    parser.add_argument("--srate", type=float, default=250.0, help="Nominal sampling rate (Hz). Default: 250.0")
    parser.add_argument("--dropout-prob", type=float, default=0.0,
                         help="Probability per sample tick of skipping --gap-size samples, to simulate a "
                              "dropout. Default: 0 (no dropouts)")
    parser.add_argument("--gap-size", type=int, default=5,
                         help="Number of consecutive samples to skip on a simulated dropout. Default: 5")
    parser.add_argument("--jitter", type=float, default=0.0,
                         help="Max +/- seconds of random jitter to add to each sample's timing. "
                              "Default: 0 (perfectly regular)")
    parser.add_argument("--no-markers", action="store_true",
                         help="Don't also stream a mock irregularly-sampled marker/event stream")
    args = parser.parse_args()

    threads = [threading.Thread(
        target=run_regular_stream,
        args=(args.name, args.type, args.n_channels, args.srate, args.dropout_prob, args.gap_size, args.jitter),
        daemon=True,
    )]
    if not args.no_markers:
        threads.append(threading.Thread(
            target=run_marker_stream, args=("MockMarkers", 2.0, 5.0), daemon=True,
        ))

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
