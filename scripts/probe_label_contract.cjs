/* Independent import/display probe. Does not alter application files. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'..');
const OUT=path.join(ROOT,'evidence','ui','label-contract');
fs.mkdirSync(OUT,{recursive:true});
const label=process.argv[2]||'probe';
if(!/^[a-z0-9_-]+$/i.test(label))throw Error('Use a plain evidence name');
const report={started_at:new Date().toISOString(),cases:[],scope:'Real local API and real Pyodide; raw import, exported JSON and displayed SVG label.'};
const base=process.env.VERTICE_URL||'http://127.0.0.1:8770/';
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
  try{
    for(const engine of ['local','browser']){
      const context=await browser.newContext({viewport:{width:1440,height:1000}});
      const page=await context.newPage();page.setDefaultTimeout(30000);
      await page.goto(new URL(engine==='browser'?'?engine=browser':'',base).href);
      await page.locator('#solve').waitFor();
      for(const [name,value] of [['empty',''],['spaces','  Inicio  '],['emoji80','🧭'.repeat(80)],['literal_html','<script>alert(1)</script>']]){
        const graph={schema_version:1,directed:true,nodes:[{id:'A',label:value,x:120,y:200},{id:'B',label:'Fin',x:600,y:200}],edges:[{id:'ab',source:'A',target:'B',weight:'0.3'}]};
        await page.locator('#import-file').setInputFiles({name:`${name}.json`,mimeType:'application/json',buffer:Buffer.from(JSON.stringify(graph))});
        await page.waitForFunction(()=>!document.querySelector('#import-button').disabled);
        const stored=await page.evaluate(()=>JSON.parse(localStorage.getItem('vertice.graph.v1'))?.graph);
        const imported=stored?.nodes?.length===2&&stored.nodes[0].id==='A';
        const record={engine,name,expected_label_code_points:[...value].length,imported,preserved:imported&&stored.nodes[0].label===value,notice:await page.locator('#notice-text').textContent()};
        if(imported){
          const shown=await page.locator('#nodes [data-node="A"]').textContent();
          record.svg_has_unpaired_surrogate=[...shown].some(char=>char.codePointAt(0)>=0xd800&&char.codePointAt(0)<=0xdfff);
          await page.locator('#file-menu-button').click();
          const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#export-button').click()]);
          const file=await download.path();const exported=JSON.parse(fs.readFileSync(file,'utf8'));
          record.export_preserves_label=exported.nodes.find(node=>node.id==='A')?.label===value;
          await page.locator('#solve').click();await page.locator('#result-content').waitFor({state:'visible'});
          record.cost=await page.locator('#result-cost').textContent();
        }
        record.passed=record.imported&&record.preserved&&record.export_preserves_label&&record.cost==='0.3'&&!record.svg_has_unpaired_surrogate;
        report.cases.push(record);
        if(!record.passed)await page.screenshot({path:path.join(OUT,`${label}-${engine}-${name}.png`),fullPage:true});
      }
      await context.close();
    }
  }catch(error){report.error=error.stack||String(error);process.exitCode=1;}
  finally{
    await browser.close();report.finished_at=new Date().toISOString();report.passed=report.cases.filter(row=>row.passed).length;report.failed=report.cases.filter(row=>!row.passed).length+(report.error?1:0);
    report.hashes=Object.fromEntries(['web/app.js','web/index.html','vertice/graph.py'].map(name=>[name,crypto.createHash('sha256').update(fs.readFileSync(path.join(ROOT,name))).digest('hex')]));
    fs.writeFileSync(path.join(OUT,`${label}.json`),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
    if(report.failed)process.exitCode=1;
  }
})();
