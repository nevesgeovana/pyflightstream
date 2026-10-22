// A classic script, not a module: a browser refuses to import a module from a page opened
// from a folder without a server, and the offline edition is read that way (FR-2331).
(window.pyfsUnderstanding = window.pyfsUnderstanding || {}).renderLayers = function renderLayers(host, nodes, edges, selectPackage, selectEdge) {
  const ns = 'http://www.w3.org/2000/svg';
  const make = (tag, attrs, parent, text) => {
    const el = document.createElementNS(ns, tag);
    for (const [key,value] of Object.entries(attrs)) el.setAttribute(key,value);
    if (text !== undefined) el.textContent = text;
    parent.appendChild(el); return el;
  };
  host.replaceChildren();
  const ranks = [...new Set(nodes.map(n=>n.layer))].sort((a,b)=>a===null?1:b===null?-1:a-b);
  const positions = new Map();
  const maxLines = Math.max(1,...nodes.map(n=>n.lines));
  let contentWidth = 660;
  ranks.forEach((rank,row)=>{
    let x = 110;
    nodes.filter(n=>n.layer===rank).sort((a,b)=>a.id.localeCompare(b.id)).forEach(n=>{
      const width = Math.max(150, n.id.length*9+28, 330*n.lines/maxLines);
      positions.set(n.id,{x,y:row*115+35,width}); x += width+24;
    });
    contentWidth = Math.max(contentWidth,x);
  });
  const width = contentWidth + nodes.length*9+45, height = ranks.length*115+30;
  const svg = make('svg',{width,height,viewBox:'0 0 '+width+' '+height,role:'group','aria-label':'Package layer ranks and import dependencies'},host);
  const defs = make('defs',{},svg);
  for (const [id,color] of [['normal','var(--md-typeset-a-color)'],['risk','#d64c59']]) {
    const marker=make('marker',{id:'ug-layer-arrow-'+id,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto'},defs);
    make('path',{d:'M0 0 L10 5 L0 10 Z',fill:color},marker);
  }
  ranks.forEach((rank,row)=>{
    make('rect',{class:'ug-layer-row',x:0,y:row*115+15,width,height:90,rx:6},svg);
    make('text',{class:'ug-layer-rank',x:14,y:row*115+68},svg,rank===null?'Unranked':'Rank '+rank);
  });
  const edgeGroup=make('g',{},svg), nodeGroup=make('g',{},svg);
  const renderedEdges=[], renderedNodes=[];
  const nodeOrder=[...positions.keys()];
  edges.forEach(e=>{
    const a=positions.get(e.source),b=positions.get(e.target);
    if(!a || !b || e.source===e.target)return;
    // Route imports through the gutters so no connector crosses a package label.
    const rail=contentWidth+18+nodeOrder.indexOf(e.target)*9;
    const ax=a.x+a.width*.72, bx=b.x+b.width*.28;
    const outgoing=a.y+72, incoming=b.y-12;
    const path=make('path',{class:'ug-layer-edge'+(e.upward||e.cycle?' ug-risk':''),d:'M'+ax+' '+(a.y+58)+' V'+outgoing+' H'+rail+' V'+incoming+' H'+bx+' V'+b.y,'marker-end':'url(#ug-layer-arrow-'+(e.upward||e.cycle?'risk':'normal')+')'},edgeGroup);
    make('title',{},path,e.source+' imports '+e.target+': '+e.count+' occurrences'+(e.upward?' (upward)':'')+(e.cycle?' (cycle)':''));
    path.addEventListener('click',()=>selectEdge(e));renderedEdges.push({el:path,e});
  });
  function highlight(id) {
    const related=new Set([id]);
    for(const {e} of renderedEdges)if(e.source===id || e.target===id){related.add(e.source);related.add(e.target);}
    for(const {el,e} of renderedEdges){const active=e.source===id||e.target===id;el.classList.toggle('ug-active',!!id&&active);el.classList.toggle('ug-dim',!!id&&!active);}
    for(const {el,n} of renderedNodes){el.classList.toggle('ug-active',n.id===id);el.classList.toggle('ug-dim',!!id&&!related.has(n.id));}
  }
  nodes.forEach(n=>{
    const p=positions.get(n.id);
    const group=make('g',{class:'ug-layer-node',transform:'translate('+p.x+','+p.y+')',tabindex:0,role:'button','aria-label':n.id+', '+n.lines.toLocaleString()+' physical lines, '+(n.layer===null?'unranked':'rank '+n.layer)},nodeGroup);
    make('rect',{width:p.width,height:58,rx:7},group);
    make('text',{class:'ug-layer-name',x:12,y:23},group,n.id);
    make('text',{x:12,y:45},group,n.lines.toLocaleString()+' lines');
    group.addEventListener('mouseenter',()=>highlight(n.id));
    group.addEventListener('mouseleave',()=>highlight(null));
    group.addEventListener('focus',()=>highlight(n.id));
    group.addEventListener('blur',()=>highlight(null));
    group.addEventListener('click',()=>selectPackage(n.id));
    group.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectPackage(n.id);}});
    renderedNodes.push({el:group,n});
  });
};
