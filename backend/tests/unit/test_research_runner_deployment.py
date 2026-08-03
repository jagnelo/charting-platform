from pathlib import Path


def test_research_runner_compose_contract_preserves_isolated_execution_boundary():
    """The service boundary is part of the Python sandbox, not optional deployment prose."""
    compose = (Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text()
    service = compose.split("  research-runner:\n", 1)[1].split("\n  # ── Vue frontend", 1)[0]

    assert 'network_mode: "none"' in service
    assert "read_only: true" in service
    assert 'user: "10001:10001"' in service
    assert 'cap_drop: ["ALL"]' in service
    assert 'security_opt: ["no-new-privileges:true"]' in service
    assert 'tmpfs: ["/tmp:rw,noexec,nosuid,size=64m"]' in service
    assert "- research_jobs:/jobs" in service
    assert "- research_results:/results" in service
    assert "RESEARCH_JOB_DIR: /jobs" in service
    assert "RESEARCH_RESULT_DIR: /results" in service


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
