/* Verify a prefixed static copy, or an anonymous public URL in VERTICE_URL. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const ROOT=path.resolve(__dirname,'..');
const name=process.argv[2]||'static-prefix';
if(!/^[a-z0-9_-]+$/i.test(name))throw Error('Use a plain evidence name');
const OUT=path.join(ROOT,'evidence','publication',name);
fs.mkdirSync(OUT,{recursive:true});
const digest=data=>crypto.createHash('sha256').update(data).digest('hex');
const report={started_at:new Date().toISOString(),checks:[],errors:[],scope:'Fresh, unauthenticated browser context and HTTP requests. Public only when VERTICE_URL names a public origin.'};
function check(name,passed,details={}){report.checks.push({name,passed:!!passed,...details});if(!passed)throw Error(name);}
let server,browser,base=process.env.VERTICE_URL;
async function startLocal(){
  fs.mkdirSync(path.join(ROOT,'tmp'),{recursive:true});
  const directory=fs.mkdtempSync(path.join(ROOT,'tmp','prefix-qa-'));
  fs.cpSync(path.join(ROOT,'web'),path.join(directory,'vertice-sdv-openlab'),{recursive:true});
  const code='import sys,json; from server import LocalServer; s=LocalServer(("127.0.0.1",0),web_root=sys.argv[1]); print(json.dumps({"port":s.server_port}),flush=True); s.serve_forever(poll_interval=0.1)';
  server=spawn(process.env.VERTICE_PYTHON||'python',['-c',code,directory],{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let stderr='';server.stderr.on('data',chunk=>stderr+=chunk.toString());
  const metadata=await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(Error('Local fixture server did not start: '+stderr)),15000);
    let buffer='';server.stdout.on('data',chunk=>{buffer+=chunk.toString();if(buffer.includes('\n')){clearTimeout(timeout);try{resolve(JSON.parse(buffer.split('\n')[0]));}catch(error){reject(error);}}});
    server.on('error',error=>{clearTimeout(timeout);reject(error);});
    server.once('exit',code=>{clearTimeout(timeout);reject(Error('Fixture server exited '+code+': '+stderr));});
  });
  report.fixture_directory=directory;
  return `http://127.0.0.1:${metadata.port}/vertice-sdv-openlab/`;
}
(async()=>{
  try{
    if(!base)base=await startLocal();
    if(!base.endsWith('/'))base+='/';
    report.base=base;report.public_origin=!['localhost','127.0.0.1'].includes(new URL(base).hostname);
    browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
    const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    const page=await context.newPage();page.setDefaultTimeout(45000);
    const errors=[],requests=[];
    page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>requests.push(request.url()));
    await page.goto(new URL('?engine=browser',base).href,{waitUntil:'networkidle'});
    await page.locator('#solve').click();await page.locator('#result-content').waitFor({state:'visible'});
    check('Static deployment calculates through actual browser Python',await page.locator('#result-cost').textContent()==='11');
    await page.locator('#explore-trace').click();await page.locator('#next-step').click();
    check('Actual trace can be inspected',await page.locator('#timeline-count').textContent()==='2 / 43');
    await page.screenshot({path:path.join(OUT,'studio-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    check('Mobile static studio has no page overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:path.join(OUT,'studio-mobile.png'),fullPage:true});
    await page.goto(new URL('qa.html?engine=browser',base).href);
    await page.locator('#qa-run').click();await page.waitForFunction(()=>!document.querySelector('#qa-download').disabled);
    const worker=JSON.parse(await page.locator('#qa-json').textContent());
    fs.writeFileSync(path.join(OUT,'worker.json'),JSON.stringify(worker,null,2)+'\n');
    check('Whole results, traces, raw imports and queue match native reference',worker.passed&&worker.engine.mode==='browser',{checks:worker.checks.length,passed:worker.checks.filter(row=>row.passed).length});
    const files=['index.html','app.js','engine.js','python-worker.js','proyecto.html','project.js','project.css','style.css','python/manifest.json','vendor/pyodide/pyodide.mjs','vendor/pyodide/pyodide.asm.wasm','vendor/pyodide/pyodide.asm.mjs','vendor/pyodide/python_stdlib.zip','fonts/Manrope.ttf','fonts/DMSans.ttf','docs/VerticeSDV_Informe.pdf','media/VerticeSDV_Demo.mp4','media/VerticeSDV.vtt'];
    const manifest=JSON.parse(fs.readFileSync(path.join(ROOT,'web/python/manifest.json'),'utf8'));
    files.push(...manifest.files.map(file=>'python/vertice/'+file.name));
    for(const file of files){
      const response=await context.request.get(new URL(file,base).href,{timeout:90000});
      const data=await response.body(),expected=digest(fs.readFileSync(path.join(ROOT,'web',file)));
      check(`Delivered bytes match: ${file}`,response.ok()&&digest(data)===expected,{status:response.status(),bytes:data.length,sha256:digest(data)});
    }
    const partial=await context.request.get(new URL('media/VerticeSDV_Demo.mp4',base).href,{headers:{Range:'bytes=500000-500255'}});
    check('The served video supports accurate partial downloads',partial.status()===206&&(await partial.body()).equals(fs.readFileSync(path.join(ROOT,'web/media/VerticeSDV_Demo.mp4')).subarray(500000,500256)),{status:partial.status(),range:partial.headers()['content-range']});
    await page.goto(new URL('proyecto.html',base).href,{waitUntil:'networkidle'});
    await page.getByRole('button',{name:'Ir al capítulo Rendimiento',exact:true}).click();
    const chapter=JSON.parse(fs.readFileSync(path.join(ROOT,'web/data/film.json'),'utf8')).chapters.find(row=>row.label==='Rendimiento');
    await page.waitForFunction(start=>{const video=document.querySelector('#film');return video.readyState>=3&&!video.paused&&video.currentTime>=start&&video.currentTime<start+5;},chapter.start);
    check('The delivered video plays after chapter seeking',await page.locator('#film').evaluate(video=>!video.error));
    await page.locator('#film').evaluate(video=>video.pause());
    check('Mobile deliverables heading preserves word separation',await page.locator('.deliverables h2').innerText()==='La evidencia está incluida.');
    await page.screenshot({path:path.join(OUT,'project-mobile.png'),fullPage:true});
    const release=JSON.parse(fs.readFileSync(path.join(ROOT,'web/data/release.json'),'utf8'));
    if(release.published){
      for(const [id,key] of [['code-link','repository'],['package-link','package']]){
        check(`${key} is visible with the release URL`,await page.locator('#'+id).isVisible()&&await page.locator('#'+id).getAttribute('href')===release[key]);
      }
    }
    check('No external resource requests from the page',requests.every(url=>new URL(url).origin===new URL(base).origin));
    check('No uncaught browser errors',errors.length===0,{errors});
  }catch(error){report.errors.push(error.stack||String(error));process.exitCode=1;}
  finally{
    await browser?.close();server?.kill();
    report.finished_at=new Date().toISOString();report.passed=report.checks.filter(row=>row.passed).length;report.failed=report.checks.filter(row=>!row.passed).length+report.errors.length;
    fs.writeFileSync(path.join(OUT,'qa.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({base,passed:report.passed,failed:report.failed,error:report.errors[0]||null}));
  }
})();
