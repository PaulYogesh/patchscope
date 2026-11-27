"""Read-only file-execution evidence from a PUBLIC, separately declared reproducer.

Not a security sandbox. Caller must opt in to executing trusted fixture code.
Never derives paths from private/held-out pytest verification tests.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from patchscope.repair import temporary_repo

_MARKER = "PATCHSCOPE_PUBLIC_TRACE_V1:"
_BOOTSTRAP = r'''
import json, runpy, sys, traceback
from pathlib import Path
repo = Path(sys.argv[1]).resolve()
script = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(repo))
files = {}
def tracer(frame, event, arg):
    if event != 'line':
        return tracer
    try:
        fp = Path(frame.f_code.co_filename).resolve()
        relative = fp.relative_to(repo).as_posix()
    except (OSError, ValueError):
        return tracer
    if fp.suffix == '.py' and not fp.name.startswith('test_') and fp.name != 'conftest.py':
        files[relative] = files.get(relative, 0) + 1
    return tracer
sys.settrace(tracer)
failed, error_type = False, None
try:
    runpy.run_path(str(script), run_name='__main__')
except BaseException as exc:
    failed = True
    error_type = type(exc).__name__
finally:
    sys.settrace(None)
    print('PATCHSCOPE_PUBLIC_TRACE_V1:' + json.dumps({
        'reproducer_failed': failed, 'error_type': error_type,
        'executed_paths': sorted(files), 'line_events_by_file': files,
    }, sort_keys=True), flush=True)
'''


def trace_public_reproducer(repo: Path, script: Path, *, timeout: int = 15) -> dict:
    """Run a declared public reproducer in a disposable repository copy.

    A failing reproducer is required for an informative trace. No test code is
    shown to the agent and no oracle labels are consulted. Runtime execution
    should only be enabled for locally inspected, trusted code.
    """
    repo, script = Path(repo).resolve(), Path(script).resolve()
    if not repo.is_dir() or not script.is_file() or script.suffix != '.py':
        raise ValueError('invalid_public_reproducer')
    if script.is_relative_to(repo) or 'reproducers' not in script.parts:
        raise ValueError('reproducer_must_be_separate_public_script')
    if not 1 <= timeout <= 120:
        raise ValueError('invalid_public_trace_timeout')
    start = perf_counter()
    with temporary_repo(repo) as working:
        result = subprocess.run(
            [sys.executable, '-I', '-c', _BOOTSTRAP, str(working), str(script)],
            cwd=working, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
    trace_rows = [line[len(_MARKER):] for line in result.stdout.splitlines()
                  if line.startswith(_MARKER)]
    if result.returncode or len(trace_rows) != 1:
        raise ValueError('public_reproducer_trace_unavailable')
    trace = json.loads(trace_rows[0])
    if not trace.get('reproducer_failed'):
        raise ValueError('public_reproducer_did_not_reproduce_bug')
    paths = trace.get('executed_paths', [])
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise ValueError('invalid_public_trace_paths')
    return {
        'kind': 'public_execution_trace',
        'public_reproducer_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
        'reproducer_failed': True,
        'reproducer_error_type': trace.get('error_type'),
        'executed_paths': paths,
        'line_events_by_file': trace['line_events_by_file'],
        'elapsed_ms': round((perf_counter() - start) * 1000, 3),
    }


def render_trace_hint(trace: dict) -> str:
    paths = trace['executed_paths']
    return (
        'PUBLIC REPRODUCER EXECUTION EVIDENCE (not oracle labels):\n'
        'A separate reported-failure reproducer executed these repository Python files: '
        + (', '.join(paths) if paths else '(no repository files recorded)') + '\n'
        'Execution is not proof that any file is faulty; unexecuted code may still matter. '
        'Compare this observable execution evidence with the observed source before choosing an edit.'
    )
