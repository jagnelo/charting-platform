"""Small shared identifiers for the isolated Nautilus worker wire protocol."""

NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1 = "strategy-lab.nautilus-runtime-bundle.v1"
NAUTILUS_RUNTIME_BUNDLE_SCHEMA = "strategy-lab.nautilus-runtime-bundle.v2"
NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3 = "strategy-lab.nautilus-runtime-bundle.v3"
NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE = (
    "application/vnd.charting.strategy-lab.strategy-context-stream+ndjson"
)
NAUTILUS_CONTEXT_STREAM_SCHEMA = "strategy-lab.strategy-runtime.context-stream.v2"
NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE = (
    "application/vnd.charting.strategy-lab.invocation-result-stream+ndjson"
)
NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA = "strategy-lab.strategy-runtime.result-stream.v1"
NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE = (
    "application/vnd.charting.strategy-lab.nautilus-event-stream+ndjson"
)
NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA = "strategy-lab.nautilus.native-event-stream.v1"


__all__ = [
    "NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE",
    "NAUTILUS_CONTEXT_STREAM_SCHEMA",
    "NAUTILUS_INVOCATION_RESULT_STREAM_MEDIA_TYPE",
    "NAUTILUS_INVOCATION_RESULT_STREAM_SCHEMA",
    "NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE",
    "NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA",
    "NAUTILUS_RUNTIME_BUNDLE_SCHEMA",
    "NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V1",
    "NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3",
]
