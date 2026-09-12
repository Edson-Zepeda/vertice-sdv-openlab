const film=document.querySelector('#film');
const status=document.querySelector('#film-status');
const chapterContainer=document.querySelector('#chapters');
let chapters=[];
function message(value){status.textContent=value;status.hidden=!value;}
try {
  const response=await fetch('./data/film.json');
  if(response.ok){
    const metadata=await response.json();
    const candidate=metadata?.chapters;
    if(!Array.isArray(candidate)||!candidate.every((chapter,index)=>
      chapter&&typeof chapter.label==='string'&&chapter.label.trim()&&
      typeof chapter.start==='number'&&Number.isFinite(chapter.start)&&chapter.start>=0&&
      (index===0||chapter.start>candidate[index-1].start)
    ))throw new Error('Invalid chapter metadata');
    chapters=candidate;
    for(const [i,chapter] of chapters.entries()){
      const button=document.createElement('button');button.textContent=chapter.label;button.dataset.index=String(i);
      button.setAttribute('aria-label',`Ir al capítulo ${chapter.label}`);
      button.addEventListener('click',()=>{
        film.currentTime=chapter.start;
        film.play().then(()=>message('')).catch(()=>message('Pulsa reproducir para continuar.'));
      });chapterContainer.append(button);
    }
  }
} catch { /* Native video controls remain available. */ }
film.addEventListener('timeupdate',()=>{
  const index=chapters.findLastIndex(chapter=>film.currentTime>=chapter.start-.1);
  for(const button of chapterContainer.children)button.setAttribute('aria-current',String(Number(button.dataset.index)===index));
});
film.addEventListener('error',()=>message('No se pudo abrir el video. Puedes descargarlo abajo.'));
try {
  const response=await fetch('./data/release.json');
  if(response.ok){const release=await response.json();if(release.published){
    for(const [id,key] of [['code-link','repository'],['package-link','package']]){
      const anchor=document.getElementById(id);const url=new URL(release[key]);
      if(url.protocol==='https:'&&url.hostname==='github.com'){anchor.href=url.href;anchor.hidden=false;}
    }
  }}
} catch { /* Publication links appear only when verified metadata is available. */ }
