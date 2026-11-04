"""Реальная запись браузера с выполнением CLI. Не запись нового чата LLM."""
import argparse
import asyncio
import tempfile
import time
import json
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from strategist.store import digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--chromium',default=shutil.which('chromium'))
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    target=root/'submission/walkthrough-cli.webm'
    check=root/'submission/video-check.json'
    if target.exists():
        raise SystemExit('Запись уже существует; сохраните её отдельно перед новым запуском')
    commands={
        'resume':['-m','strategist','-p','projects/demo','resume'],
        'impact':['-m','strategist','-p','projects/demo','impact'],
        'tests':['-m','unittest','discover','-s','tests','-v'],
        'second':['-m','strategist','-p','projects/second','search','редактировать'],
    }
    records=[]
    async def execute(name):
        cmd=commands[name]
        process=await asyncio.create_subprocess_exec(sys.executable,*cmd,cwd=root,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=60)
        from types import SimpleNamespace
        r=SimpleNamespace(returncode=process.returncode,stdout=stdout.decode(),stderr=stderr.decode())
        records.append({'argv':['python',*cmd],'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        if name in ('resume','impact') and r.returncode==0:
            data=json.loads(r.stdout)
            if name=='resume':
                data={'revision':data['revision'],'workflow':data['workflow'],'budget':data['budget'],
                      'validation':{'valid':data['validation']['valid'],'warnings':data['validation']['warnings']}}
            else:
                data={k:[{'id':v.get('id','STRATEGY'),'status':v['status'],'version':v.get('version',1)} for v in values] for k,values in data.items()}
            return json.dumps(data,ensure_ascii=False,indent=2)
        return r.stdout+r.stderr
    try:
        from playwright.async_api import async_playwright
        async def record():
          async with async_playwright() as pw:
            browser=await pw.chromium.launch(executable_path=a.chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            context=await browser.new_context(viewport={'width':1440,'height':1000})
            page=await context.new_page();await page.expose_function('runCommand',execute)
            await page.set_content('''<meta charset="utf-8"><style>body{font:22px/1.5 system-ui;background:#112e2a;color:#ecfff2;padding:35px}h1{font-size:35px}button{font:22px system-ui;padding:12px;margin:5px}pre{font:18px/1.4 monospace;white-space:pre-wrap;background:#183e37;padding:20px;max-height:690px;overflow:auto}.notice{color:#ffdc89}</style>
            <h1>Стратег Фабрики проектов · проверяемое продолжение</h1>
            <p class="notice">Реальная запись исполнения CLI. Сохранённое учебное демо. Нового чата LLM в этой записи нет.</p>
            <p id="caption">Источники → утверждения → решение → пересмотр. Продуктовые данные синтетические.</p>
            <button onclick="run('resume')">Восстановить</button><button onclick="run('impact')">Последствия</button><button onclick="run('tests')">Тесты</button><button onclick="run('second')">Другая задача</button>
            <pre id="out">Видео не заменяет обязательный сквозной прогон нового чата. Публичная публикация видео не выполнена.</pre>
            <script>window.finished=false;async function run(name){finished=false;document.querySelector('#out').textContent='Выполняется реальная команда '+name+'…';document.querySelector('#out').textContent=await window.runCommand(name);finished=true;}</script>''')
            folder=Path(tempfile.mkdtemp(prefix='strategist-screen-'))
            frames=[];running=True
            async def capture():
                while running:
                    image=folder/f'frame-{len(frames):05d}.png'
                    captured=time.monotonic()
                    await page.screenshot(path=str(image))
                    frames.append((image,captured))
                    await asyncio.sleep(.2)
            task=asyncio.create_task(capture())
            await page.wait_for_timeout(4000)
            for name,caption in [('resume','Чтение состояния из файлов; бюджет времени уже учитывает предыдущую работу.'),
                                 ('impact','Контрсвидетельства, обещания и сама стратегия входят в последствия пересмотра.'),
                                 ('tests','Регрессионные тесты проверяют ошибки из ревью; они не измеряют качество LLM.'),
                                 ('second','Другая задача: права редактирования каталога, не удержание.')]:
                await page.locator('#caption').evaluate('(node,text)=>node.textContent=text',caption)
                await page.locator(f'button[onclick="run(\'{name}\')"]').click()
                await page.wait_for_function('window.finished===true',timeout=60000)
                await page.wait_for_timeout(7000)
            await page.locator('#caption').evaluate('(node)=>node.textContent="Итог: технические проверки и текущая трасса сохранены. Новый чат, полная запись и доступ жюри требуют завершения."')
            await page.wait_for_timeout(4000)
            running=False
            await task
            await context.close();await browser.close()
            concat=folder/'frames.txt'
            entries=[]
            for i,(image,stamp) in enumerate(frames):
                duration=(frames[i+1][1]-stamp) if i+1<len(frames) else .2
                entries.extend(["file '"+image.name+"'",f'duration {duration:.6f}'])
            entries.append("file '"+frames[-1][0].name+"'")
            concat.write_text('\n'.join(entries)+'\n')
            subprocess.run(['ffmpeg','-v','error','-f','concat','-safe','0','-i',str(concat),'-c:v','libvpx-vp9','-r','12','-pix_fmt','yuv420p',str(target)],check=True,timeout=120)
            shutil.rmtree(folder)
        asyncio.run(record())
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(target)],capture_output=True,text=True,check=True)
        duration=float(json.loads(probe.stdout)['format']['duration'])
        result={'status':'partial','at':datetime.now(timezone.utc).isoformat(),'path':'walkthrough-cli.webm',
                'duration_seconds':duration,'under_ten_minutes':duration<=600,'sha256':digest(target.read_bytes()),
                'kind':'Real Chromium frame capture with monotonic timestamps and system FFmpeg; actual CLI execution, replay of saved demo',
                'ffmpeg_version':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
                'new_llm_chat_included':False,'fulfills_full_submission':False,'publication':'not published to an allowed video hosting service'}
        (root/'evals/video-commands.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    except Exception as exc:
        result={'status':'blocked','reason':type(exc).__name__+': '+str(exc)[:500],
                'fulfills_full_submission':False,'new_llm_chat_included':False}
        check.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));raise SystemExit(2)
    check.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
