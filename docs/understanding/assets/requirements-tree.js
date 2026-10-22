// A classic script, not a module: a browser refuses to import a module from a page opened
// from a folder without a server, and the offline edition is read that way (FR-2331).
(window.pyfsUnderstanding = window.pyfsUnderstanding || {}).createRequirementsTree = function createRequirementsTree({req, mission, colors, select, chart}) {
  const el = id => document.getElementById(id);
  const byId = new Map(req.nodes.map(n => [n.id, n]));
  const expanded = new Set(['mission']);
  let matches = new Set(), included = new Set(), selected = '', lastFilter = '';
  const root = {id:'mission', label:'Mission', title:mission.mission, children:[]};
  const nodes = new Map();
  const groups = new Map();
  for (const stage of [...mission.stages, mission.nfr_tree]) {
    const group = {id:'stage:'+stage.id, label:stage.name, children:[], parent:root};
    root.children.push(group);
    groups.set(stage.id, group);
  }
  for (const n of req.nodes) nodes.set(n.id, {id:n.id, label:(n.hid || 'No HID')+' / '+n.id, title:n.first_sentence || n.statement, requirement:n, children:[]});
  for (const n of req.nodes) {
    const node = nodes.get(n.id);
    let parent = nodes.get(n.parent);
    // Broken or cyclic authored links must not remove a requirement from the view.
    const seen = new Set([n.id]);
    let ancestor = parent;
    while (ancestor && !seen.has(ancestor.id)) { seen.add(ancestor.id); ancestor = nodes.get(ancestor.requirement.parent); }
    if (ancestor) parent = null;
    if (!parent) {
      const stage = groups.get(n.stage) || groups.get('nfr');
      const key = stage.id + ':' + n.area;
      if (!groups.has(key)) {
        const area = {id:key, label:n.area, title:mission.areas[n.area] || n.area, children:[], parent:stage};
        stage.children.push(area); groups.set(key, area);
      }
      parent = groups.get(key);
    }
    node.parent = parent;
    parent.children.push(node);
  }
  const all = [root, ...groups.values(), ...nodes.values()];
  function path(node, visit) {
    const seen = new Set();
    while (node && !seen.has(node.id)) { seen.add(node.id); visit(node); node = node.parent; }
  }
  function draw() {
    const hierarchy = d3.hierarchy(root, n => expanded.has(n.id) ? n.children.filter(c => included.has(c.id)) : null);
    d3.tree().nodeSize([44, 270])(hierarchy);
    const visible = hierarchy.descendants();
    const min = d3.min(visible, n => n.x), max = d3.max(visible, n => n.x);
    const height = Math.max(480, max-min+100), width = Math.max(980, d3.max(visible,n=>n.y)+320);
    const svg = d3.select(el('ug-tree')).selectAll('svg').data([null]).join('svg')
      .attr('width',width).attr('height',height).attr('viewBox',null).attr('role','tree').attr('aria-label','Mission and authored requirements');
    const g = svg.selectAll('g.ug-tree-content').data([null]).join('g').attr('class','ug-tree-content').attr('transform','translate(24,'+(50-min)+')');
    g.selectAll('path.ug-tree-link').data(hierarchy.links(),d=>d.target.data.id).join('path').attr('class','ug-tree-link').lower().attr('d',d3.linkHorizontal().x(d=>d.y).y(d=>d.x));
    const item = g.selectAll('g.ug-tree-node').data(visible,d=>d.data.id).join('g').attr('class',d=>'ug-tree-node'+(matches.has(d.data.id)?' ug-match':'')+(selected===d.data.id?' ug-selected':''))
      .attr('transform',d=>'translate('+d.y+','+d.x+')').attr('role','treeitem').attr('tabindex',0)
      .attr('aria-level',d=>d.depth+1).attr('aria-label',d=>d.data.label)
      .attr('aria-selected',d=>selected===d.data.id)
      .attr('aria-expanded',d=>d.data.children.some(c=>included.has(c.id))?expanded.has(d.data.id):null);
    function activate(event,d) {
      const n=d.data;
      if (expanded.has(n.id)) expanded.delete(n.id); else expanded.add(n.id);
      if(n.requirement) {selected=n.id;select(n.id);} else draw();
    }
    item.on('click',activate).on('keydown',(event,d)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();activate(event,d);}});
    item.selectAll('rect').data(d=>[d]).join('rect').attr('x',-15).attr('y',-20).attr('width',258).attr('height',40).attr('rx',5);
    item.selectAll('circle').data(d=>[d]).join('circle').attr('r',7).attr('fill',d=>colors[d.data.requirement?.status] || 'var(--ug-primary)');
    item.selectAll('text').data(d=>[d]).join('text').attr('x',14).attr('y',4).each(function(d){
      const text=d3.select(this).text('');
      const label=(d.data.children.some(c=>included.has(c.id))?(expanded.has(d.data.id)?'- ': '+ '):'')+d.data.label;
      const words=label.split(' '), lines=[''];
      words.forEach(w=>{const i=lines.length-1;if((lines[i]+' '+w).trim().length>33)lines.push(w);else lines[i]=(lines[i]+' '+w).trim();});
      lines.forEach((line,i)=>text.append('tspan').attr('x',14).attr('dy',i?14:lines.length>1?-7:0).text(line));
    });
    item.selectAll('title').data(d=>[d]).join('title').text(d=>d.data.label+(d.data.requirement?' | '+d.data.requirement.status:'')+'\n'+(d.data.title||''));
    el('ug-tree-count').textContent=visible.length+' visible nodes. '+matches.size+' matching requirements. Context ancestors remain visible.';
  }
  function update(matched, filter) {
    matches = new Set(matched.map(n=>n.id)); included = new Set(['mission']);
    matched.forEach(n=>path(nodes.get(n.id),p=>included.add(p.id)));
    const signature=JSON.stringify(filter);
    if(signature!==lastFilter && (filter.term || filter.stage || filter.area || !['live','all'].includes(filter.status))) {
      matched.forEach(n=>path(nodes.get(n.id)?.parent,p=>expanded.add(p.id)));
    }
    lastFilter=signature;
    draw();
  }
  el('ug-expand').onclick=()=>{all.forEach(n=>expanded.add(n.id));draw();};
  el('ug-collapse').onclick=()=>{expanded.clear();expanded.add('mission');draw();};
  const cy = chart('ug-neighborhood', [], {name:'preset'});
  const panel = el('ug-neighborhood');
  const legend = document.createElement('div');
  legend.className = 'ug-legend ug-neighborhood-legend';
  legend.setAttribute('aria-label', 'Neighborhood node kinds');
  legend.innerHTML = ['Selected','Parent','Child','Module','Test'].map(kind => '<span><i aria-hidden="true" class="ug-'+kind.toLowerCase()+'-key"></i>'+kind+'</span>').join('') + '<span>Requirement fills show status; parent and child outlines show kind.</span>';
  panel.parentElement.insertAdjacentElement('afterend', legend);
  const detail = document.createElement('p');
  detail.className = 'ug-status';
  detail.setAttribute('aria-live', 'polite');
  legend.insertAdjacentElement('afterend', detail);
  cy.on('tap','node',e=>{
    const node = e.target.data();
    if(node.requirementId) select(node.requirementId);
    else if(node.kind === 'Module') location.href = new URL(/\.html$/.test(location.pathname) ? 'code.html' : '../code/', location.href).href + '#module=' + encodeURIComponent(node.moduleId);
    else if(node.kind === 'Test') detail.textContent = 'Test path: ' + (node.path || 'No path recorded') + (node.anchor ? ' | ' + node.anchor : '');
  });
  function fitNeighborhood() {
    if (!cy.nodes().length || !panel.clientWidth) return;
    const width = panel.clientWidth;
    const columns = Math.max(1, Math.floor(width / 190));
    const neighbors = cy.nodes().filter(node => node.data('kind') !== 'Selected');
    panel.style.height = (150 + Math.ceil(neighbors.length / columns) * 150) + 'px';
    cy.resize();
    cy.nodes().filter(node => node.data('kind') === 'Selected').position({x:width/2,y:45});
    neighbors.forEach((node, i) => node.position({x:(i%columns+.5)*width/columns,y:190+Math.floor(i/columns)*150}));
    cy.nodes().style('font-size',14);
    cy.edges().style('font-size',12);
    cy.fit(cy.elements(), 28);
    if (cy.zoom() > 1) { cy.zoom(1); cy.center(); }
    // Preserve a readable screen font after fitting, including narrow panels.
    cy.nodes().style('font-size',14 / cy.zoom());
    cy.edges().style('font-size',12 / cy.zoom());
  }
  let panelWidth = 0;
  const resize = new ResizeObserver(() => {
    if(panel.clientWidth !== panelWidth) { panelWidth = panel.clientWidth; fitNeighborhood(); }
  });
  resize.observe(panel);
  cy.on('destroy',()=>{resize.disconnect();legend.remove();detail.remove();});
  function neighborhood(id) {
    selected=id; draw(); detail.textContent='';
    const n=byId.get(id); if(!n)return;
    const center='req:'+id;
    const families=[[],[],[],[]];
    function requirement(r,kind){return {id:'req:'+r.id,label:r.hid+' / '+r.id,requirementId:r.id,kind,status:r.status};}
    if(byId.has(n.parent))families[0].push(requirement(byId.get(n.parent),'Parent'));
    families[1]=req.nodes.filter(r=>r.parent===id).map(r=>requirement(r,'Child'));
    families[2]=[...new Map(n.code_anchors.map(a=>[a.module,{id:'module:'+a.module,label:a.module.replace(/^pyflightstream\./,''),kind:'Module',moduleId:a.module}])).values()];
    families[3]=[...new Map(n.test_anchors.map(a=>[a.anchor||a.path,{id:'test:'+(a.anchor||a.path),label:(a.anchor||a.path).split('::').pop().replace(/^tests\//,''),kind:'Test',path:a.path,anchor:a.anchor}])).values()];
    // Round-robin selection leaves room for every recorded relationship family.
    const chosen=[], seen=new Set([center]);
    for(let i=0;chosen.length<29&&families.some(f=>i<f.length);i++)for(const family of families){
      const a=family[i];if(a&&!seen.has(a.id)&&chosen.length<29){chosen.push(a);seen.add(a.id);}
    }
    const total=new Set(families.flat().map(a=>a.id)).size;
    el('ug-neighborhood-summary').textContent=n.hid+' / '+id+': '+chosen.length+' of '+total+' connections shown'+(total>chosen.length?' (30-node limit).':'.')+' Parent and child requirements, satisfying modules and verifying tests. Select a parent or child to recenter, a module to open Code, or a test to show its path. Full anchors are in the card.';
    const elements=[{data:{id:center,label:n.hid+' / '+id,requirementId:id,kind:'Selected',rank:3},classes:n.status}];
    chosen.forEach((a,i)=>{
      elements.push({data:{...a,rank:i<10?2:1,label:a.kind+'\n'+(a.label.length>44?a.label.slice(0,41)+'...':a.label)},classes:a.status||''});
      const inward=a.kind==='Child'||a.kind==='Module'||a.kind==='Test';
      const relation=a.kind==='Module'?'satisfies':a.kind==='Test'?'verifies':'refines';
      elements.push({data:{id:'edge:'+i,source:inward?a.id:center,target:inward?center:a.id,relation}});
    });
    cy.elements().remove();cy.add(elements);
    fitNeighborhood();
    cy.userZoomingEnabled(false);cy.userPanningEnabled(false);
  }
  return {update, neighborhood, reset(){expanded.clear();expanded.add('mission');lastFilter='';}};
};
