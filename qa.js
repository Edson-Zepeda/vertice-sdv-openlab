import { solveGraph, normalizeGraphJSON, engineStatus } from './engine.js';
const run=document.querySelector('#qa-run');
const download=document.querySelector('#qa-download');
const output=document.querySelector('#qa-results');
const status=document.querySelector('#qa-status');
let report;
const canonical=value=>JSON.stringify(value,(_key,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b))):item);
function record(name,passed,detail='') {
  const row={name,passed,detail};report.checks.push(row);
  const li=document.createElement('li');li.textContent=`${passed?'Aprobado':'Fallo'} · ${name}${detail?' · '+detail:''}`;output.append(li);
}
run.addEventListener('click',async()=>{
  run.disabled=true;download.disabled=true;output.replaceChildren();
  report={generated_at:new Date().toISOString(),environment:{url:location.href,user_agent:navigator.userAgent},checks:[]};
  try {
    status.textContent='Cargando referencias y Python…';
    const reference=await(await fetch('./qa-cases.json',{cache:'no-store'})).json();
    const manifest=await(await fetch('./python/manifest.json',{cache:'no-store'})).json();
    record('Mismo código Python nativo y web',manifest.files.every(f=>reference.core[f.name]===f.sha256));
    report.core=reference.core;report.reference_sha256=reference.source_sha256;
    for(const row of reference.cases){
      status.textContent=`Comprobando ${row.title}…`;
      try {
        const start=performance.now();const result=await solveGraph(row.payload);
        record(row.id,canonical(result)===canonical(row.native_result),`${(performance.now()-start).toFixed(1)} ms; comparación completa`);
      } catch(error){record(row.id,false,error.message);}
    }
    const base={schema_version:1,directed:false,nodes:[{id:'A',label:'Café 🚗 你好',x:0,y:0},{id:'B',label:'Destino',x:100,y:100}],edges:[{id:'e1',source:'A',target:'B',weight:'TOKEN'}]};
    const document=JSON.stringify(base);
    for(const [name,raw,accepted,expected] of [
      ['Importación decimal exacta',document.replace('"TOKEN"','0.1'),true,'0.1'],
      ['Rechazo de decimal mayor al máximo',document.replace('"TOKEN"','1000000000000.000001'),false],
      ['Rechazo de precisión excesiva',document.replace('"TOKEN"','1e-1000'),false],
      ['Rechazo de exponente extremo',document.replace('"TOKEN"','1e9999999999999999999999'),false],
      ['Rechazo de campos duplicados',document.replace('"TOKEN"','1').replace('"directed":false','"directed":true,"directed":false'),false],
      ['Rechazo de peso negativo',document.replace('"TOKEN"','-1'),false],
      ['Rechazo de Infinity',document.replace('"TOKEN"','Infinity'),false],
      ['Conservación de Unicode',document.replace('"TOKEN"','"0.125000"'),true,'0.125'],
    ]){
      try {const graph=await normalizeGraphJSON(raw);record(name,accepted&&graph.edges[0].weight===expected&&graph.nodes[0].label===base.nodes[0].label);}
      catch(error){record(name,!accepted,error.message);}
    }
    const cancelled=new AbortController();cancelled.abort();
    try {await solveGraph(reference.cases[0].payload,{signal:cancelled.signal});record('Solicitud cancelada antes de iniciar',false);}
    catch(error){record('Solicitud cancelada antes de iniciar',error.name==='AbortError');}
    const [one,two,three]=await Promise.all(reference.cases.slice(0,3).map(row=>solveGraph(row.payload)));
    record('Tres solicitudes simultáneas conservan sus resultados',[one,two,three].every((result,i)=>canonical(result)===canonical(reference.cases[i].native_result)));
    report.engine=engineStatus();report.passed=report.checks.every(c=>c.passed);
    status.textContent=`${report.checks.filter(c=>c.passed).length} / ${report.checks.length} comprobaciones aprobadas · ${report.engine.mode}`;
  } catch(error){record('Ejecución completa',false,error.message);status.textContent='La verificación no pudo completarse.';report.passed=false;}
  finally{document.querySelector('#qa-json').textContent=JSON.stringify(report,null,2);run.disabled=false;download.disabled=false;}
});
download.addEventListener('click',()=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='vertice-browser-verification.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
