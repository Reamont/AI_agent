"""Упаковка с явным исключением приватных/локальных файлов и манифестом."""
import json
import re
import zipfile
from pathlib import Path
from .store import Problem, digest

EXCLUDE = {".git", ".venv", "__pycache__", ".pytest_cache", "private", "dist", "build", "node_modules"}
PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credential": re.compile(rb"(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})"),
    "personal_email": re.compile(rb"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}"),
    "credential_assignment": re.compile(rb"(?i)(?:api_key|access_token|password)\s*[:=]\s*[\"']?[A-Za-z0-9_-]{16,}"),
}


def files(root):
    root = Path(root).resolve()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in EXCLUDE or part.endswith(".egg-info") for part in rel.parts):
            continue
        if p.is_symlink():
            raise Problem(f"Символьная ссылка запрещена в пакете: {rel}")
        if not p.is_file() or p.suffix in (".pyc", ".tmp") or p.name == "write.lock":
            continue
        if p.name.startswith(".env") and p.name != ".env.example":
            continue
        yield p


def audit(root):
    root = Path(root).resolve()
    findings = []
    candidates = list(files(root))
    for p in candidates:
        data = p.read_bytes()
        # ZIP, PDF и растры не считаются проверенными regex-сканером: исходные
        # материалы DOCX/XLSX просматриваются в их XML, PDF — извлечением текста.
        if p.suffix in (".docx", ".xlsx"):
            with zipfile.ZipFile(p) as z:
                data = b"\n".join(z.read(n) for n in z.namelist() if n.endswith(".xml"))
        elif p.suffix == ".pdf":
            from pypdf import PdfReader
            data = "\n".join(page.extract_text() or "" for page in PdfReader(p).pages).encode()
        elif p.suffix in (".png", ".jpg", ".webm", ".mp4"):
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(data):
                findings.append({"file": str(p.relative_to(root)), "kind": name})
    return {"valid": not findings, "files": len(candidates), "findings": findings,
            "limits": "Эвристика; изображения/видео требуют визуального контроля, произвольные ПДн не гарантируются"}


def pack(root, target):
    root, target = Path(root).resolve(), Path(target).resolve()
    if target.is_relative_to(root):
        raise Problem("Архив должен находиться вне упаковываемого каталога")
    result = audit(root)
    if not result["valid"]:
        raise Problem("Пакет содержит возможные секреты/ПДн; смотрите audit")
    manifest = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files(root):
            name = str(p.relative_to(root))
            manifest[name] = digest(p.read_bytes())
            z.write(p, name)
        z.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(target) as z:
        if z.testzip() is not None:
            raise Problem("Повреждённый архив")
        if any(digest(z.read(name)) != sha for name, sha in manifest.items()):
            raise Problem("Не совпали хеши архива")
    return {"archive": str(target), "sha256": digest(target.read_bytes()), "files": len(manifest), "verified": True}
