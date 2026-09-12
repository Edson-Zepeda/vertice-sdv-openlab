/* Browser checks for the deliverables page and the actual encoded video. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'..');
const OUT=path.join(ROOT,'evidence','project-page');
const base=process.env.VERTICE_URL||'http://127.0.0.1:8770/';
const report={started_at:new Date().toISOString(),base,checks:[],errors:[],accessibility:[]};
fs.mkdirSync(OUT,{recursive:true});
function check(name,ok,detail={}){report.checks.push({name,passed:!!ok,...detail});if(!ok)throw Error(name);}
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const page=await context.newPage();
  const failures=[],requests=[];
  page.on('pageerror',error=>failures.push(error.message));
  page.on('request',request=>requests.push(request.url()));
  try{
    await page.goto(new URL('proyecto.html',base).href,{waitUntil:'networkidle'});
    await page.waitForFunction(()=>document.querySelector('#film').readyState>=1);
    const film=JSON.parse(fs.readFileSync(path.join(ROOT,'web/data/film.json'),'utf8'));
    const duration=await page.locator('#film').evaluate(video=>video.duration);
    check('Actual MP4 metadata loads',Math.abs(duration-film.duration)<.1,{duration,planned:film.duration});
    check('Nine chapter controls',await page.locator('#chapters button').count()===9);
    const requestsBeforeAxe=[...requests];
    check('Page assets load from the same origin',requestsBeforeAxe.every(url=>new URL(url).origin===new URL(base).origin),{requests:requestsBeforeAxe});
    for(const width of [320,390,768,1440]){
      await page.setViewportSize({width,height:width<500?844:1000});
      const sizes=await page.evaluate(()=>({viewport:innerWidth,body:document.documentElement.scrollWidth,h1:parseFloat(getComputedStyle(document.querySelector('h1')).fontSize)}));
      check(`No page overflow at ${width}px`,sizes.body<=sizes.viewport,{sizes});
      check(`Readable heading at ${width}px`,sizes.h1>=40,{font_px:sizes.h1});
      await page.screenshot({path:path.join(OUT,`page-${width}.png`),fullPage:true});
    }
    await page.setViewportSize({width:1440,height:1000});
    for(const [index,chapter] of film.chapters.entries()){
      await page.getByRole('button',{name:`Ir al capítulo ${chapter.label}`,exact:true}).click();
      await page.waitForFunction(start=>{const video=document.querySelector('#film');return video.readyState>=3&&!video.seeking&&!video.paused&&video.currentTime>=start&&video.currentTime<start+3;},chapter.start);
      const state=await page.locator('#film').evaluate(video=>({time:video.currentTime,ready:video.readyState,error:video.error?.code||null}));
      check(`Playback at chapter ${index+1}: ${chapter.label}`,state.error===null&&state.time>=chapter.start,{state});
      await page.waitForFunction(label=>document.querySelector('#chapters [aria-current="true"]')?.textContent===label,chapter.label);
      check(`Selected chapter is exposed: ${chapter.label}`,await page.getByRole('button',{name:`Ir al capítulo ${chapter.label}`,exact:true}).getAttribute('aria-current')==='true');
      await page.locator('#film').evaluate(video=>video.pause());
    }
    const caption=await page.locator('#film').evaluate(async video=>{
      video.textTracks[0].mode='hidden';
      const start=performance.now();
      while(!video.textTracks[0].cues?.length&&performance.now()-start<5000)await new Promise(resolve=>setTimeout(resolve,50));
      return {tracks:video.textTracks.length,cues:video.textTracks[0].cues?.length||0,language:video.textTracks[0].language};
    });
    const expectedCues=(fs.readFileSync(path.join(ROOT,'web/media/VerticeSDV.vtt'),'utf8').match(/ --> /g)||[]).length;
    check('Spanish captions load as a native track',caption.tracks===1&&caption.cues===expectedCues&&expectedCues>0&&caption.language==='es',{caption,expectedCues});
    await page.getByRole('button',{name:'Ir al capítulo Clases',exact:true}).focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(()=>!document.querySelector('#film').paused);
    check('Chapters are usable by keyboard',await page.locator('#film').evaluate(video=>!video.paused));
    await page.locator('#film').evaluate(video=>video.pause());
    for(const title of ['Cómo encuentra la ruta','Cómo se comprueba','Qué representa']){
      await page.locator('summary').filter({hasText:title}).click();
      check(`Method disclosure opens: ${title}`,await page.locator('details').filter({has:page.locator('summary').filter({hasText:title})}).getAttribute('open')!==null);
    }
    const pdf=await context.request.get(new URL('docs/VerticeSDV_Informe.pdf',base).href);
    const pdfBytes=await pdf.body();
    check('The report download matches the delivered PDF',pdf.ok()&&crypto.createHash('sha256').update(pdfBytes).digest('hex')===sha(path.join(ROOT,'docs/VerticeSDV_Informe.pdf')),{bytes:pdfBytes.length});
    const range=await context.request.get(new URL('media/VerticeSDV_Demo.mp4',base).href,{headers:{Range:'bytes=100000-100127'}});
    const rangeBytes=await range.body();
    check('The video supports accurate byte-range seeking',range.status()===206&&rangeBytes.equals(fs.readFileSync(path.join(ROOT,'web/media/VerticeSDV_Demo.mp4')).subarray(100000,100128)),{status:range.status(),bytes:rangeBytes.length,content_range:range.headers()['content-range']});
    let axe;try{axe=require.resolve('axe-core/axe.min.js');}catch{const local=path.resolve(ROOT,'../../work/qa-deps/node_modules/axe-core/axe.min.js');if(fs.existsSync(local))axe=local;}
    if(!axe)throw Error('axe-core is required for this verification; set NODE_PATH to the optional QA dependencies.');
    const axeURL=new URL('__qa__/axe.min.js',base).href;
    await page.route(axeURL,route=>route.fulfill({contentType:'text/javascript',body:fs.readFileSync(axe,'utf8')}));
    await page.addScriptTag({url:axeURL});
    for(const width of [390,1440]){
      await page.setViewportSize({width,height:1000});
      const result=await page.evaluate(()=>axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}}));
      const violations=result.violations.map(item=>({id:item.id,impact:item.impact,nodes:item.nodes.map(node=>({target:node.target,summary:node.failureSummary}))}));
      report.accessibility.push({width,violations});check(`Automated accessibility scan at ${width}px`,violations.length===0,{violations});
    }
    check('No JavaScript errors in the verified interactions',failures.length===0,{errors:failures});
    // Degraded metadata must preserve native video and download controls.
    await page.route('**/data/film.json',route=>route.fulfill({status:503,body:'Unavailable'}));
    await page.reload({waitUntil:'networkidle'});
    check('Video controls survive unavailable chapter metadata',await page.locator('#film').evaluate(video=>video.controls)&&await page.locator('a[download]').count()===1);
    check('No uncaught error when chapter metadata is unavailable',failures.length===0,{errors:failures});
  }catch(error){report.errors.push(error.stack||String(error));process.exitCode=1;await page.screenshot({path:path.join(OUT,'failure.png'),fullPage:true}).catch(()=>{});}
  finally{
    report.finished_at=new Date().toISOString();report.passed=report.checks.filter(x=>x.passed).length;report.failed=report.checks.filter(x=>!x.passed).length+report.errors.length;
    report.source_hashes=Object.fromEntries(['web/proyecto.html','web/project.css','web/project.js','web/data/film.json','web/media/VerticeSDV_Demo.mp4','docs/VerticeSDV_Informe.pdf'].map(name=>[name,sha(path.join(ROOT,name))]));
    fs.writeFileSync(path.join(OUT,'qa.json'),JSON.stringify(report,null,2)+'\n');
    await browser.close();console.log(JSON.stringify({passed:report.passed,failed:report.failed,error:report.errors[0]||null}));
  }
})();
