"""What we accept as an uploaded file, and how we check it. Pure functions, no database.

Rules: the file NAME picks the type (allowlist below), then the CONTENT must really be that type.
We never open, unpack or run an uploaded file; we only look at its first bytes, its zip file list, and
whether text is valid UTF-8. Anything that can carry a program (macros, scripts, embedded files) is refused."""
import io
import re
import unicodedata
import zipfile

MAX_NAME = 100

# Extension -> (kind, mime). "docs" = Word documents, "files" = everything else. ("sheets" comes later.)
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT_EXTENSIONS = {
    "txt": "text/plain", "md": "text/markdown", "csv": "text/csv", "json": "application/json", "sql": "text/plain",
    "py": "text/plain", "java": "text/plain", "c": "text/plain", "cc": "text/plain", "cpp": "text/plain",
    "cxx": "text/plain", "h": "text/plain", "hpp": "text/plain", "cs": "text/plain", "js": "text/plain",
    "ts": "text/plain",
}
ALLOWED = {"pdf": ("files", "application/pdf"), "docx": ("docs", DOCX_MIME)}
ALLOWED.update({ext: ("files", mime) for ext, mime in TEXT_EXTENSIONS.items()})

ALLOWED_LIST = "PDF, DOCX, TXT, MD, CSV, JSON, SQL and code (PY, JAVA, C, CPP, H, HPP, CS, JS, TS)"


def clean_name(raw: str) -> str:
    """A safe display name: no folders, no control or direction-flipping characters, at most 100 long."""
    name = unicodedata.normalize("NFC", raw or "")
    name = re.split(r"[\\/]", name)[-1]  # drop any folder part, from either kind of slash
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')  # isprintable drops control + U+202E
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > MAX_NAME:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) < 20:
            name = stem[: MAX_NAME - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_NAME]
    return name


def extension_of(name: str) -> str:
    return name.rpartition(".")[2].lower() if "." in name else ""


# PDFs can carry scripts and launch actions. We never open a PDF, but we refuse the obvious ones.
# (Best effort: it reads the raw bytes, so it cannot see inside compressed parts of a file.)
_PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia)(?![A-Za-z0-9])")
_PDF_HEX_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")  # /J#61vaScript is the same name as /JavaScript


def _check_pdf(raw: bytes) -> None:
    if not raw.startswith(b"%PDF-"):
        raise ValueError("That file is not a real PDF.")
    plain = _PDF_HEX_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), raw)
    if _PDF_ACTIVE.search(plain):
        raise ValueError("That PDF contains scripts or embedded files, so it can't be shared.")


_BAD_DOCX_PARTS = (".exe", ".dll", ".js", ".vbs", ".bat", ".cmd", ".ps1", ".sh", ".com", ".scr", ".jar", ".msi")


def _check_docx(raw: bytes) -> None:
    bad = ValueError("That file is not a real Word (.docx) document.")
    if not raw.startswith(b"PK\x03\x04"):
        raise bad
    try:
        infos = zipfile.ZipFile(io.BytesIO(raw)).infolist()  # reads only the list of parts, unpacks nothing
    except zipfile.BadZipFile:
        raise bad
    if len(infos) > 2000 or sum(i.file_size for i in infos) > 200 * 1024 * 1024:
        raise ValueError("That document is too large once unpacked.")
    names = {i.filename for i in infos}
    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        raise bad
    for name in names:
        low = name.lower()
        if low.endswith("vbaproject.bin") or low.startswith("word/embeddings/") or low.endswith(_BAD_DOCX_PARTS):
            raise ValueError("That document contains macros or embedded programs, so it can't be shared.")


def _check_text(raw: bytes) -> None:
    if b"\x00" in raw:
        raise ValueError("That file is not plain text.")
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Text and code files must be saved as UTF-8.")


def check_content(ext: str, raw: bytes) -> None:
    """Raise ValueError (with a message for the user) unless the bytes really are what the extension says."""
    if ext == "pdf":
        _check_pdf(raw)
    elif ext == "docx":
        _check_docx(raw)
    elif ext in TEXT_EXTENSIONS:
        _check_text(raw)
    else:
        raise ValueError("That file type is not allowed.")
