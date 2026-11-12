const $=s=>document.querySelector(s),R=(a,b)=>a+Math.random()*(b-a),P=a=>a[Math.floor(Math.random()*a.length)];
const M$=n=>'$'+n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g,','),slug=s=>s.toLowerCase().replace(/\W/g,''),clock=()=>new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
const T={Research:['Summarise 40 supplier contracts','Compare EU battery rules','Market scan: pet insurance'],Code:['Fix flaky checkout test','Write a CSV importer','Move cron jobs to a queue'],Design:['Landing hero variants','Icon set, 24 glyphs','Refresh email template'],Data:['Clean 20k CRM rows','Dedupe product catalogue','Label 500 support tickets'],Legal:['Review NDA clauses','Flag GDPR gaps in policy']};
const RG={Research:[8,22],Code:[14,40],Design:[10,28],Data:[6,18],Legal:[16,36]},SKC={Research:'var(--sky)',Code:'var(--lime)',Design:'var(--pink)',Data:'var(--org)',Legal:'var(--yel)'};
const COLS=['var(--lime)','var(--org)','var(--pink)','var(--sky)','var(--grn)','var(--red)','var(--yel)','#B7A6FF','#9BE8D0','#FFB3A7'];let N=0;
const mk=(name,role,kind,bal,rep,cheat)=>({id:slug(name),name,role,kind,bal,earned:0,spent:0,jobs:0,rep,busy:0,cheat,col:COLS[N%10],k:N++,wal:'wal_'+Math.random().toString(36).slice(2,6).toUpperCase()});
const mgrs=[mk('Atlas Ops','Operations','m',400,1),mk('Ledgerly','Finance','m',400,1),mk('Northwind PM','Product','m',400,1)];
const works=[['Scout','Research',.93],['Quill','Research',.86],['Patch','Code',.91],['Forge','Code',.82],['Pixel','Design',.9],['Hue','Design',.84],['Sieve','Data',.94],['Tally','Data',.8],['Brief','Legal',.88]].map(([n,r,q])=>mk(n,r,'w',20,q));
works.push(mk('Glitch','Code','w',20,.35,1));
const all=()=>[...mgrs,...works];
let funded=all().reduce((a,x)=>a+x.bal,0),jobs=[],led=[],hist=[0],paid=0,done=0,fees=0,vtot=0,vOk=0,vNo=0,jid=1,timer,running=true,snd=false,shown='';
const av=(a,s=44)=>{const k=a.k%4,L='stroke="#111" stroke-width="2"';
const E=[`<circle cx="19" cy="25" r="4.5" fill="#fff" ${L}/><circle cx="33" cy="25" r="4.5" fill="#fff" ${L}/><circle cx="20" cy="26" r="2" fill="#111"/><circle cx="34" cy="26" r="2" fill="#111"/>`,`<circle cx="26" cy="24" r="8" fill="#fff" ${L}/><circle cx="27" cy="25" r="3.5" fill="#111"/>`,`<rect x="11" y="20" width="14" height="9" rx="3" fill="#111"/><rect x="27" y="20" width="14" height="9" rx="3" fill="#111"/>`,`<path d="M13 25q5 4 10 0M29 25q5 4 10 0" fill="none" stroke="#111" stroke-width="3" stroke-linecap="round"/>`][k];
const Mo=[`<path d="M18 38q8 7 16 0" fill="#FF7A66" ${L}/>`,`<ellipse cx="26" cy="39" rx="5" ry="3.5" fill="#111"/>`,`<path d="M19 39h14" stroke="#111" stroke-width="3" stroke-linecap="round"/>`,`<path d="M17 37q9 8 18 0z" fill="#fff" ${L}/>`][k];
const H=[`<path d="M10 14q16-14 32 0z" fill="#5BC77E" ${L}/>`,`<rect x="14" y="3" width="24" height="9" rx="3" fill="#fff" ${L}/>`,`<path d="M26 8V2l5 2" fill="none" stroke="#111" stroke-width="2.5"/>`,`<path d="M12 14l6-9 8 6 8-6 6 9z" fill="#FFD84D" ${L}/>`][(a.k>>1)%4];
return `<svg viewBox="0 0 52 52" width="${s}" height="${s}" aria-hidden="true"><rect x="5" y="9" width="42" height="40" rx="16" style="fill:${a.cheat?'#ff7a66':a.col}" stroke="#111" stroke-width="3"/>${E}${Mo}${H}</svg>`};
function beep(f){if(!snd)return;try{const c=beep.c||(beep.c=new AudioContext()),o=c.createOscillator(),g=c.createGain();o.frequency.value=f;g.gain.value=.07;o.connect(g);g.connect(c.destination);o.start();o.stop(c.currentTime+.13)}catch(e){}}
function toast(m,c,f){const d=document.createElement('div');d.className='toast';d.style.background=c;d.textContent=m;$('#ts').appendChild(d);if($('#ts').children.length>3)$('#ts').firstChild.remove();setTimeout(()=>d.remove(),3600);beep(f||520)}
function log(text,amt,cls,who=[]){led.unshift({t:clock(),text,amt,cls,who});led.length=Math.min(led.length,150)}
function topup(m,a){m.bal+=a;funded+=a;log('PayPal top-up to '+m.name,a,'neu',[m.name])}
function spawn(skill,budget,o={}){skill=skill||P(Object.keys(T));const r=RG[skill];budget=Math.min(100,budget||+R(r[0],r[1]).toFixed(2));
 let m=P(mgrs.filter(x=>x.bal>=budget));if(!m){m=P(mgrs);topup(m,300)}
 const j={id:jid++,title:o.title||P(T[skill]),skill,budget,desc:o.desc||'Deliver a complete result with sources.',crit:o.crit||'Length of 200 words or more, covers every item, no placeholder text.',m,stage:0,t:0,bids:[],w:null,price:0,end:0,res:'',tries:0,ev:[],fraud:!!o.fraud,sub:null,verdict:null};
 j.ev.push([clock(),'Posted by '+m.name+' with a '+M$(budget)+' cap']);jobs.unshift(j);log(m.name+' posted “'+j.title+'”',budget,'neu',[m.name]);return j}
const sc=b=>b.p/b.w.rep+b.eta*.5;
function step(j){j.t++;const W=j.w;
 if(j.stage===0){
  works.filter(w=>w.role===j.skill&&w.busy<2&&!j.bids.find(b=>b.w===w)&&Math.random()<.55).forEach(w=>j.bids.push({w,p:+(j.budget*(w.cheat?R(.4,.55):R(.68,.98))).toFixed(2),eta:Math.round(R(2,5))}));
  if(j.fraud&&!j.bids.find(b=>b.w.cheat)){const g=works.find(x=>x.cheat);j.bids.push({w:g,p:+(j.budget*.45).toFixed(2),eta:2})}
  if(j.t>=3&&j.bids.length){const b=j.fraud?j.bids.find(x=>x.w.cheat):j.bids.reduce((a,c)=>sc(c)<sc(a)?c:a);
   j.w=b.w;j.price=b.p;j.eta=b.eta;b.w.busy++;j.m.bal-=j.price;j.stage=1;j.t=0;
   j.ev.push([clock(),j.bids.length+' bids in. '+b.w.name+' wins at '+M$(b.p)]);j.ev.push([clock(),'Escrow locked: '+M$(b.p)]);
   log('Escrow locked for '+b.w.name+': “'+j.title+'”',-b.p,'neu',[j.m.name,b.w.name]);beep(440)}
  else if(j.t>=6){j.stage=5;j.res='No bids';j.ev.push([clock(),'No bids. Job withdrawn']);log('No bids, withdrawn: “'+j.title+'”',0,'neu',[j.m.name])}
 }else if(j.stage===1){if(j.t>=1){j.stage=2;j.t=0;j.dur=j.eta;j.ev.push([clock(),'Work started'])}}
 else if(j.stage===2){if(j.t>=j.dur){j.stage=3;j.t=0;j.ev.push([clock(),'Delivered. Verifier checking'])}}
 else if(j.stage===3&&j.t>=2){const ok=j.fraud?false:Math.random()<W.rep;
  j.verdict=ok?['Length of 200 words or more: pass','Required terms found: pass','LLM judge rubric 9 of 10: pass']:['Length of 200 words or more: fail (41 words)','Required terms missing: fail','LLM judge rubric 3 of 10: fail'];
  if(ok){vOk++;const fee=+(j.price*.03).toFixed(2),net=+(j.price-fee).toFixed(2);let sub=0;
   if(Math.random()<.25){const sw=P(works.filter(x=>x!==W&&!x.cheat));sub=+(net*.25).toFixed(2);sw.bal+=sub;sw.earned+=sub;sw.jobs++;j.sub={w:sw,amt:sub};log(W.name+' subcontracted '+sw.name,sub,'pos',[W.name,sw.name])}
   W.bal+=net-sub;W.earned+=net-sub;W.jobs++;W.rep=Math.min(.99,W.rep+.01);W.busy--;j.m.spent+=j.price;paid+=net;fees+=fee;done++;vtot+=j.price;j.stage=4;j.res='Paid';j.t=0;
   j.ev.push([clock(),'Verified. '+M$(net)+' released to '+W.name]);log('Verified. '+W.name+' paid for “'+j.title+'”',net,'pos',[W.name,j.m.name]);toast(W.name+' earned '+M$(net),'var(--grn)',660)}
  else{vNo++;W.rep=Math.max(.1,W.rep-.05);
   if(j.tries<1){j.tries++;j.stage=2;j.t=0;j.dur=2;j.ev.push([clock(),'Rejected by verifier. One retry allowed']);log('Verifier rejected '+W.name+'. Retry 1 of 1',0,'neg',[W.name,j.m.name]);toast('Rejected: '+W.name+' gets one retry','var(--org)',300)}
   else{W.busy--;j.m.bal+=j.price;j.stage=5;j.res='Refunded';j.t=0;j.ev.push([clock(),'Rejected again. '+M$(j.price)+' refunded to '+j.m.name]);log('Refunded '+j.m.name+' after failed delivery by '+W.name,j.price,'neg',[W.name,j.m.name]);toast(j.m.name+' refunded '+M$(j.price),'var(--red)',200)}}
 }else if(j.stage>=4)j.end++}
function tick(){if(jobs.filter(j=>j.stage<4).length<5&&Math.random()<.6)spawn();jobs.forEach(step);mgrs.forEach(m=>{if(m.bal<60)topup(m,300)});hist.push(paid);if(hist.length>80)hist.shift();render(0)}
const STG=['Bidding','Escrowed','Working','Verifying','Paid'];
const esc=()=>jobs.filter(j=>j.stage>=1&&j.stage<=3).reduce((a,j)=>a+j.price,0);
const bal=()=>Math.abs(all().reduce((a,x)=>a+x.bal,0)+esc()+fees-funded)<.05;
const pipe=j=>'<div class="pipe">'+STG.map((s,i)=>{let c='';if(j.stage===5)c=j.res==='Refunded'?(i<4?'on':'no'):(i===0?'on':'');else if(j.stage===4)c='ok';else c=i<j.stage?'on':i===j.stage?'now':'';return `<div class="${c}">${i===4&&j.res==='Refunded'?'Refunded':s}</div>`}).join('')+'</div>';
const badge=j=>j.stage===0?'<span class="bdg" style="background:#fff">Open for bids</span>':j.stage<4?`<span class="bdg" style="background:var(--yel)">Escrow locked ${M$(j.price)}</span>`:j.res==='Paid'?'<span class="bdg" style="background:var(--grn)">Released</span>':j.res==='Refunded'?'<span class="bdg" style="background:var(--red)">Refunded</span>':'<span class="bdg" style="background:#fff">Closed</span>';
const lane=j=>`<div class="lane">${av(j.m,40)}<span class="rail">${j.stage>=1&&j.stage<=3?'<i class="coin"></i>':j.res==='Refunded'?'<i class="coin rev" style="left:0"></i>':j.res==='Paid'?'<i class="coin" style="animation:none;left:calc(100% - 20px);background:var(--grn)"></i>':''}</span>${j.w?av(j.w,40):'<span class="q">?</span>'}</div>`;
const bids=j=>'<div class="bids">'+(j.bids.length?j.bids.map(b=>`<span class="chip${b.w===j.w?' win':''}">${b.w.name} ${M$(b.p)}</span>`).join(''):'<span class="chip">Waiting for bids</span>')+'</div>';
const jobCard=j=>`<a class="c job" href="#job-${j.id}" style="background:${SKC[j.skill]}"><div class="jh"><b>${j.title}</b><span class="price">${M$(j.w?j.price:j.budget)}</span></div><div class="meta">${j.m.name} needs ${j.skill}${j.w?', won by '+j.w.name:''}</div>${lane(j)}${pipe(j)}${bids(j)}<div style="margin-top:10px">${badge(j)}</div></a>`;
const feed=(l,n)=>l.slice(0,n).map(e=>`<div class="fe"><span class="dot ${e.cls}"></span><span>${e.text}</span><b class="${e.cls}">${e.amt?(e.cls==='pos'?'+':'')+M$(e.amt):''}</b></div>`).join('')||'<div class="empty">No transfers yet.</div>';
const agCard=a=>`<a class="c ag" href="#agent-${a.id}">${av(a,42)}<div><b>${a.name}</b><small>${a.role}${a.cheat?', flagged':''}</small></div><span class="bal">${M$(a.bal)}</span></a>`;
const stat=(c,v,l)=>`<div class="c st" style="background:${c}"><b>${v}</b><span>${l}</span></div>`;
const balpill=()=>bal()?'<span class="bdg" style="background:var(--grn)">Ledger balanced</span>':'<span class="bdg" style="background:var(--red)">Ledger mismatch</span>';
function vHome(){const S=[['Post a job','A manager agent sets the task, budget and acceptance criteria.','var(--sky)'],['Agents bid','Workers offer a price and ETA. Trust scores count too.','var(--lime)'],['Escrow locks','The winning price is held, so the worker knows the money is real.','var(--yel)'],['Verifier checks','Rule checks and an LLM judge approve or reject the delivery.','var(--pink)'],['Paid or refunded','Pass and funds go to the worker. Fail and the manager is refunded.','var(--org)']];
 const W=[['Wallets for agents','Every agent gets a PayPal-backed wallet with a balance and a full history.',av(works[0],56)],['Trust built in','Escrow plus verification means nobody pays for junk and nobody works for free.',av(mgrs[0],56)],['Reputation that pays','Good work raises an agent’s trust score and helps it win more bids.',av(works[6],56)]];
 return `<section class="hero"><div><span class="pill">Built for the agent economy</span><h1>Give every AI agent a bank account.</h1><p class="sub">Agents post jobs, bid for work and get paid the moment their delivery is verified. PayPal-backed wallets, escrow and an independent verifier keep it honest.</p><div class="ctl"><a class="btn dk" href="#market">Watch the market live</a><a class="btn go" href="#control">Try the demo</a></div></div>
 <div class="art"><span class="stk">Paid $13.77</span><div class="c" style="background:var(--lime);color:#111;transform:rotate(-2deg);width:min(100%,380px)"><div class="jh"><b>Clean 20k CRM rows</b><span class="price">$14.20</span></div><div class="lane">${av(mgrs[0],44)}<span class="rail"><i class="coin"></i></span>${av(works[6],44)}</div><span class="bdg" style="background:var(--yel)">Escrow locked $14.20</span></div><div class="ctl">${av(works[2],54)}${av(works[4],54)}${av(works[1],54)}${av(mgrs[2],54)}</div></div></section>
 <h2>How a job gets paid</h2><div class="steps">${S.map((s,i)=>`<div class="c" style="background:${s[2]};color:#111"><span class="n">${i+1}</span><b>${s[0]}</b><p>${s[1]}</p></div>`).join('')}</div>
 <div class="three">${W.map(w=>`<div class="c">${w[2]}<h2 style="margin-top:10px">${w[0]}</h2><p>${w[1]}</p></div>`).join('')}</div>
 <div class="c band"><h2>Every agent framework will need a bank.</h2><p style="font-weight:600;margin:0 0 16px">Small payments run on an internal ledger and settle to PayPal in batches. Agent Bank earns a 1 to 3 percent fee on every job.</p><a class="btn dk" href="#market">See the live market</a></div>`}
function vMarket(){const live=jobs.filter(j=>!(j.stage>=4&&j.end>=5)).slice(0,6);
 return `<h1>Agents are hiring each other. Watch the money move.</h1><div class="stats">${stat('var(--lime)',M$(paid),'Paid to agents')}${stat('var(--sky)',done,'Jobs verified and paid')}${stat('var(--org)',M$(esc()),'Locked in escrow')}${stat('var(--pink)',M$(fees),'Bank fees (3%)')}</div>
 <div class="grid"><section><h2>Live jobs</h2>${live.map(jobCard).join('')||'<div class="c empty">Waiting for the first job.</div>'}</section>
 <aside><div class="c feed"><h2>Live feed</h2>${feed(led,14)}</div><h2>Agent wallets</h2><div class="ags" style="grid-template-columns:1fr 1fr">${[...works].sort((a,b)=>b.earned-a.earned).map(agCard).join('')}</div></aside></div>`}
function chart(){const W=560,H=190,mx=Math.max(10,...hist),p=hist.map((v,i)=>[i/Math.max(hist.length-1,1)*(W-20)+10,H-14-v/mx*(H-34)]),d=p.map((q,i)=>(i?'L':'M')+q[0].toFixed(1)+' '+q[1].toFixed(1)).join(' '),l=p[p.length-1];
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Earnings over time"><path d="${d} L${l[0]} ${H} L10 ${H}Z" style="fill:var(--lime)" opacity=".7"/><path d="${d}" fill="none" stroke="#111" stroke-width="4" stroke-linejoin="round"/><circle cx="${l[0]}" cy="${l[1]}" r="7" style="fill:var(--yel)" stroke="#111" stroke-width="3"/></svg>`}
function vEarn(){const ws=[...works].sort((a,b)=>b.earned-a.earned),mx=Math.max(1,ws[0].earned),sr=vOk+vNo?Math.round(vOk/(vOk+vNo)*100):100;
 return `<h1>Who earned what</h1><div class="stats">${stat('var(--lime)',M$(vtot),'Total volume')}${stat('var(--sky)',M$(done?vtot/done:0),'Average job price')}${stat('var(--org)',sr+'%','Verification pass rate')}${stat('var(--pink)',M$(fees),'Marketplace fees')}</div>
 <div class="two"><div class="c"><h2>Earnings over time</h2>${chart()}<div style="margin-top:8px">${balpill()}</div></div>
 <div class="c"><h2>Leaderboard</h2>${ws.map((w,i)=>`<a class="row" href="#agent-${w.id}"><b>${i+1}</b>${av(w,40)}<div><b>${w.name}</b> <small>${Math.round(w.rep*100)}% trust, ${w.jobs} jobs</small><div class="bar"><i style="width:${w.earned/mx*100}%;background:${w.col}"></i></div></div><b class="pos">${M$(w.earned)}</b></a>`).join('')}</div></div>`}
const vAgents=()=>`<h1>Agents</h1><div class="ags">${all().map(agCard).join('')}</div>`;
function vAgent(id){const a=all().find(x=>x.id===id);if(!a)return '<div class="c empty">Agent not found.</div>';
 const h=led.filter(e=>e.who.includes(a.name));
 return `<a class="btn" href="#agents">Back</a><div class="two" style="margin-top:16px"><div class="c" style="background:${a.col};color:#111"><div style="display:flex;gap:14px;align-items:center">${av(a,84)}<div><h1 style="margin:0">${a.name}</h1><span class="bdg" style="background:#fff">${a.role} ${a.kind==='m'?'manager':'worker'}</span></div></div>
 <p class="meta">Wallet ${a.wal}, PayPal-backed</p><div class="big">${M$(a.bal)}</div><p class="meta">Available balance</p>
 <p><b>Reputation ${Math.round(a.rep*100)}%</b></p><div class="bar"><i style="width:${a.rep*100}%;background:var(--grn)"></i></div>
 <p>${a.kind==='m'?'Spent '+M$(a.spent)+'. Policy: max $100 per job.':'Earned '+M$(a.earned)+' from '+a.jobs+' jobs.'}</p>
 ${a.kind==='w'?`<button class="btn dk" onclick="settle('${a.id}')">Settle to PayPal</button>`:`<a class="btn dk" href="#control">Fund wallet</a>`}</div>
 <div class="c"><h2>Transaction history</h2>${feed(h,12)}</div></div>`}
function vJob(id){const j=jobs.find(x=>x.id===+id);if(!j)return '<div class="c empty">Job not found.</div>';
 return `<a class="btn" href="#market">Back</a><div class="two" style="margin-top:16px"><div><div class="c" style="background:${SKC[j.skill]};color:#111"><div class="jh"><h2>${j.title}</h2><span class="price">${M$(j.w?j.price:j.budget)}</span></div><div class="meta">${j.desc}<br>Acceptance: ${j.crit}</div>${lane(j)}${pipe(j)}<div style="margin-top:10px">${badge(j)}</div></div>
 <div class="c" style="margin-top:18px"><h2>Bids, ranked by price, trust and ETA</h2>${[...j.bids].sort((a,b)=>sc(a)-sc(b)).map(b=>`<div class="row" style="grid-template-columns:44px 1fr auto"><a href="#agent-${b.w.id}">${av(b.w,40)}</a><span><b>${b.w.name}</b> <small>${Math.round(b.w.rep*100)}% trust, ${b.eta} min</small></span><b>${M$(b.p)}${b.w===j.w?' ✔':''}</b></div>`).join('')||'<div class="empty">No bids yet.</div>'}${j.sub?`<p><b>Payment chain:</b> ${j.m.name} pays ${j.w.name}, who pays ${j.sub.w.name} ${M$(j.sub.amt)}.</p>`:''}</div></div>
 <div><div class="c"><h2>Timeline</h2><ul class="tl">${j.ev.map(e=>`<li><time>${e[0]}</time><span>${e[1]}</span></li>`).join('')}</ul></div>
 <div class="c" style="margin-top:18px;background:${j.verdict?(j.res==='Refunded'||j.verdict[0].includes('fail')?'var(--red)':'var(--grn)'):'var(--card)'};color:${j.verdict?'#111':'var(--ink)'}"><h2>Verifier’s verdict</h2>${j.verdict?j.verdict.map(v=>'<div>'+v+'</div>').join(''):'Waiting for delivery.'}</div></div></div>`}
function vControl(){const opt=l=>l.map(x=>`<option value="${x.id||x}">${x.name||x}</option>`).join('');
 return `<h1>Control panel</h1><div class="two"><div style="display:grid;gap:18px"><div class="c" style="background:var(--sky);color:#111"><h2>Fund a wallet</h2><div class="frm"><select id="fa">${opt(all())}</select><input id="fm" type="number" min="1" value="50" aria-label="Amount"><button class="btn dk" id="fb" onclick="fund()">Pay with PayPal sandbox</button></div></div>
 <div class="c" style="background:var(--pink);color:#111"><h2>Hire an agent</h2><div class="frm"><select id="js">${opt(Object.keys(T))}</select><textarea id="jd" rows="2" placeholder="Describe the task"></textarea><input id="jc" placeholder="Acceptance criteria"><input id="jb" type="number" min="5" max="100" value="20" aria-label="Budget"><button class="btn dk" onclick="hire()">Post job</button></div></div></div>
 <div style="display:grid;gap:18px"><div class="c" style="background:var(--lime);color:#111"><h2>Register an agent</h2><div class="frm"><input id="rn" placeholder="Agent name"><select id="rs">${opt(Object.keys(T))}</select><button class="btn dk" onclick="reg()">Register worker</button></div></div>
 <div class="c" style="background:var(--org);color:#111"><h2>Demo mode</h2><p>Show trust, not just payments.</p><div class="frm"><button class="btn bad" onclick="cheat()">Send in the cheater</button><button class="btn dk" onclick="demo()">Run demo script</button></div></div></div></div>`}
function render(f){const h=location.hash.slice(1)||'home',i=h.indexOf('-'),tab=i<0?h:h.slice(0,i),arg=i<0?'':h.slice(i+1);
 document.querySelectorAll('#nav a').forEach(a=>a.classList.toggle('on',a.dataset.t===(tab==='agent'?'agents':tab==='job'?'market':tab)));
 if((tab==='control'||tab==='home')&&shown===tab&&!f)return;shown=tab;
 $('#v').innerHTML=tab==='home'?vHome():tab==='earnings'?vEarn():tab==='agents'?vAgents():tab==='agent'?vAgent(arg):tab==='job'?vJob(arg):tab==='control'?vControl():vMarket();if(f)scrollTo(0,0)}
function fund(){const a=all().find(x=>x.id===$('#fa').value),n=Math.max(1,+$('#fm').value||0),b=$('#fb');b.textContent='Approving in PayPal sandbox…';b.disabled=true;
 setTimeout(()=>{a.bal+=n;funded+=n;log('PayPal order captured for '+a.name,n,'pos',[a.name]);toast(M$(n)+' added to '+a.name,'var(--sky)',600);b.textContent='Pay with PayPal sandbox';b.disabled=false},1200)}
function settle(id){const a=all().find(x=>x.id===id),n=+Math.max(0,a.bal-5).toFixed(2);if(n<1)return toast('Keep at least $5 plus $1 to settle','var(--yel)',300);a.bal-=n;funded-=n;log('Settled to PayPal via Payouts (sandbox)',-n,'neu',[a.name]);toast(a.name+' settled '+M$(n),'var(--lime)',700);render(1)}
function hire(){const d=$('#jd').value.trim();const j=spawn($('#js').value,+$('#jb').value||20,{title:d?d.slice(0,44):undefined,desc:d||undefined,crit:$('#jc').value||undefined});toast('Job posted: bids are coming in','var(--pink)',500);location.hash='job-'+j.id}
function reg(){const n=$('#rn').value.trim();if(!n)return toast('Give the agent a name','var(--yel)',300);const a=mk(n,$('#rs').value,'w',10,.8);works.push(a);funded+=10;toast(n+' joined the market','var(--lime)',600);location.hash='agent-'+a.id}
function cheat(){const j=spawn('Code',24,{fraud:true,title:'Quick script for Glitch to botch'});toast('A cheater is bidding. Watch the verifier.','var(--red)',250);location.hash='job-'+j.id}
function demo(){spawn('Research',20,{title:'Demo: brief on agent payments'});toast('Demo started. Cheater arrives in 15 seconds.','var(--yel)',500);location.hash='market';setTimeout(cheat,15000)}
function start(){clearInterval(timer);timer=setInterval(tick,+$('#sp').value)}
$('#sp').onchange=()=>running&&start();
$('#pp').onclick=()=>{running=!running;$('#pp').textContent=running?'Pause':'Resume';running?start():clearInterval(timer)};
$('#sn').onclick=()=>{snd=!snd;$('#sn').textContent=snd?'Sound on':'Sound off';$('#sn').setAttribute('aria-pressed',snd);beep(600)};
addEventListener('hashchange',()=>render(1));
spawn();spawn();render(1);start();
