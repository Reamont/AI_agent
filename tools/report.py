"""Создать PDF и настоящие скриншоты локального представления сохранённых результатов."""
import argparse
import html
import json
import shutil
import subprocess
import re
from pathlib import Path
from datetime import datetime, timezone

from strategist.store import load, digest
from strategist.engine import validate
from strategist import __version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium', help='Путь к системному Chromium; иначе playwright browser')
    parser.add_argument('--font', default='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    parser.add_argument('--revision', help='Полный commit для действующих ссылок на версии инструкций')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    revision = args.revision or subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if not re.fullmatch(r'[a-f0-9]{40}',revision):
        raise ValueError('Для ссылок нужен полный commit SHA')
    sub = root / 'submission'
    screenshots = sub / 'screenshots'
    screenshots.mkdir(exist_ok=True)
    state = load(root / 'projects/demo')
    validity = validate(root / 'projects/demo', True)
    verification = json.loads((root/'evals/verification.json').read_text())
    esc = lambda x: html.escape(str(x))
    body = '''<header><div class="tag">УЧЕБНОЕ ДЕМО · СОХРАНЁННЫЙ ПРОГОН</div>
    <h1>Стратег Фабрики проектов</h1><p>Проверяемые основания. Сохранение выбора. Пересмотр по новым данным.</p></header>'''
    body += '<section id="overview"><h2>От запроса к решению</h2><p class="lead">«Удержание падает — менять продукт или сообщение?»</p>'
    body += '<div class="grid"><article><b>Данные</b><p>200/300 → 170/300</p><small>Синтетические счётчики. Сравнимость D30 опровергнута.</small></article>'
    body += '<article><b>Четыре направления</b><p>Сохранить · улучшить · сменить сегмент · закрыть</p><small>Качественное сравнение и сильные возражения</small></article>'
    body += '<article><b>Актуальный следующий шаг</b><p>Аудит окна наблюдения</p><small>Пилот не запускать до зрелой когорты</small></article></div>'
    body += '<h3>Источники и память</h3><table><tr><th>Источники</th><th>Утверждения</th><th>Версия состояния</th><th>Структура</th></tr>'
    body += f'<tr><td>{len(state["sources"])}</td><td>{len(state["claims"])}</td><td>{state["revision"]}</td><td>{"проверена" if validity["valid"] else "ошибка"}</td></tr></table>'
    body += '<p>Документ DOCX · таблицы CSV/XLSX · открытый методический сайт · точные локаторы · SHA256</p>'
    body += '<p class="notice">Не официальный бриф МегаФона. Нет реальных метрик, интервью или утверждённого решения человека.</p></section>'
    body += '<section id="impact"><h2>Новое свидетельство → пересмотр</h2><p class="lead">14 дней вместо 30: прежний вывод об удержании неприменим.</p><table><tr><th>ID</th><th>Сохранённое основание / вывод</th><th>Текущий статус</th></tr>'
    for cid in ['C-WINDOW', 'C-DECLINE', 'C-CAUSE', 'C-FUNCTION', 'C-UPDATE']:
        c = state['claims'][cid]
        statuses={'current':'актуально','refuted':'опровергнуто','needs_review':'требует пересмотра'}
        body += f'<tr><td>{cid}</td><td>{esc(c["text"])}</td><td>{esc(statuses.get(c["status"],c["status"]))}</td></tr>'
    body += '</table><h3>Последствия</h3><p>D-01, D-02, P-PILOT и стратегия требуют пересмотра. После нового источника P-CURRENT перепроверено: только список задач и CSV, без приглашения.</p>'
    body += '<p class="notice">D-03 предложено: сохранить объём инвестиций до аудита D30, не обещать недоступное приглашение. Принимающий решение и исполнитель не назначены.</p></section>'
    body += '<section><h2>Границы проверки</h2><p>Автоматические тесты проверяют инструменты и инварианты; качество стратегии требует эксперта. Baseline не измерен. Видео не готово.</p></section>'
    document = '''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Стратег — сохранённые результаты</title><style>
    *{box-sizing:border-box}body{font:19px/1.55 system-ui,sans-serif;margin:0;color:#172c30;background:#eff4f1}header{padding:35px 60px;background:#103f39;color:#fff}h1{font-size:42px;margin:10px 0}h2{font-size:30px;margin-top:0}h3{margin:24px 0 12px}.tag{font-size:13px;letter-spacing:2px;color:#b8ecbd}section{margin:30px 50px;padding:32px;background:white;border:1px solid #d4e1d9;border-radius:16px}.lead{font-size:25px;font-weight:550}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}article{background:#f0f6f2;padding:22px;border-radius:12px}article p{font-size:24px}small{font-size:16px;color:#50635e}table{width:100%;border-collapse:collapse;font-size:17px}td,th{padding:12px 15px;border-bottom:1px solid #d4dfd8;text-align:left}th{background:#edf4ef}.notice{border-left:4px solid #d5a430;padding:14px 20px;background:#fff8e3}
    </style>''' + body + '</html>'
    view = sub/'demo-view.html'
    view.write_text(document)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        executable = args.chromium or shutil.which('chromium')
        browser = p.chromium.launch(executable_path=executable, headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
        # file:// запрещён политикой управляемого браузера; отрисовываем созданный
        # нами HTML в пустой странице, не отключая browser policy и не читая файлы браузером.
        page.set_content(document, wait_until='load')
        page.screenshot(path=str(screenshots/'overview.png'))
        page.locator('#impact').screenshot(path=str(screenshots/'impact.png'))
        browser.close()
    source = '''# Описание работы — Стратег Фабрики проектов 0.1.0

## Результат и границы
Один агент LLM в среде разработки, детерминированный Python CLI, проверяемая память.
Учебный продукт «Контур задач», не официальный бриф МегаФона. Реального рыночного
исследования, интервью и утверждения стратегии человеком нет. Сквозной прогон
инструментов выполнен; его будущий просмотр — replay.

## Архитектура и контекст
AGENTS.md — единые постоянные инструкции; Cursor-адаптер ссылается на него.
knowledge/ — методика; inputs/sources/evidence — недоверенные материалы;
state/project.json — актуальное состояние и память; history — версии; outputs —
читаемые результаты. Атомарный JSON, lock, контрольные суммы и ссылки позволяют
новому процессу восстановить состояние без истории чата. Семантического поиска нет.
Точное устройство и ограничения описаны в docs/architecture.md.

## Фактически использованные модели и инструменты
При создании: текущий Codex/GPT-6 в этой сессии, Python 3.12, pip, Git, shell,
Cloud Environment Runtime/Onboarding, urllib, pypdf, python-docx, openpyxl,
unittest, Chromium/Playwright, ReportLab и DejaVu Sans.
Другие модели, MCP и субагенты не запускались. При работе: LLM выбранной среды
для синтеза, CLI для расчёта/памяти и разрешённый HTTPS для чтения. Нет скрытых
ключей/подписок/MCP. Модельная подписка среды нужна для нового исследования,
тариф и токены неизвестны. Все версии зависимостей зафиксированы в lock-файлах.

## Ключевые инструкции, версия 0.1.0
AGENTS.md: цикл, доказательность и границы; instructions/agent.md: первый ход и
prompt injection; workflows/research.md: вопросы решения; prompts/first-message.md:
возобновление; knowledge/methods.md: аналитика, экономика, коммуникация.
CLI сохраняет записи, а не заменяет исследование заранее заготовленным ответом.

## Демонстрационный путь
Запрос о падении удержания → уточнение D30 → план вопросов → реальный импорт
DOCX/CSV/XLSX/TXT/сайта → воспроизводимый weighted расчёт 200/300 и 170/300 →
гипотезы/пробелы → 4 варианта со сильными возражениями → продуктовая и
коммуникационная стратегии → таблица обещаний и план опыта → simulated D-01 →
checkpoint → resume в другом процессе → отложенная интерпретация ранее импортированных
данных 14/30 дней → impact → предложено D-02. После ревью реально записан новый resume,
затем создан и импортирован capability-update-after-resume. Он изменил доступность
приглашения: пересмотрены C-FUNCTION, D-02, P-CURRENT и стратегия; предложено D-03.
P-CURRENT перепроверено по C-AVAILABLE-V2. Точные argv/выходы/хеши и тексты текущей
LLM сохранены в evals/llm-traces; это self-recorded текущая сессия, не независимый
новый чат и не выгрузка переписки провайдером. Настоящий новый чат должен быть записан отдельно.
Второй сценарий: права доступа библиотечного каталога по PDF/HTML; текущая LLM
выбрала тест пересказа, а не когортный анализ. Полная вторая стратегия не строилась.

## Дополнительные возможности и доказательство пользы
Проверки качества обнаруживают пропуски, несогласованный период и дубликаты.
Повторный импорт не создаёт второй источник. Пересмотр затрагивает зависимые
решения и обещания, сохраняя независимые факты. Checkpoint и относительные
пути позволяют переносить проект. Это функциональная польза, не измеренный
бизнес-эффект. Все 13 опций и ограничения перечислены в docs/extensions.md.

## Стоимость, время, ошибки, участие человека
Начало создания 04.11.2026 09:53 UTC; завершение пакета в evals/build-timing.json.
Отдельных платных API-вызовов 0. Полная цена LLM, подписки, инфраструктуры и труда
неизвестна; нулевой полной стоимостью не называется. Время разработки отдельно от
демо и локальных тестов. Пользователь предоставил задание; владельцы/реальные
интервью не выдуманы. Были 403/404 внешних сайтов, ошибка DNS, предупреждение
не закрытого CSV (исправлено), ошибка относительного пути audit (исправлена).
Чистая установка обнаружила исключение requirements.lock из ZIP; правило упаковки
исправлено, повторная проверка сохраняется в evals/clean-install.json.
Автопроверка запретила сброс проекта; вместо него применена обратимая минимизация
публичного источника. Полный текст с контактом автора исключён из пакета, нужный
фрагмент, URL, исходный хеш и локатор сохранены. Старые метаданные истории сохранены;
полные исторические веб-байты не переносятся в сдаваемом архиве.

## Baseline и оценка
НЕ ИЗМЕРЕНО: нет отдельного сопоставимого чата или независимого аналитика.
evals/baseline.md задаёт общую рубрику и протокол. Самопроверка стратегии текущей
LLM не независимая экспертиза. Ускорение, экономия и проценты улучшения не заявлены.
Автотесты проверяют структуру и функции, не гарантируют истинность и качество решения.

## Безопасность и запуск
Материалы недоверенные; команда раскрыть секрет из тестового источника не выполнена.
Платный вызов с неизвестной ценой останавливается; права источников проверяет агент.
HTTPS allowlist/redirect/DNS, лимиты, без обхода TLS. Фоновый мониторинг отсутствует.
Архив исключает .env, private, venv, git и кеши; эвристический audit не заменяет
ручную проверку любых ПДн/картинок. Полная публичная документация с контактами
минимизирована до требуемого фрагмента. См. README: venv → pip requirements.lock →
install -e → doctor → tests → resume. Для нового проекта init и разрешённые материалы.

## Статус сдачи
Локальный проект и учебное демо подготовлены, ZIP проверяется манифестом. Этот PDF
включает настоящие скриншоты локального HTML-представления фактического состояния,
не имитацию экрана чата. Видеозапись НЕ ГОТОВА, сценарий не заменяет запись.
Исходник отправляется в существующий GitHub-репозиторий; его видимость не меняется.
Доступ жюри независимо не проверен (GitHub API Forbidden). Для финального видео
пользователь выбрал Яндекс Диск, но доступ на загрузку к нему не подключён.
Финальную отправку делает капитан.
'''
    source=source.replace('0.1.0',__version__)
    source+='''
## Исправления после ревью
Проверка хеша CSV выполняется до расчёта внутри транзакции. Дедупликация не отменяет
замену источника; контрсвидетельства и обещания стратегии входят в граф. Каскадные
изменения версионируются. Обновление решения/обещания сохраняет ID и историю;
decision_maker отделён от owner. Конфигурация и workflow валидируются, NaN/Infinity
не принимаются. Журнал различает транзакцию, отказ, невалидный результат, запрос
денег и реальные расходы. История проверяется отдельно от восстановимости её
материалов. Память демо учитывает 18.4594 минуты первоначального календарного
интервала с паузами; это не точный труд LLM. Условия четырёх вариантов исправлены,
диагностика/прототип/пилот разделены, C-COMM остаётся гипотезой. Полная карта всех
33 замечаний — docs/review-fixes.md, без заявления готовности нерешённых пунктов.
'''
    video_check=sub/'video-check.json'
    if video_check.exists():
        video=json.loads(video_check.read_text())
        source+='\n## Статус реальной технической записи\n'+('Записано реальное выполнение CLI в Chromium, '+str(round(video.get('duration_seconds',0),1))+' секунды. Это видеозапись воспроизведения сохранённого демо, не нового чата; полный обязательный ролик по-прежнему не готов. Размещение на Яндекс Диске не выполнено.' if video.get('status')=='partial' else 'Попытка записи не завершилась: '+video.get('reason','неизвестно')+'. Готовая полная видеозапись не заявлена.')+'\n'
    links=['AGENTS.md','instructions/agent.md','workflows/research.md','prompts/first-message.md','docs/review-fixes.md','docs/requirements-matrix.md','evals/llm-traces/continuation.jsonl','evals/llm-traces/second-task.jsonl']
    source+='\n## Навигация по конкретной версии\n\n'
    for path in links:
        source+=f'[{path}](https://github.com/Reamont/AI_agent/blob/{revision}/{path})\n'
    (sub/'report-source.md').write_text(source)
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    pdfmetrics.registerFont(TTFont('ReportFont', args.font))
    normal = ParagraphStyle('Body', fontName='ReportFont', fontSize=10.3, leading=14.3, spaceAfter=8)
    heading = ParagraphStyle('Heading', parent=normal, fontSize=16, leading=21, spaceBefore=14, keepWithNext=True, textColor=HexColor('#103f39'))
    title = ParagraphStyle('Title', parent=heading, fontSize=23, leading=30)
    story = []
    for block in source.split('\n\n'):
        if block.startswith('#'):
            first, _, rest = block.partition('\n')
            style = title if first.startswith('# ') else heading
            story.append(Paragraph(esc(first.lstrip('# ')), style))
            if rest.strip():
                story.append(Paragraph(esc(rest).replace('\n', ' '), normal))
        else:
            link_lines=block.splitlines()
            if link_lines and all(re.fullmatch(r'\[([^\]]+)\]\((https://[^)]+)\)',line) for line in link_lines):
                for line in link_lines:
                    label,url=re.fullmatch(r'\[([^\]]+)\]\((https://[^)]+)\)',line).groups()
                    story.append(Paragraph(f'<link href="{esc(url)}" color="#14624c">{esc(label)}</link>',normal))
            else:
                story.append(Paragraph(esc(block).replace('\n', ' '), normal))
    story += [PageBreak(), Paragraph('Реальный скриншот: сохранённый результат', heading)]
    from PIL import Image as PILImage
    for filename in ['overview.png', 'impact.png']:
        p = screenshots/filename
        w,h = PILImage.open(p).size
        width = 500
        story += [Image(str(p), width=width, height=width*h/w), Spacer(1,12)]
        if filename == 'overview.png':
            story += [Paragraph('Это экран HTML-представления реальных JSON/outputs. Не новый чат и не новое исследование.', normal),PageBreak()]
    story += [Paragraph('Результаты автоматической проверки', heading), Paragraph(esc('valid=' + str(verification['valid']) + '; команд: ' + str(len(verification['checks'])) + '; ожидаемый провал плохого CSV выделен отдельно.'), normal)]
    pdfpath = sub/'report.pdf'
    def footer(canvas, doc):
        canvas.setFont('ReportFont',8)
        canvas.drawString(45,25,f'Стратег Фабрики проектов · {__version__} · Учебный прогон')
        canvas.drawRightString(550,25,str(doc.page))
    SimpleDocTemplate(str(pdfpath),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=40,bottomMargin=45).build(story,onFirstPage=footer,onLaterPages=footer)
    from pypdf import PdfReader
    reader = PdfReader(pdfpath)
    text='\n'.join(p.extract_text() or '' for p in reader.pages)
    check={'at':datetime.now(timezone.utc).isoformat(),'pages':len(reader.pages),'cyrillic_extracted':'Стратег' in text,
           'screenshots':[{'path':'screenshots/'+p.name,'sha256':digest(p.read_bytes())} for p in screenshots.glob('*.png')],
           'pdf_sha256':digest(pdfpath.read_bytes()),'instruction_commit':revision,
           'version_links':len(links),'keep_headings_with_next':True,'render_review':'pending; rasterize and inspect separately'}
    (sub/'report-check.json').write_text(json.dumps(check,ensure_ascii=False,indent=2))
    print(json.dumps(check,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
