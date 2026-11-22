// Interface sem framework. Todo texto vindo da API entra por textContent, nunca innerHTML:
// os documentos indexados são conteúdo de terceiros e não podem injetar HTML na página.

const $ = (id) => document.getElementById(id);

const SUGGESTIONS = [
  'Quantos dias de férias posso vender?',
  'Qual o prazo para pedir reembolso de despesas?',
  'Quem aciona o incident commander num SEV1?',
  'Posso fazer deploy na sexta-feira?',
];

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of [].concat(children)) node.append(child);
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'content-type': 'application/json' }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message ?? body.detail?.message ?? `HTTP ${response.status}`);
  return body;
}

function renderAnswer(text) {
  // Transforma [n] em marcadores clicáveis que levam à fonte correspondente.
  const container = $('answer-text');
  container.replaceChildren();
  for (const part of text.split(/(\[\d+\])/)) {
    const match = /^\[(\d+)\]$/.exec(part);
    if (match) {
      container.append(el('a', { className: 'cite', href: `#fonte-${match[1]}`, textContent: match[1] }));
    } else {
      container.append(part);
    }
  }
}

// O caminho de títulos costuma começar pelo próprio título do documento; não precisa repetir.
const sectionOf = (c) => (c.heading.startsWith(`${c.title} › `) ? c.heading.slice(c.title.length + 3) : c.heading === c.title ? '' : c.heading);

function renderResult(data) {
  renderAnswer(data.answer);
  const badge = $('grounded');
  badge.textContent = data.grounded ? '✓ fundamentada nas fontes' : '! sem fonte nos documentos';
  badge.className = `badge ${data.grounded ? 'ok' : 'warn'}`;

  $('citations').replaceChildren(
    ...data.citations.map((c) =>
      el('li', { id: `fonte-${c.number}` }, [
        el('div', { className: 'citation-head' }, [
          el('span', { className: 'num', textContent: c.number }),
          el('strong', { textContent: c.title }),
          el('span', { className: 'where', textContent: [sectionOf(c), c.page ? `p. ${c.page}` : ''].filter(Boolean).join(' · ') }),
        ]),
        el('p', { className: 'excerpt', textContent: c.excerpt }),
        el('code', { textContent: c.source }),
      ]),
    ),
  );
  if (data.citations.length === 0) $('citations').append(el('li', { className: 'empty', textContent: 'Nenhuma fonte citada.' }));

  $('retrieved').replaceChildren(
    ...data.retrieved.map((r, i) =>
      el('tr', {}, [
        el('td', { textContent: i + 1 }),
        el('td', { textContent: `${r.source} › ${r.heading || (r.page ? `página ${r.page}` : '—')}` }),
        el('td', { textContent: r.lexicalRank ?? '—' }),
        el('td', { textContent: r.vectorRank ?? '—' }),
        el('td', { textContent: r.score.toFixed(4) }),
      ]),
    ),
  );
  $('result').hidden = false;
}

async function ask(question) {
  const button = $('ask-button');
  button.disabled = true;
  button.textContent = 'Buscando…';
  $('error').hidden = true;
  try {
    renderResult(await api('/api/ask', { method: 'POST', body: JSON.stringify({ question }) }));
  } catch (error) {
    $('error').textContent = `Não foi possível responder: ${error.message}`;
    $('error').hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = 'Perguntar';
  }
}

async function loadSidebar() {
  const [health, documents] = await Promise.all([api('/health'), api('/api/documents')]);
  $('engine').textContent = `${health.chunks} trechos · ${health.generator} · ${health.embedder}`;
  $('doc-count').textContent = documents.length;
  $('documents').replaceChildren(
    ...documents.map((d) =>
      el('li', { title: d.source }, [el('span', { textContent: d.title }), el('small', { textContent: `${d.chunk_count} trechos` })]),
    ),
  );
}

$('ask-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const question = $('question').value.trim();
  if (question) ask(question);
});

$('suggestions').append(
  ...SUGGESTIONS.map((text) =>
    el('button', {
      type: 'button',
      textContent: text,
      onclick: () => {
        $('question').value = text;
        ask(text);
      },
    }),
  ),
);

const initial = new URLSearchParams(location.search).get('q');
loadSidebar().catch((error) => {
  $('engine').textContent = `API indisponível: ${error.message}`;
});
if (initial) {
  $('question').value = initial;
  ask(initial);
}
