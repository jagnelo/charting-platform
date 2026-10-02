# Build from the backend directory so the isolated image can copy only the
# package-owned probe/contracts. Every mutable input is supplied explicitly by
# the build caller; there is intentionally no fallback to the backend v1 image.
ARG PYTHON_BASE_IMAGE
FROM ${PYTHON_BASE_IMAGE}

ARG NAUTILUS_WHEEL_URL
ARG NAUTILUS_WHEEL_SHA256
ARG NAUTILUS_WHEEL_FILENAME

WORKDIR /opt/strategy-lab-v2

RUN test -n "${NAUTILUS_WHEEL_URL}" \
    && test -n "${NAUTILUS_WHEEL_SHA256}" \
    && test -n "${NAUTILUS_WHEEL_FILENAME}"

ADD --checksum=sha256:${NAUTILUS_WHEEL_SHA256} ${NAUTILUS_WHEEL_URL} /tmp/${NAUTILUS_WHEEL_FILENAME}
RUN python -m pip install --no-cache-dir --no-deps /tmp/${NAUTILUS_WHEEL_FILENAME} \
    && rm -f /tmp/${NAUTILUS_WHEEL_FILENAME}

COPY app/strategy_lab_v2/__init__.py app/strategy_lab_v2/__init__.py
COPY app/strategy_lab_v2/canonical.py app/strategy_lab_v2/canonical.py
COPY app/strategy_lab_v2/capabilities.py app/strategy_lab_v2/capabilities.py
COPY app/strategy_lab_v2/contracts.py app/strategy_lab_v2/contracts.py
COPY app/strategy_lab_v2/decimal_math.py app/strategy_lab_v2/decimal_math.py
COPY app/strategy_lab_v2/observations.py app/strategy_lab_v2/observations.py
COPY app/strategy_lab_v2/rebalance.py app/strategy_lab_v2/rebalance.py
COPY app/strategy_lab_v2/sdk.py app/strategy_lab_v2/sdk.py
COPY app/strategy_lab_v2/strategy_validation.py app/strategy_lab_v2/strategy_validation.py
COPY app/strategy_lab_v2/conformance.py app/strategy_lab_v2/conformance.py
COPY app/strategy_lab_v2/nautilus_runtime_data.py app/strategy_lab_v2/nautilus_runtime_data.py
COPY app/strategy_lab_v2/nautilus_runtime_adapter.py app/strategy_lab_v2/nautilus_runtime_adapter.py
COPY app/strategy_lab_v2/nautilus_strategy_bridge.py app/strategy_lab_v2/nautilus_strategy_bridge.py
COPY app/strategy_lab_v2/nautilus_runtime_adapter_probe.py app/strategy_lab_v2/nautilus_runtime_adapter_probe.py
COPY app/strategy_lab_v2/nautilus_runtime_probe.py app/strategy_lab_v2/nautilus_runtime_probe.py
COPY app/strategy_lab_v2/nautilus_runtime_protocol.py app/strategy_lab_v2/nautilus_runtime_protocol.py
COPY app/strategy_lab_v2/nautilus_runtime_cli.py app/strategy_lab_v2/nautilus_runtime_cli.py
COPY app/strategy_lab_v2/nautilus_rc_fixture_probe.py app/strategy_lab_v2/nautilus_rc_fixture_probe.py
COPY strategy_runtime/__init__.py strategy_runtime/__init__.py
COPY strategy_runtime/protocol.py strategy_runtime/protocol.py
COPY strategy_runtime/runner.py strategy_runtime/runner.py

CMD ["python", "-m", "app.strategy_lab_v2.nautilus_runtime_cli", "--probe", "--expected-version", "2.0.0rc5"]
