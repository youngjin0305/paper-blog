(() => {
  'use strict';
  const data = window.researchGraph, canvas = document.getElementById('atlas-canvas');
  if (!data?.research || !canvas) return;
  const research = data.research, byId = new Map(data.nodes.map(n => [n.id,n]));
  const detail = document.getElementById('atlas-detail');
  const controls = Object.fromEntries(['topic','method','target','search','pending','unclassified'].map(k => [k,document.getElementById('atlas-'+k)]));
  let mode = location.hash==='#lineage' ? 'lineage' : research.taxonomy ? 'fields' : 'lineage', selected = null, comparison = [];
  let fieldPath = research.taxonomy ? [research.taxonomy.root] : [], fieldFacet = '', fieldQuery = '';
  const collapsedFields = new Set();
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
    const membership=research.taxonomy?.memberships[n.id];
    if(membership){const names=research.taxonomy.branches.filter(b=>membership.branches.includes(b.id)).map(b=>b.label);describe(detail,'분야 분류',names.join(' · '));detail.append(link('분야 분류 근거 ↗',membership.evidence.url),element('small',membership.evidence.locator));}
    const incoming=research.relations.filter(r=>r.target===n.id && (r.status==='reviewed'||controls.pending.checked));
    const outgoing=research.relations.filter(r=>r.source===n.id && (r.status==='reviewed'||controls.pending.checked));
    for(const [label,rels,inbound] of [['출발점',incoming,true],['후속 연구',outgoing,false]]) {
      detail.append(element('h3',label));
      if(!rels.length)detail.append(element('p','현재 자료에서 직접 계승·분석 근거 미확인'));
      for(const r of rels){const other=byId.get(inbound?r.source:r.target);if(!other)continue;const box=element('div',undefined,'atlas-relation');
        box.append(button(other.title,()=>{showNode(other);}),element('strong',research.relationLabels[r.kind]),element('p',r.change));evidence(box,r);detail.append(box);}
    }
    describe(detail,'확인한 연구 조건',studies(n).map(s=>`${s.target} · ${research.methods[s.method]} · ${s.goal||''}\n${s.conditions||'기재 확인 안 됨'}`).join('\n\n'));
    describe(detail,'저자가 밝힌 한계',p?.limitations);
    detail.append(button(comparison.includes(n.id)?'비교에서 제외':'비교에 추가',()=>toggleCompare(n.id)));
    if(mode==='fields')detail.append(button('분야 설명과 논문 목록으로 돌아가기',()=>render()));
    if(window.innerWidth<=1150)detail.scrollIntoView({behavior:'smooth',block:'start'});
    if(mode==='lineage'){canvas.replaceChildren();timeline(visible());}
  }
  function toggleCompare(id){comparison=comparison.includes(id)?comparison.filter(x=>x!==id):[...comparison.slice(-1),id];render();if(selected)showNode(byId.get(selected));}
  function card(n){const p=profile(n),box=element('article',undefined,'atlas-card'+(n.id===selected?' selected':''));box.dataset.paper=n.id;
    box.append(element('span',status(p),'atlas-badge'),button((n.core?'★ ':'')+n.title,()=>showNode(n),'atlas-title'),element('p',p?.contribution||'연구 조건과 변경점 분류가 필요합니다.'));
    const tags=element('div',undefined,'atlas-tags'); for(const m of new Set(studies(n).map(s=>s.method)))tags.append(element('span',research.methods[m]));box.append(tags);
    for(const r of research.relations.filter(r=>r.target===n.id&&r.status==='reviewed'))box.append(element('small',research.relationLabels[r.kind]+' ← '+(byId.get(r.source)?.authors[0]||'선행 연구'),'atlas-parent'));
    const actions=element('div',undefined,'atlas-actions');actions.append(button(comparison.includes(n.id)?'비교 제외':'비교 +',()=>toggleCompare(n.id)));article(actions,n);box.append(actions);return box;}
  function timeline(nodes){
    const relations=research.relations.filter(r=>(r.status==='reviewed'||controls.pending.checked)&&byId.has(r.source)&&byId.has(r.target));
    const degree=id=>relations.filter(r=>r.source===id||r.target===id).length;
    const anchor=byId.get(selected)||[...nodes].sort((a,b)=>degree(b.id)-degree(a.id)||a.year-b.year)[0];
    if(!anchor)return;selected=anchor.id;
    const picker=element('label','기준 논문','succession-picker'),select=element('select');select.id='succession-paper';
    const choices=nodes.some(n=>n.id===anchor.id)?nodes:[anchor,...nodes];
    for(const n of choices){const option=element('option',`${n.year} · ${n.title}`);option.value=n.id;option.selected=n.id===anchor.id;select.append(option);}
    select.addEventListener('change',()=>showNode(byId.get(select.value)));picker.append(select);canvas.append(picker);
    canvas.append(element('p','한 논문의 직접 선행·후속 연구만 표시합니다. 다른 논문을 선택하면 그 논문의 연결로 이동합니다. 연결 논문은 필터 밖이어도 함께 표시합니다.','atlas-hint'));
    const wrap=element('div',undefined,'succession-view');
    const group=(label,rels,inbound)=>{const section=element('section',undefined,'succession-group');section.append(element('h2',`${label} · ${rels.length}`));
      if(!rels.length)section.append(element('p','현재 자료에서 직접 관계 미확인. 연구가 없다는 뜻은 아닙니다.','atlas-hint'));
      for(const r of [...rels].sort((a,b)=>byId.get(inbound?a.source:a.target).year-byId.get(inbound?b.source:b.target).year)){
        const n=byId.get(inbound?r.source:r.target),item=element('div',undefined,'succession-relation');
        item.append(element('span',`${n.year} · ${research.relationLabels[r.kind]}`,'succession-label'),element('p',r.change));
        if(r.status==='pending')item.append(element('small','자동 추출 · 검토 전'));
        if(!nodes.some(node=>node.id===n.id))item.append(element('small','현재 목록 필터 밖의 연결 논문'));
        item.append(card(n),link('연결 근거 ↗',r.evidence.url),element('small',`${r.evidence.locator} · ${r.basis==='abstract'?'초록':'전문'} 근거`));section.append(item);}
      return section;};
    wrap.append(group('직접 선행 연구',relations.filter(r=>r.target===anchor.id),true));
    const focus=element('section',undefined,'succession-focus');focus.append(element('h2','현재 기준 논문'),element('span',String(anchor.year),'succession-label'),card(anchor));wrap.append(focus);
    wrap.append(group('직접 후속 연구',relations.filter(r=>r.source===anchor.id),false));canvas.append(wrap);
  }
  function compare(){if(comparison.length<2){canvas.append(element('p','계승 지도에서 논문 두 편의 ‘비교 +’를 선택하세요.'));if(comparison.length)canvas.append(card(byId.get(comparison[0])));return;}
    const ns=comparison.map(id=>byId.get(id)),table=element('table',undefined,'atlas-compare');
    for(const [label,fn] of [['논문',n=>n.title],['근거 수준',n=>status(profile(n))],['출발점',n=>research.relations.filter(r=>r.target===n.id&&(r.status==='reviewed'||controls.pending.checked)).map(r=>byId.get(r.source)?.title+' — '+r.change).join('\n')],['변경점',n=>profile(n)?.contribution],['대상·기법·목표·조건',n=>studies(n).map(s=>`${s.target} / ${research.methods[s.method]} / ${s.goal||''}\n${s.conditions||'기재 확인 안 됨'}`).join('\n\n')],['저자 명시 한계',n=>profile(n)?.limitations]]){const row=element('tr');row.append(element('th',label));for(const n of ns)row.append(element('td',fn(n)||'기재 확인 안 됨'));table.append(row);}
    const wrap=element('div',undefined,'atlas-table-scroll');wrap.append(table);canvas.append(element('p','조건이 다른 결과의 단순 수치 순위는 제공하지 않습니다. 비교 선택은 필터 변경 후에도 유지됩니다.','atlas-hint'),wrap,button('비교 선택 비우기',()=>{comparison=[];render();}));
  }
  function fields(){
    const tax=research.taxonomy;
    if(!tax){canvas.append(element('p','아직 분야 분류가 없습니다.'));return;}
    const branches=new Map(tax.branches.map(b=>[b.id,b])), current=branches.get(fieldPath.at(-1));
    const descendants=id=>{const result=new Set([id]),pending=[id];while(pending.length){const parent=pending.pop();for(const b of tax.branches)if(b.parents.includes(parent)&&!result.has(b.id)){result.add(b.id);pending.push(b.id);}}return result;};
    const papers=id=>{const ids=descendants(id);return ordered(data.nodes.filter(n=>{const m=tax.memberships[n.id];return m&&m.branches.some(b=>ids.has(b))&&(!fieldFacet||m.facets.includes(fieldFacet));}));};
    const pathTo=id=>{const parent=branches.get(id)?.parents[0];return parent?[...pathTo(parent),id]:[id];};
    const locate=id=>{fieldFacet='';fieldPath=pathTo(id);for(const key of [...collapsedFields])if(fieldPath.some(p=>key.split('/').includes(p)))collapsedFields.delete(key);render();canvas.querySelector('.field-current')?.scrollIntoView({behavior:'smooth',block:'center'});};
    const canonical=s=>norm(s).replace(/cryptoanalysis/g,'cryptanalysis');
    const searchable=s=>canonical(s).replace(/[^\p{L}\p{N}]+/gu,' ').trim();
    const taxonomyPath=id=>pathTo(id).map(p=>branches.get(p).label).join(' → ');
    const searchBox=element('section',undefined,'field-search');
    const searchLabel=element('label','논문·분야 찾기');searchLabel.htmlFor='field-search-input';
    const searchInput=element('input');searchInput.id='field-search-input';searchInput.type='search';searchInput.placeholder='논문 제목·저자·ID 또는 Quantum, Truncated';searchInput.value=fieldQuery;
    const results=element('div',undefined,'field-search-results');results.setAttribute('aria-live','polite');
    searchBox.append(searchLabel,searchInput,element('small','지도에 등록된 모든 분야·미분류 논문을 검색합니다. 교차 필터와 무관하게 찾습니다.'),results);canvas.append(searchBox);
    const search=()=>{fieldQuery=searchInput.value;results.replaceChildren();const terms=searchable(fieldQuery).split(/\s+/).filter(Boolean);if(!terms.length)return;
      const match=text=>terms.every(t=>searchable(text).includes(t));
      const foundBranches=tax.branches.filter(b=>match([b.label,b.english,...(b.aliases||[]),b.description].join(' ')));
      const foundPapers=ordered(data.nodes.filter(n=>{const m=tax.memberships[n.id];return match([n.title,...n.authors,n.id,...(m?.branches||[]).map(id=>taxonomyPath(id)+' '+branches.get(id).english)].join(' '));}));
      results.append(element('p',`분야 ${foundBranches.length}개 · 논문 ${foundPapers.length}편`));
      if(!foundBranches.length&&!foundPapers.length)results.append(element('p','검색 결과가 없습니다. 다른 제목·저자·분야명으로 찾아보세요.'));
      for(const b of foundBranches){const row=element('div',undefined,'field-search-result');row.append(button(b.label+' · '+b.english,()=>locate(b.id)),element('small',taxonomyPath(b.id)));results.append(row);}
      for(const n of foundPapers){const row=element('div',undefined,'field-search-result');row.dataset.resultPaper=n.id;row.append(button(n.title,()=>showNode(n),'atlas-title'));const m=tax.memberships[n.id];
        if(m){for(const id of m.branches){row.append(element('small',taxonomyPath(id)),button('트리에서 보기 · '+branches.get(id).label,()=>locate(id)));}row.append(element('small',m.evidence.locator+' · 분류 근거 '+m.evidence.checkedAt.slice(0,10)));}
        else row.append(element('small','분야 미분류 · 수집 카테고리: '+n.topicLabel));
        article(row,n);results.append(row);}
    };
    searchInput.addEventListener('input',search);searchInput.addEventListener('keydown',e=>{if(e.key==='Escape'){searchInput.value='';search();}});search();
    const crumbs=element('nav',undefined,'field-breadcrumbs');crumbs.setAttribute('aria-label','분야 탐색 경로');
    fieldPath.forEach((id,i)=>{if(i)crumbs.append(element('span','/'));const b=button(branches.get(id).label,()=>{fieldPath=fieldPath.slice(0,i+1);render();});if(i===fieldPath.length-1)b.setAttribute('aria-current','page');crumbs.append(b);});canvas.append(crumbs);
    const facets=element('div',undefined,'field-facets');facets.append(element('span','논문에 겹쳐 보기'));
    for(const [id,label] of [['','전체'],['ai','AI 활용'],['related-key','관련키 조건'],['quantum','양자 계산']]){const b=button(label,()=>{fieldFacet=id;render();});b.setAttribute('aria-pressed',String(fieldFacet===id));facets.append(b);}canvas.append(facets);
    const matches=papers(current.id);
    const tree=element('div',undefined,'field-tree');tree.setAttribute('aria-label','대칭키 암호분석 분야 트리');
    const build=(id,path)=>{const b=branches.get(id),li=element('li'),row=element('div',undefined,'field-tree-row');
      const choose=button('',()=>{fieldPath=[...path,id];selected=null;render();},'field-node'+(id===current.id?' field-current':''));choose.dataset.field=id;
      choose.append(element('strong',b.label),element('small',b.english),element('span',papers(id).length?`${papers(id).length}편`:'연결 논문 미등록'));
      if(b.axis==='computing')choose.append(element('em','계산 관점 · 여러 기법과 결합'));
      if(b.parents.length>1)choose.append(element('em','결합 기법 · 여러 갈래에 표시'));
      row.append(choose);li.append(row);
      const children=tax.branches.filter(child=>child.parents.includes(id));
      if(children.length){const section=element('details',undefined,'field-subtree');const key=[...path,id].join('/');section.open=!collapsedFields.has(key);section.addEventListener('toggle',()=>{if(section.open)collapsedFields.delete(key);else collapsedFields.add(key);});section.append(element('summary','세부 갈래 '+children.length+'개'));const ul=element('ul');for(const child of children)ul.append(build(child.id,[...path,id]));section.append(ul);li.append(section);}
      const direct=ordered(data.nodes.filter(n=>{const m=tax.memberships[n.id];return m&&m.branches.includes(id)&&(!fieldFacet||m.facets.includes(fieldFacet));}));
      if(direct.length){const list=element('details',undefined,'field-tree-papers');list.append(element('summary',`이 갈래의 논문 ${direct.length}편`));for(const n of direct){const item=button(n.title,()=>showNode(n),'field-paper atlas-title');item.dataset.paper=n.id;list.append(item);}li.append(list);}
      return li;};
    const root=element('ul');root.append(build(tax.root,[]));tree.append(root);canvas.append(tree);
    canvas.append(element('p','가지선은 분야의 포함 관계입니다. 결합 기법은 양쪽 가지에 표시하고, 상위 논문 수는 중복 없이 셉니다. 논문 목록과 세부 갈래는 접고 펼칠 수 있습니다.','atlas-hint'));
    canvas.append(button('분야 설명·전체 논문 목록 보기 ↓',()=>{detail.scrollIntoView({behavior:'smooth',block:'start'});},'field-detail-jump'));
    detail.replaceChildren(element('p','FIELD GUIDE','atlas-badge'),element('h2',current.label),element('p',current.english),element('p',current.description),link('기법 설명의 출처 ↗',current.source));
    if(current.parents.length>1){detail.append(element('h3','함께 연결되는 갈래'));for(const id of current.parents)detail.append(button(branches.get(id).label,()=>{fieldPath=[tax.root,id,current.id];render();}));}
    detail.append(element('h3',`연결 논문 ${matches.length}편`));
    if(!matches.length)detail.append(element('p','현재 목록에서 이 갈래에 연결한 논문이 없습니다. 연구 자체가 없다는 뜻은 아닙니다.'));
    for(const n of matches){const m=tax.memberships[n.id],row=element('div',undefined,'field-paper-row');row.append(button(n.title,()=>showNode(n),'atlas-title'),element('small',`${n.year}${m.overview?' · Survey':''}${m.facets.includes('ai')?' · AI 활용':''}${m.facets.includes('related-key')?' · 관련키':''}`));article(row,n);detail.append(row);}
    detail.append(element('h3','지도 범위'),element('p',tax.scope),element('p','AI는 활용 도구, 관련키는 공격 조건입니다. 여러 분석 기법에 함께 적용될 수 있어 독립된 하위 분야로 강제하지 않습니다. 양자 계산도 여러 기법과 결합하는 관점이며 여기서는 대칭키 공격을 다룹니다. 한 논문은 여러 갈래에 속할 수 있고 상위 개수는 중복 없이 셉니다.'));
    const unmapped=data.nodes.filter(n=>['cryptanalysis','ai-cryptanalysis'].includes(n.topic)&&!tax.memberships[n.id]);
    detail.append(element('small',`현재 CryptAnalysis·AI CryptAnalysis 목록 중 ${unmapped.length}편은 이 지도에서 미분류 또는 범위 밖입니다.`));
    const list=element('details');list.append(element('summary','미분류·범위 밖 논문 보기'));for(const n of unmapped)list.append(button(n.title,()=>showNode(n),'atlas-title'));detail.append(list);
  }
  function render(){const nodes=visible();canvas.replaceChildren();document.getElementById('atlas-comparison-count').textContent=`${comparison.length}/2`;
    document.querySelector('.flow-controls').hidden=mode==='fields';
    document.querySelector('.atlas-layout').classList.toggle('field-layout',mode==='fields');
    const all=data.nodes.filter(n=>n.topic===controls.topic.value),classified=all.filter(n=>profile(n));document.getElementById('atlas-status').textContent=`현재 ${nodes.length}편 · 분야 전체 ${all.length}편 · 분류 있음 ${classified.length}편 / 미분류 ${all.length-classified.length}편 · 우선순위와 분류 근거는 별개`;
    for(const b of document.querySelectorAll('[data-mode]'))b.setAttribute('aria-pressed',String(b.dataset.mode===mode));
    if(mode==='fields'){document.getElementById('atlas-status').textContent='Cryptography / 대칭키 암호분석 · 두 수집 카테고리의 논문을 기법별로 함께 탐색합니다.';fields();}else if(mode==='compare')compare();else if(!nodes.length)canvas.append(element('p','조건에 맞는 논문이 없습니다. 필터를 바꾸거나 미분류 논문을 포함하세요.'));else timeline(nodes);
    if(mode==='lineage'&&selected&&nodes.length)showNode(byId.get(selected));
  }
  for(const [id,label] of Object.entries(research.methods)){const o=element('option',label);o.value=id;controls.method.append(o);}
  for(const t of [...new Set(data.nodes.flatMap(n=>studies(n).map(s=>s.target)))].sort()){const o=element('option',t);o.value=t;controls.target.append(o);}
  for(const el of Object.values(controls))el.addEventListener(el.type==='search'?'input':'change',()=>{selected=null;detail.replaceChildren(element('h2','논문 또는 연구 조합을 선택하세요'));render();});
  for(const b of document.querySelectorAll('[data-mode]'))b.addEventListener('click',()=>{mode=b.dataset.mode;render();});
  for(const s of research.searches){const box=element('div');box.append(element('h3',s.checkedAt+' · '+s.scope),element('p',s.queries.join(' / ')),element('p',s.note));document.getElementById('atlas-search-log').append(box);}
  render();
})();
