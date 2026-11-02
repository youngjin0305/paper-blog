(() => {
  'use strict';
  const data = window.researchGraph, canvas = document.getElementById('atlas-canvas');
  if (!data?.research || !canvas) return;
  const research = data.research, byId = new Map(data.nodes.map(n => [n.id,n]));
  const detail = document.getElementById('atlas-detail');
  const controls = Object.fromEntries(['topic','method','target','search','pending','unclassified'].map(k => [k,document.getElementById('atlas-'+k)]));
  let mode = 'lineage', selected = null, comparison = [], frame;
  const element = (tag,text,cls) => { const el=document.createElement(tag); if(text!==undefined) el.textContent=text; if(cls) el.className=cls; return el; };
  const button = (text,action,cls) => {const b=element('button',text,cls); b.type='button'; b.addEventListener('click',action); return b;};
  const safe = url => {try {const u=new URL(url); return u.protocol==='https:'?u.href:'#';} catch {return '#';}};
  const link = (text,url) => {const a=element('a',text);a.href=safe(url);a.target='_blank';a.rel='noopener noreferrer';return a;};
  const profile = n => n.research;
  const studies = n => profile(n)?.studies || [];
  const norm = s => String(s||'').normalize('NFKC').toLowerCase();
  const status = p => !p ? '미분류' : p.status==='pending' ? '자동 분류 · 검토 전' : p.basis==='abstract' ? '초록 근거 · 분류 확인' : '전문 근거 · 분류 확인';
  const ordered = ns => [...ns].sort((a,b)=>a.year-b.year || a.id.localeCompare(b.id));
  function available(n) {return n.topic===controls.topic.value && (profile(n)? profile(n).status==='reviewed'||controls.pending.checked : controls.unclassified.checked);}
  function visible() {return ordered(data.nodes.filter(n=>available(n)
    && (!controls.method.value || studies(n).some(s=>s.method===controls.method.value))
    && (!controls.target.value || studies(n).some(s=>s.target===controls.target.value))
    && norm([n.title,...n.authors,profile(n)?.contribution].join(' ')).includes(norm(controls.search.value))));}
  function evidence(parent,p) {if(!p?.evidence)return;const e=p.evidence;parent.append(element('p',status(p),'atlas-badge'),link('근거 원문 ↗',e.url),element('small',`${e.locator} · 확인 ${e.checkedAt.slice(0,10)}`));}
  function article(parent,n) {if(n.summaryId){const a=element('a','정리 글 읽기 →','atlas-read');a.href=document.documentElement.dataset.static==='true'?'posts/'+encodeURIComponent(n.summaryId)+'.html':'/posts/'+encodeURIComponent(n.summaryId);parent.append(a);}else parent.append(link('원문 읽기 ↗',n.url));}
  function describe(parent,label,value){parent.append(element('h3',label),element('p',value||'기재 확인 안 됨 — 추가 검토 필요'));}
  function showNode(n) {
    selected=n.id; const p=profile(n); detail.replaceChildren(element('h2',n.title));
    detail.append(element('p',`${n.year} · ${n.authors.join(', ')} · ${n.venue}`));article(detail,n);
    evidence(detail,p);describe(detail,'이 논문이 바꾼 점',p?.contribution);
    const incoming=research.relations.filter(r=>r.target===n.id && (r.status==='reviewed'||controls.pending.checked));
    const outgoing=research.relations.filter(r=>r.source===n.id && (r.status==='reviewed'||controls.pending.checked));
    for(const [label,rels,inbound] of [['출발점',incoming,true],['후속 연구',outgoing,false]]) {
      detail.append(element('h3',label));
      if(!rels.length)detail.append(element('p','현재 자료에서 직접 계승·분석 근거 미확인'));
      for(const r of rels){const other=byId.get(inbound?r.source:r.target);if(!other)continue;const box=element('div',undefined,'atlas-relation');
        box.append(button(other.title,()=>{showNode(other);paint();}),element('strong',research.relationLabels[r.kind]),element('p',r.change));evidence(box,r);detail.append(box);}
    }
    describe(detail,'확인한 연구 조건',studies(n).map(s=>`${s.target} · ${research.methods[s.method]} · ${s.goal||''}\n${s.conditions||'기재 확인 안 됨'}`).join('\n\n'));
    describe(detail,'저자가 밝힌 한계',p?.limitations);
    detail.append(button(comparison.includes(n.id)?'비교에서 제외':'비교에 추가',()=>toggleCompare(n.id)));
    paint();
  }
  function toggleCompare(id){comparison=comparison.includes(id)?comparison.filter(x=>x!==id):[...comparison.slice(-1),id];render();if(selected)showNode(byId.get(selected));}
  function card(n){const p=profile(n),box=element('article',undefined,'atlas-card'+(n.id===selected?' selected':''));box.dataset.paper=n.id;
    box.append(element('span',status(p),'atlas-badge'),button((n.core?'★ ':'')+n.title,()=>showNode(n),'atlas-title'),element('p',p?.contribution||'연구 조건과 변경점 분류가 필요합니다.'));
    const tags=element('div',undefined,'atlas-tags'); for(const m of new Set(studies(n).map(s=>s.method)))tags.append(element('span',research.methods[m]));box.append(tags);
    for(const r of research.relations.filter(r=>r.target===n.id&&r.status==='reviewed'))box.append(element('small',research.relationLabels[r.kind]+' ← '+(byId.get(r.source)?.authors[0]||'선행 연구'),'atlas-parent'));
    const actions=element('div',undefined,'atlas-actions');actions.append(button(comparison.includes(n.id)?'비교 제외':'비교 +',()=>toggleCompare(n.id)));article(actions,n);box.append(actions);return box;}
  function timeline(nodes){const wrap=element('div',undefined,'atlas-timeline');
    wrap.append(element('p','연도별 계승·분석 지도 · 논문 선택 시 직접 연결 강조 · 의미가 다른 직접 연결은 생략하지 않음','atlas-hint'));
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.classList.add('atlas-lines');svg.setAttribute('aria-hidden','true');wrap.append(svg);
    for(const year of [...new Set(nodes.map(n=>n.year))]){const row=element('section',undefined,'atlas-year');row.append(element('h2',String(year)));const cards=element('div',undefined,'atlas-year-cards');
      const yearNodes=nodes.filter(n=>n.year===year).sort((a,b)=>(studies(a)[0]?.method||'').localeCompare(studies(b)[0]?.method||''));
      for(const n of yearNodes)cards.append(card(n));row.append(cards);wrap.append(row);}
    canvas.append(wrap);requestAnimationFrame(paint);
  }
  function paint(){cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
    const wrap=canvas.querySelector('.atlas-timeline'),svg=canvas.querySelector('svg');if(!wrap||!svg)return;
    svg.replaceChildren();const rect=wrap.getBoundingClientRect();svg.setAttribute('width',rect.width);svg.setAttribute('height',rect.height);
    const shape=(tag,attrs)=>{const e=document.createElementNS(svg.namespaceURI,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e;};
    const defs=shape('defs',{}),marker=shape('marker',{id:'atlas-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});marker.append(shape('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#467765'}));defs.append(marker);svg.append(defs);
    const positions=new Map([...wrap.querySelectorAll('[data-paper]')].map(e=>[e.dataset.paper,e]));
    let lane=0;
    for(const r of research.relations){if((r.status!=='reviewed'&&!controls.pending.checked)||!positions.has(r.source)||!positions.has(r.target))continue;
      const a=positions.get(r.source).getBoundingClientRect(),b=positions.get(r.target).getBoundingClientRect();
      const x=a.left+a.width/2-rect.left,y=a.bottom-rect.top,tx=b.left+b.width/2-rect.left,ty=b.top-rect.top;
      const active=!selected||r.source===selected||r.target===selected;
      const gutter=48+(lane++%7)*4, out=y+12, into=ty-12;
      const path=shape('path',{d:`M ${x} ${y} L ${x} ${out} L ${gutter} ${out} L ${gutter} ${into} L ${tx} ${into} L ${tx} ${ty}`,fill:'none','stroke-dasharray':r.status==='pending'?'5 5':'none',stroke:'#467765','stroke-width':active?2:1,opacity:active?.7:.12,'marker-end':'url(#atlas-arrow)'});path.append(shape('title',{}));path.firstChild.textContent=research.relationLabels[r.kind]+': '+r.change;svg.append(path);
    }
    for(const [id,box] of positions)box.classList.toggle('selected',id===selected);
  });}
  function matrix(nodes){const universe=data.nodes.filter(n=>n.topic===controls.topic.value&&profile(n)?.status==='reviewed');
    const targets=[...new Set([...universe,...nodes].flatMap(n=>studies(n).map(s=>s.target)))].sort();
    canvas.append(element('p','숫자는 해당 조합을 명시한 논문 수입니다. 빈칸은 현재 분류 자료에서 미확인입니다.','atlas-hint'));
    if(!targets.length){canvas.append(element('p','이 분야의 연구 조건 분류가 아직 없습니다. 미분류 논문을 포함해 살펴보세요.'));return;}
    const scroller=element('div',undefined,'atlas-table-scroll'),table=element('table',undefined,'atlas-matrix'),head=element('tr');head.append(element('th','기법 / 대상'));
    for(const t of targets)head.append(element('th',t));const thead=element('thead');thead.append(head);table.append(thead);const tbody=element('tbody');
    for(const [method,label] of Object.entries(research.methods)){const tr=element('tr');tr.append(element('th',label));for(const target of targets){
      const matches=pool=>pool.filter(n=>studies(n).some(s=>s.method===method&&s.target===target));const local=matches(nodes),all=matches(universe);const td=element('td');
      const b=button(local.length?`${local.length}편`:all.length?`필터 밖 ${all.length}편`:'미확인',()=>showCell(target,method,local,all),local.length?'atlas-filled':'atlas-empty');b.setAttribute('aria-label',`${target} · ${label}: ${b.textContent}`);td.append(b);tr.append(td);
    }tbody.append(tr);}table.append(tbody);scroller.append(table);canvas.append(scroller);
  }
  function showCell(target,method,nodes,all){detail.replaceChildren(element('h2',`${target} × ${research.methods[method]}`));
    detail.append(element('p',nodes.length?'연구별 조건을 확인한 뒤 비교하세요.':all.length?'현재 필터가 관련 연구를 숨기고 있습니다.':'현재 자료에서 미확인입니다. 연구가 없다는 결론이 아닙니다.'));
    for(const n of nodes.length?nodes:all){detail.append(button(n.title,()=>showNode(n),'atlas-title'));describe(detail,'조건',studies(n).filter(s=>s.target===target&&s.method===method).map(s=>s.conditions||'기재 확인 안 됨').join('\n'));}
    const query=`${target} neural cryptanalysis ${method==='difference'?'input difference':method==='data'?'dataset':method==='interpretation'?'interpretability':method}`;
    detail.append(element('h3','추가 조사 질문'),element('p',`${target}에서 ${research.methods[method]}을 다룬 연구가 있는가? 적용 조건과 실패 결과도 함께 확인하기.`),link('arXiv에서 검색 ↗','https://arxiv.org/search/?query='+encodeURIComponent(query)+'&searchtype=all'));
    const note=`# 조사 질문\n${target} × ${research.methods[method]}\n\n상태: 추가 조사 필요; 미연구 단정 금지\n검색어: ${query}\n현재 필터 ${nodes.length}편 / 검토된 자료 ${all.length}편\n\n관련 논문\n${all.map(n=>'- '+n.title+' '+n.url).join('\n')}\n\n조사일:\n검색한 출처·범위:\n찾은 연구:\n다음 검증 실험:\n`;
    detail.append(button('조사 메모 내려받기',()=>{const url=URL.createObjectURL(new Blob([note],{type:'text/markdown;charset=utf-8'}));const a=element('a');a.href=url;a.download='research-question.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}));
  }
  function compare(){if(comparison.length<2){canvas.append(element('p','계승 지도에서 논문 두 편의 ‘비교 +’를 선택하세요.'));if(comparison.length)canvas.append(card(byId.get(comparison[0])));return;}
    const ns=comparison.map(id=>byId.get(id)),table=element('table',undefined,'atlas-compare');
    for(const [label,fn] of [['논문',n=>n.title],['근거 수준',n=>status(profile(n))],['출발점',n=>research.relations.filter(r=>r.target===n.id&&(r.status==='reviewed'||controls.pending.checked)).map(r=>byId.get(r.source)?.title+' — '+r.change).join('\n')],['변경점',n=>profile(n)?.contribution],['대상·기법·목표·조건',n=>studies(n).map(s=>`${s.target} / ${research.methods[s.method]} / ${s.goal||''}\n${s.conditions||'기재 확인 안 됨'}`).join('\n\n')],['저자 명시 한계',n=>profile(n)?.limitations]]){const row=element('tr');row.append(element('th',label));for(const n of ns)row.append(element('td',fn(n)||'기재 확인 안 됨'));table.append(row);}
    const wrap=element('div',undefined,'atlas-table-scroll');wrap.append(table);canvas.append(element('p','조건이 다른 결과의 단순 수치 순위는 제공하지 않습니다. 비교 선택은 필터 변경 후에도 유지됩니다.','atlas-hint'),wrap,button('비교 선택 비우기',()=>{comparison=[];render();}));
  }
  function render(){const nodes=visible();canvas.replaceChildren();document.getElementById('atlas-comparison-count').textContent=`${comparison.length}/2`;
    const all=data.nodes.filter(n=>n.topic===controls.topic.value),classified=all.filter(n=>profile(n));document.getElementById('atlas-status').textContent=`현재 ${nodes.length}편 · 분야 전체 ${all.length}편 · 분류 있음 ${classified.length}편 / 미분류 ${all.length-classified.length}편 · 우선순위와 분류 근거는 별개`;
    for(const b of document.querySelectorAll('[data-mode]'))b.setAttribute('aria-pressed',String(b.dataset.mode===mode));
    if(mode==='compare')compare();else if(!nodes.length)canvas.append(element('p','조건에 맞는 논문이 없습니다. 필터를 바꾸거나 미분류 논문을 포함하세요.'));else if(mode==='matrix')matrix(nodes);else timeline(nodes);
  }
  for(const [id,label] of Object.entries(research.methods)){const o=element('option',label);o.value=id;controls.method.append(o);}
  for(const t of [...new Set(data.nodes.flatMap(n=>studies(n).map(s=>s.target)))].sort()){const o=element('option',t);o.value=t;controls.target.append(o);}
  for(const el of Object.values(controls))el.addEventListener(el.type==='search'?'input':'change',()=>{selected=null;detail.replaceChildren(element('h2','논문 또는 연구 조합을 선택하세요'));render();});
  for(const b of document.querySelectorAll('[data-mode]'))b.addEventListener('click',()=>{mode=b.dataset.mode;render();});
  for(const s of research.searches){const box=element('div');box.append(element('h3',s.checkedAt+' · '+s.scope),element('p',s.queries.join(' / ')),element('p',s.note));document.getElementById('atlas-search-log').append(box);}
  window.addEventListener('resize',paint);render();
})();
