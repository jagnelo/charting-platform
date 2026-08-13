from pathlib import Path


def test_compose_host_ports_are_overrideable_for_isolated_acceptance_stacks():
    compose = (Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text()

    assert '"${POSTGRES_HOST_PORT:-5432}:5432"' in compose
    assert '"${BACKEND_HOST_PORT:-8000}:8000"' in compose
    assert '"${FRONTEND_HOST_PORT:-80}:80"' in compose


def test_research_runner_compose_contract_preserves_isolated_execution_boundary():
    """The service boundary is part of the Python sandbox, not optional deployment prose."""
    compose = (Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text()
    service = compose.split("  research-runner:\n", 1)[1].split("\n  # ── Vue frontend", 1)[0]

    assert 'network_mode: "none"' in service
    assert "read_only: true" in service
    assert "mem_limit: ${RESEARCH_CONTAINER_MEMORY_LIMIT:-768m}" in service
    assert 'cpus: "${RESEARCH_CONTAINER_CPUS:-1.0}"' in service
    assert "pids_limit: ${RESEARCH_CONTAINER_PIDS_LIMIT:-128}" in service
    assert 'user: "10001:10001"' in service
    assert 'cap_drop: ["ALL"]' in service
    assert '"no-new-privileges:true"' in service
    assert '"seccomp:./backend/seccomp/research-runner.json"' in service
    assert 'tmpfs: ["/tmp:rw,noexec,nosuid,size=64m"]' in service
    assert "- research_jobs:/jobs" in service
    assert "- research_results:/results" in service
    assert "RESEARCH_JOB_DIR: /jobs" in service
    assert "RESEARCH_RESULT_DIR: /results" in service
    assert "RESEARCH_MAX_OUTPUT_BYTES:" in service
    assert "RESEARCH_MAX_OUTPUT_ROWS:" in service
    assert "RESEARCH_MAX_OUTPUT_ARTIFACTS:" in service
    assert "RESEARCH_MAX_JOB_BYTES:" in service


def test_backend_compose_contract_shares_research_job_protocol_volumes():
    compose = (Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text()
    service = compose.split("  backend:\n", 1)[1].split("\n  # ── ARQ worker", 1)[0]

    assert "RESEARCH_JOB_DIR:  /jobs" in service
    assert "RESEARCH_RESULT_DIR: /results" in service
    assert "- research_jobs:/jobs" in service
    assert "- research_results:/results" in service


def test_worker_compose_contract_inherits_seed_and_workstation_bootstrap_flags():
    """Seed isolation must cover the worker, not only the HTTP backend."""
    compose = (Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text()
    service = compose.split("  worker:\n", 1)[1].split("\n  # User code never runs", 1)[0]

    assert "E2E_SEED_INSTRUMENTS: ${E2E_SEED_INSTRUMENTS:-false}" in service
    assert "E2E_SEED_MARKET_DATA: ${E2E_SEED_MARKET_DATA:-false}" in service
    assert "CORE_WORKSTATION_BOOTSTRAP_ENABLED: ${CORE_WORKSTATION_BOOTSTRAP_ENABLED:-false}" in service
    assert "CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS: ${CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS:-45}" in service


def test_research_runner_image_pins_curated_numerical_dependencies_and_thread_budget():
    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile.research-runner").read_text()

    assert '"numpy==2.1.3"' in dockerfile
    assert '"pandas==2.2.3"' in dockerfile
    assert '"scipy==1.14.1"' in dockerfile
    assert '"statsmodels==0.14.4"' in dockerfile
    assert "OPENBLAS_NUM_THREADS=1" in dockerfile
    assert "OMP_NUM_THREADS=1" in dockerfile
    assert "MKL_NUM_THREADS=1" in dockerfile
    assert "NUMEXPR_NUM_THREADS=1" in dockerfile


def test_research_runner_seccomp_profile_denies_namespace_escape_and_process_creation():
    import json

    profile = json.loads(
        (Path(__file__).resolve().parents[2] / "seccomp" / "research-runner.json").read_text()
    )
    denied = set(profile["syscalls"][0]["names"])

    assert profile["defaultAction"] == "SCMP_ACT_ALLOW"
    assert profile["syscalls"][0]["action"] == "SCMP_ACT_ERRNO"
    assert {"unshare", "setns", "mount", "ptrace", "clone", "clone3", "fork", "vfork"} <= denied


def test_live_resource_probe_is_bounded_and_requires_expected_failure_modes():
    probe = (Path(__file__).resolve().parents[3] / "ops" / "probe-research-runner-resources.sh").read_text()

    assert "memory=805306368" in probe
    assert "nano_cpus=1000000000" in probe
    assert "pids=128" in probe
    assert "run_expect memory-cgroup 137" in probe
    assert "run_expect tmpfs-capacity 1 'No space left on device'" in probe
    assert "2 * 1024 * 1024 * 1024" in probe
    assert "range(0, len(x), 4096)" in probe
    assert "256 * 1024 * 1024" in probe
    assert "70 * 1024 * 1024" in probe
    assert "pressure.bin" in probe
    assert "for index in 1 2 3 4 5 6 7 8" in probe
    assert "concurrent-memory: contained" in probe
    assert "restart_before" in probe and "restart_after" in probe


def test_live_recovery_probe_is_bounded_and_verifies_orphan_cleanup():
    probe = (Path(__file__).resolve().parents[3] / "ops" / "probe-research-runner-recovery.sh").read_text()

    assert "isolated research runner" in probe
    assert "100000000" in probe
    assert "docker kill" in probe
    assert "StartedAt" in probe
    assert ".running" in probe
    assert ".processed" in probe
    assert ".cancel" in probe
    assert "progress.json" in probe
    assert '"status":"completed"' in probe


def test_live_sustained_probe_overlaps_cancellation_and_success_without_leaking_sentinels():
    probe = (Path(__file__).resolve().parents[3] / "ops" / "probe-research-runner-sustained.sh").read_text()

    assert "TC2000_RUNNER_STRESS_ROUNDS" in probe
    assert "600" in probe
    assert ".cancel" in probe
    assert ".running" in probe
    assert ".processed" in probe
    assert "progress.json" in probe
    assert '"status":"canceled"' in probe
    assert '"status":"completed"' in probe
