#!/usr/bin/env python3
"""Monitor live LSL streams while recording and log per-stream timing stats.

Resolves whatever LSL streams are on the network at startup and, once per interval,
logs each stream's sample count, pull lag, and clock offset to a logfile. Runs until
interrupted (Ctrl+C).

Usage:
    python3 -m lsl_monitor.lsl_monitor
    python3 -m lsl_monitor.lsl_monitor --logfile session1_watchdog.log --interval 0.5
"""

import argparse
import logging
import math
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


def log_summary(
        labels: dict,
        nominal_srates: dict,
        counts: dict,
        session_start: float,
        session_end: float,
        time_correction_fail_counts: dict,
        high_lag_counts: dict,
        startup_issue_counts: dict,
    ) -> None:
    """Log a per-stream end-of-session summary, flagging any stream that had issues.
    Issues suppressed as expected startup noise (see `startup_grace_period` in monitor())
    are reported separately and don't affect the OK/ISSUES verdict."""
    duration = session_end - session_start
    logger.info("=== Session summary ===")
    logger.info(f"Monitored {len(labels)} stream(s) for {duration:.1f}s")
    for uid, label in labels.items():
        total = counts[uid]
        effective_srate = total / duration if duration > 0 else 0.0
        nominal_srate = nominal_srates[uid]

        issues = []
        if total == 0:
            issues.append("no samples ever received")
        if time_correction_fail_counts[uid]:
            issues.append(f"{time_correction_fail_counts[uid]} time-correction failure(s)")
        if high_lag_counts[uid]:
            issues.append(f"{high_lag_counts[uid]} high-lag tick(s)")

        stats = f"{total} samples over {duration:.1f}s (~{effective_srate:.1f} Hz"
        stats += f", nominal {nominal_srate:.1f} Hz)" if nominal_srate > 0 else ")"
        if startup_issue_counts[uid]:
            stats += f" [{startup_issue_counts[uid]} startup issue(s) ignored]"

        if issues:
            logger.warning(f"{label}: {stats} -- ISSUES: {'; '.join(issues)}")
        else:
            logger.info(f"{label}: {stats} -- OK")


def monitor(
        logfile: str = None,
        interval: float = 1.0,
        wait_time: float = 2.0,
        max_buflen: int = 360,
        recover: bool = False,
        time_correction_timeout: float = 0.5,
        lag_threshold_periods: float = 10.0,
        startup_grace_period: float = 5.0,
    ) -> None:
    """Attach to all currently-resolvable LSL streams and log per-stream timing stats
    to `logfile` every `interval` seconds until interrupted. If `logfile` is not given,
    defaults to a timestamped file under logs/.

    For regularly-sampled streams, a tick whose lag (time since the last received sample)
    exceeds `lag_threshold_periods` times the stream's nominal sample period is logged as
    a warning instead of routine debug detail, since it suggests a stall or dropout.
    Irregularly-sampled streams (nominal rate 0, e.g. markers) are exempt from this check,
    since gaps between events are expected.

    A stream's first `time_correction()` call, and any high-lag tick within
    `startup_grace_period` seconds of that stream being attached, are expected artifacts of
    LSL's initial clock-sync and of catching up on backlog buffered during
    resolve_streams()/attach -- these are logged at a lower level and excluded from the
    WARNING-worthy issue counts, so only genuine mid-session problems get flagged. A
    per-stream summary is logged on exit."""
    logfile = logfile or default_logfile()
    configure_logging(logfile)
    logger.info(f"Logging to {logfile}")

    streams = pylsl.resolve_streams(wait_time=wait_time)

    # Count (name, hostname) occurrences so we only append a disambiguating uid suffix
    # to labels where name + hostname alone wouldn't be unique.
    name_hostname_counts = {}
    for s in streams:
        key = (s.name(), s.hostname())
        name_hostname_counts[key] = name_hostname_counts.get(key, 0) + 1

    inlets = {}
    labels = {}
    nominal_srates = {}
    attach_times = {}
    for s in streams:
        uid = s.uid()
        inlets[uid] = pylsl.StreamInlet(s, max_buflen=max_buflen, recover=recover)
        nominal_srates[uid] = s.nominal_srate()
        attach_times[uid] = pylsl.local_clock()
        label = f"{s.name()} ({s.hostname()})"
        if name_hostname_counts[(s.name(), s.hostname())] > 1:
            label += f" [{uid[:8]}]"
        labels[uid] = label
        logger.info(f"attached: {labels[uid]} ({s.channel_count()} ch @ {s.nominal_srate()} Hz)")

    counts = {uid: 0 for uid in inlets}
    last_seen = {uid: None for uid in inlets}
    time_correction_fail_counts = {uid: 0 for uid in inlets}
    high_lag_counts = {uid: 0 for uid in inlets}
    startup_issue_counts = {uid: 0 for uid in inlets}
    session_start = pylsl.local_clock()
    try:
        while True:
            t = pylsl.local_clock()
            for uid, inlet in inlets.items():
                label = labels[uid]
                nominal_srate = nominal_srates[uid]
                in_startup_grace = (t - attach_times[uid]) < startup_grace_period
                chunk, stamps = inlet.pull_chunk(timeout=0.0)
                counts[uid] += len(stamps)
                if stamps:
                    last_seen[uid] = stamps[-1]

                try:
                    off = inlet.time_correction(timeout=time_correction_timeout)
                except Exception as e:
                    off = float("nan")
                    if in_startup_grace:
                        startup_issue_counts[uid] += 1
                        logger.info(f"{label} TIME_CORRECTION_FAIL {e} (startup, ignored)")
                    else:
                        time_correction_fail_counts[uid] += 1
                        logger.warning(f"{label} TIME_CORRECTION_FAIL {e}")

                lag = t - last_seen[uid] if last_seen[uid] is not None else float("nan")
                message = (f"{label} n={len(stamps):5d} total={counts[uid]:8d} "
                           f"lag={lag:+.3f} off={off:+.4f}")

                lag_threshold = lag_threshold_periods / nominal_srate if nominal_srate > 0 else None
                if lag_threshold is not None and not math.isnan(lag) and lag > lag_threshold:
                    if in_startup_grace:
                        startup_issue_counts[uid] += 1
                        logger.debug(f"{message} -- high lag, but within startup grace period, ignored")
                    else:
                        high_lag_counts[uid] += 1
                        logger.warning(f"{message} -- lag exceeds {lag_threshold_periods:.0f} nominal "
                                        f"sample periods ({lag_threshold:.3f}s); possible stall/dropout")
                else:
                    logger.debug(message)

            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Stopped.")
    finally:
        log_summary(
            labels=labels,
            nominal_srates=nominal_srates,
            counts=counts,
            session_start=session_start,
            session_end=pylsl.local_clock(),
            time_correction_fail_counts=time_correction_fail_counts,
            high_lag_counts=high_lag_counts,
            startup_issue_counts=startup_issue_counts,
        )


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
    parser.add_argument("--lag-threshold-periods", type=float, default=10.0,
                         help="Flag a regularly-sampled stream's tick as a warning when its lag exceeds "
                              "this many nominal sample periods (irregularly-sampled streams, e.g. "
                              "markers, are exempt). Default: 10")
    parser.add_argument("--startup-grace-period", type=float, default=5.0,
                         help="Seconds after each stream is attached during which time-correction "
                              "failures and high lag are treated as expected startup noise rather "
                              "than warnings. Default: 5.0")
    args = parser.parse_args()

    monitor(
        logfile=args.logfile,
        interval=args.interval,
        wait_time=args.wait_time,
        max_buflen=args.max_buflen,
        recover=args.recover,
        time_correction_timeout=args.time_correction_timeout,
        lag_threshold_periods=args.lag_threshold_periods,
        startup_grace_period=args.startup_grace_period,
    )


if __name__ == "__main__":
    main()
