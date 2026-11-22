from __future__ import annotations

import pytest

from rag_docs.chunking import chunk_sections
from rag_docs.loaders import load_bytes, parse_markdown
from rag_docs.models import EmptyDocumentError, Section, UnsupportedFormatError
from rag_docs.text import fold, normalize, split_sentences, tokenize

from .conftest import CORPUS


def test_text_normalization() -> None:
    assert fold("Férias Ação") == "ferias acao"
    assert tokenize("Quais são as FÉRIAS do estagiário?") == ["ferias", "estagiario"]
    assert normalize("a\x00b   c\n\n\n\nd") == "ab c\n\nd"


def test_sentence_split_keeps_abbreviations_and_money() -> None:
    text = "Use o app, ex. Corporate Expenses. O limite é R$ 1.200,00 por mês. Dr. Silva aprova."
    assert split_sentences(text) == [
        "Use o app, ex. Corporate Expenses.",
        "O limite é R$ 1.200,00 por mês.",
        "Dr. Silva aprova.",
    ]


def test_markdown_keeps_heading_path_and_ignores_headings_in_code() -> None:
    title, sections = parse_markdown(
        "---\ntitle: Guia\n---\n# Raiz\nintro\n## Deploy\n```bash\n# não é título\n```\n"
        "### Rollback\ncomo voltar\n## Outro\nfim"
    )
    assert title == "Guia"
    assert [s.heading_path for s in sections] == [
        ("Raiz",),
        ("Raiz", "Deploy"),
        ("Raiz", "Deploy", "Rollback"),
        ("Raiz", "Outro"),
    ]
    assert "# não é título" in sections[1].text


def test_html_drops_scripts_navigation_and_footer() -> None:
    doc = load_bytes((CORPUS / "politica-de-trabalho-hibrido.html").read_bytes(), "politica-de-trabalho-hibrido.html")
    text = " ".join(s.text for s in doc.sections)
    assert doc.title == "Política de trabalho híbrido"
    assert "terças e quintas-feiras" in text
    assert "scripts são ignorados" not in text
    assert "Intranet" not in text and "Atualizado em" not in text


def test_pdf_pages_and_line_joining() -> None:
    doc = load_bytes((CORPUS / "politica-de-viagens.pdf").read_bytes(), "politica-de-viagens.pdf")
    assert [s.page for s in doc.sections] == [1, 2]
    assert "diária de US$ 70 para alimentação" in doc.sections[1].text


def test_rejects_unsupported_empty_and_corrupted_files() -> None:
    with pytest.raises(UnsupportedFormatError, match=r"\.docx"):
        load_bytes(b"x", "relatorio.docx")
    with pytest.raises(EmptyDocumentError):
        load_bytes(b"   \n", "vazio.txt")
    with pytest.raises(UnsupportedFormatError, match="PDF inválido"):
        load_bytes(b"%PDF-1.7 lixo", "quebrado.pdf")


def test_source_name_never_keeps_directories() -> None:
    doc = load_bytes("conteúdo".encode("cp1252"), "../../etc/C:\\Users\\x\\notas.txt")
    assert doc.source == "notas.txt"
    assert doc.sections[0].text == "conteúdo"


def test_chunks_respect_size_overlap_and_heading() -> None:
    paragraph = " ".join(f"Frase número {i} sobre o processo de deploy." for i in range(40))
    sections = [Section(text=f"{paragraph}\n\n{paragraph}", heading_path=("Guia", "Deploy"))]
    chunks = chunk_sections(sections, max_chars=400, overlap=80)
    assert len(chunks) > 5
    assert all(len(c.text) <= 400 for c in chunks)
    assert all(c.heading == "Guia › Deploy" for c in chunks)
    # Overlap: o fim de um chunk reaparece no início do próximo.
    assert chunks[1].text.split("\n\n")[0] in chunks[0].text
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_giant_unbroken_text_is_cut() -> None:
    chunks = chunk_sections([Section(text="x" * 1000)], max_chars=300, overlap=0)
    assert [len(c.text) for c in chunks] == [300, 300, 300, 100]


@pytest.mark.parametrize(("size", "overlap"), [(100, 0), (500, 300), (500, -1)])
def test_invalid_chunk_parameters(size: int, overlap: int) -> None:
    with pytest.raises(ValueError, match=r"max_chars|overlap"):
        chunk_sections([Section(text="abc")], max_chars=size, overlap=overlap)
