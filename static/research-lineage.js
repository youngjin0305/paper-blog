(() => {
  const data = window.researchGraph;
  const forest = document.getElementById('lineage-forest');
  if (!data || !forest) return;
  const field = document.getElementById('flow-field');
  const quality = document.getElementById('flow-quality');
  const links = document.getElementById('flow-links');
  const search = document.getElementById('flow-search');
  const reviewed = document.getElementById('flow-reviewed');
  const neighbors = document.getElementById('flow-neighbors');
  const details = document.getElementById('lineage-details');
  const dialog = document.getElementById('lineage-dialog');
  const byId = new Map(data.nodes.map(node => [node.id, node]));
  let selected = null, parents = new Map(), drawing = 0;
  neighbors.disabled = true;
  neighbors.title = '카드의 연결·선정 근거에서 논문을 먼저 선택하세요.';
  const normalize = value => String(value || '').normalize('NFKC').toLowerCase();
  const html = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const shape = (tag, attributes) => {
    const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
    return element;
  };
  const articleHref = id => document.documentElement.dataset.static === 'true'
    ? 'posts/' + encodeURIComponent(id) + '.html' : '/posts/' + encodeURIComponent(id);
  const publicHref = value => {
    try { const url = new URL(value); return url.protocol === 'https:' ? url.href : '#'; } catch { return '#'; }
  };
  const linkTo = node => {
    const link = html('a', node.summaryId ? '정리 글 읽기 →' : '원문 읽기 ↗');
    link.href = node.summaryId ? articleHref(node.summaryId) : publicHref(node.url);
    return link;
  };
  const relatedEdges = id => data.edges.filter(edge => edge.source === id || edge.target === id);
  const chronological = (a, b) => a.year - b.year || (a.timeOrder || 0) - (b.timeOrder || 0) || a.id.localeCompare(b.id);
  const precedes = (a, b) => a.year < b.year || (a.year === b.year && a.datePrecision === 'day'
    && b.datePrecision === 'day' && a.timeOrder < b.timeOrder);
  const edgeLabel = edge => edge.kind === 'citation' ? '확인된 인용' : '주제 연결 · 추정';

  function heading(text) {
    const title = html('h2', text); title.id = 'lineage-detail-title';
    details.replaceChildren(title);
  }
  function openDetails() { if (!dialog.open) dialog.showModal(); }
  function showEdge(edge) {
    const source = byId.get(edge.source), target = byId.get(edge.target);
    heading(edgeLabel(edge));
    details.append(html('p', source.title + ' → ' + target.title));
    if (edge.kind === 'citation') {
      details.append(html('p', '아래의 후속 논문이 선행 논문을 참고문헌에서 인용합니다. 인용 사실만 확인하며 방법을 직접 계승·개선했다는 뜻은 아닙니다.'),
        html('p', `대조: ${edge.evidence.match} · 출처: ${edge.evidence.origin === 'crossref-references' ? 'Crossref 등록 참고문헌' : 'PDF References'} · 확인 ${new Date(edge.evidence.checkedAt).toLocaleDateString('sv-SE', {timeZone: 'Asia/Seoul'})}`));
      if (edge.evidence.excerpt) details.append(html('blockquote', edge.evidence.excerpt));
      const link = html('a', '인용 근거 원문 ↗'); link.href = publicHref(edge.evidence.url); details.append(link);
    } else {
      details.append(html('p', edge.reason), html('p', `유사도 ${edge.similarity.toFixed(3)}. 실제 인용·영향 관계가 확인된 연결은 아닙니다.`));
    }
    const actions = html('div', undefined, 'flow-detail-actions');
    actions.append(linkTo(source), linkTo(target)); details.append(actions); openDetails();
  }
  function showNode(node) {
    selected = node.id; neighbors.disabled = false;
    heading(node.title);
    details.append(html('p', `${node.year} · ${node.group} / ${node.topicLabel} · ${node.status}`),
      html('p', node.authors.join(', ')), html('p', node.qualityReason + ' · ' + node.venue),
      html('p', node.conceptLabels.join(' / ')), linkTo(node));
    const parent = parents.get(node.id);
    if (parent) details.append(html('p', '이번 계보에서 선택한 선행 논문: ' + byId.get(parent.source).title));
    const list = html('ul');
    for (const edge of relatedEdges(node.id)) {
      const incoming = edge.target === node.id;
      const other = byId.get(incoming ? edge.source : edge.target);
      if (!other) continue;
      const item = html('li'), button = html('button', `${edgeLabel(edge)} · ${incoming ? '선행' : '후속'}: ${other.title}`);
      button.addEventListener('click', () => showEdge(edge)); item.append(button); list.append(item);
    }
    if (list.childElementCount) details.append(html('h3', '모든 연결 근거'), list);
    else details.append(html('p', '현재 확보한 자료에서 연결 근거가 확인되지 않았습니다.'));
    if (neighbors.checked) draw();
    openDetails();
  }

  function visibleNodes() {
    let nodes = data.nodes.filter(node => {
      const matchField = field.value === 'all' || field.value === 'topic:' + node.topic || field.value === 'group:' + node.group;
      const matchQuality = quality.value === 'all' || (quality.value === 'core' ? node.core
        : quality.value === 'venues' ? node.core || (node.inScope && node.venueConfirmed) : node.recommended);
      return matchField && matchQuality && (!reviewed.checked || node.summaryId);
    });
    const terms = normalize(search.value).split(/\s+/).filter(Boolean);
    const focus = new Set(terms.length ? nodes.filter(node => terms.every(term =>
      normalize([node.title, ...node.authors, ...node.conceptLabels].join(' ')).includes(term))).map(node => node.id)
      : neighbors.checked && selected ? [selected] : []);
    if (terms.length || (neighbors.checked && selected)) {
      const expanded = new Set(focus);
      for (const edge of data.edges) {
        if (links.value === 'citation' && edge.kind !== 'citation') continue;
        if (focus.has(edge.source)) expanded.add(edge.target);
        if (focus.has(edge.target)) expanded.add(edge.source);
      }
      nodes = nodes.filter(node => expanded.has(node.id));
    }
    nodes.sort((a, b) => Number(focus.has(b.id)) - Number(focus.has(a.id)) || Number(b.core) - Number(a.core)
      || b.year - a.year || b.score - a.score || a.id.localeCompare(b.id));
    return {nodes: nodes.slice(0, data.settings.max_nodes), total: nodes.length, focus};
  }

  function buildParents(nodes, edges) {
    const result = new Map();
    for (const node of nodes) {
      const incoming = edges.filter(edge => edge.target === node.id && precedes(byId.get(edge.source), node));
      incoming.sort((a, b) => Number(b.kind === 'citation') - Number(a.kind === 'citation')
        || chronological(byId.get(b.source), byId.get(a.source)));
      if (incoming.length) result.set(node.id, incoming[0]);
    }
    return result;
  }

  function card(node, focus) {
    const slot = html('div', undefined, 'lineage-node');
    const parent = parents.get(node.id);
    if (parent) {
      const badge = html('button', '↓ ' + edgeLabel(parent), 'lineage-parent-link ' + parent.kind);
      badge.title = byId.get(parent.source).title + ' → ' + node.title;
      badge.addEventListener('click', () => showEdge(parent)); slot.append(badge);
    }
    const article = html('article', undefined, 'lineage-card' + (node.core ? ' core' : '') + (focus.has(node.id) ? ' focused' : ''));
    article.dataset.nodeId = node.id;
    const top = html('div', undefined, 'lineage-card-top');
    top.append(html('span', node.year, 'lineage-year'), html('span', node.core ? '★ 필수 논문' : node.summaryId ? '정리 완료' : '수집 논문', 'lineage-badge'));
    const title = html('h3'), link = html('a', node.title, 'lineage-title');
    link.href = node.summaryId ? articleHref(node.summaryId) : publicHref(node.url); title.append(link);
    const authors = node.authors.slice(0, 2).join(', ') + (node.authors.length > 2 ? ` 외 ${node.authors.length - 2}명` : '');
    const actions = html('div', undefined, 'lineage-card-actions'), info = html('button', '연결·선정 근거', 'lineage-info');
    info.setAttribute('aria-label', node.title + ' 연결·선정 근거'); info.addEventListener('click', () => showNode(node));
    actions.append(linkTo(node), info);
    article.append(top, html('p', node.topicLabel, 'lineage-topic'), title, html('p', authors, 'lineage-authors'), actions);
    slot.append(article); return slot;
  }

  function drawConnections() {
    const mobile = window.matchMedia('(max-width: 600px)').matches;
    for (const canvas of forest.querySelectorAll('.lineage-canvas')) {
      const tree = canvas.querySelector('.lineage-tree'), svg = canvas.querySelector('svg');
      const rect = tree.getBoundingClientRect(), positions = new Map();
      for (const article of tree.querySelectorAll('.lineage-card')) {
        const box = article.getBoundingClientRect();
        positions.set(article.dataset.nodeId, {x: box.left - rect.left + box.width / 2, top: box.top - rect.top, bottom: box.bottom - rect.top});
      }
      svg.setAttribute('width', tree.offsetWidth); svg.setAttribute('height', tree.offsetHeight);
      svg.setAttribute('viewBox', `0 0 ${tree.offsetWidth} ${tree.offsetHeight}`); svg.replaceChildren();
      const defs = shape('defs', {});
      for (const kind of ['citation', 'related']) {
        const marker = shape('marker', {id: 'lineage-arrow-' + canvas.dataset.family + '-' + kind, viewBox: '0 0 10 10', refX: 10,
          refY: 5, markerWidth: 5, markerHeight: 5, orient: 'auto'});
        marker.append(shape('path', {d: 'M 0 0 L 10 5 L 0 10 z', fill: kind === 'citation' ? '#496959' : '#9aa89d'})); defs.append(marker);
      }
      svg.append(defs);
      for (const [target, edge] of parents) {
        const a = positions.get(edge.source), b = positions.get(target);
        if (!a || !b) continue;
        // On phones siblings stack vertically. Route through the left gutter
        // so a link to a later sibling never runs through an earlier card.
        const path = mobile && Math.abs(a.x - b.x) < 1 && b.top - a.bottom > 180
          ? `M ${a.x} ${a.bottom} V ${a.bottom + 18} H 12 V ${b.top - 40} H ${b.x} V ${b.top}`
          : `M ${a.x} ${a.bottom} V ${(a.bottom + b.top) / 2} H ${b.x} V ${b.top}`;
        svg.append(shape('path', {d: path, class: 'lineage-edge ' + edge.kind,
          'data-source': edge.source, 'data-target': target,
          'marker-end': `url(#lineage-arrow-${canvas.dataset.family}-${edge.kind})`}));
      }
    }
  }
  function scheduleConnections() { cancelAnimationFrame(drawing); drawing = requestAnimationFrame(drawConnections); }

  function draw() {
    const {nodes, total, focus} = visibleNodes();
    const ids = new Set(nodes.map(node => node.id));
    const edges = data.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target) && (links.value !== 'citation' || edge.kind === 'citation'));
    parents = buildParents(nodes, edges);
    const children = new Map(nodes.map(node => [node.id, []]));
    for (const [target, edge] of parents) children.get(edge.source).push(byId.get(target));
    for (const items of children.values()) items.sort(chronological);
    const roots = nodes.filter(node => !parents.has(node.id)).sort(chronological);
    forest.replaceChildren(); document.getElementById('lineage-empty').hidden = nodes.length !== 0;
    document.getElementById('lineage-count').textContent = `${nodes.length}편 · 시작점 ${roots.length} · 가지 ${parents.size} · 전체 연결 근거 ${edges.length}`
      + (total > nodes.length ? ` · ${total - nodes.length}편은 검색/분야를 좁혀 확인` : '');
    const branch = node => {
      const item = html('li', undefined, 'lineage-branch'); item.append(card(node, focus));
      if (children.get(node.id).length) {
        const list = html('ul', undefined, 'lineage-children');
        for (const child of children.get(node.id)) list.append(branch(child));
        item.append(list);
      }
      return item;
    };
    roots.forEach((root, index) => {
      const family = html('section', undefined, 'lineage-family');
      const heading = html('div', undefined, 'lineage-family-heading');
      heading.append(html('span', String(index + 1).padStart(2, '0'), 'lineage-family-number'),
        html('h2', `${root.year} · ${root.group} / ${root.topicLabel}`));
      family.append(heading);
      const canvas = html('div', undefined, 'lineage-canvas'); canvas.dataset.family = index;
      canvas.setAttribute('tabindex', '0'); canvas.setAttribute('role', 'group');
      canvas.setAttribute('aria-label', root.title + ' 계보. 넓은 가지는 가로로 스크롤할 수 있습니다.');
      const tree = html('ul', undefined, 'lineage-tree'); tree.append(branch(root));
      canvas.append(shape('svg', {class: 'lineage-connectors', 'aria-hidden': 'true'}), tree);
      family.append(canvas); forest.append(family);
    });
    scheduleConnections();
  }

  const params = new URL(location.href).searchParams;
  for (const [control, key] of [[field, 'field'], [quality, 'quality'], [links, 'links']]) {
    if ([...control.options].some(option => option.value === params.get(key))) control.value = params.get(key);
  }
  search.value = params.get('q') || ''; reviewed.checked = params.get('reviewed') === '1';
  function filter() {
    const url = new URL(location.href);
    url.searchParams.set('field', field.value); url.searchParams.set('quality', quality.value); url.searchParams.set('links', links.value);
    if (search.value) url.searchParams.set('q', search.value); else url.searchParams.delete('q');
    if (reviewed.checked) url.searchParams.set('reviewed', '1'); else url.searchParams.delete('reviewed');
    history.replaceState(null, '', url); draw();
  }
  for (const control of [quality, links, reviewed, neighbors]) control.addEventListener('change', filter);
  field.addEventListener('change', () => { selected = null; neighbors.checked = false; neighbors.disabled = true; filter(); });
  let debounce;
  search.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(filter, 130); });
  for (const tab of document.querySelectorAll('[data-flow-view]')) tab.addEventListener('click', () => {
    const target = new URL(tab.href); target.search = location.search; tab.href = target.href;
  });
  new ResizeObserver(scheduleConnections).observe(forest);
  if (document.fonts) document.fonts.ready.then(scheduleConnections);
  draw();
})();
