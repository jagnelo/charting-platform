from __future__ import annotations

from dataclasses import replace

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.runtime import (
    RuntimeIsolationDecision,
    RuntimeIsolationProfile,
    RuntimeIsolationRequest,
    preflight_runtime_isolation,
)

IMAGE = content_digest({"image": "strategy-runtime-v2"})
DEPENDENCY = content_digest({"distribution": "numpy", "version": "2.0.0"})


def _profile() -> RuntimeIsolationProfile:
    return RuntimeIsolationProfile(
        runtime_image_digest=IMAGE,
        runtime_abi="cp312-manylinux",
        allowed_dependency_digests=frozenset({DEPENDENCY}),
    )


def test_isolation_preflight_allows_pinned_non_network_execution() -> None:
    request = RuntimeIsolationRequest("attempt-1", (DEPENDENCY,))
    report = preflight_runtime_isolation(_profile(), request)
    assert report.accepted
    assert report.decision is RuntimeIsolationDecision.ALLOW
    assert not report.rejection_reasons
    assert report.fingerprint.startswith("sha256:")


def test_isolation_preflight_rejects_insecure_profile_and_requests() -> None:
    profile = replace(
        _profile(),
        network_disabled=False,
        read_only_root=False,
        capabilities_dropped=False,
        secrets_disabled=False,
    )
    request = RuntimeIsolationRequest(
        "attempt-1",
        dependency_digests=(content_digest({"distribution": "unknown"}),),
        network_requested=True,
        writable_paths_requested=("/tmp/output",),
        secret_names_requested=("API_KEY",),
    )
    report = preflight_runtime_isolation(profile, request)
    assert report.decision is RuntimeIsolationDecision.REJECT
    assert {
        "network_must_be_disabled",
        "root_filesystem_must_be_read_only",
        "container_capabilities_must_be_dropped",
        "runtime_secrets_must_be_disabled",
        "strategy_requested_network_access",
        "strategy_requested_writable_paths",
        "strategy_requested_secrets",
        "dependency_digest_not_vetted",
    } == set(report.rejection_reasons)
    assert len(report.missing_dependency_digests) == 1


def test_isolation_contract_rejects_invalid_pins_limits_and_request_values() -> None:
    with pytest.raises(ValueError, match="runtime_image_digest"):
        RuntimeIsolationProfile("bad", "cp312")
    with pytest.raises(ValueError, match="positive integer"):
        replace(_profile(), wall_timeout_seconds=0)
    with pytest.raises(ValueError, match="dependency digests"):
        RuntimeIsolationRequest("attempt-1", (DEPENDENCY, DEPENDENCY))
    with pytest.raises(ValueError, match="secret_names_requested"):
        RuntimeIsolationRequest("attempt-1", secret_names_requested=("",))


def test_isolation_report_rejects_inconsistent_manual_records() -> None:
    with pytest.raises(ValueError, match="allowed isolation"):
        from app.strategy_lab_v2.runtime import RuntimeIsolationReport

        RuntimeIsolationReport(
            RuntimeIsolationDecision.ALLOW,
            _profile().fingerprint,
            RuntimeIsolationRequest("attempt-1").fingerprint,
            rejection_reasons=("unexpected",),
        )
