"""Relatório HTML navegável da avaliação (publicado no GitHub Pages pelo CI).

Todo o conteúdo vem do corpus e das respostas do pipeline, então tudo é escapado com
`html.escape`; o JS embutido só filtra cartões já renderizados no servidor e a página
declara uma CSP que bloqueia qualquer recurso externo.
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape

from .evaluation import AnswerMetrics, CaseResult, RetrievalMetrics

_CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:"

_MODE_LABELS = {"lexical": "Só BM25", "vector": "Só vetores", "hybrid": "Híbrida (RRF)"}

_CSS = """
:root { color-scheme: light dark; --bg:#f7f7f8; --card:#fff; --ink:#1f2328; --muted:#59636e; --line:#d1d9e0;
  --ok:#1a7f37; --ok-bg:#dafbe1; --bad:#cf222e; --bad-bg:#ffebe9; --accent:#6e40c9; --chip:#eef1f4; }
@media (prefers-color-scheme: dark) { :root { --bg:#0d1117; --card:#161b22; --ink:#e6edf3; --muted:#9198a1;
  --line:#30363d; --ok:#3fb950; --ok-bg:#12261e; --bad:#f85149; --bad-bg:#2d1214; --accent:#a371f7; --chip:#21262d; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1040px; margin:0 auto; padding:32px 20px 64px; }
h1 { font-size:26px; margin:0 0 4px; letter-spacing:-.01em; }
h2 { font-size:18px; margin:36px 0 12px; }
p.lead { color:var(--muted); margin:0 0 20px; }
a { color:var(--accent); }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
.kpi { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }
.kpi span { display:block; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
.kpi strong { font-size:26px; font-variant-numeric:tabular-nums; }
table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line);
  border-radius:12px; overflow:hidden; }
th, td { text-align:left; padding:10px 14px; border-bottom:1px solid var(--line); }
th { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
td.num { font-variant-numeric:tabular-nums; }
tr:last-child td { border-bottom:0; }
.toolbar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:0 0 14px; }
.toolbar button { border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:999px;
  padding:6px 14px; font:inherit; font-size:13px; cursor:pointer; }
.toolbar button[aria-pressed="true"] { border-color:var(--accent); color:var(--accent); font-weight:600; }
.toolbar input { flex:1; min-width:200px; border:1px solid var(--line); background:var(--card); color:var(--ink);
  border-radius:8px; padding:7px 12px; font:inherit; }
details { background:var(--card); border:1px solid var(--line); border-radius:12px; margin:0 0 10px; }
summary { cursor:pointer; padding:14px 16px; display:flex; gap:12px; align-items:baseline; list-style:none; }
summary::-webkit-details-marker { display:none; }
.badge { flex:none; font-size:12px; font-weight:600; border-radius:999px; padding:2px 10px; }
.pass { color:var(--ok); background:var(--ok-bg); }
.fail { color:var(--bad); background:var(--bad-bg); }
.body { padding:0 16px 16px; border-top:1px solid var(--line); }
.answer { white-space:pre-wrap; background:var(--bg); border-radius:8px; padding:12px 14px; margin:12px 0; }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0; }
.chip { background:var(--chip); border-radius:6px; padding:2px 8px; font-size:13px; }
.chip.hit { outline:1px solid var(--ok); }
.chip.miss { outline:1px solid var(--bad); }
.small { font-size:13px; color:var(--muted); }
.retrieved td { font-size:13px; padding:7px 10px; }
footer { margin-top:40px; color:var(--muted); font-size:13px; }
"""

_JS = """
const cards = [...document.querySelectorAll('details[data-status]')];
const buttons = [...document.querySelectorAll('.toolbar button')];
const search = document.querySelector('#busca');
let filter = 'all';
function apply() {
  const term = search.value.trim().toLowerCase();
  let visible = 0;
  for (const card of cards) {
    const show = (filter === 'all' || card.dataset.status === filter || card.dataset.kind === filter)
      && (!term || card.dataset.q.includes(term));
    card.hidden = !show;
    if (show) visible++;
  }
  document.querySelector('#contagem').textContent = visible + ' de ' + cards.length;
}
for (const button of buttons) button.addEventListener('click', () => {
  filter = button.dataset.filter;
  for (const b of buttons) b.setAttribute('aria-pressed', String(b === button));
  apply();
});
search.addEventListener('input', apply);
apply();
"""


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _chips(items: Iterable[str], css: str = "") -> str:
    return "".join(f'<span class="chip {css}">{escape(item)}</span>' for item in items)


def _case_card(index: int, case: CaseResult) -> str:
    status = "pass" if case.passed else "fail"
    kind = "answerable" if case.answerable else "refusal"
    label = "passou" if case.passed else "falhou"
    if case.answerable:
        rank = (
            f"fonte certa na posição {case.first_relevant_rank}"
            if case.first_relevant_rank
            else "fonte certa fora do top-k"
        )
        checks = (
            f"{rank} · cita a fonte esperada: {'sim' if case.cites_expected else 'não'}"
            f" · contém os fatos-chave: {'sim' if case.contains_facts else 'não'}"
        )
    else:
        checks = "fora do escopo dos documentos · " + (
            "recusou corretamente" if not case.grounded else "respondeu sem base"
        )

    citations = "".join(
        f'<span class="chip {"hit" if c.expected else ""}">[{c.number}] {escape(c.source)}'
        f"{' › ' + escape(c.heading) if c.heading else ''}</span>"
        for c in case.citations
    )
    rows = "".join(
        "<tr>"
        f'<td class="num">{position}</td>'
        f'<td>{"✅ " if hit.relevant else ""}{escape(hit.source)}<div class="small">{escape(hit.heading)}</div></td>'
        f'<td class="num">{hit.lexical_rank or "—"}</td>'
        f'<td class="num">{hit.vector_rank or "—"}</td>'
        f'<td class="num">{hit.score:.4f}</td>'
        "</tr>"
        for position, hit in enumerate(case.retrieved, start=1)
    )
    expected = (
        f'<div class="small">Fontes esperadas</div><div class="chips">{_chips(case.expected_sources)}</div>'
        if case.expected_sources
        else ""
    )
    facts = (
        f'<div class="small">Fatos-chave exigidos</div><div class="chips">'
        f"{_chips(case.must_contain, 'hit' if case.contains_facts else 'miss')}</div>"
        if case.must_contain
        else ""
    )
    return f"""
<details data-status="{status}" data-kind="{kind}" data-q="{escape(case.question.lower())}">
  <summary>
    <span class="badge {status}">{label}</span>
    <span><strong>{index}.</strong> {escape(case.question)}</span>
  </summary>
  <div class="body">
    <p class="small">{escape(checks)}</p>
    <div class="answer">{escape(case.answer)}</div>
    {f'<div class="small">Citações</div><div class="chips">{citations}</div>' if citations else ""}
    {expected}
    {facts}
    <div class="small" style="margin-top:12px">Trechos recuperados (busca híbrida)</div>
    <table class="retrieved">
      <thead><tr><th>#</th><th>Documento › seção</th><th>BM25</th><th>Vetor</th><th>RRF</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</details>"""


def render_html(
    retrieval: list[RetrievalMetrics],
    answers: AnswerMetrics,
    cases: list[CaseResult],
    *,
    generator: str,
    generated_at: str,
    revision: str | None = None,
    repository_url: str | None = None,
) -> str:
    passed = sum(1 for case in cases if case.passed)
    hybrid = next((m for m in retrieval if m.mode == "hybrid"), retrieval[-1])
    kpis = [
        ("Perguntas aprovadas", f"{passed}/{len(cases)}"),
        (f"Hit rate@{hybrid.k} (híbrida)", _pct(hybrid.hit_rate)),
        ("MRR (híbrida)", f"{hybrid.mrr:.3f}"),
        ("Citam a fonte certa", _pct(answers.faithful_citation_rate)),
        ("Recusas corretas", _pct(answers.correct_refusal_rate)),
    ]
    kpi_html = "".join(f'<div class="kpi"><span>{escape(k)}</span><strong>{escape(v)}</strong></div>' for k, v in kpis)
    retrieval_rows = "".join(
        f"<tr><td>{escape(_MODE_LABELS.get(m.mode, m.mode))}</td><td class='num'>{_pct(m.hit_rate)}</td>"
        f"<td class='num'>{m.mrr:.3f}</td><td class='num'>{m.cases}</td></tr>"
        for m in retrieval
    )
    cards = "".join(_case_card(i, case) for i, case in enumerate(cases, start=1))
    source_link = f' · <a href="{escape(repository_url)}">código-fonte</a>' if repository_url else ""
    rev = f" · revisão <code>{escape(revision[:7])}</code>" if revision else ""
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{_CSP}">
<title>RAG Docs Assistant · relatório de avaliação</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <h1>RAG Docs Assistant · relatório de avaliação</h1>
  <p class="lead">Respostas reais do pipeline (ingestão → busca híbrida → geração com citações) para as
  {len(cases)} perguntas do golden set, geradas no CI a cada push na <code>main</code>.
  Gerador: <code>{escape(generator)}</code>{rev}{source_link}.</p>

  <div class="grid">{kpi_html}</div>

  <h2>Recuperação por modo de busca</h2>
  <table>
    <thead><tr><th>Modo</th><th>Hit rate@{hybrid.k}</th><th>MRR</th><th>Perguntas</th></tr></thead>
    <tbody>{retrieval_rows}</tbody>
  </table>

  <h2>Perguntas</h2>
  <div class="toolbar" role="group" aria-label="Filtros">
    <button type="button" data-filter="all" aria-pressed="true">Todas</button>
    <button type="button" data-filter="fail" aria-pressed="false">Falhas</button>
    <button type="button" data-filter="refusal" aria-pressed="false">Fora do escopo</button>
    <input id="busca" type="search" placeholder="Filtrar por texto da pergunta" aria-label="Filtrar perguntas">
    <span id="contagem" class="small" aria-live="polite"></span>
  </div>
  {cards}

  <footer>Gerado em {escape(generated_at)}. Uma pergunta passa quando a fonte certa aparece no top-k,
  a resposta cita essa fonte e contém os fatos-chave; perguntas fora do escopo passam quando o
  assistente se recusa a responder.</footer>
</main>
<script>{_JS}</script>
</body>
</html>
"""
