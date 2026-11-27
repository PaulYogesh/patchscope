from patchscope.provenance import source_tree_sha256


def test_source_fingerprint_detects_uncommitted_source_changes(tmp_path):
    (tmp_path / "patchscope").mkdir()
    source = tmp_path / "patchscope" / "agent.py"
    source.write_text("answer = 1\n")
    before = source_tree_sha256(tmp_path)
    source.write_text("answer = 2\n")
    assert before != source_tree_sha256(tmp_path)
    assert source_tree_sha256(tmp_path) == source_tree_sha256(tmp_path)
    # Generated caches and run outputs are intentionally excluded.
    fingerprint = source_tree_sha256(tmp_path)
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "unrelated.json").write_text("junk")
    assert source_tree_sha256(tmp_path) == fingerprint
