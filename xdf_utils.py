import numpy as np
from pyxdf import load_xdf

STREAM_TIMESTAMPS_LABEL = "time_stamps"


def get_stream_metadata(stream: dict, field: str, result_type = None) -> str:
    """Extract field from XDF stream metadata."""
    result = stream.get("info", {}).get(field, [""])
    if isinstance(result, list):
        result = result[0] if result else ""
    if result_type is not None:
        return result_type(result)
    return result


def get_stream_name(stream: dict) -> str:
    """Extract a stream's name from its metadata."""
    return get_stream_metadata(
        stream=stream,
        field="name",
        result_type=str,
    )


def get_stream_type(stream: dict) -> str:
    """Extract a stream's type from its metadata."""
    return get_stream_metadata(
        stream=stream,
        field="type",
        result_type=str,
    )


def get_nominal_srate(stream: dict) -> float:
    """Extract a stream's nominal sampling rate from its metadata."""
    return get_stream_metadata(
        stream=stream,
        field="nominal_srate",
        result_type=float,
    )


def get_stream_hostname(stream: dict) -> str:
    """Extract the hostname of a stream's source recording machine from its metadata."""
    return get_stream_metadata(
        stream=stream,
        field="hostname",
        result_type=str,
    )


def get_xdf_streams_by_type(
        stream_type: str,
        xdf_file: str = None,
        xdf_data: list = None,
        exclude_name_substring: str = None,
        verbose: bool = False,
        **kwargs
        ) -> list[dict]:
    """Fetches all streams matching a specific type from an XDF file (optionally preloaded),
    optionally excluding streams whose name contains a given substring (e.g. to exclude
    impedance-check streams which otherwise share the same type as the real data stream)."""
    if xdf_data is None:
        assert xdf_file is not None, "xdf_file argument is required if no xdf_data argument is provided"
        xdf_data, _ = load_xdf(xdf_file, verbose=verbose, **kwargs)
    matches = []
    for stream in xdf_data:
        stream_type_val = stream.get('info', {}).get('type', "")
        if isinstance(stream_type_val, list):
            stream_type_val = stream_type_val[0] if stream_type_val else ""
        if str(stream_type_val).lower() != str(stream_type).lower():
            continue
        if exclude_name_substring is not None:
            stream_name = stream.get('info', {}).get('name', [""])
            stream_name = stream_name[0] if isinstance(stream_name, list) and stream_name else stream_name
            if exclude_name_substring.lower() in str(stream_name).lower():
                continue
        matches.append(stream)
    return matches


def summarize_stream_gaps(stream: dict) -> dict:
    """Summarize sample-timing quality (gaps, effective vs. nominal rate) for a single
    regularly-sampled stream. Only meaningful for streams with a nonzero nominal sampling
    rate; use get_nominal_srate() to check first."""
    timestamps = np.asarray(stream["time_stamps"], dtype=np.float64)
    nominal_srate = get_nominal_srate(stream)
    n_samples = len(timestamps)

    if n_samples < 2 or nominal_srate <= 0:
        return {
            "n_samples": n_samples,
            "duration": 0.0,
            "effective_srate": 0.0,
            "nominal_srate": nominal_srate,
            "n_gaps": 0,
            "total_missing": 0,
            "max_gap_missing": 0,
        }

    duration = timestamps[-1] - timestamps[0]
    effective_srate = (n_samples - 1) / duration if duration > 0 else 0.0
    nominal_period = 1.0 / nominal_srate

    intervals = np.diff(timestamps)
    outlier_mask = intervals > (1.5 * nominal_period)
    outlier_gaps = intervals[outlier_mask]
    implied_missing = np.round(outlier_gaps / nominal_period).astype(int) - 1
    implied_missing = implied_missing[implied_missing > 0]

    return {
        "n_samples": n_samples,
        "duration": duration,
        "effective_srate": effective_srate,
        "nominal_srate": nominal_srate,
        "n_gaps": len(implied_missing),
        "total_missing": int(implied_missing.sum()) if len(implied_missing) else 0,
        "max_gap_missing": int(implied_missing.max()) if len(implied_missing) else 0,
    }


def classify_stream_gaps(summary: dict, expected_n_samples: int = None) -> str:
    """Classify a stream's gap summary (from summarize_stream_gaps()) into a human-readable
    verdict, optionally comparing its sample count against an expected value (e.g. the max
    across streams that should be time-aligned, to flag streams that cut off early)."""
    if summary["n_samples"] < 2:
        return "NO DATA"
    if expected_n_samples is not None and summary["n_samples"] < 0.5 * expected_n_samples:
        return "CORRUPT / TOO SHORT"
    # Sustained rate mismatch with no discrete gaps: every interval is a bit off nominal,
    # rather than a few isolated dropouts -- treat separately from the "ok" case since it
    # usually indicates a real clock deviation rather than dropped samples.
    if summary["n_gaps"] == 0:
        if summary["nominal_srate"] > 0:
            rate_ratio = summary["effective_srate"] / summary["nominal_srate"]
            if abs(1 - rate_ratio) > 0.02:
                return "SUSTAINED RATE MISMATCH (no discrete gaps, likely real clock deviation)"
        return "ok"
    missing_fraction = summary["total_missing"] / summary["n_samples"]
    if missing_fraction < 0.005:
        return "ok (negligible gaps)"
    if summary["n_gaps"] <= 3 and missing_fraction < 0.15:
        return "salvageable (few concentrated gaps)"
    return "SEVERE (many/large gaps)"
