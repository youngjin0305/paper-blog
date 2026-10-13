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
  const showAll = document.getElementById('lineage-show-all');
  const byId = new Map(data.nodes.map(node => [node.id, node]));
  let selected = null, drawing = 0, layoutWidth = 0;
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
  const edgeLabel = edge => edge.kind === 'citation' ? '확인된 인용' : '주제 연결 · 추정';
  const preservationReason = edge => (data.settings.lineage_keep_edges || [])
    .find(rule => rule.source === edge.source && rule.target === edge.target)?.reason || '';

  function flowEdges(edges) {
    // Reduce only the currently displayed field. Hidden intermediate papers
    // must never be used to remove a direct connection.
    const reachability = pool => {
      const outgoing = new Map();
      for (const edge of pool) {
        if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
        outgoing.get(edge.source).push(edge);
      }
      return (source, target, skip = null) => {
        const pending = [source], seen = new Set([source]);
        while (pending.length) {
          for (const edge of outgoing.get(pending.pop()) || []) {
            if (edge === skip) continue;
            if (edge.target === target) return true;
            if (!seen.has(edge.target)) { seen.add(edge.target); pending.push(edge.target); }
          }
        }
        return false;
      };
    };
    const allPaths = reachability(edges);
    const citationPaths = reachability(edges.filter(edge => edge.kind === 'citation'));
    // Transitive reduction is unambiguous for a DAG. Keep a cyclic field
    // intact rather than simultaneously removing its routes into a cycle.
    const cyclic = edges.some(edge => allPaths(edge.target, edge.source));
    return edges.filter(edge => showAll.checked || preservationReason(edge) || cyclic
      || !(edge.kind === 'citation' ? citationPaths : allPaths)(edge.source, edge.target, edge))
      .map(edge => ({...edge, keepReason: preservationReason(edge)}));
  }

  function heading(text) {
    const title = html('h2', text); title.id = 'lineage-detail-title';
    details.replaceChildren(title);
  }
  function openDetails() { if (!dialog.open) dialog.showModal(); }
  function showEdge(edge) {
    const source = byId.get(edge.source), target = byId.get(edge.target);
    heading(edgeLabel(edge));
    details.append(html('p', source.title + ' → ' + target.title));
    const keepReason = preservationReason(edge);
    if (keepReason) details.append(html('p', '표시 예외: ' + keepReason, 'lineage-keep-reason'));
    if (edge.kind === 'citation') {
      details.append(html('p', '화살표 끝의 논문이 시작점의 논문을 참고문헌에서 인용합니다. 인용 사실만 확인하며 방법을 직접 계승·개선했다는 뜻은 아닙니다.'),
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

  function card(node, focus) {
    const slot = html('div', undefined, 'lineage-node');
    const article = html('article', undefined, 'lineage-card' + (node.core ? ' core' : '') + (focus.has(node.id) ? ' focused' : ''));
    article.dataset.nodeId = node.id;
    article.dataset.year = node.year;
    const top = html('div', undefined, 'lineage-card-top');
    top.append(html('span', node.core ? '★ 필수 논문' : node.summaryId ? '정리 완료' : '수집 논문', 'lineage-badge'));
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
    for (const canvas of forest.querySelectorAll('.lineage-canvas')) {
      const timeline = canvas.querySelector('.lineage-timeline'), svg = canvas.querySelector('svg');
      const origin = timeline.getBoundingClientRect(), positions = new Map();
      for (const row of timeline.querySelectorAll('.lineage-year-row')) {
        const cards = [...row.querySelectorAll('.lineage-card')];
        const boxes = cards.map(card => card.getBoundingClientRect());
        cards.forEach((card, index) => {
          const box = boxes[index];
          positions.set(card.dataset.nodeId, {x: box.left - origin.left + box.width / 2,
            left: box.left - origin.left, right: box.right - origin.left,
            top: box.top - origin.top, bottom: box.bottom - origin.top});
        });
      }
      svg.setAttribute('width', timeline.offsetWidth); svg.setAttribute('height', timeline.offsetHeight);
      svg.setAttribute('viewBox', `0 0 ${timeline.offsetWidth} ${timeline.offsetHeight}`); svg.replaceChildren();
      const defs = shape('defs', {});
      for (const kind of ['citation', 'related']) {
        const marker = shape('marker', {id: 'lineage-arrow-' + canvas.dataset.field + '-' + kind, viewBox: '0 0 10 10', refX: 10,
          refY: 5, markerWidth: 5, markerHeight: 5, orient: 'auto'});
        marker.append(shape('path', {d: 'M 0 0 L 10 5 L 0 10 z', fill: kind === 'citation' ? '#496959' : '#9aa89d'})); defs.append(marker);
      }
      svg.append(defs);
      const gap = window.matchMedia('(max-width: 600px)').matches ? 16 : 32;
      const channels = [...new Set([...positions.values()].flatMap(box => [box.left - gap / 2, box.right + gap / 2]))];
      const usedChannels = new Map();
      const blocked = (points, source, target) => [...positions].some(([id, box]) => {
        if (id === source || id === target) return false;
        return points.slice(1).some((point, index) => {
          const prev = points[index];
          return prev[0] === point[0]
            ? point[0] > box.left + 1 && point[0] < box.right - 1 && Math.max(prev[1], point[1]) > box.top + 1 && Math.min(prev[1], point[1]) < box.bottom - 1
            : point[1] > box.top + 1 && point[1] < box.bottom - 1 && Math.max(prev[0], point[0]) > box.left + 1 && Math.min(prev[0], point[0]) < box.right - 1;
        });
      });
      const edges = flowEdges(data.edges.filter(edge => positions.has(edge.source) && positions.has(edge.target)
        && (links.value !== 'citation' || edge.kind === 'citation')));
      edges.forEach((edge, index) => {
        const a = positions.get(edge.source), b = positions.get(edge.target);
        const sourceYear = byId.get(edge.source).year, targetYear = byId.get(edge.target).year;
        let points;
        if (sourceYear === targetYear && Math.abs(a.top - b.top) < 1) {
          // Same-year citations remain visible without inventing a date order.
          const y = Math.min(a.top, b.top) - 24 - (index % 3) * 6;
          points = [[a.x, a.top], [a.x, y], [b.x, y], [b.x, b.top]];
        } else {
          const rowBottom = Math.max(...[...positions.values()].filter(box => Math.abs(box.top - a.top) < 1).map(box => box.bottom));
          const startY = rowBottom + 24 + (index % 3) * 6;
          const endY = b.top - 24 - (index % 3) * 6;
          const direct = [[a.x, a.bottom], [a.x, startY], [b.x, startY], [b.x, b.top]];
          if (b.top > a.bottom && !blocked(direct, edge.source, edge.target)) points = direct;
          else {
            const candidates = channels.map(x => ({x, cost: Math.abs(a.x - x) + Math.abs(b.x - x) + (usedChannels.get(x) || 0) * 32}))
              .sort((x, y) => x.cost - y.cost || x.x - y.x);
            const channel = candidates.find(({x}) => !blocked([[a.x, a.bottom], [a.x, startY], [x, startY], [x, endY], [b.x, endY], [b.x, b.top]], edge.source, edge.target)).x;
            usedChannels.set(channel, (usedChannels.get(channel) || 0) + 1);
            points = [[a.x, a.bottom], [a.x, startY], [channel, startY], [channel, endY], [b.x, endY], [b.x, b.top]];
          }
        }
        const path = points.map((point, i) => `${i ? 'L' : 'M'} ${point[0]} ${point[1]}`).join(' ');
        const visible = shape('path', {d: path, class: 'lineage-edge ' + edge.kind + (edge.keepReason ? ' preserved' : ''),
          'data-source': edge.source, 'data-target': edge.target,
          'marker-end': `url(#lineage-arrow-${canvas.dataset.field}-${edge.kind})`});
        const hit = shape('path', {d: path, class: 'lineage-edge-hit', tabindex: 0, role: 'button',
          'aria-label': edgeLabel(edge) + ': ' + byId.get(edge.source).title + ' → ' + byId.get(edge.target).title});
        hit.addEventListener('click', () => showEdge(edge));
        hit.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showEdge(edge); } });
        svg.append(visible, hit);
      });
    }
  }
  function scheduleConnections() { cancelAnimationFrame(drawing); drawing = requestAnimationFrame(drawConnections); }

  function draw() {
    layoutWidth = forest.clientWidth;
    const {nodes, total, focus} = visibleNodes();
    const ids = new Set(nodes.map(node => node.id));
    const edges = data.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target) && (links.value !== 'citation' || edge.kind === 'citation'));
    const topics = [...new Set(nodes.map(node => node.topic))].sort((a, b) => {
      const x = nodes.find(node => node.topic === a), y = nodes.find(node => node.topic === b);
      return x.group.localeCompare(y.group) || x.topicLabel.localeCompare(y.topicLabel);
    });
    forest.replaceChildren(); document.getElementById('lineage-empty').hidden = nodes.length !== 0;
    const within = edges.filter(edge => byId.get(edge.source).topic === byId.get(edge.target).topic);
    const shown = topics.flatMap(topic => flowEdges(within.filter(edge => byId.get(edge.source).topic === topic)));
    document.getElementById('lineage-exception-legend').hidden = !shown.some(edge => edge.keepReason);
    document.getElementById('lineage-count').textContent = `${nodes.length}편 · ${topics.length}개 분야 · 인용 ${shown.filter(edge => edge.kind === 'citation').length} · 주제 연결 ${shown.filter(edge => edge.kind === 'related').length}`
      + (within.length > shown.length ? ` · 중복 연결 ${within.length - shown.length}개 생략` : '')
      + (edges.length > within.length ? ` · 분야 간 연결 ${edges.length - within.length} (카드 근거에서 확인)` : '')
      + (total > nodes.length ? ` · ${total - nodes.length}편은 검색/분야를 좁혀 확인` : '');
    topics.forEach((topic, index) => {
      const items = nodes.filter(node => node.topic === topic);
      const years = [...new Set(items.map(node => node.year))].sort((a, b) => a - b);
      const mobile = window.matchMedia('(max-width: 600px)').matches;
      const capacity = Math.max(1, Math.floor((layoutWidth - (mobile ? 94 : 172)) / (mobile ? 244 : 292)));
      const columns = Math.min(3, capacity, Math.max(...years.map(year => items.filter(node => node.year === year).length)));
      const section = html('section', undefined, 'lineage-field');
      section.dataset.topic = topic;
      const heading = html('div', undefined, 'lineage-field-heading');
      heading.append(html('h2', items[0].group + ' / ' + items[0].topicLabel), html('span', items.length + '편'));
      section.append(heading);
      const canvas = html('div', undefined, 'lineage-canvas'); canvas.dataset.field = index;
      canvas.setAttribute('tabindex', '0'); canvas.setAttribute('role', 'group');
      canvas.setAttribute('aria-label', items[0].topicLabel + ' 연도별 그래프. 같은 해의 논문이 많으면 가로로 스크롤할 수 있습니다.');
      const timeline = html('div', undefined, 'lineage-timeline'), placed = new Map();
      for (const year of years) {
        const bucket = items.filter(node => node.year === year);
        const desired = node => {
          const parents = shown.filter(edge => edge.target === node.id && placed.has(edge.source));
          return parents.length ? parents.reduce((sum, edge) => sum + placed.get(edge.source), 0) / parents.length : (columns - 1) / 2;
        };
        bucket.sort((a, b) => desired(a) - desired(b) || Number(b.core) - Number(a.core) || chronological(a, b));
        const row = html('div', undefined, 'lineage-year-row'); row.dataset.year = year;
        row.append(html('span', year, 'lineage-year-label'), html('div', undefined, 'lineage-year-guide'), html('div', undefined, 'lineage-year-spacer'));
        const cells = html('div', undefined, 'lineage-cells'); cells.dataset.columns = columns;
        for (let offset = 0; offset < bucket.length; offset += columns) {
          const free = new Set(Array.from({length: columns}, (_, column) => column)), slots = new Map();
          for (const node of bucket.slice(offset, offset + columns)) {
            const column = [...free].sort((a, b) => Math.abs(a - desired(node)) - Math.abs(b - desired(node)) || a - b)[0];
            free.delete(column); slots.set(column, node); placed.set(node.id, column);
          }
          for (let column = 0; column < columns; column++) {
            const cell = html('div', undefined, 'lineage-cell');
            if (slots.has(column)) cell.append(card(slots.get(column), focus));
            cells.append(cell);
          }
        }
        row.append(cells, html('div', undefined, 'lineage-right-spacer')); timeline.append(row);
      }
      canvas.append(shape('svg', {class: 'lineage-connectors', role: 'group', 'aria-label': '논문 연결 근거'}), timeline);
      section.append(canvas); forest.append(section);
    });
    scheduleConnections();
  }

  const params = new URL(location.href).searchParams;
  for (const [control, key] of [[field, 'field'], [quality, 'quality'], [links, 'links']]) {
    if ([...control.options].some(option => option.value === params.get(key))) control.value = params.get(key);
  }
  search.value = params.get('q') || ''; reviewed.checked = params.get('reviewed') === '1';
  showAll.checked = params.get('expand') === '1';
  function filter() {
    const url = new URL(location.href);
    url.searchParams.set('field', field.value); url.searchParams.set('quality', quality.value); url.searchParams.set('links', links.value);
    if (search.value) url.searchParams.set('q', search.value); else url.searchParams.delete('q');
    if (reviewed.checked) url.searchParams.set('reviewed', '1'); else url.searchParams.delete('reviewed');
    if (showAll.checked) url.searchParams.set('expand', '1'); else url.searchParams.delete('expand');
    history.replaceState(null, '', url); draw();
  }
  for (const control of [quality, links, reviewed, neighbors, showAll]) control.addEventListener('change', filter);
  field.addEventListener('change', () => { selected = null; neighbors.checked = false; neighbors.disabled = true; filter(); });
  let debounce;
  search.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(filter, 130); });
  for (const tab of document.querySelectorAll('[data-flow-view]')) tab.addEventListener('click', () => {
    const target = new URL(tab.href); target.search = location.search; tab.href = target.href;
  });
  new ResizeObserver(() => {
    if (forest.clientWidth !== layoutWidth) draw(); else scheduleConnections();
  }).observe(forest);
  if (document.fonts) document.fonts.ready.then(scheduleConnections);
  draw();
})();
