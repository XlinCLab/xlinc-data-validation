# Top-level keys of a single stream dict, as returned by pyxdf.load_xdf()
STREAM_TIME_SERIES = "time_series"
STREAM_TIME_STAMPS = "time_stamps"
STREAM_INFO = "info"

# Keys within a stream's "info" metadata dict
INFO_NAME = "name"
INFO_TYPE = "type"
INFO_HOSTNAME = "hostname"
INFO_NOMINAL_SRATE = "nominal_srate"
INFO_DESC = "desc"

# Nested keys under info.desc.channels.channel[] describing each channel
INFO_CHANNELS = "channels"
INFO_CHANNEL = "channel"
INFO_LABEL = "label"
INFO_UNIT = "unit"
