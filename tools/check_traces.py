"""Целостность записанных инструментов; не оценка качества/независимости LLM."""
import json
from pathlib import Path
from strategist.store import digest


def main():
    root=Path(__file__).resolve().parents[1];results=[]
    for path in sorted((root/'evals/llm-traces').glob('*.jsonl')):
        records=[json.loads(line) for line in path.read_text().splitlines()]
        errors=[];calls=0;pending=False;resume_at=None;new_input_at=None
        for entry in records:
            if entry['kind']=='tool_call':
                if pending:errors.append('Вызов без результата')
                pending=True;calls+=1
                if entry['argv'][-1]=='resume':resume_at=entry['at']
            if entry['kind']=='tool_output':
                if not pending:errors.append('Результат без вызова')
                pending=False
                for stream in ['stdout','stderr']:
                    if digest(entry[stream].encode())!=entry[stream+'_sha256']:errors.append('Изменён '+stream)
                if entry['exit_code']!=entry['expected_exit_code']:errors.append('Неожиданный код возврата')
            if entry['kind']=='input_artifact':
                new_input_at=entry['at']
                if digest(entry['content'].encode())!=entry['sha256']:errors.append('Изменён входной материал')
        if pending:errors.append('Последний вызов не завершён')
        if new_input_at and (not resume_at or new_input_at<=resume_at):errors.append('Новый материал не следует за resume')
        results.append({'path':str(path.relative_to(root)),'valid':not errors,'errors':errors,'tool_calls':calls,
                        'new_input_after_resume':bool(new_input_at and resume_at and new_input_at>resume_at),
                        'independent_new_chat':records[0]['independent_new_chat'],'sha256':digest(path.read_bytes())})
    result={'valid':bool(results) and all(r['valid'] for r in results),'traces':results,
            'scope':'Целостность входов/команд/результатов; LLM self-recorded, не provider transcript и не независимая оценка'}
    (root/'evals/traces-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['valid'] else 2)


if __name__=='__main__':main()
