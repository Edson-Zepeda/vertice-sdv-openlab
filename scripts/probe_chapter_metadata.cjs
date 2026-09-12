/* Actual browser failures under damaged chapter data; native playback must survive. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'..'),name=process.argv[2]||'after';
if(!/^[a-z0-9_-]+$/i.test(name))throw Error('Use a plain evidence name');
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({reducedMotion:'reduce'});
  const cases=[['missing',{}],['null',{chapters:null}],['bad_label',{chapters:[{label:{bad:true},start:0}]}],['bad_time',{chapters:[{label:'Prueba',start:'oops'}]}],['negative',{chapters:[{label:'Prueba',start:-1}]}],['unordered',{chapters:[{label:'A',start:10},{label:'B',start:2}]}]];
  const report={created_at:new Date().toISOString(),cases:[]};
  try{
    for(const [id,metadata]of cases){
      const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.route('**/data/film.json',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(metadata)}));
      await page.goto('http://127.0.0.1:8770/proyecto.html');
      await page.locator('#film').evaluate(async video=>{await video.play();});
      await page.waitForFunction(()=>document.querySelector('#film').currentTime>.25);
      const state=await page.locator('#film').evaluate(video=>({playing:!video.paused,controls:video.controls,error:video.error?.message||null}));
      const buttons=await page.locator('#chapters button').count();
      report.cases.push({id,metadata,state,buttons,errors,passed:state.playing&&state.controls&&!state.error&&buttons===0&&errors.length===0});
      await page.close();
    }
  }finally{await browser.close();}
  report.passed=report.cases.filter(row=>row.passed).length;report.failed=report.cases.length-report.passed;
  report.source_hashes=Object.fromEntries(['web/project.js','web/proyecto.html'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(ROOT,file))).digest('hex')]));
  const output=path.join(ROOT,'evidence/project-page/metadata');fs.mkdirSync(output,{recursive:true});
  fs.writeFileSync(path.join(output,name+'.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({passed:report.passed,failed:report.failed}));if(report.failed)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
