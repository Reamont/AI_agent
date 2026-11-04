"""Сохранение текущего реального прогона: тексты LLM явно отмечаются как self-recorded.

Это регистратор, не клиент модели и не генератор фиктивных ответов/новых чатов.
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from strategist.store import digest


class Trace:
    @classmethod
    def attach(cls, path):
        value=cls.__new__(cls)
        value.path=Path(path)
        if not value.path.is_file():
            raise ValueError('Трасса не существует')
        value.root=Path(__file__).resolve().parents[1]
        return value

    def __init__(self, path, task):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():
            raise ValueError('Трасса уже существует: не перезаписываем')
        self.root=Path(__file__).resolve().parents[1]
        self.append('metadata', {'task':task,'executor':'Текущий Codex-сеанс',
                    'independent_new_chat':False,'llm_text_provenance':'self-recorded by current assistant; no provider transcript API',
                    'paid_model_api_calls':0,'tokens':None,'model_price':None})

    def append(self, kind, payload):
        with self.path.open('a',encoding='utf-8') as f:
            f.write(json.dumps({'at':datetime.now(timezone.utc).isoformat(),'kind':kind,**payload},ensure_ascii=False)+'\n')

    def assistant(self, text):
        self.append('assistant_output',{'text':text,'origin':'current LLM, explicitly recorded; not an independent evaluation'})

    def command(self,*args,expected=0):
        command=['-m','strategist',*args]
        self.append('tool_call',{'tool':'Python CLI','argv':['python',*command]})
        result=subprocess.run([sys.executable,*command],cwd=self.root,capture_output=True,text=True,timeout=60)
        self.append('tool_output',{'exit_code':result.returncode,'expected_exit_code':expected,
                                 'stdout':result.stdout,'stderr':result.stderr,
                                 'stdout_sha256':digest(result.stdout.encode()),'stderr_sha256':digest(result.stderr.encode())})
        if result.returncode!=expected:
            raise RuntimeError(result.stderr or result.stdout)
        return json.loads(result.stdout) if result.stdout else None
