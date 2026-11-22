"""Divisão em chunks que respeita títulos, parágrafos e frases, nessa ordem de preferência."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Chunk, Section
from .text import split_sentences


def _units(text: str, max_chars: int) -> Iterable[str]:
    """Parágrafos; parágrafo grande demais vira frases; frase gigante (tabela, log) é cortada no limite."""
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            yield paragraph
            continue
        for sentence in split_sentences(paragraph):
            if len(sentence) <= max_chars:
                yield sentence
            else:
                for start in range(0, len(sentence), max_chars):
                    yield sentence[start : start + max_chars]


def _overlap_tail(parts: list[str], overlap: int) -> list[str]:
    """Últimas unidades do chunk anterior que cabem no overlap: contexto para a frase não chegar "solta"."""
    tail: list[str] = []
    size = 0
    for part in reversed(parts):
        if size + len(part) > overlap:
            break
        tail.insert(0, part)
        size += len(part) + 2
    return tail


def chunk_sections(sections: Iterable[Section], *, max_chars: int = 1200, overlap: int = 200) -> list[Chunk]:
    if max_chars < 200:
        raise ValueError("max_chars deve ser >= 200")
    if not 0 <= overlap < max_chars // 2:
        raise ValueError("overlap deve estar entre 0 e max_chars/2")

    chunks: list[Chunk] = []

    def emit(parts: list[str], section: Section) -> None:
        text = "\n\n".join(parts).strip()
        if text:
            chunks.append(Chunk(len(chunks), text, section.heading_path, section.page))

    for section in sections:
        current: list[str] = []
        size = 0
        has_new_content = False
        for unit in _units(section.text, max_chars):
            if current and size + len(unit) + 2 > max_chars:
                emit(current, section)
                current = _overlap_tail(current, overlap)
                size = sum(len(p) + 2 for p in current)
                has_new_content = False
            current.append(unit)
            size += len(unit) + 2
            has_new_content = True
        if has_new_content:
            emit(current, section)
    return chunks
