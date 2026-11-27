from pathlib import Path

from patchscope.evidence_exposure import visible_importers, render_exposure_markdown


def test_static_absolute_importers(tmp_path):
    (tmp_path / 'policy.py').write_text('def f():\n    return 1\n')
    (tmp_path / 'compat.py').write_text('def g():\n    return 1\n')
    (tmp_path / 'service.py').write_text('from policy import f\n')
    (tmp_path / 'other.py').write_text('import policy as p\n')
    (tmp_path / 'test_service.py').write_text('from compat import g\n')
    assert visible_importers(tmp_path, 'policy.py') == ['other.py', 'service.py']
    assert visible_importers(tmp_path, 'compat.py') == []


def test_markdown_exposure_rendering():
    result = {'n_distinct_tasks': 1,
              'summary': {'decoy_observed': 1, 'decoy_first_read': 1,
                          'decoy_wrong_locus_patches': 1, 'decoy_failures': 1},
              'rows': [{'task_id': 'task1', 'extra_path': 'compat.py',
                        'static_oracle_importers': ['service.py'],
                        'decoy_extra_file_patch': True, 'decoy_verified': False,
                        'exposures': {'neutral': {'first_read': 'compat.py'},
                                      'decoy': {'first_read': 'compat.py',
                                                'extra_file_observed': True,
                                                'oracle_observed': False}}}]}
    report = render_exposure_markdown({'expanded': result})
    assert 'service.py' in report and 'task1' in report
    assert 'causal mediation' in report


def test_expanded_fixture_import_structure():
    root = Path(__file__).resolve().parents[1]
    import json
    manifest = json.loads((root / 'experiments/benchmark-decoy-v040.json').read_text())
    assert len(manifest['tasks']) == 8
    for task in manifest['tasks']:
        repo = root / task['repo_path']
        assert visible_importers(repo, task['oracle']['paths'][0]) == ['service.py']
        assert visible_importers(repo, task['misleading_pool'][0]) == []
