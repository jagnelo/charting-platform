import hashlib
import importlib.util
import json
from pathlib import Path


def load_queue_module():
    path = Path(__file__).parents[2] / "scripts" / "integration_queue.py"
    spec = importlib.util.spec_from_file_location("integration_queue_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_queue_uses_resolved_worktree_path_for_active_claim(tmp_path: Path) -> None:
    module = load_queue_module()
    branch = "feat/example"
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    alias = tmp_path / "worktree-alias"
    alias.symlink_to(worktree, target_is_directory=True)

    claim_root = tmp_path / "repo"
    claim_dir = claim_root / ".ai" / "session-claims"
    claim_dir.mkdir(parents=True)
    identifier = (
        f"{module.slug(branch)}-"
        f"{hashlib.sha256(str(worktree.resolve()).encode()).hexdigest()[:10]}"
    )
    (claim_dir / f"{identifier}.json").write_text(
        json.dumps({"session_id": "current-writer"})
    )

    module.records = lambda: [{"path": str(alias), "branch": branch}]
    module.values = lambda _: {
        "status": "ready_for_integration",
        "validation_tier": "full_integration",
    }
    module.git = lambda *args, **kwargs: {
        ("rev-parse", "HEAD"): "source-sha",
        ("rev-parse", f"origin/{branch}"): "source-sha",
        ("status", "--porcelain"): "",
        ("rev-list", "staging...source-sha"): "0 0",
    }.get(tuple(args), "")
    module.common_root = lambda: claim_root
    module.exact_ci = lambda *_: ("green", "passed")
    module.docker_disposition = lambda *_: ("clean", "no owned containers")

    result = module.queue()

    assert len(result) == 1
    assert result[0]["state"] == "in-progress"
    assert result[0]["reason"] == "active writer session current-writer"
