"""Извлечение данных без исполнения инструкций, макросов и формул."""
import csv
import io
import re
import socket
import ipaddress
import os
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

from .store import Problem, digest, canonical, atomic, transaction, load, now, bump, outcome
from .validation import text


class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        if tag in ("p", "div", "h1", "h2", "li", "tr", "section"):
            self.parts.append("\n")

    def handle_data(self, text):
        if not self.skip:
            self.parts.append(text)


def _extract(data, extension):
    chunks, warnings = [], []
    if extension in (".docx", ".xlsx"):
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if len(z.infolist()) > 4096 or sum(i.file_size for i in z.infolist()) > 64 * 1024 * 1024:
                raise Problem("Контейнер документа превышает лимит распаковки 64 MB/4096 entries")
    def add(locator, text):
        if str(text).strip():
            chunks.append({"locator": locator, "text": str(text).strip()})
    if extension in (".md", ".txt"):
        for i, line in enumerate(data.decode("utf-8-sig").splitlines(), 1):
            add(f"line:{i}", line)
    elif extension == ".csv":
        for i, row in enumerate(csv.reader(io.StringIO(data.decode("utf-8-sig"))), 1):
            add(f"row:{i}", " | ".join(row))
    elif extension == ".pdf":
        from pypdf import PdfReader
        pdf = PdfReader(io.BytesIO(data))
        if pdf.is_encrypted:
            raise Problem("Защищённый PDF не поддерживается")
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            add(f"page:{i}", text)
            if not text.strip():
                warnings.append(f"page:{i}: нет текста, нужен OCR (не реализован)")
    elif extension == ".docx":
        from docx import Document
        doc = Document(io.BytesIO(data))
        for i, paragraph in enumerate(doc.paragraphs, 1):
            add(f"paragraph:{i}", paragraph.text)
        for ti, table in enumerate(doc.tables, 1):
            for ri, row in enumerate(table.rows, 1):
                add(f"table:{ti}/row:{ri}", " | ".join(c.text for c in row.cells))
    elif extension == ".xlsx":
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            for sheet in wb:
                for row_number, row in enumerate(sheet.iter_rows(), 1):
                    values = []
                    for cell in row:
                        if cell.data_type == "f":
                            warnings.append(f"{sheet.title}!{cell.coordinate}: формула не вычислялась")
                        values.append("" if cell.value is None else str(cell.value))
                    if row:
                        add(f"{sheet.title}!A{row_number}:{get_column_letter(len(row))}{row_number}", " | ".join(values) if any(values) else "")
        finally:
            wb.close()
    elif extension in (".html", ".htm"):
        parser = TextHTML()
        parser.feed(data.decode("utf-8-sig"))
        for i, line in enumerate("".join(parser.parts).splitlines(), 1):
            add(f"html-line:{i}", " ".join(line.split()))
        warnings.append("Статический HTML; JavaScript, авторизация и динамический контент не исполнялись")
    else:
        raise Problem(f"Формат {extension} не поддерживается")
    suspicious = re.compile(r"ignore.{0,40}(instructions|rules)|reveal.{0,30}(secret|token)|игнорируй.{0,40}(правил|инструкц)|раскрой.{0,30}(секрет|токен)", re.I)
    flags = [c["locator"] for c in chunks if suspicious.search(c["text"])]
    return {"chunks": chunks, "warnings": warnings, "untrusted": True, "injection_flags": flags}


def extract(data, extension):
    import zipfile
    from xml.etree.ElementTree import ParseError
    from lxml.etree import XMLSyntaxError
    from pypdf.errors import PdfReadError
    from docx.opc.exceptions import PackageNotFoundError
    from openpyxl.utils.exceptions import InvalidFileException
    try:
        return _extract(data, extension)
    except Problem:
        raise
    except (zipfile.BadZipFile, ParseError, XMLSyntaxError, PdfReadError, PackageNotFoundError,
            InvalidFileException, UnicodeError, ValueError, KeyError, IndexError) as exc:
        raise Problem(f"Документ не прочитан ({type(exc).__name__}); источник не зарегистрирован") from exc


def predecessors(source):
    return set(source.get("supersedes_ids", [])) | ({source["supersedes"]} if source.get("supersedes") else set())


def superseded(s, sid):
    return any(sid in predecessors(src) for src in s["sources"].values())


def invalidate(s, source_ids=(), claim_ids=(), skip_roots=False):
    affected = set(claim_ids)
    changed = True
    while changed:
        changed = False
        for cid, c in s["claims"].items():
            if cid not in affected and (any(r["source_id"] in source_ids for r in c["references"]) or (set(c["depends_on"]) | set(c.get("counterevidence", []))) & affected):
                affected.add(cid)
                changed = True
    for cid in affected:
        c = s["claims"][cid]
        if skip_roots and cid in claim_ids:
            continue
        if c["status"] not in ("withdrawn", "refuted", "needs_review"):
            bump(c, "Изменилось основание или контрсвидетельство")
            c["status"] = "needs_review"
    decisions, promises = [], []
    for collection, result in (("decisions", decisions), ("promises", promises)):
        for rid, record in s[collection].items():
            if set(record["basis"]) & affected:
                if record["status"] != "needs_review":
                    bump(record, "Изменилось основание")
                    record["status"] = "needs_review"
                result.append(rid)
    strategy = []
    st = s.get("strategy")
    if st and (set(st.get("basis", [])) & affected or set(st.get("promise_ids", [])) & set(promises)):
        if st["status"] != "needs_review":
            bump(st, "Изменились основания или обещания стратегии")
            st["status"] = "needs_review"
        strategy.append(st.get("id", "STRATEGY"))
    return {"claims": sorted(affected), "decisions": decisions, "promises": promises, "strategy": strategy}


def link_replacement(s, sid, old):
    if not old:
        return None
    if old not in s["sources"] or old == sid:
        raise Problem("Заменяемый источник не существует или совпадает с новым")
    # Рёбра идут от старого к новому; исключаем цикл до изменения записи.
    pending, seen = [sid], set()
    while pending:
        node = pending.pop()
        if node == old:
            raise Problem("Цикл замены источников")
        if node not in seen:
            seen.add(node)
            pending += [k for k, v in s["sources"].items() if node in predecessors(v)]
    src = s["sources"][sid]
    olds = predecessors(src)
    if old in olds:
        return {"claims": [], "decisions": [], "promises": [], "strategy": []}
    bump(src, "Добавлена связь замены источника")
    src["supersedes_ids"] = sorted(olds | {old})
    src["supersedes"] = src.get("supersedes") or old
    previous = s["sources"][old]
    bump(previous, "Источник заменён новой версией")
    previous["superseded_by"] = sorted(set(previous.get("superseded_by", [])) | {sid})
    return invalidate(s, source_ids=[old])


def ingest(root, path, origin=None, rights="provided_for_project", supersedes=None, expected_revision=None, *, extraction_override=None, metadata=None):
    p = Path(path)
    cfg = load(root)["config"]
    if p.stat().st_size > cfg.get("max_source_bytes", 12582912):
        raise Problem("Материал превышает лимит размера")
    data = p.read_bytes()
    sha = digest(data)
    text(rights, "rights")
    identity = (metadata or {}).get("original_response_sha256", sha)
    sid = "SRC-" + identity[:16]
    with transaction(root, "ingest", "Извлечь недоверенный материал и сохранить происхождение", [p.name], expected_revision) as s:
        if not metadata or not metadata.get("original_response_sha256"):
            sid = next((k for k, v in s["sources"].items() if sha in {v["sha256"]} | {p["sha256"] for p in v.get("representations", [])}), sid)
        if sid in s["sources"] and sha in {s["sources"][sid]["sha256"]} | {p["sha256"] for p in s["sources"][sid].get("representations", [])}:
            impact = link_replacement(s, sid, supersedes)
            outcome(s, "done", "Существующее представление проверено; связь замены обработана", deduplicated=True)
            return {"id": sid, "deduplicated": True, "impact": impact}
        extracted = extraction_override if extraction_override is not None else extract(data, p.suffix.lower())
        if not extracted["chunks"]:
            raise Problem("Текст не извлечён; скан/пустой документ требует другого метода")
        existing = s["sources"].get(sid)
        suffix = ("-" + sha[:16]) if existing else ""
        target = f"sources/{sid}{suffix}{p.suffix.lower()}"
        (Path(root) / target).write_bytes(data)
        text_path = f"evidence/{sid}{suffix}.json"
        atomic(Path(root) / text_path, extracted)
        representation = {"sha256": sha, "path": target, "extracted": text_path, "extracted_sha256": digest(canonical(extracted))}
        if existing:
            bump(existing, "Добавлено представление того же первоисточника")
            existing.setdefault("representations", [{k: existing[k] for k in representation}]).append(representation)
        else:
            s["sources"][sid] = {"id": sid, "identity_sha256": identity, "version": 1, "history": [], "name": p.name, "sha256": sha, "path": target,
                             "extracted": text_path, "extracted_sha256": digest(canonical(extracted)), "origin": origin or f"provided:{p.name}",
                             "accessed_at": now(), "rights": rights, "independence_group": origin or sha,
                             "representations": [representation], "supersedes": None, "warnings": extracted["warnings"],
                             "injection_flags": extracted["injection_flags"], "trust": "untrusted"}
        if metadata:
            for key in ("original_response_sha256", "snapshot_mode", "selection"):
                if key in metadata:
                    s["sources"][sid][key] = metadata[key]
        impact = link_replacement(s, sid, supersedes)
        return {"id": sid, "deduplicated": False, "chunks": len(extracted["chunks"]),
                "warnings": extracted["warnings"], "injection_flags": extracted["injection_flags"], "impact": impact}


def check_url(url, allowed_domains):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None, 443):
        raise Problem("Разрешены только HTTPS URL без credentials на порту 443")
    host = u.hostname.lower().rstrip(".")
    if host not in {h.lower().rstrip('.') for h in allowed_domains}:
        raise Problem("Домен не разрешён конфигурацией проекта")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        # В managed cloud DNS внешних имён может выполняться только sidecar.
        # Узкое исключение для фиксированных публичных хостов GitHub: произвольные
        # allowlisted домены по-прежнему требуют успешной DNS-проверки.
        proxy = os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", ""))
        if (host in {"raw.githubusercontent.com", "github.com"}
                and proxy == "http://proxy:8080"
                and not urllib.request.proxy_bypass(host)):
            return url
        raise Problem(f"DNS недоступен: {type(exc).__name__}") from exc
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise Problem("Локальный/служебный адрес запрещён")
    return url


class GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, domains):
        super().__init__()
        self.domains = domains
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.domains)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(root, url, rights="reference_only", contains=None):
    cfg = load(root)["config"]
    check_url(url, cfg.get("allowed_domains", []))
    opener = urllib.request.build_opener(GuardedRedirect(cfg["allowed_domains"]))
    request = urllib.request.Request(url, headers={"User-Agent": "FabrikaStrategist/0.1 (research; static reader)"})
    try:
        with opener.open(request, timeout=20) as response:
            check_url(response.url, cfg["allowed_domains"])
            mime = response.headers.get_content_type()
            extension = {"text/html": ".html", "text/plain": ".txt", "application/pdf": ".pdf"}.get(mime)
            if not extension:
                raise Problem(f"Тип ответа {mime} не поддерживается")
            data = response.read(cfg.get("max_source_bytes", 12582912) + 1)
            if len(data) > cfg.get("max_source_bytes", 12582912):
                raise Problem("Ответ превышает лимит размера")
            # Снимок допускается только при явно указанных правах. По умолчанию
            # не сохраняем полный чужой текст — возвращаем требование решения.
            if rights == "reference_only":
                raise Problem("Для полного снимка задайте --rights с проверенным основанием воспроизведения")
            full_sha = digest(data)
            selected = None
            if contains:
                extracted = extract(data, extension)
                selected = {**extracted, "chunks": [c for c in extracted["chunks"] if contains in c["text"]]}
                if not selected["chunks"]:
                    raise Problem("Запрошенный фрагмент не найден; источник не сохранён")
                data = "\n".join(c["text"] for c in selected["chunks"]).encode()
                extension = ".txt"
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / ("web" + extension)
                p.write_bytes(data)
                return ingest(root, p, origin=response.url, rights=rights, extraction_override=selected,
                              metadata={"original_response_sha256": full_sha, "snapshot_mode": "excerpt" if contains else "full",
                                        "selection": contains})
    except Problem:
        raise
    except Exception as exc:
        # Не печатаем headers/proxy credentials. CLI журналирует только тип ошибки.
        raise Problem(f"Сайт недоступен ({type(exc).__name__}); содержание не получено") from exc
