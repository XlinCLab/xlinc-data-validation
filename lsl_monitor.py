#!/usr/bin/env python3
"""Monitor live LSL streams while recording and log per-stream timing stats.

Resolves whatever LSL streams are on the network at startup and, once per interval,
logs each stream's sample count, pull lag, and clock offset to a logfile. Runs until
interrupted (Ctrl+C).

Usage:
    python lsl_monitor.py
    python lsl_monitor.py --logfile session1_watchdog.log --interval 0.5
"""

import argparse
import logging
import os
import time
from datetime import datetime

import pylsl

logger = logging.getLogger(__name__)

DEFAULT_LOG_DIR = "logs"


def default_logfile() -> str:
    """Build a timestamped path under logs directory."""
    os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(DEFAULT_LOG_DIR, f"lsl_watchdog_{timestamp}.log")


def configure_logging(logfile: str) -> None:
    """Attach a file handler (all levels) and a console handler (INFO+) to the module
    logger, so per-tick detail goes to `logfile` while notable events also print live."""
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')

    file_handler = logging.FileHandler(logfile, mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def monitor(
        logfile: str = None,
        interval: float = 1.0,
        wait_time: float = 2.0,
        max_buflen: int = 360,
        recover: bool = False,
        time_correction_timeout: float = 0.5,
    ) -> None:
    """Attach to all currently-resolvable LSL streams and log per-stream timing stats
    to `logfile` every `interval` seconds until interrupted. If `logfile` is not given,
    defaults to a timestamped file under logs/."""
    logfile = logfile or default_logfile()
    configure_logging(logfile)
    logger.info(f"Logging to {logfile}")

    streams = pylsl.resolve_streams(wait_time=wait_time)
    inlets = {}
    for s in streams:
        inlets[s.name()] = pylsl.StreamInlet(s, max_buflen=max_buflen, recover=recover)
        logger.info(f"attached: {s.name()} ({s.channel_count()} ch @ {s.nominal_srate()} Hz)")

    counts = {n: 0 for n in inlets}
    try:
        while True:
            t = pylsl.local_clock()
            for name, inlet in inlets.items():
                chunk, stamps = inlet.pull_chunk(timeout=0.0)
                counts[name] += len(stamps)
                try:
                    off = inlet.time_correction(timeout=time_correction_timeout)
                except Exception as e:
                    off = float("nan")
                    logger.warning(f"{name} TIME_CORRECTION_FAIL {e}")

                last = stamps[-1] if stamps else float("nan")
                logger.debug(f"{name} n={len(stamps):5d} total={counts[name]:8d} "
                             f"lag={t - last:+.3f} off={off:+.4f}")

            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor live LSL streams while recording and log per-stream timing "
                     "stats (sample counts, pull lag, clock offset) until interrupted."
    )
    parser.add_argument("-o", "--logfile", default=None,
                         help="Path to write the monitoring log to. "
                              "Default: logs/lsl_watchdog_<timestamp>.log")
    parser.add_argument("--interval", type=float, default=1.0,
                         help="Seconds between log ticks. Default: 1.0")
    parser.add_argument("--wait-time", type=float, default=2.0,
                         help="Seconds to wait when resolving streams at startup. Default: 2.0")
    parser.add_argument("--max-buflen", type=int, default=360,
                         help="Max buffer length (seconds) for each stream inlet. Default: 360")
    parser.add_argument("--recover", action="store_true",
                         help="Attempt to recover an inlet if its stream is lost. Default: off")
    parser.add_argument("--time-correction-timeout", type=float, default=0.5,
                         help="Timeout (seconds) for each stream's time_correction() call. Default: 0.5")
    args = parser.parse_args()

    monitor(
        logfile=args.logfile,
        interval=args.interval,
        wait_time=args.wait_time,
        max_buflen=args.max_buflen,
        recover=args.recover,
        time_correction_timeout=args.time_correction_timeout,
    )


if __name__ == "__main__":
    main()
