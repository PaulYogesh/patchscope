import os
import py_compile

from patchscope.repair import run_pytest


def test_verification_reads_same_size_edit_with_stale_bytecode(tmp_path):
    module = tmp_path / "backoff.py"
    module.write_text("value = 8\n")
    (tmp_path / "test_contract.py").write_text(
        "from backoff import value\n\n"
        "def test_value():\n"
        "    assert value == 1\n"
    )
    # Seed a real timestamp-based cache, as a copied fixture could contain one.
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    import sys
    py_compile.compile(
        str(module),
        cfile=str(cache / f"backoff.{sys.implementation.cache_tag}.pyc"),
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
        doraise=True,
    )
    before = module.stat()
    assert not run_pytest(tmp_path)["passed"]
    module.write_text("value = 1\n")
    os.utime(module, ns=(before.st_atime_ns, before.st_mtime_ns))
    result = run_pytest(tmp_path)
    assert result["passed"], result["output"]
