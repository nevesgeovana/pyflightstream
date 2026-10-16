(() => {
  "use strict";
  const asset = new URL(document.currentScript.src);
  const base = new URL("../", asset);
  const colors = {implemented: "#238b65", pending: "#c58b20", deferred: "#936bc9", retired: "#808b96"};
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const $ = id => document.getElementById(id);
  const link = (page, kind, id, label) => '<a href="' + new URL(page + "/", base).href + "#" + kind + "=" + encodeURIComponent(id) + '">' + esc(label || id) + "</a>";
  const source = a => a.path ? '<a href="https://github.com/nevesgeovana/pyflightstream/blob/' + sourceRevision + '/' + a.path.split("/").map(encodeURIComponent).join("/") + (a.line ? "#L" + a.line : "") + '">' + esc(a.anchor || a.path + (a.line ? ":" + a.line : "")) + "</a>" : esc(a.anchor);
  const list = values => values.length ? "<ul>" + values.map(v => "<li>" + v + "</li>").join("") + "</ul>" : "<p>None recorded in this scenario or registry.</p>";
  const workspaceFiles = step => step.workspace_files?.length ? "<h4>Workspace files</h4>" + list(step.workspace_files.map(row => '<a href="' + new URL("../workspace-files/", base).href + "#" + encodeURIComponent(row.id) + '"><code>' + esc(row.path) + "</code></a>")) : "";
  const option = (value, label) => '<option value="' + esc(value) + '">' + esc(label) + "</option>";
  let cleanup = () => {};
  let cache;
  let sourceRevision;
  async function data() {
    if (!cache) cache = Promise.all(["requirements", "mission", "code", "execution"].map(async name => {
      const response = await fetch(new URL("data/" + name + ".json", base));
      if (!response.ok) throw new Error(name + ": HTTP " + response.status);
      return response.json();
    })).catch(error => { cache = null; throw error; });
    return cache;
  }
  function setHash(kind, id) { history.replaceState(null, "", "#" + kind + "=" + encodeURIComponent(id)); }
  function selection() { return new URLSearchParams(location.hash.slice(1)); }
  function palette() {
    const style = getComputedStyle(document.body);
    const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
    return {primary:read("--ug-node", "#496b75"), edge:read("--ug-edge", "#596875"), module:read("--ug-module", "#a7100d"), test:read("--ug-test", "#fb7007"), text:read("--ug-text", "#242424"), accent:read("--ug-module", "#a7100d")};
  }
  function cyStyle() {
    const p = palette();
    return [
      {selector:"node", style:{"background-color":p.primary, label:"data(label)", color:p.text, "font-size":12, "text-valign":"bottom", "text-margin-y":6, "text-wrap":"wrap", "text-max-width":130, width:35, height:35}},
      {selector:"node:parent", style:{"background-color":p.primary, "background-opacity":0.06, "border-width":1,"border-color":p.accent, "text-valign":"top", padding:22}},
      {selector:"edge", style:{width:1.4,"line-color":p.edge,"target-arrow-color":p.edge,"target-arrow-shape":"triangle","curve-style":"bezier",opacity:0.85}},
      {selector:"node[size]",style:{width:"data(size)",height:"data(size)"}},
      {selector:"edge[weight]",style:{width:"data(weight)"}},
      {selector:".risk",style:{"line-color":"#d64c59","target-arrow-color":"#d64c59",opacity:0.9}},
      ...Object.entries(colors).map(([status,color])=>({selector:'.' + status,style:{"background-color":color}})),
      {selector:'node[kind = "Selected"]',style:{shape:"ellipse",width:52,height:52,"border-width":5,"border-color":p.text,"border-style":"double"}},
      {selector:'node[kind = "Parent"]',style:{shape:"hexagon","border-width":3,"border-color":p.module}},
      {selector:'node[kind = "Child"]',style:{shape:"triangle","border-width":3,"border-color":p.primary}},
      {selector:'node[kind = "Module"]',style:{shape:"round-rectangle","background-color":p.module,width:48,height:34}},
      {selector:'node[kind = "Test"]',style:{shape:"diamond","background-color":p.test,width:44,height:44}},
      {selector:'edge[relation]',style:{label:"data(relation)",color:p.text,"font-size":12,"text-rotation":"autorotate","text-background-color":"#ffffff","text-background-opacity":0,"text-margin-y":-8}}
    ];
  }
  async function init() {
    cleanup();
    const host = document.querySelector("[data-understanding]");
    if (!host) return;
    const charts = [];
    let disposed = false;
    let hashHandler = () => {};
    let requirementsTree;
    const observer = new MutationObserver(() => charts.filter(c => !c.destroyed()).forEach(c => c.style(cyStyle())));
    observer.observe(document.body,{attributes:true,attributeFilter:["data-md-color-scheme"]});
    cleanup = () => {disposed=true; charts.forEach(c=>c.destroy()); observer.disconnect(); window.removeEventListener("hashchange",hashHandler);};
    const notice = text => { host.querySelector('[role="status"]').textContent = text; };
    try {
      const [req,mission,code,execution] = await data();
      if (disposed) return;
      sourceRevision = req.source_revision;
      const stages = [...mission.stages,mission.nfr_tree];
      const reqById = new Map(req.nodes.map(n=>[n.id,n]));
      const moduleById = new Map(code.modules.map(n=>[n.id,n]));
      const allSteps = [...execution.steps,...execution.branches];
      function chart(id,elements,layout) {
        const cy = cytoscape({container:$(id), elements,style:cyStyle(),layout, minZoom:0.03,maxZoom:4,wheelSensitivity:0.2});
        charts.push(cy); return cy;
      }
      function reqCard(id) {
        const n=reqById.get(id); if(!n)return;
        const chain=[];let p=n;const seen=new Set();
        while(p && !seen.has(p.id)){seen.add(p.id);chain.unshift(link("requirements","req",p.id));p=reqById.get(p.parent);}
        $("ug-card").innerHTML="<h3>"+esc(n.id+" / "+(n.hid||"Retired UID"))+"</h3><p><strong>"+esc(n.status)+"</strong> | "+esc(n.area)+" | "+esc(stages.find(s=>s.id===n.stage)?.name)+"</p><p>"+esc(n.statement)+"</p><p>Authored parent chain: "+chain.join(" &gt; ")+"</p><h4>Code anchors</h4>"+list(n.code_anchors.map(a=>link("code","module",a.module)+"<br>"+source(a)))+"<h4>Test anchors</h4>"+list(n.test_anchors.map(source))+"<p>Requirement source: "+source(n.source)+"</p>";
        setHash("req",id); requirementsTree?.neighborhood(id);
      }
      function moduleCard(id) {
        const m=moduleById.get(id);if(!m){const cited=req.nodes.filter(n=>n.code_anchors.some(a=>a.module===id));if(cited.length){$("ug-card").innerHTML="<h3>"+esc(id)+"</h3><p>Repository tooling or test module, outside the product module inventory.</p>"+list(cited[0].code_anchors.filter(a=>a.module===id).map(source))+list(cited.map(n=>link("requirements","req",n.id)));setHash("module",id);}return;}
        $("ug-card").innerHTML="<h3>"+esc(m.id)+"</h3><p>"+m.lines.toLocaleString()+" physical lines; "+m.code_lines.toLocaleString()+" code lines. "+source(m)+"</p><h4>Requirements that cite this module</h4>"+list(m.requirements.map(id=>link("requirements","req",id)))+"<h4>Execution steps in this scenario</h4>"+list(m.execution_steps.map(id=>{const s=allSteps.find(s=>s.id===id);return link("execution","step",id,s.order+". "+s.function); }));
        setHash("module",id); $("ug-card").scrollIntoView({block:"nearest"});
      }
      function stepCard(id) {
        const s=allSteps.find(s=>s.id===id); if(!s)return;
        $("ug-card").innerHTML="<h3>"+esc(s.order+". "+s.function)+"</h3><p>Lane: "+esc(s.lane)+". "+link("code","module",s.module_id)+"<br>"+source({path:s.module,line:s.line})+"</p><h4>Reads and inputs</h4>"+list(s.inputs.map(esc))+"<h4>Writes and outputs</h4>"+list(s.outputs.map(esc))+workspaceFiles(s)+"<p>"+esc(s.note||"")+"</p><p>Next calls or transitions: "+esc(s.next.join(", "))+"</p>";
        setHash("step",id); $("ug-card").scrollIntoView({block:"nearest"});
      }
      if(host.dataset.understanding === "index") {
        $("ug-mission").innerHTML="<p><strong>Mission:</strong> "+esc(mission.mission)+"</p><ol>"+mission.stages.map(s=>"<li><strong>"+esc(s.name)+"</strong>: "+esc(s.areas.join(", "))+"</li>").join("")+"</ol><p>Plus a separate NFR tree, retaining the authored parent relationships.</p><p>"+esc(mission.mapping_note)+"</p>";
        notice(req.summary.live+" live requirements; "+code.summary.modules+" modules; "+execution.steps.length+" static steps.");return;
      }
      if(!window.d3 || !window.cytoscape) throw new Error("Vendored chart libraries are unavailable. Read the static graph and file tables, or rebuild the documentation with its chart assets.");
      if(host.dataset.understanding === "requirements") {
        $("ug-stage").innerHTML=option("","All stages")+stages.map(s=>option(s.id,s.name)).join("");
        $("ug-area").innerHTML=option("","All areas")+Object.entries(mission.areas).map(([a,n])=>option(a,a+": "+n)).join("");
        $("ug-status-filter").innerHTML=option("live","All live statuses")+Object.keys(colors).map(s=>option(s,s)).join("")+option("all","Including retired");
        $("ug-legend").innerHTML=Object.entries(colors).map(([s,c])=>'<span><i class="ug-dot" style="background:'+c+'"></i>'+esc(s)+"</span>").join("");
        const {createRequirementsTree} = await import(new URL("requirements-tree.js", asset));
        if (disposed) return;
        requirementsTree = createRequirementsTree({req, mission, colors, select:reqCard, chart});
        let matched=[],limit=60;
        function results() {
          $("ug-results").innerHTML='<table class="ug-table"><thead><tr><th>Requirement</th><th>Status</th><th>First sentence</th></tr></thead><tbody>'+matched.slice(0,limit).map(n=>'<tr><td><button data-req="'+esc(n.id)+'">'+esc(n.id)+"<br>"+esc(n.hid)+"</button></td><td>"+esc(n.status)+"</td><td>"+esc(n.first_sentence)+"</td></tr>").join("")+"</tbody></table>";
          $("ug-more").hidden=matched.length<=limit;
          $("ug-results").querySelectorAll("[data-req]").forEach(b=>b.onclick=()=>reqCard(b.dataset.req));
        }
        function reset(){ $("ug-search").value="";$("ug-stage").value="";$("ug-area").value="";$("ug-status-filter").value="live";requirementsTree.reset();render(); }
        function render() {
          const term=$("ug-search").value.toLowerCase(),stage=$("ug-stage").value,area=$("ug-area").value,status=$("ug-status-filter").value;
          matched=req.nodes.filter(n=>(!term||(n.id+" "+n.hid+" "+n.statement).toLowerCase().includes(term))&&(!stage||n.stage===stage)&&(!area||n.area===area)&&(status==="all"||(status==="live"?n.status!=="retired":n.status===status)));
          requirementsTree.update(matched, {term,stage,area,status});
          const hierarchy={name:"Mission",children:stages.map(s=>({name:s.name,stage:s.id,children:[...new Set(matched.filter(n=>n.stage===s.id).map(n=>n.area))].map(a=>({name:a,stage:s.id,area:a,children:matched.filter(n=>n.stage===s.id&&n.area===a).map(n=>({name:n.id,id:n.id,status:n.status,value:1}))}))})).filter(s=>s.children.length)};
          const root=d3.hierarchy(hierarchy).sum(d=>d.value||0);d3.partition().size([2*Math.PI,300])(root);
          const svg=d3.select($("ug-sunburst")).html("").append("svg").attr("viewBox","-350 -350 700 700").attr("role","img").attr("aria-label","Requirements sunburst by mission, stage, area and status");
          const arc=d3.arc().startAngle(d=>d.x0).endAngle(d=>d.x1).padAngle(.002).innerRadius(d=>d.y0).outerRadius(d=>d.y1-1);
          svg.selectAll("path").data(root.descendants().filter(d=>d.depth)).join("path").attr("d",arc).attr("fill",d=>colors[d.data.status]|| (d.depth===1?"var(--ug-node)":"#84929c")).attr("fill-opacity",d=>d.data.status?1:.65).style("cursor","pointer").on("click",(_,d)=>{if(d.data.id)reqCard(d.data.id);else{$("ug-stage").value=d.data.stage;$("ug-area").value=d.data.area||"";render();}}).append("title").text(d=>d.ancestors().reverse().map(n=>n.data.name).join(" / ")+": "+d.value+ (d.data.status?" ("+d.data.status+")":""));
          svg.selectAll("text.stage").data(root.children||[]).join("text").attr("class","stage").attr("transform",d=>{const angle=(d.x0+d.x1)/2;const r=(d.y0+d.y1)/2;return "translate("+(Math.sin(angle)*r)+","+(-Math.cos(angle)*r)+")";}).attr("text-anchor","middle").attr("font-size",8).attr("fill","currentColor").text(d=>(d.x1-d.x0)>.18?d.data.name:"").style("pointer-events","none");
          svg.append("circle").attr("r",65).attr("fill","transparent").style("cursor","pointer").on("click",reset);
          svg.append("text").attr("text-anchor","middle").attr("font-size",14).attr("fill","currentColor").text(matched.length+" requirements").style("pointer-events","none");
          notice(matched.length+" matching requirements. Grouping follows the approved SRS stages.");limit=60;results();
        }
        ["ug-stage","ug-area","ug-status-filter"].forEach(id=>$(id).onchange=render);
        let debounce;$("ug-search").oninput=()=>{clearTimeout(debounce);debounce=setTimeout(()=>{if(!disposed)render();},160);};
        $("ug-reset").onclick=reset;$("ug-more").onclick=()=>{limit+=100;results();};
        hashHandler=()=>{const id=selection().get("req");if(reqById.has(id)){reset();$("ug-search").value=id;$("ug-status-filter").value="all";render();reqCard(id);}};
        render();hashHandler();
      }
      if(host.dataset.understanding === "code") {
        const {renderLayers} = await import(new URL("code-view.js", asset));
        if (disposed) return;
        let moduleGraph;
        const packageColors=d3.scaleOrdinal(d3.schemeTableau10).domain(code.nodes.map(n=>n.id));
        function edgeCard(e) { $("ug-edge-card").innerHTML="<h3>"+esc(e.source+" imports "+e.target)+"</h3><p>"+e.count+" occurrences. "+(e.upward?"Upward edge. ":"")+(e.cycle?"Part of a root-unit cycle.":"")+"</p>"+list(e.imports.map(i=>link("code","module",i.src)+" → "+link("code","module",i.target)+" ("+esc(i.kind)+", line "+i.line+")")); }
        function packageCard(id) {
          const modules=code.modules.filter(m=>m.package===id);const ids=[...new Set(modules.flatMap(m=>m.requirements))];
          $("ug-package-card").innerHTML="<h3>"+esc(id)+"</h3><p>"+modules.length+" modules. Select a module below or in the package graph.</p>"+list(modules.map(m=>link("code","module",m.id,m.id+" ("+m.lines+" lines)")))+"<details><summary>"+ids.length+" requirements citing this unit</summary>"+list(ids.map(id=>link("requirements","req",id)))+"</details>";
          $("ug-module-graph").hidden=false;if(moduleGraph)moduleGraph.destroy();
          const names=new Set(modules.map(m=>m.id));const edges=new Map();
          code.imports.filter(i=>names.has(i.src)&&names.has(i.target)&&i.src!==i.target).forEach(i=>edges.set(i.src+":"+i.target,{data:{id:i.src+":"+i.target,source:i.src,target:i.target},classes:code.module_sccs.some(c=>c.includes(i.src)&&c.includes(i.target))?"risk":""}));
          moduleGraph=chart("ug-module-graph",[...modules.map(m=>({data:{id:m.id,label:m.id.replace("pyflightstream.","")}})),...edges.values()],{name:"breadthfirst",directed:true,padding:30});
          moduleGraph.on("tap","node",e=>moduleCard(e.target.id()));
          $("ug-treemap-package").value=id;treemap();setHash("package",id);
        }
        function layerRender() {
          const nodes=code.nodes.filter(n=>$("ug-code-scope").value==="all"||n.kind==="package");const ids=new Set(nodes.map(n=>n.id));const edges=code.edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
          renderLayers($("ug-layers"),nodes,edges,packageCard,edgeCard);
          $("ug-dsm").innerHTML='<table class="ug-table ug-dsm"><thead><tr><th>Importer ↓ / dependency →</th>'+nodes.map(n=>"<th>"+esc(n.id)+"</th>").join("")+"</tr></thead><tbody>"+nodes.map(a=>"<tr><th>"+esc(a.id)+"</th>"+nodes.map(b=>{const e=edges.find(e=>e.source===a.id&&e.target===b.id);return e?'<td style="background:'+(e.upward||e.cycle?"#d64c5933":"#468b8b22")+'"><button data-edge="'+esc(e.source+":"+e.target)+'">'+e.count+"</button></td>":"<td>"+(a.id===b.id?"·":"")+"</td>";}).join("")+"</tr>").join("")+"</tbody></table>";
          $("ug-dsm").querySelectorAll("[data-edge]").forEach(b=>b.onclick=()=>edgeCard(code.edges.find(e=>e.source+":"+e.target===b.dataset.edge)));
          notice(code.summary.modules+" modules; "+code.summary.physical_lines.toLocaleString()+" physical lines; "+code.summary.upward_edges+" upward edges. "+nodes.length+" root units displayed.");
        }
        function treemap() {
          const pkg=$("ug-treemap-package").value;const modules=code.modules.filter(m=>!pkg||m.package===pkg);
          $("ug-module-select").innerHTML=option("","Select a module")+modules.map(m=>option(m.id,m.id)).join("");
          const h=d3.hierarchy({children:[...d3.group(modules,m=>m.package)].map(([name,children])=>({name,children}))}).sum(d=>d.lines||0).sort((a,b)=>b.value-a.value);
          d3.treemap().size([1000,600]).paddingOuter(3).paddingTop(20).paddingInner(2)(h);
          const svg=d3.select($("ug-treemap")).html("").append("svg").attr("viewBox","0 0 1000 600").attr("role","img").attr("aria-label","Module size treemap");
          const tiles=svg.selectAll("g").data(h.leaves()).join("g").attr("transform",d=>"translate("+d.x0+","+d.y0+")").style("cursor","pointer").on("click",(_,d)=>moduleCard(d.data.id));
          tiles.append("rect").attr("width",d=>d.x1-d.x0).attr("height",d=>d.y1-d.y0).attr("fill",d=>packageColors(d.data.package)).attr("fill-opacity",.75);
          tiles.append("title").text(d=>d.data.id+": "+d.data.lines+" physical lines");
          tiles.filter(d=>d.x1-d.x0>70&&d.y1-d.y0>24).append("text").attr("x",4).attr("y",16).attr("font-size",10).attr("fill","#111").text(d=>d.data.id.split(".").pop().slice(0,Math.floor((d.x1-d.x0)/6)));
          svg.selectAll("text.package").data(h.children||[]).join("text").attr("class","package").attr("x",d=>d.x0+3).attr("y",d=>d.y0+14).attr("font-size",12).attr("fill","currentColor").text(d=>d.x1-d.x0>50?d.data.name:"");
        }
        $("ug-treemap-package").innerHTML=option("","All root units")+code.nodes.map(n=>option(n.id,n.id)).join("");
        $("ug-treemap-package").onchange=treemap;$("ug-module-select").onchange=e=>moduleCard(e.target.value);
        $("ug-code-scope").onchange=layerRender;$("ug-code-fit").onclick=()=>{layerRender();$("ug-layers").scrollTo({left:0,top:0});};
        hashHandler=()=>{const s=selection();if(s.has("module"))moduleCard(s.get("module"));else if(s.has("package"))packageCard(s.get("package"));};
        layerRender();treemap();hashHandler();
      }
      if(host.dataset.understanding === "execution") {
        const row=execution.example_row;$("ug-example").innerHTML="<strong>Example matrix row:</strong> POL "+esc(row.POL)+", "+esc(row.WORKFLOW)+", build "+esc(row.FS_BUILD)+". "+esc(row.FLIGHT_CONDITION)+"; sweep "+esc(row.SWEEP_VALUES)+".<br>"+esc(execution.representative_case.prerequisites);
        $("ug-lane").innerHTML=option("","All lanes")+execution.lanes.map(n=>option(n,n)).join("");
        function swimlane() {
          const term=$("ug-step-search").value.toLowerCase(),lane=$("ug-lane").value;
          const steps=execution.steps.filter(s=>(!lane||s.lane===lane)&&(!term||JSON.stringify(s).toLowerCase().includes(term)));
          $("ug-swimlane").innerHTML='<table class="ug-table ug-swimlane"><thead><tr>'+execution.lanes.map(l=>"<th>"+esc(l)+"</th>").join("")+"</tr></thead><tbody>"+steps.map(s=>"<tr>"+execution.lanes.map(l=>s.lane!==l?"<td></td>":'<td class="ug-step"><button data-step="'+s.id+'">'+esc(s.order+". "+s.function)+"</button><small>"+link("code","module",s.module_id,s.module_id.replace("pyflightstream.",""))+"</small><details><summary>Reads and writes</summary><strong>Reads / inputs</strong>"+list(s.inputs.map(esc))+"<strong>Writes / outputs</strong>"+list(s.outputs.map(esc))+workspaceFiles(s)+"</details></td>").join("")+"</tr>").join("")+"</tbody></table>";
          $("ug-swimlane").querySelectorAll("[data-step]").forEach(b=>b.onclick=()=>stepCard(b.dataset.step));
          notice(steps.length+" of "+execution.steps.length+" static steps displayed; "+execution.branches.length+" alternative branches. No solver was run.");
        }
        $("ug-step-search").oninput=swimlane;$("ug-lane").onchange=swimlane;
        $("ug-branches").innerHTML=execution.branches.map(s=>'<p><button class="ug-button" data-step="'+s.id+'">'+esc(s.function)+"</button> "+esc(s.note)+"</p>").join("");
        $("ug-branches").querySelectorAll("[data-step]").forEach(b=>b.onclick=()=>stepCard(b.dataset.step));
        if(!d3.sankey)throw new Error("The pinned d3-sankey extension did not load.");
        const flow=d3.sankey().nodeId(d=>d.id).nodeWidth(16).nodePadding(28).extent([[170,30],[890,460]])(structuredClone(execution.flow));
        const svg=d3.select($("ug-sankey")).html("").append("svg").attr("viewBox","0 0 1080 500").attr("role","img").attr("aria-label","Input to product relationship Sankey");
        svg.append("g").selectAll("path").data(flow.links).join("path").attr("d",d3.sankeyLinkHorizontal()).attr("fill","none").attr("stroke","var(--ug-edge)").attr("stroke-opacity",.35).attr("stroke-width",d=>Math.max(1,d.width)).on("click",(_,d)=>{$("ug-flow-detail").textContent=d.source.name+" → "+d.target.name+": one curated dependency relationship.";}).append("title").text(d=>d.source.name+" → "+d.target.name);
        const nodes=svg.append("g").selectAll("g").data(flow.nodes).join("g");
        nodes.append("rect").attr("x",d=>d.x0).attr("y",d=>d.y0).attr("width",d=>d.x1-d.x0).attr("height",d=>d.y1-d.y0).attr("fill","var(--ug-node)").on("click",(_,d)=>{$("ug-flow-detail").textContent=d.name+". Incoming relationships: "+d.targetLinks.length+"; outgoing relationships: "+d.sourceLinks.length+".";});
        nodes.append("text").attr("x",d=>d.x0<500?d.x0-8:d.x1+8).attr("y",d=>(d.y0+d.y1)/2).attr("dy",".35em").attr("text-anchor",d=>d.x0<500?"end":"start").attr("font-size",13).attr("fill","currentColor").text(d=>d.name);
        hashHandler=()=>stepCard(selection().get("step"));swimlane();hashHandler();
      }
      window.addEventListener("hashchange",hashHandler);
    } catch(error) { if(!disposed){notice("View unavailable: "+error.message);host.dataset.error=error.message;console.error(error);} }
  }
  if(typeof document$ !== "undefined")document$.subscribe(init);
  else if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);
  else init();
})();
