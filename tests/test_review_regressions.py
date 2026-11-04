"""Воспроизведения замечаний ревью, а не тесты текстовых шаблонов агента."""
import copy
import json
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_workflow
from strategist import engine
from strategist.ingest import ingest, extract
from strategist.store import Problem, load, init, transaction, atomic, envelope, digest, checkpoint
from strategist.package import pack


class ReviewRegressions(unittest.TestCase):
    setUp = test_workflow.Workflow.setUp
    tearDown = test_workflow.Workflow.tearDown
    source = test_workflow.Workflow.source
    claim = test_workflow.Workflow.claim
    def decision(self, **changes):
        value = {"id": "D1", "status": "proposed", "decision": "Проверить задачу до инвестиций",
                 "selected_option": "O1", "decision_maker": "не назначен", "owner": "не назначен",
                 "basis": ["C1"], "alternatives": ["O1", "O2"], "assumptions": ["Учебная задача"],
                 "actions": [{"action": "Проверить", "owner": "не назначен"}], "metrics": ["проверяемость"],
                 "deadline": "не задан", "review_if": "Изменение источника"}
        value.update(changes)
        return value

    def promise(self):
        return {"id": "P1", "basis": ["C1"], "message": "Текущая возможность", "capability": "Capability",
                "available": True, "limitation": "Только фикстура", "allowed_wording": "Учебная возможность"}

    def strategy(self, **changes):
        value = json.loads((Path(__file__).resolve().parents[1] / 'projects/demo/outputs/strategy.json').read_text())
        value.update(basis=["C1"], promise_ids=["P1"])
        value.update(changes)
        return value

    def prepare(self):
        sid = self.source()
        self.claim(sid)
        engine.add_record(self.root, "promises", self.promise())
        return sid

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'strategist', '-p', str(self.root), *args], text=True, capture_output=True)

    def test_r01_sparse_xlsx_c3(self):
        from openpyxl import Workbook
        import io
        wb = Workbook()
        wb.active['C3'] = 'Только C3'
        buffer = io.BytesIO()
        wb.save(buffer)
        wb.close()
        chunks = extract(buffer.getvalue(), '.xlsx')['chunks']
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['locator'], 'Sheet!A3:C3')
        self.assertIn('Только C3', chunks[0]['text'])

    def test_r02_tampered_csv_no_result_overwrite(self):
        sid = self.source('period,cohort,eligible,retained\n2026-01,A,100,40\n', 'numbers.csv')
        engine.analyze(self.root, sid)
        result_path = self.root/f'evidence/analysis-{sid}.json'
        original = result_path.read_bytes()
        s = load(self.root)
        (self.root/s['sources'][sid]['path']).write_text('period,cohort,eligible,retained\n2026-01,A,100,99\n')
        with self.assertRaises(Problem):
            engine.analyze(self.root, sid)
        self.assertEqual(result_path.read_bytes(), original)
        self.assertEqual(load(self.root)['revision'], s['revision'])

    def test_r03_dedup_still_links_replacement_and_invalidates(self):
        old = self.source()
        self.claim(old)
        new = self.source('New data', 'new.md')
        result = ingest(self.root, self.base/'new.md', supersedes=old)
        self.assertTrue(result['deduplicated'])
        self.assertIn('C1', result['impact']['claims'])
        s = load(self.root)
        self.assertIn(old, s['sources'][new]['supersedes_ids'])
        self.assertEqual(s['claims']['C1']['status'], 'needs_review')
        version = s['claims']['C1']['version']
        ingest(self.root, self.base/'new.md', supersedes=old)
        self.assertEqual(load(self.root)['claims']['C1']['version'], version)
        with self.assertRaises(Problem):
            ingest(self.root, self.base/'new.md', supersedes='missing')

    def test_r04_replaced_source_cannot_support_current_fact(self):
        old = self.source()
        self.source('New data', 'new.md', supersedes=old)
        self.claim(old)
        self.assertEqual(load(self.root)['claims']['C1']['status'], 'needs_review')
        with transaction(self.root, 'tamper', 'Воспроизвести некорректный current') as s:
            s['claims']['C1']['status'] = 'current'
        self.assertFalse(engine.validate(self.root)['valid'])

    def test_r05_counterevidence_invalidates_and_versions(self):
        sid = self.source()
        self.claim(sid)
        self.claim(sid, 'C2', type='hypothesis', references=[], counterevidence=['C1'])
        engine.revise(self.root, 'C1', 'refuted', 'Контрсвидетельство изменилось')
        s = load(self.root)
        self.assertEqual(s['claims']['C2']['status'], 'needs_review')
        self.assertEqual(s['claims']['C2']['version'], 2)
        self.assertEqual(s['claims']['C1']['version'], 2)

    def test_r06_resaving_stale_strategy_does_not_clear_review(self):
        self.prepare()
        st = self.strategy()
        engine.set_strategy(self.root, st)
        engine.revise(self.root, 'C1', 'refuted', 'New evidence')
        result = engine.set_strategy(self.root, st)
        self.assertEqual(result['status'], 'needs_review')

    def test_r07_strategy_depends_on_promise_not_only_direct_basis(self):
        sid = self.prepare()
        self.claim(sid, 'C2')
        engine.set_strategy(self.root, self.strategy(basis=['C2']))
        result = engine.revise(self.root, 'C1', 'refuted', 'Changed promised capability')
        self.assertTrue(result['strategy'])
        self.assertEqual(load(self.root)['strategy']['status'], 'needs_review')

    def test_r08_impact_and_validate_show_strategy(self):
        self.prepare()
        engine.set_strategy(self.root, self.strategy())
        engine.revise(self.root, 'C1', 'refuted', 'New evidence')
        result = self.cli('impact')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(json.loads(result.stdout)['strategy'])
        self.assertIn('strategy: требует пересмотра', engine.validate(self.root, True)['warnings'])

    def test_r09_invalid_config_and_nonfinite_limits(self):
        config = load(self.root)['config']
        invalids = [{}, None, [], {**config, 'name': ''}]
        for key in ('money_limit', 'time_budget_minutes'):
            for value in (float('nan'), float('inf'), '100', True, -1):
                invalids.append({**config, key: value})
        for i, cfg in enumerate(invalids):
            with self.subTest(cfg=cfg), self.assertRaises(Problem):
                init(self.base/f'invalid-{i}', cfg)
        with self.assertRaises(Problem):
            engine.budget(self.root, amount=True)

    def test_r10_progress_wrong_types_are_rejected(self):
        for update in [{'pending':[{'id':'P','status':'banana'}]}, {'next_action':None}, {'errors':None}, {'pending':[None]}]:
            p = self.base/'progress.json'
            p.write_text(json.dumps(update))
            result = self.cli('progress', str(p))
            self.assertEqual(result.returncode, 2)
            self.assertIn('error', json.loads(result.stderr))
            self.assertTrue(engine.validate(self.root)['valid'])

    def test_r11_malformed_json_shapes_and_documents_return_json_errors(self):
        for command, value in [('strategy', {'options':[None]}), ('strategy', []), ('claim', None), ('decision', [])]:
            p = self.base/'malformed.json'
            p.write_text(json.dumps(value))
            result = self.cli(command, str(p))
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(json.loads(result.stderr)['status'], 'error')
        for suffix in ['.pdf','.docx','.xlsx']:
            p = self.base/('broken'+suffix)
            p.write_text('not a real document')
            result = self.cli('ingest', str(p))
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)
            json.loads(result.stderr)
        self.assertEqual(load(self.root)['events'][-1]['status'], 'error')

    def test_r12_decision_lifecycle_and_confirmation_artifact(self):
        self.prepare()
        engine.add_record(self.root, 'decisions', self.decision())
        approval = {'decision_id':'D1','selected_option':'O1','decision_maker':'Учебный согласующий','approved':True}
        path = self.root/'decisions/approval.json'
        path.write_text(json.dumps(approval))
        confirmed = engine.update_record(self.root, 'decisions', {'id':'D1','status':'confirmed','decision_maker':'Учебный согласующий',
            'human_confirmation':{'artifact':'decisions/approval.json','sha256':digest(path.read_bytes())}}, 'Синтетический тест подтверждения')
        self.assertEqual(confirmed['version'],2)
        self.assertEqual(confirmed['history'][-1]['before']['status'],'proposed')
        rejected = engine.update_record(self.root,'decisions',{'id':'D1','status':'rejected','owner':'Учебный исполнитель'},'Изменение тестового выбора')
        self.assertEqual(rejected['version'],3)
        self.assertEqual(rejected['decision_maker'],'Учебный согласующий')
        self.assertEqual(len(load(self.root)['decisions']),1)

    def test_r12_promise_review_requires_current_basis_and_review_note(self):
        sid = self.prepare()
        engine.revise(self.root,'C1','refuted','Old capability changed')
        with self.assertRaises(Problem):
            engine.update_record(self.root,'promises',{'id':'P1','status':'current','review_note':'Проверено'},'Review')
        self.claim(sid,'C2')
        with self.assertRaises(Problem):
            engine.update_record(self.root,'promises',{'id':'P1','basis':['C2'],'status':'current'},'Review')
        p=engine.update_record(self.root,'promises',{'id':'P1','basis':['C2'],'status':'current','review_note':'Новая точная цитата C2'},'Review')
        self.assertEqual(p['status'],'current')
        self.assertEqual(p['version'],3)

    def test_r13_decision_requires_actual_choice_and_decision_maker(self):
        self.prepare()
        for key in ('decision','selected_option','decision_maker'):
            d=self.decision();del d[key]
            with self.assertRaises(Problem):engine.add_record(self.root,'decisions',d)

    def test_r15_corrupt_history_and_unavailable_artifacts_distinct(self):
        sid = self.prepare()
        checkpoint(self.root,'Inspect evidence')
        source = load(self.root)['sources'][sid]
        old = self.root/source['path']
        new = self.root/'sources/new-path.md'
        new.write_bytes(old.read_bytes())
        with transaction(self.root,'move_fixture','Сохранить текущее представление') as s:
            s['sources'][sid]['path']='sources/new-path.md'
            for rep in s['sources'][sid].get('representations',[]):rep['path']='sources/new-path.md'
        old.unlink()
        result = engine.validate(self.root)
        self.assertTrue(result['valid'])
        self.assertTrue(any(not v['artifacts_restorable'] for v in result['history']))
        (self.root/'state/history/000000.json').write_text('{}')
        self.assertFalse(engine.validate(self.root)['valid'])

    def test_r16_strategy_validation_uses_locked_state(self):
        self.prepare()
        original = transaction
        @contextmanager
        def controlled(*args,**kwargs):
            with original(self.root,'race','Контролируемое изменение') as s:s['claims']['C1']['status']='refuted'
            with original(*args,**kwargs) as s:yield s
        with patch('strategist.engine.transaction',controlled):
            result=engine.set_strategy(self.root,self.strategy())
        self.assertEqual(result['status'],'needs_review')

    def test_r17_search_decision_id_and_promise_content(self):
        self.prepare()
        engine.add_record(self.root,'decisions',self.decision())
        self.assertEqual(engine.search(self.root,'D1')[0]['id'],'D1')
        self.assertTrue(any(r['kind']=='promises' for r in engine.search(self.root,'Текущая возможность')))

    def test_r18_rejection_and_invalid_analysis_not_logged_as_success(self):
        engine.budget(self.root,amount=999)
        e=load(self.root)['events'][-1]
        self.assertEqual(e['status'],'blocked')
        self.assertEqual(e['cost'],0)
        self.assertEqual(e['requested_cost'],999)
        self.assertEqual(e['transaction_status'],'committed')
        sid=self.source('period,cohort,eligible,retained\n2026-01,A,,5\n','bad.csv')
        engine.analyze(self.root,sid)
        self.assertEqual(load(self.root)['events'][-1]['status'],'invalid')

    def test_r19_account_actual_time_separately_from_reservation(self):
        engine.budget(self.root,amount=0,minutes=3)
        self.assertEqual(load(self.root)['budget']['elapsed_minutes'],0)
        engine.account_time(self.root,2,'Тестовый фактический интервал','synthetic timer','T1')
        b=load(self.root)['budget']
        self.assertEqual(b['elapsed_minutes'],2)
        self.assertEqual(b['reserved_minutes'],1)
        with self.assertRaises(Problem):engine.account_time(self.root,2,'Duplicate','timer','T1')

    def test_r20_legacy_stable_id_deduplicates_by_representation(self):
        sid=self.source()
        with transaction(self.root,'migrate_fixture','Другой стабильный ID') as s:
            source=s['sources'].pop(sid);source['id']='SRC-original-identity';s['sources'][source['id']]=source
        self.assertEqual(ingest(self.root,self.base/'brief.md')['id'],'SRC-original-identity')
        self.assertEqual(len(load(self.root)['sources']),1)

    def test_r21_fixture_generator_preserves_existing_csv(self):
        folder=self.base/'fixtures';folder.mkdir()
        existing=folder/'cohorts.csv';existing.write_text('KEEP ORIGINAL')
        script=Path(__file__).resolve().parents[1]/'tools/make_fixtures.py'
        result=subprocess.run([sys.executable,str(script),str(folder)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(existing.read_text(),'KEEP ORIGINAL')
        self.assertFalse((folder/'brief.docx').exists())

    def test_r20_multiple_representations_have_citable_locators(self):
        identity='b'*64
        for filename,quote,locator in [('first.txt','First excerpt','line:4'),('second.txt','Capability exists','line:9')]:
            p=self.base/filename;p.write_text(quote)
            result=ingest(self.root,p,metadata={'original_response_sha256':identity},
                          extraction_override={'chunks':[{'locator':locator,'text':quote}],'warnings':[],'injection_flags':[],'untrusted':True})
        sid=result['id']
        self.claim(sid,references=[{'source_id':sid,'locator':'line:9','quote':'Capability exists'}])
        self.assertEqual(len(load(self.root)['sources']),1)
        self.assertEqual(len(load(self.root)['sources'][sid]['representations']),2)
        self.assertTrue(engine.validate(self.root)['valid'])

    def test_r22_pack_refuses_corrupt_state(self):
        (self.root/'state/project.json').write_text('{}')
        with self.assertRaises(Problem):pack(self.root,self.base/'broken.zip')
