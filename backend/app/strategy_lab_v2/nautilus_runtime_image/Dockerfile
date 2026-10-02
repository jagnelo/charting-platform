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

COPY __init__.py app/strategy_lab_v2/__init__.py
COPY canonical.py app/strategy_lab_v2/canonical.py
COPY conformance.py app/strategy_lab_v2/conformance.py
COPY nautilus_runtime_data.py app/strategy_lab_v2/nautilus_runtime_data.py
COPY nautilus_runtime_adapter.py app/strategy_lab_v2/nautilus_runtime_adapter.py
COPY nautilus_runtime_adapter_probe.py app/strategy_lab_v2/nautilus_runtime_adapter_probe.py
COPY nautilus_runtime_probe.py app/strategy_lab_v2/nautilus_runtime_probe.py
COPY nautilus_rc_fixture_probe.py app/strategy_lab_v2/nautilus_rc_fixture_probe.py

ENTRYPOINT ["python", "-m", "app.strategy_lab_v2.nautilus_runtime_probe"]
CMD ["--expected-version", "2.0.0rc5"]
