"""Офлайн-проверка README-команд; JSON сохраняет реальные exit codes и вывод."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', default='evals/verification.json')
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    commands = [
        ['-m', 'strategist', 'doctor'],
        ['-m', 'unittest', 'discover', '-s', 'tests', '-v'],
        ['-m', 'strategist', '-p', 'projects/demo', 'validate', '--strategy'],
        ['-m', 'strategist', '-p', 'projects/demo', 'resume'],
        ['-m', 'strategist', '-p', 'projects/demo', 'analyze', 'SRC-4a27200479e7936b'],
        ['-m', 'strategist', '-p', 'projects/second', 'validate'],
        ['-m', 'strategist', '-p', 'projects/second', 'resume'],
        ['-m', 'strategist', '-p', '.', 'audit'],
    ]
    records = []
    for cmd in commands:
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run([sys.executable, *cmd], cwd=root, capture_output=True, text=True, timeout=90)
        records.append({'command': 'python ' + ' '.join(cmd), 'started_at': started,
                        'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        print(cmd, result.returncode)
    # Проверить ожидаемый провал плохого CSV отдельным вызовом; не называть провал успехом данных.
    cmd = ['-m', 'strategist', '-p', 'projects/demo', 'analyze', 'SRC-4193cc7c15c57c2d']
    result = subprocess.run([sys.executable, *cmd], cwd=root, capture_output=True, text=True, timeout=30)
    records.append({'command': 'python ' + ' '.join(cmd), 'exit_code': result.returncode,
                    'expected_exit_code': 2, 'stdout': result.stdout, 'stderr': result.stderr})
    valid = all(r['exit_code'] == r.get('expected_exit_code', 0) for r in records)
    target = root / a.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'valid': valid, 'checks': records, 'note': 'CLI/структурные тесты, не независимая экспертиза стратегии'}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if valid else 2)


if __name__ == '__main__':
    main()
