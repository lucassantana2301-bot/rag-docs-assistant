"""Leitura de Markdown, texto, HTML e PDF para seções com o caminho de títulos de cada trecho."""

from __future__ import annotations

import io
import re
from pathlib import Path, PurePosixPath

from bs4 import BeautifulSoup, Tag
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .models import EmptyDocumentError, LoadedDocument, Section, UnsupportedFormatError
from .text import normalize

SUPPORTED_EXTENSIONS = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
}

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^(```|~~~)")


def _decode(data: bytes) -> str:
    # UTF-8 primeiro (com ou sem BOM); Latin-1 como último recurso, porque nunca falha.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _strip_front_matter(text: str) -> tuple[str, str | None]:
    if not text.startswith("---\n"):
        return text, None
    end = text.find("\n---", 4)
    if end < 0:
        return text, None
    header = text[4:end]
    title = next(
        (line.split(":", 1)[1].strip().strip("\"'") for line in header.splitlines() if line.startswith("title:")),
        None,
    )
    return text[end + 4 :].lstrip("\n"), title


def parse_markdown(text: str) -> tuple[str | None, list[Section]]:
    """Divide pelo títulos, guardando o caminho (H1 › H2 › H3). Títulos dentro de bloco de código são ignorados."""
    text, front_title = _strip_front_matter(text)
    sections: list[Section] = []
    path: list[tuple[int, str]] = []
    buffer: list[str] = []
    title = front_title
    in_fence = False

    def flush() -> None:
        body = normalize("\n".join(buffer))
        if body:
            sections.append(Section(text=body, heading_path=tuple(h for _, h in path)))
        buffer.clear()

    for line in text.splitlines():
        if _FENCE.match(line.strip()):
            in_fence = not in_fence
            buffer.append(line)
            continue
        match = None if in_fence else _HEADING.match(line)
        if match:
            flush()
            level, heading = len(match.group(1)), match.group(2).strip()
            if level == 1 and title is None:
                title = heading
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, heading))
        else:
            buffer.append(line)
    flush()
    return title, sections


def parse_html(text: str) -> tuple[str | None, list[Section]]:
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg", "form"]):
        tag.decompose()
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    found = soup.find("main") or soup.find("article") or soup.body
    root: Tag | BeautifulSoup = found if isinstance(found, Tag) else soup

    # Converte para pseudo-Markdown preservando a hierarquia de títulos.
    lines: list[str] = []
    for element in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "td", "th", "blockquote"]):
        content = element.get_text(" ", strip=True)
        if not content:
            continue
        if element.name and element.name.startswith("h") and len(element.name) == 2:
            lines.append(f"{'#' * int(element.name[1])} {content}")
        elif element.name == "li":
            lines.append(f"- {content}")
        else:
            lines.append(content)
        lines.append("")
    md_title, sections = parse_markdown("\n".join(lines))
    return title or md_title, sections


def parse_pdf(data: bytes) -> tuple[str | None, list[Section]]:
    try:
        reader = PdfReader(io.BytesIO(data))
    except (PdfReadError, ValueError) as error:
        raise UnsupportedFormatError(f"PDF inválido ou corrompido: {error}") from error
    if reader.is_encrypted:
        raise UnsupportedFormatError("PDF protegido por senha não é suportado")
    metadata_title = reader.metadata.title if reader.metadata else None
    sections = []
    for number, page in enumerate(reader.pages, start=1):
        content = normalize(page.extract_text() or "")
        # Hifenização de fim de linha ("pa-\ngamento") é artefato do PDF, não do texto.
        content = re.sub(r"(\w)-\n(\w)", r"\1\2", content)
        # Quebra de linha simples no PDF é só a largura da página; parágrafo é linha em branco.
        content = re.sub(r"(?<!\n)\n(?!\n)", " ", content)
        if content:
            sections.append(Section(text=content, page=number))
    return metadata_title, sections


def load_bytes(data: bytes, filename: str) -> LoadedDocument:
    # Só o nome entra no índice: evita guardar caminhos absolutos da máquina de quem importou.
    name = PurePosixPath(filename.replace("\\", "/")).name
    extension = PurePosixPath(name).suffix.lower()
    media_type = SUPPORTED_EXTENSIONS.get(extension)
    if media_type is None:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFormatError(f"formato não suportado: {extension or 'sem extensão'} (aceitos: {supported})")

    if media_type == "application/pdf":
        title, sections = parse_pdf(data)
    elif media_type == "text/html":
        title, sections = parse_html(_decode(data))
    elif media_type == "text/markdown":
        title, sections = parse_markdown(_decode(data))
    else:
        body = normalize(_decode(data))
        title, sections = None, [Section(text=body)] if body else []

    if not sections:
        raise EmptyDocumentError(f"{name}: nenhum texto extraído (PDF escaneado precisa de OCR antes)")
    fallback_title = PurePosixPath(name).stem.replace("-", " ").replace("_", " ").strip().capitalize()
    return LoadedDocument(source=name, title=title or fallback_title, media_type=media_type, sections=sections)


def load_path(path: Path) -> LoadedDocument:
    return load_bytes(path.read_bytes(), path.name)
