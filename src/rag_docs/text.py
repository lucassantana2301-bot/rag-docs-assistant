"""Normalização de texto compartilhada entre chunking, embeddings locais e respostas extrativas."""

from __future__ import annotations

import re
import unicodedata

_WORD = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
# Divide em fim de frase sem quebrar abreviações comuns ("ex.", "Sr.") nem números ("R$ 1.200,00").
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\"“(])")
_ABBREVIATIONS = ("ex.", "sr.", "sra.", "dr.", "dra.", "p.", "etc.", "obs.", "aprox.", "art.", "nº.")

# Palavras sem valor de busca em português. Lista curta de propósito: cortar demais derruba recall.
_RAW_STOPWORDS = """
    a o as os um uma uns umas de do da dos das no na nos nas em por para pelo pela pelos pelas com sem
    e ou que se ao aos à às é ser foi são sou era como mais menos muito qual quais quando onde quem
    eu tu ele ela nós vós eles elas meu minha seu sua seus suas nosso nossa isso isto aquilo este esta
    esse essa já não sim também tem têm ter há posso pode podem preciso devo deve the of and to in is
    """.split()


def normalize(text: str) -> str:
    """NFKC, espaços colapsados e sem caracteres de controle (comuns em texto extraído de PDF)."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fold(text: str) -> str:
    """Minúsculas e sem acento: "Férias" e "ferias" viram o mesmo termo."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


STOPWORDS = frozenset(fold(word) for word in _RAW_STOPWORDS)


def tokenize(text: str, *, drop_stopwords: bool = True) -> list[str]:
    tokens = _WORD.findall(fold(text))
    if drop_stopwords:
        return [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    return tokens


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_END.split(text.strip())
    sentences: list[str] = []
    for part in parts:
        if sentences and sentences[-1].lower().endswith(_ABBREVIATIONS):
            sentences[-1] = f"{sentences[-1]} {part}"
        else:
            sentences.append(part)
    return [s.strip() for s in sentences if s.strip()]
