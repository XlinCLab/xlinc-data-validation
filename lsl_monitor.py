import time
import pylsl

def monitor(interval=1.0, logfile="lsl_watchdog.log"):
    streams = pylsl.resolve_streams(wait_time=2.0)
    inlets = {}
    for s in streams:
        inlets[s.name()] = pylsl.StreamInlet(s, max_buflen=360, recover=False)
        print(f"attached: {s.name()} ({s.channel_count()} ch @ {s.nominal_srate()} Hz)")

    counts = {n: 0 for n in inlets}
    f = open(logfile, "w", buffering=1)
    while True:
        t = pylsl.local_clock()
        for name, inlet in inlets.items():
            chunk, stamps = inlet.pull_chunk(timeout=0.0)
            counts[name] += len(stamps)
            try:
                off = inlet.time_correction(timeout=0.5)
            except Exception as e:
                off = float("nan")
                f.write(f"{t:.3f} {name} TIME_CORRECTION_FAIL {e}\n")

            last = stamps[-1] if stamps else float("nan")
            f.write(f"{t:.3f} {name} n={len(stamps):5d} total={counts[name]:8d} "
                    f"lag={t - last:+.3f} off={off:+.4f}\n")

        time.sleep(interval)

monitor()