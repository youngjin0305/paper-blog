(() => {
  const data = window.researchGraph;
  const svg = document.getElementById('flow-svg');
  if (!data || !svg) return;
  const viewport = document.getElementById('flow-viewport');
  const details = document.getElementById('flow-details');
  const field = document.getElementById('flow-field');
  const quality = document.getElementById('flow-quality');
  const links = document.getElementById('flow-links');
  const search = document.getElementById('flow-search');
  const reviewed = document.getElementById('flow-reviewed');
  const neighbors = document.getElementById('flow-neighbors');
  neighbors.disabled = true;
  neighbors.title = '노드의 ⓘ를 눌러 논문을 먼저 선택하세요.';
  const ns = 'http://www.w3.org/2000/svg';
  const colors = ['#2d654d', '#6477a3', '#9d6b35', '#8c638e', '#527f88'];
  const byId = new Map(data.nodes.map(n => [n.id, n]));
  let selected = null, bounds = {width: 500, height: 400}, camera = {x: 0, y: 0, width: 500, height: 400};
  let drag = null;
  const normalize = s => String(s || '').normalize('NFKC').toLowerCase();
  const html = (tag, text, className) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (className) e.className = className;
    return e;
  };
  const shape = (tag, attrs = {}, text) => {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const articleHref = id => document.documentElement.dataset.static === 'true'
    ? 'posts/' + encodeURIComponent(id) + '.html' : '/posts/' + encodeURIComponent(id);
  const publicHref = raw => {
    try { const u = new URL(raw); return u.protocol === 'https:' ? u.href : '#'; } catch { return '#'; }
  };
  const linkTo = node => {
    const link = html('a', node.summaryId ? '정리 글 읽기 →' : '원문 읽기 ↗');
    link.href = node.summaryId ? articleHref(node.summaryId) : publicHref(node.url);
    return link;
  };
  const heading = text => { details.replaceChildren(html('h2', text)); };
  const relatedEdges = id => data.edges.filter(e => e.source === id || e.target === id);

  function showNode(node) {
    selected = node.id;
    neighbors.disabled = false;
    heading(node.title);
    details.append(html('p', `${node.year} · ${node.topicLabel} · ${node.status}`), html('p', node.authors.join(', ')),
      html('p', `${node.qualityReason} · ${node.venue}`), html('p', node.conceptLabels.join(' / ')), linkTo(node));
    const list = html('ul');
    for (const edge of relatedEdges(node.id)) {
      const other = byId.get(edge.source === node.id ? edge.target : edge.source);
      if (!other) continue;
      const item = html('li');
      const button = html('button', `${edge.kind === 'citation' ? '인용' : '주제 연결(추정)'} · ${other.title}`);
      button.addEventListener('click', () => showEdge(edge));
      item.append(button); list.append(item);
    }
    if (list.childElementCount) details.append(html('h3', '연결된 논문'), list);
    else details.append(html('p', '현재 확보한 자료에서 연결 근거가 확인되지 않았습니다.'));
    if (neighbors.checked) draw();
  }

  function showEdge(edge) {
    const source = byId.get(edge.source), target = byId.get(edge.target);
    heading(edge.kind === 'citation' ? '확인된 인용 관계' : '주제 연결 · 추정');
    details.append(html('p', `${source.title} → ${target.title}`));
    if (edge.kind === 'citation') {
      details.append(html('p', '화살표 끝의 논문이 시작점의 논문을 참고문헌에서 인용합니다. 인용 사실만 확인하며, 방법을 직접 개선했다는 뜻은 아닙니다.'),
        html('p', `대조: ${edge.evidence.match} · 출처: ${edge.evidence.origin === 'crossref-references' ? 'Crossref 등록 참고문헌' : 'PDF References'} · 확인 ${new Date(edge.evidence.checkedAt).toLocaleDateString('sv-SE', {timeZone: 'Asia/Seoul'})}`));
      if (edge.evidence.excerpt) details.append(html('blockquote', edge.evidence.excerpt));
      const link = html('a', '인용 근거 원문 ↗'); link.href = publicHref(edge.evidence.url); details.append(link);
    } else {
      details.append(html('p', edge.reason), html('p', `유사도 ${edge.similarity.toFixed(3)}. 공통 개념이 있어 배치한 연결이며 확인된 인용으로 취급하지 않습니다.`));
    }
    const actions = html('div', undefined, 'flow-detail-actions'); actions.append(linkTo(source), linkTo(target)); details.append(actions);
  }

  function visibleNodes() {
    let nodes = data.nodes.filter(n => {
      const matchField = field.value === 'all' || field.value === 'topic:' + n.topic || field.value === 'group:' + n.group;
      const matchQuality = quality.value === 'all' || (quality.value === 'core' ? n.core
        : quality.value === 'venues' ? n.core || (n.inScope && n.venueConfirmed) : n.recommended);
      return matchField && matchQuality && (!reviewed.checked || n.summaryId);
    });
    let focus = new Set();
    const terms = normalize(search.value).split(/\s+/).filter(Boolean);
    if (terms.length) {
      focus = new Set(nodes.filter(n => terms.every(t => normalize([n.title, ...n.authors, ...n.conceptLabels].join(' ')).includes(t))).map(n => n.id));
    } else if (neighbors.checked && selected) focus.add(selected);
    if (terms.length || (neighbors.checked && selected)) {
      const expanded = new Set(focus);
      for (const edge of data.edges) {
        if (links.value === 'citation' && edge.kind !== 'citation') continue;
        if (focus.has(edge.source)) expanded.add(edge.target);
        if (focus.has(edge.target)) expanded.add(edge.source);
      }
      nodes = nodes.filter(n => expanded.has(n.id));
    }
    nodes.sort((a, b) => Number(focus.has(b.id)) - Number(focus.has(a.id)) || Number(b.core) - Number(a.core)
      || b.year - a.year || b.score - a.score || a.id.localeCompare(b.id));
    const total = nodes.length;
    return {nodes: nodes.slice(0, data.settings.max_nodes), total, focus};
  }

  function wrap(text, length = 29) {
    const lines = [], words = text.split(/\s+/); let current = '';
    for (let word of words) {
      while (word.length > length) { if (current) { lines.push(current); current = ''; } lines.push(word.slice(0, length)); word = word.slice(length); }
      if (current && current.length + word.length + 1 > length) { lines.push(current); current = ''; }
      current += (current ? ' ' : '') + word;
    }
    if (current) lines.push(current);
    return lines.length > 4 ? [...lines.slice(0, 3), lines[3].slice(0, length - 1) + '…'] : lines;
  }

  function fit(full = true) {
    const ratio = viewport.clientWidth / viewport.clientHeight;
    const mobile = viewport.clientWidth < 600 && !full;
    const width = mobile ? Math.min(bounds.width, 500) : Math.max(bounds.width, bounds.height * ratio);
    camera = {x: mobile ? 0 : (bounds.width - width) / 2, y: 0, width, height: width / ratio};
    applyCamera();
  }
  function applyCamera() { svg.setAttribute('viewBox', `${camera.x} ${camera.y} ${camera.width} ${camera.height}`); }
  function zoom(factor) {
    if (camera.width * factor < 250 || camera.width * factor > bounds.width * 5) return;
    camera.x += camera.width * (1 - factor) / 2;
    camera.y += camera.height * (1 - factor) / 2;
    camera.width *= factor; camera.height *= factor; applyCamera();
  }

  function draw() {
    const {nodes, total, focus} = visibleNodes();
    const ids = new Set(nodes.map(n => n.id));
    const edges = data.edges.filter(e => ids.has(e.source) && ids.has(e.target) && (links.value !== 'citation' || e.kind === 'citation'));
    svg.replaceChildren();
    document.getElementById('flow-count').textContent = `${nodes.length}편 · 인용 ${edges.filter(e => e.kind === 'citation').length} · 주제 연결 ${edges.filter(e => e.kind === 'related').length}`
      + (total > nodes.length ? ` · ${total - nodes.length}편은 검색/분야를 좁혀 확인` : '');
    document.getElementById('flow-empty').hidden = nodes.length !== 0;
    if (!nodes.length) return;
    const defs = shape('defs');
    for (const kind of ['citation', 'related']) {
      const marker = shape('marker', {id: 'arrow-' + kind, viewBox: '0 0 10 10', refX: 10, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse'});
      marker.append(shape('path', {d: 'M 0 0 L 10 5 L 0 10 z', fill: kind === 'citation' ? '#496959' : '#9aa89d'})); defs.append(marker);
    }
    svg.append(defs);
    const years = [...new Set(nodes.map(n => n.year))].sort((a, b) => a - b);
    const topics = [...new Set(nodes.map(n => n.topic))].sort((a, b) => {
      const x = nodes.find(n => n.topic === a), y = nodes.find(n => n.topic === b);
      return x.group.localeCompare(y.group) || x.topicLabel.localeCompare(y.topicLabel);
    });
    const positions = new Map(); let y = 65;
    bounds = {width: years.length * 275 + 70, height: 400};
    years.forEach((year, column) => {
      svg.append(shape('line', {x1: 35 + column * 275, y1: 42, x2: 35 + column * 275, y2: 1200, class: 'flow-year-line'}),
        shape('text', {x: 40 + column * 275, y: 28, class: 'flow-year'}, year));
    });
    topics.forEach((topic, lane) => {
      const items = nodes.filter(n => n.topic === topic);
      svg.append(shape('text', {x: 40, y: y + 22, class: 'flow-lane'}, items[0].group + ' / ' + items[0].topicLabel));
      let rows = 1;
      years.forEach((year, column) => {
        const bucket = items.filter(n => n.year === year).sort((a, b) => Number(b.core) - Number(a.core)
          || a.concepts.join().localeCompare(b.concepts.join()) || a.title.localeCompare(b.title));
        rows = Math.max(rows, bucket.length);
        bucket.forEach((node, row) => positions.set(node.id, {x: 40 + column * 275, y: y + 100 + row * 168, color: colors[lane % colors.length]}));
      });
      y += rows * 168 + 126;
    });
    bounds.height = y + 25;
    viewport.classList.toggle('compact', bounds.height < 500);
    for (const line of svg.querySelectorAll('.flow-year-line')) line.setAttribute('y2', bounds.height - 20);
    const edgeLayer = shape('g'); svg.append(edgeLayer);
    for (const [edgeIndex, edge] of edges.entries()) {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      const same = a.x === b.x;
      const skip = !same && b.x - a.x > 300 && a.y === b.y;
      const rise = 68 + (edgeIndex % 3) * 10;
      const path = same ? `M ${a.x + 230} ${a.y + 72} C ${a.x + 275} ${a.y + 72}, ${b.x + 275} ${b.y + 72}, ${b.x + 230} ${b.y + 72}`
        : skip ? `M ${a.x + 115} ${a.y} C ${a.x + 115} ${a.y - rise}, ${b.x + 115} ${b.y - rise}, ${b.x + 115} ${b.y}`
        : `M ${a.x + 230} ${a.y + 72} C ${a.x + 260} ${a.y + 72}, ${b.x - 30} ${b.y + 72}, ${b.x} ${b.y + 72}`;
      const e = shape('path', {d: path, class: 'flow-edge ' + edge.kind, 'marker-end': 'url(#arrow-' + edge.kind + ')'});
      const hit = shape('path', {d: path, class: 'flow-edge-hit', tabindex: 0, role: 'button', 'aria-label':
        (edge.kind === 'citation' ? '인용 근거: ' : '주제 연결 근거: ') + byId.get(edge.source).title + ' → ' + byId.get(edge.target).title});
      hit.addEventListener('click', () => showEdge(edge));
      hit.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); showEdge(edge); } });
      edgeLayer.append(e, hit);
    }
    for (const node of nodes) {
      const p = positions.get(node.id);
      const g = shape('g', {transform: `translate(${p.x} ${p.y})`, class: 'graph-node' + (node.core ? ' core' : '') + (focus.has(node.id) ? ' focused' : ''), 'data-node-id': node.id});
      const a = shape('a', {href: node.summaryId ? articleHref(node.summaryId) : publicHref(node.url), class: 'node-link', 'aria-label': node.title + (node.summaryId ? ' 정리 글 읽기' : ' 원문 읽기')});
      a.append(shape('title', {}, node.title + '\n' + node.qualityReason), shape('rect', {width: 230, height: 146, rx: 10, class: 'node-card', stroke: p.color}),
        shape('text', {x: 14, y: 23, class: 'node-year'}, `${node.core ? '★ ' : ''}${node.year}`));
      wrap(node.title).forEach((line, row) => a.append(shape('text', {x: 14, y: 47 + row * 18, class: 'node-title'}, line)));
      a.append(shape('text', {x: 14, y: 130, class: 'node-status'}, node.summaryId ? '정리 완료 · 요약 읽기 →' : node.status + ' · 원문 ↗'));
      const info = shape('g', {class: 'node-info', tabindex: 0, role: 'button', 'aria-label': node.title + ' 선정·연결 근거'});
      info.append(shape('circle', {cx: 211, cy: 20, r: 12}), shape('text', {x: 211, y: 24, 'text-anchor': 'middle'}, 'i'));
      info.addEventListener('click', () => showNode(node));
      info.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); showNode(node); } });
      g.append(a, info); svg.append(g);
    }
    fit(false);
  }

  const params = new URL(location.href).searchParams;
  if ([...field.options].some(o => o.value === params.get('field'))) field.value = params.get('field');
  if ([...quality.options].some(o => o.value === params.get('quality'))) quality.value = params.get('quality');
  search.value = params.get('q') || '';
  function filter() {
    const url = new URL(location.href);
    url.searchParams.set('field', field.value); url.searchParams.set('quality', quality.value);
    if (search.value) url.searchParams.set('q', search.value); else url.searchParams.delete('q');
    history.replaceState(null, '', url); draw();
  }
  for (const control of [quality, links, reviewed, neighbors]) control.addEventListener('change', filter);
  field.addEventListener('change', () => { selected = null; neighbors.checked = false; neighbors.disabled = true; filter(); });
  let debounce;
  search.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(filter, 130); });
  document.getElementById('flow-zoom-in').addEventListener('click', () => zoom(0.8));
  document.getElementById('flow-zoom-out').addEventListener('click', () => zoom(1.25));
  document.getElementById('flow-fit').addEventListener('click', () => fit(true));
  viewport.addEventListener('pointerdown', e => {
    if (e.target.closest('.node-link, .node-info, .flow-edge-hit')) return;
    drag = {x: e.clientX, y: e.clientY, camera: {...camera}}; viewport.setPointerCapture(e.pointerId);
  });
  viewport.addEventListener('pointermove', e => {
    if (!drag) return;
    camera.x = drag.camera.x - (e.clientX - drag.x) * camera.width / viewport.clientWidth;
    camera.y = drag.camera.y - (e.clientY - drag.y) * camera.height / viewport.clientHeight; applyCamera();
  });
  viewport.addEventListener('pointerup', () => { drag = null; });
  viewport.addEventListener('pointercancel', () => { drag = null; });
  viewport.addEventListener('wheel', e => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoom(e.deltaY > 0 ? 1.15 : 0.87); } }, {passive: false});
  new ResizeObserver(() => { if (!drag) fit(false); }).observe(viewport);
  draw();
})();
