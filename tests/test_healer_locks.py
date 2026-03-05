from apple_flow.healer_locks import (
    canonicalize_lock_keys,
    diff_paths_to_lock_keys,
    predict_lock_set,
)


def test_predict_lock_set_from_issue_text_paths():
    prediction = predict_lock_set(issue_text="fails in src/apple_flow/store.py and tests/test_store.py")
    assert prediction.keys
    assert prediction.source in {"path_level", "directory_escalation"}
    assert all(key.startswith(("path:", "dir:", "module:", "repo:")) for key in prediction.keys)


def test_predict_lock_set_falls_back_to_repo_lock():
    prediction = predict_lock_set(issue_text="no explicit file paths mentioned")
    assert prediction.keys == ["repo:*"]
    assert prediction.source == "coarse_repo_lock"


def test_diff_paths_to_lock_keys_escalates_for_large_sets():
    keys = diff_paths_to_lock_keys([f"src/pkg/file_{i}.py" for i in range(20)])
    assert keys
    assert all(key.startswith("dir:") for key in keys)


def test_canonicalize_lock_keys_dedupes_and_sorts():
    keys = canonicalize_lock_keys(["PATH:src/a.py", "path:src/a.py", "repo:*", ""])
    assert keys == ["path:src/a.py", "repo:*"]
