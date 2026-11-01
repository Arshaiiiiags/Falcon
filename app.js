import {hokmTable} from './hokm.js';
import {icon} from './icons.js';
import {partyHome,partyRoom,partyStage,partyMembers,partyLog} from './party.js';
import {translate,messages} from './i18n.js';
import {escapeHTML as esc,backgammonBoard,pasurBoard} from './games.js';
const read=(key,fallback)=>{try{return localStorage.getItem(key)||fallback;}catch{return fallback;}};
const write=(key,value)=>{try{localStorage.setItem(key,value);}catch{}};
const themes=['royal-gold','midnight-purple','persian-turquoise','dark-minimal','light-ivory'];
const themeKeys=['royalGold','purple','turquoise','dark','ivory'];
const S={lang:read('pgc_lang','fa'),theme:read('pgc_theme','royal-gold'),user:null,csrf:'',view:'lounge',history:[],achievements:[],ranking:[],busy:false,menu:false,game:null,gameType:null,selected:null,pasur:{card:null,capture:[]},hokmCard:null,historyGame:'',historyStatus:'',hasMore:false,rankGame:'backgammon',rankLevel:'medium',offline:!navigator.onLine,installPrompt:null,startIntent:null};
S.party={list:[],id:null,cur:null,after:0,msgs:[],game:null,gameVersion:-1,draft:'',chatFocus:false,polling:false,sending:false,html:{}};
if(!['fa','en'].includes(S.lang))S.lang='fa';
if(!themes.includes(S.theme))S.theme='royal-gold';
const t=(key,vars)=>translate(S.lang,key,vars);
const num=n=>new Intl.NumberFormat(S.lang==='fa'?'fa-IR':'en-US').format(n);
const date=value=>value?new Intl.DateTimeFormat(S.lang==='fa'?'fa-IR':'en-GB',{month:'short',day:'numeric',year:'numeric'}).format(new Date(value)):t('none');
const $=selector=>document.querySelector(selector);
const modal=$('#modal');
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),6500);}
class APIError extends Error{constructor(code,status){super(code);this.code=code;this.status=status;}}
async function api(path,{method='GET',data}={}){
 let response;
 try{response=await fetch('/api'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json',...(method!=='GET'?{'X-CSRF-Token':S.csrf}:{})},...(data!==undefined?{body:JSON.stringify(data)}:{})});}catch{S.offline=true;throw new APIError('network_error',0);}
 let body;try{body=await response.json();}catch{throw new APIError('server_error',response.status);}
 S.offline=false;
 if(body.csrf)S.csrf=body.csrf;
 if(body.token)S.csrf=body.token;
 if(!response.ok)throw new APIError(body.error||'server_error',response.status);
 return body;
}
function busy(value){S.busy=value;$('.page-area')?.classList.toggle('busy',value);$('#main')?.setAttribute('aria-busy',String(value));document.querySelectorAll('#modal button[type=submit]').forEach(b=>b.disabled=value);$('#busy-indicator')?.remove();if(value){const node=document.createElement('div');node.id='busy-indicator';node.className='busy-overlay';node.setAttribute('role','status');node.innerHTML=`<span class="spinner"></span>${t('loading')}`;document.body.append(node);}}
async function task(fn){if(S.busy)return;busy(true);try{await fn();}catch(error){
 if(['state_conflict','invalid_state'].includes(error.code)){try{if(S.view==='party'&&S.party.id){S.party.gameVersion=-1;await partyPoll();}else if(S.game)await refreshGame();}catch{}}
 if(error.code==='auth_required'){S.user=null;S.game=null;S.view='lounge';showAuth('login');}
 const message=messages[S.lang][error.code]?t(error.code):t('error');
 if(modal.open&&modal.querySelector('.form-error'))modal.querySelector('.form-error').textContent=message;
 toast(message);
 }finally{busy(false);render();}}
function applyAppearance(){document.documentElement.lang=S.lang;document.documentElement.dir=S.lang==='fa'?'rtl':'ltr';document.documentElement.dataset.theme=S.theme;write('pgc_lang',S.lang);write('pgc_theme',S.theme);document.title=t('brand')+' · Persian Game Club';}
async function dashboard(){const me=await api('/me');S.user=me.user;if(S.user){await loadHistory();S.achievements=(await api('/achievements')).achievements;}else{S.history=[];S.achievements=[];}}
async function loadHistory(append=false){const q=new URLSearchParams({limit:'20',offset:String(append?S.history.length:0)});if(S.historyGame)q.set('game',S.historyGame);if(S.historyStatus)q.set('status',S.historyStatus);const j=await api('/matches?'+q);S.history=append?[...S.history,...j.matches]:j.matches;S.hasMore=j.pagination.has_more;}
async function loadRankings(){S.ranking=(await api('/leaderboard?'+new URLSearchParams({game:S.rankGame,level:S.rankLevel}))).leaderboard;}
function nav(view,label){return `<button class="nav-item ${S.view===view?'active':''}" data-action="navigate" data-view="${view}" ${S.view===view?'aria-current="page"':''}>${icon(view==='party'?'users':view==='rules'?'book':view==='rankings'?'trophy':view==='settings'?'settings':view==='history'?'history':'lounge')}<span>${t(label)}</span></button>`;}
function render(){
 S.party.html={}; const chat=$('#chat-input');if(chat){S.party.draft=chat.value;S.party.chatFocus=document.activeElement===chat;}
 const focused=document.activeElement;
 const focusData=focused?.closest('[data-action],[data-filter]')?.dataset;
 const restoreFocus=focusData?JSON.stringify({...focusData}):null;
 applyAppearance();const user=S.user;
 $('#shell').innerHTML=`${S.offline?`<div class="offline-banner" role="status">${t('offline')}</div>`:''}<div class="app-layout"><div class="mobile-backdrop ${S.menu?'open':''}" data-action="menu-close"></div><aside class="sidebar ${S.menu?'open':''}"><button class="brand" data-action="navigate" data-view="lounge"><img src="/icon.svg" alt="" width="43" height="43"><span><strong>${t('brand')}</strong><small>${t('brandSub')}</small></span></button><div class="nav-label">${t('explore')}</div><nav aria-label="${t('explore')}">${nav('lounge','lounge')}${nav('party','groups')}${nav('history','history')}${nav('rankings','rankings')}${nav('rules','rules')}<div class="nav-label">${t('account')}</div>${nav('settings','settings')}</nav><div class="sidebar-bottom"><div class="sidebar-help">${icon('shield')}<span>${t('safeCopy')}</span></div><div class="profile-mini"><div class="avatar">${user?esc(user.username.slice(0,1).toUpperCase()):icon('user')}</div><div><strong>${user?esc(user.username):t('guestTitle')}</strong><span>${user?t('single').split('·')[0]:t('signup')}</span></div><button data-action="${user?'logout':'login'}" aria-label="${t(user?'logout':'login')}">${icon(user?'logout':'chevron')}</button></div></div></aside><div class="page-area ${S.busy?'busy':''}"><header class="topbar"><div class="breadcrumb"><button class="icon-button mobile-menu" data-action="menu" aria-label="${t('explore')}" aria-expanded="${S.menu}">${icon('menu')}</button><span>${t('brand')}</span>${icon('chevron','directional')}<b>${t(S.view==='game'?S.gameType:S.view==='rules'?'rules':S.view)}</b></div><div class="top-actions"><button class="lang-button" data-action="language" aria-label="${S.lang==='fa'?'EN — Switch to English':'فا — تغییر به فارسی'}">${S.lang==='fa'?'EN':'فا'}</button><button class="icon-button theme-toggle" data-action="theme-cycle" aria-label="${t('appearance')}">${icon('sun')}</button><span class="top-divider"></span>${user?`<span class="balance" title="${t('yourBalance')}">${icon('coin')}${num(user.coins)}</span><div class="avatar" aria-label="${esc(user.username)}">${esc(user.username.slice(0,1).toUpperCase())}</div>`:`<button class="button primary" data-action="login">${t('login')}</button>`}</div></header><main id="main" tabindex="-1" aria-busy="${S.busy}">${content()}</main></div></div>`;
 if(restoreFocus&&!modal.open){const target=[...document.querySelectorAll('[data-action],[data-filter]')].find(el=>JSON.stringify({...el.dataset})===restoreFocus);target?.focus({preventScroll:true});}
 if(S.party.chatFocus&&$('#chat-input')){$('#chat-input').focus({preventScroll:true});}
 scrollLog(true);
}
function heading(title,copy=''){return `<div class="page-heading"><div><h1>${esc(title)}</h1>${copy?`<p>${esc(copy)}</p>`:''}</div><span class="date-chip">${date(new Date().toISOString())}</span></div>`;}
function content(){let html='';switch(S.view){case'game':return gameView();case'party':html=partyView();break;case'history':html=historyView();break;case'rankings':html=rankingsView();break;case'rules':html=rulesView();break;case'settings':html=settingsView();break;default:html=loungeView();}return html+`<footer class="footer"><span><img src="/icon.svg" alt="">${t('footer')}</span><span>${icon('shield')}${t('safeCopy')}</span></footer>`;}
function joinPanel(){return `<div class="join-panel"><span>${icon('user')}</span><div><h3>${t('guestTitle')}</h3><p>${t('guestCopy')}</p></div><button class="button primary" data-action="signup">${t('signup')} ${icon('arrow','directional')}</button></div>`;}
function loungeView(){
 const u=S.user;
 return `${heading(u?t('welcomeUser',{name:u.username}):t('welcome'),t('intro'))}
 <section id="collection" aria-label="${t('gamesTitle')}">
  <div class="section-head"><h2>${t('gamesTitle')}</h2><span class="collection-tag">${t('single')}</span></div>
  <div class="game-grid">${gameCard('hokm')}${gameCard('backgammon')}${gameCard('pasur')}</div>
 </section>
 ${u?`<div class="stats-strip" aria-label="${t('account')}">${stat('coin',u.coins,'yourBalance')}${stat('dice',u.total.played,'played')}${stat('trophy',u.total.won,'won')}</div>`:''}
 <section class="recent-section"><div class="section-head"><h2>${t('recent')}</h2>${u?`<button class="text-button" data-action="navigate" data-view="history">${t('seeAll')}${icon('arrow','directional')}</button>`:''}</div>${u?S.history.length?matchesTable(S.history.slice(0,3)):`<div class="empty-state"><h3>${t('noMatches')}</h3><p>${t('noMatchesCopy')}</p></div>`:joinPanel()}</section>
 <section class="learn-strip"><div><h2>${t('learnTitle')}</h2><p>${t('learnCopy')}</p></div><button class="button" data-action="navigate" data-view="rules">${icon('book')}${t('learn')}</button></section>`;
}
function stat(symbol,value,label){return `<div class="stat"><div class="stat-symbol">${icon(symbol)}</div><div><b>${typeof value==='number'?num(value):value}</b><small>${t(label)}</small></div></div>`;}
function gameCard(game){return `<article class="game-card"><div class="game-image ${game==='backgammon'?'bg-image':game==='hokm'?'hokm-cover':''}">${game==='backgammon'?'<img src="/club-art.png" alt="" width="600" height="330" loading="lazy">':game==='hokm'?'<div class="cover-fan hokm-cover-fan" aria-hidden="true"><img src="/card-SA.webp" alt="" width="320" height="448"><img src="/card-HA.webp" alt="" width="320" height="448"><img src="/card-CA.webp" alt="" width="320" height="448"><img src="/card-DA.webp" alt="" width="320" height="448"></div>':'<div class="cover-fan" aria-hidden="true"><img src="/card-SK.webp" alt="" width="320" height="448"><img src="/card-HQ.webp" alt="" width="320" height="448"><img src="/card-DA.webp" alt="" width="320" height="448"></div>'}<span class="image-tag">${icon(game==='backgammon'?'dice':'cards')}${t(game==='backgammon'?'strategy':game==='hokm'?'hokmTeams':'cards')}</span></div><div class="game-card-body"><div class="game-card-title"><h3>${t(game)}</h3><span>${t(game+'Fa')}</span></div><p>${t(game==='backgammon'?'bgDesc':game==='hokm'?'hokmDesc':'pasurDesc')}</p><div class="game-meta"><span>${icon('coin')}${t('fee')}</span><span>${icon('user')}${t(game==='hokm'?'hokmThreeAI':'levels')}</span></div><button class="button primary" data-action="setup" data-game="${game}"><span>${t('playGame',{game:t(game)})}</span>${icon('arrow','directional')}</button></div></article>`;}
function matchesTable(matches){return `<div class="panel table-wrap" role="region" aria-label="${t('history')}" tabindex="0"><table><thead><tr><th>${t('match')}</th><th>${t('date')}</th><th>${t('status')}</th><th>${t('result')}</th><th>${t('score')}</th><th><span class="sr-only">${t('resume')}</span></th></tr></thead><tbody>${matches.map(m=>`<tr><td><span class="table-game">${icon(m.game==='backgammon'?'dice':'cards')}${t(m.game)} <small class="muted">#${num(m.id)}</small></span></td><td>${date(m.created_at)}</td><td><span class="badge">${t(m.status)}</span></td><td><span class="${m.result==='loss'?'badge loss':''}">${t(m.result||'none')}</span></td><td dir="ltr">${esc(m.score||'—')}</td><td>${['active','pending'].includes(m.status)?`<div class="button-row"><button class="text-button" data-action="resume" data-mid="${m.id}">${t('resume')}${icon('arrow','directional')}</button>${m.status==='pending'?`<button class="text-button" data-action="cancel-match" data-mid="${m.id}">${t('cancelMatch')}</button>`:''}</div>`:['completed','abandoned'].includes(m.status)?`<button class="text-button" data-action="resume" data-mid="${m.id}">${t('match')} ${icon('chevron','directional')}</button>`:''}</td></tr>`).join('')}</tbody></table></div>`;}
function options(values,selected,all=false){return `${all?`<option value="">${t('all')}</option>`:''}${values.map(v=>`<option value="${v}" ${v===selected?'selected':''}>${t(v)}</option>`).join('')}`;}
function historyView(){return heading(t('history'),t('safeCopy'))+(!S.user?joinPanel():`<div class="filters"><label>${t('filterGame')}<select data-filter="historyGame">${options(['backgammon','pasur','hokm'],S.historyGame,true)}</select></label><label>${t('filterStatus')}<select data-filter="historyStatus">${options(['pending','active','completed','cancelled','abandoned'],S.historyStatus,true)}</select></label><button class="button" data-action="refresh">${icon('refresh')}${t('refresh')}</button></div>${S.history.length?matchesTable(S.history):`<div class="empty-state">${icon('history')}<h3>${t('noMatches')}</h3><p>${t('noMatchesCopy')}</p></div>`}${S.hasMore?`<button class="button" style="margin-top:18px" data-action="load-more">${t('loadMore')}</button>`:''}`);}
function rankingsView(){return heading(t('rankings'),t('rankingsCopy'))+(!S.user?joinPanel():`<div class="filters"><label>${t('filterGame')}<select data-filter="rankGame">${options(['backgammon','pasur','hokm'],S.rankGame)}</select></label><label>${t('difficulty')}<select data-filter="rankLevel">${options(['easy','medium','hard'],S.rankLevel)}</select></label><button class="button" data-action="refresh">${icon('refresh')}${t('refresh')}</button></div>${S.ranking.length?`<div class="panel table-wrap" role="region" aria-label="${t('rankings')}" tabindex="0"><table><thead><tr><th>${t('rank')}</th><th>${t('player')}</th><th>${t('played')}</th><th>${t('won')}</th><th>${t('winRate')}</th></tr></thead><tbody>${S.ranking.map(r=>`<tr><td>${r.rank<=3?icon('trophy'):''} ${num(r.rank)}</td><td>${esc(r.username)}</td><td>${num(r.played)}</td><td>${num(r.won)}</td><td>${num(r.win_rate)}%</td></tr>`).join('')}</tbody></table></div>`:`<div class="empty-state">${icon('trophy')}<h3>${t('noRankings')}</h3></div>`}<section class="recent-section"><h2>${t('achievements')}</h2><div class="achievements">${S.achievements.map(a=>`<div class="achievement ${a.earned?'earned':''}">${icon(a.earned?'trophy':'star')}<div><strong>${esc(a[S.lang==='fa'?'name_fa':'name_en'])}</strong><small>${a.earned?t('earned')+' · '+date(a.earned_at):t('locked')}</small></div></div>`).join('')}</div></section>`);}
function settingsView(){return heading(t('settings'))+`<div class="settings-grid"><section class="panel"><h2>${t('appearance')}</h2><div class="themes">${themes.map((theme,i)=>`<button class="theme-swatch ${S.theme===theme?'selected':''}" data-action="theme" data-theme="${theme}" aria-pressed="${S.theme===theme}"><i style="--swatch-a:${['#164c43','#61467b','#16766d','#21322b','#e6d8b9'][i]};--swatch-b:${['#d2b477','#b39063','#c0ba83','#79917c','#725a36'][i]}"></i>${t(themeKeys[i])}</button>`).join('')}</div><label class="form-label" for="language-setting">${t('language')}</label><select id="language-setting" data-filter="language"><option value="fa" ${S.lang==='fa'?'selected':''}>فارسی</option><option value="en" ${S.lang==='en'?'selected':''}>English</option></select><section class="coins-panel"><h3>${t('yourBalance')}: ${S.user?num(S.user.coins):'—'}</h3><p>${t('refillInfo')}</p>${S.user?`<button class="button" data-action="refill" ${S.user.coins>=5?'disabled':''}>${icon('coin')}${t('refill')}</button>`:`<button class="button" data-action="signup">${t('signup')}</button>`}</section></section><section class="panel"><h2>${t('changePassword')}</h2>${S.user?`<form data-form="password" class="settings-form"><label class="form-label" for="current-password">${t('currentPassword')}</label><input id="current-password" name="current" type="password" autocomplete="current-password" required maxlength="128"><label class="form-label" for="new-password">${t('newPassword')}</label><input id="new-password" name="new" type="password" autocomplete="new-password" required minlength="8" maxlength="128"><button class="button primary" type="submit">${t('changePassword')}</button></form>`:`<p class="muted">${t('loginCopy')}</p><button class="button" style="margin-top:18px" data-action="login">${t('login')}</button>`}<div class="coins-panel"><h3>${t('install')}</h3><p>${t('installCopy')}</p>${S.installPrompt?`<button class="button" data-action="install">${icon('download')}${t('installNow')}</button>`:''}</div></section></div>`;}
function rulesView(){return heading(t('rulesTitle'),t('rulesIntro'))+`<div class="rules-grid"><article class="panel rule-panel"><h2>${icon('dice')}${t('backgammon')}</h2><p>${t('bgRules')}</p><p>${t('bgScoring')}</p><button class="button primary" data-action="setup" data-game="backgammon">${t('play')}${icon('arrow','directional')}</button></article><article class="panel rule-panel"><h2>${icon('cards')}${t('pasur')}</h2><p>${t('pasurRules')}</p><p>${t('pasurScoring')}</p><button class="button primary" data-action="setup" data-game="pasur">${t('play')}${icon('arrow','directional')}</button></article><article class="panel rule-panel"><h2>${icon('cards')}${t('hokm')}</h2><p>${t('hokmRules')}</p><p>${t('hokmScoring')}</p><p class="hokm-rule-source"><a href="https://www.jahanshiri.ir/cardgames/en/hokm" target="_blank" rel="noopener noreferrer">${t('hokmRulesSource')}</a></p><button class="button primary" data-action="setup" data-game="hokm">${t('play')}${icon('arrow','directional')}</button></article></div><section class="panel coins-panel"><h2>${icon('coin')}${t('yourBalance')}</h2><p>${t('coinRules')}</p></section>`;}
function gameView(){
 if(S.gameType!=='hokm'||!S.game)return classicGameView();
 const g=S.game,st=g.state,active=g.match_status==='active';
 return `<div class="game-page hokm-page"><div class="game-topline"><div><h1>${t('hokm')}</h1><small>#${num(g.match_id)} · ${t('levelLabel',{level:t(st.level)})} · ${t('hokmThreeAI')}</small></div><button class="text-button" data-action="navigate" data-view="lounge">${icon('arrow','directional')}${t('backClub')}</button></div>${hokmTable(g,S.hokmCard,t,num,S.user?.username||t('you'))}${active?`<div class="game-actions"><button class="text-button" data-action="resign">${t('resign')}</button><button class="text-button" data-action="refresh-game">${icon('refresh')}${t('refresh')}</button></div>`:`<section class="terminal-panel">${icon('trophy')}<h2>${t(g.match_status==='abandoned'?'expired':st.winner===0?'youWon':'youLost')}</h2><p>${t(st.resigned?'gameResigned':'gameOver')}</p><div class="button-row"><button class="button primary" data-action="setup" data-game="hokm">${t('newGame')}</button><button class="button" data-action="navigate" data-view="history">${t('viewHistory')}</button></div></section>`}<p class="game-hint">${icon('shield')} ${t('safeCopy')}</p></div>`;
}
function classicGameView(){if(!S.game)return heading(t('loading'));const g=S.game,st=g.state,isBG=S.gameType==='backgammon',active=g.match_status==='active';const won=st.winner===0,draw=st.draw===true;if(isBG&&active&&S.selected===null&&st.bar[0]>0&&st.legal_moves.some(m=>m.src==='bar'))S.selected='bar';return `<div class="game-page"><div class="game-topline"><div><h1>${t(S.gameType)}</h1><small>#${num(g.match_id)} · ${t('levelLabel',{level:t(st.level)})}</small></div><button class="text-button" data-action="navigate" data-view="lounge">${icon('arrow','directional')}${t('backClub')}</button></div><div class="player-strip"><div class="player-seat"><div class="avatar">${esc(S.user?.username.slice(0,1).toUpperCase()||'')}</div><span><strong>${esc(S.user?.username||t('you'))}</strong><small>${t('you')}</small></span></div>${isBG?`<span class="turn-chip">${t(active?'yourTurn':g.match_status)}</span>`:`<div class="score-display"><span>${num(st.scores[0])}</span><small>:</small><span>${num(st.scores[1])}</span></div>`}<div class="player-seat"><span><strong>${t('opponent')}</strong><small>${!isBG?t('target')+': '+num(st.target_score):t(st.level)}</small></span><div class="avatar ai">${icon('dice')}</div></div></div>${isBG?backgammonBoard(g,S.selected,t,num):pasurBoard(g,S.pasur,t,num)}${active?`<div class="game-actions">${isBG?`<div>${st.must_respond?`<p class="game-hint">${t('doubleOffer',{value:num(st.cube.pending_value)})}</p><div class="button-row"><button class="button primary" data-action="cube-accept">${t('accept')}</button><button class="button" data-action="cube-decline">${t('decline')}</button></div>`:st.can_roll?`<div class="button-row"><button class="button primary" data-action="bg-roll">${icon('dice')}${t('roll')}</button>${st.can_double?`<button class="button" data-action="bg-double">${t('double')}</button>`:''}</div>`:`<p class="game-hint">${t(S.selected!==null?'selectDestination':'selectChecker')}</p>`}</div>`:''}<button class="text-button" data-action="resign">${t('resign')}</button><button class="text-button" data-action="refresh-game">${icon('refresh')}${t('refresh')}</button></div>`:`<section class="terminal-panel">${icon(g.match_status==='abandoned'?'clock':'trophy')}<h2>${t(g.match_status==='abandoned'?'expired':draw?'gameDraw':won?'youWon':'youLost')}</h2><p>${st.resigned?t('gameResigned'):t('gameOver')}</p><div class="button-row"><button class="button primary" data-action="setup" data-game="${S.gameType}">${t('newGame')}</button><button class="button" data-action="navigate" data-view="history">${t('viewHistory')}</button></div></section>`}<p class="game-hint">${icon('shield')} ${t('safeCopy')}</p></div>`;}
function partyView(){
 if(!S.user)return heading(t('ptTitle'),t('ptIntro'))+joinPanel();
 const P=S.party;
 if(P.id&&P.cur)return partyRoom(P,S,t,num);
 return heading(t('ptTitle'),t('ptIntro'))+partyHome(P,t,num);
}
function scrollLog(force=false){const log=$('#party-log');if(!log)return;const near=log.scrollHeight-log.scrollTop-log.clientHeight<80;if(force||near)log.scrollTop=log.scrollHeight;}
async function loadParties(){S.party.list=(await api('/parties')).parties;}
async function openParty(id){const P=S.party;Object.assign(P,{id,cur:null,after:0,msgs:[],game:null,gameVersion:-1,draft:'',html:{}});S.hokmCard=null;S.selected=null;S.pasur={card:null,capture:[]};await partyPoll(true);}
function partyLeaveState(){Object.assign(S.party,{id:null,cur:null,after:0,msgs:[],game:null,gameVersion:-1,draft:'',html:{}});}
// One poll = members + room + new chat lines (+ my game state when it changed). Partial DOM updates keep the chat draft and focus.
async function partyPoll(full=false){
 const P=S.party;if(!P.id||!S.user||P.polling)return;P.polling=true;
 try{
  let j;
  try{j=await api(`/parties/${P.id}?after=${P.after}`);}
  catch(e){if(e.code==='party_not_found'){partyLeaveState();try{await loadParties();}catch{}render();toast(t('party_not_found'));}return;}
  const mineBefore=P.msgs.at(-1)?.id;
  P.cur=j;P.msgs=P.after===0?j.messages:[...P.msgs,...j.messages].slice(-200);
  if(j.messages.length)P.after=j.messages.at(-1).id;
  const r=j.room;
  if(r.my_seat!==null&&r.status!=='lobby'){
   if(P.gameVersion!==r.version){try{const g=await api(`/parties/${P.id}/game`);P.game=g;P.gameVersion=g.version;if(S.hokmCard&&!(g.state.legal_cards||[]).includes(S.hokmCard))S.hokmCard=null;S.selected=null;S.pasur={card:null,capture:[]};if(g.game==='backgammon'&&g.match_status==='active'&&g.state.bar[0]>0&&g.state.legal_moves.some(m=>m.src==='bar'))S.selected='bar';}catch{}}
  }else{P.game=null;P.gameVersion=-1;}
  if(full||S.view!=='party')render();else updatePartyPanels(mineBefore);
 }finally{P.polling=false;}
}
function updatePartyPanels(prevLast){
 const P=S.party;if(S.view!=='party'||!P.cur||!$('#party-stage'))return;
 const parts={'party-stage':partyStage(P,S,t,num),'party-members':partyMembers(P,t,num),'party-log':partyLog(P,t,S.lang)};
 for(const [id,html] of Object.entries(parts)){if(P.html[id]===html)continue;const el=$('#'+id);if(!el)continue;
  const active=document.activeElement;const had=el.contains(active)&&active?.dataset?.action;
  if(id==='party-log'){const mine=P.msgs.at(-1)?.user_id===P.cur.me&&P.msgs.at(-1)?.id!==prevLast;el.innerHTML=html;scrollLog(mine);}
  else el.innerHTML=html;
  P.html[id]=html;
  if(had){const same=[...el.querySelectorAll('[data-action]')].find(n=>n.dataset.action===had);same?.focus({preventScroll:true});}}
}
async function partyGame(kind,data={}){const P=S.party;const g=await api(`/parties/${P.id}/game/${kind}`,{method:'POST',data:{...data,version:P.game.version}});P.game=g;P.gameVersion=g.version;S.hokmCard=null;S.selected=null;S.pasur={card:null,capture:[]};await partyPoll();}
async function partyRoomPost(path,data){await api(`/parties/${S.party.id}/room/${path}`,{method:'POST',data});S.party.gameVersion=-1;await partyPoll();}
async function sendChat(){
 const P=S.party,input=$('#chat-input');if(!input||P.sending)return;const text=input.value.trim();if(!text)return;
 P.sending=true;
 try{await api(`/parties/${P.id}/messages`,{method:'POST',data:{text}});input.value='';P.draft='';await partyPoll();}
 catch(e){toast(messages[S.lang][e.code]?t(e.code):t('error'));}
 finally{P.sending=false;}
}
async function consumeJoin(){
 const code=read('pgc_join','');if(!code||!S.user)return false;
 try{localStorage.removeItem('pgc_join');}catch{}
 const j=await api('/parties/join',{method:'POST',data:{code}});await loadParties();await openParty(j.party.id);S.view='party';return true;
}
function copyText(text){(navigator.clipboard?.writeText(text)||Promise.reject()).then(()=>toast(t('ptCopied'))).catch(()=>toast(text));}
setInterval(()=>{if(S.view==='party'&&S.party.id&&S.user&&!S.busy&&!document.hidden&&!modal.open)partyPoll().catch(()=>{});},2500);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&S.view==='party'&&S.party.id)partyPoll().catch(()=>{});});
function openModal(html){modal.innerHTML=html;if(!modal.open)modal.showModal();}
function modalHead(title){return `<div class="modal-head"><h2 id="modal-title">${t(title)}</h2><button class="icon-button" type="button" data-action="modal-close" aria-label="${t('close')}">${icon('close')}</button></div>`;}
function showAuth(mode){const register=mode==='register';openModal(`${modalHead(register?'registerTitle':'loginTitle')}<p class="modal-copy">${t(register?'registerCopy':'loginCopy')}</p><form class="auth-form" data-form="${register?'register':'login'}"><label class="form-label" for="auth-username">${t('username')}</label><input id="auth-username" name="username" autocomplete="username" required minlength="3" maxlength="20" ${register?'aria-describedby="username-hint"':''}>${register?`<small id="username-hint">${t('usernameHint')}</small>`:''}<label class="form-label" for="auth-password">${t('password')}</label><input id="auth-password" name="password" type="password" autocomplete="${register?'new':'current'}-password" required minlength="8" maxlength="128">${register?`<small>${t('passwordHint')}</small><label class="form-label" for="auth-confirm">${t('confirm')}</label><input id="auth-confirm" name="confirm" type="password" autocomplete="new-password" required minlength="8" maxlength="128">`:''}<p class="form-error" role="alert"></p><button class="button primary" type="submit">${t(register?'submitRegister':'submitLogin')}${icon('arrow','directional')}</button></form><p class="modal-switch">${t(register?'haveAccount':'newAccount')}<button class="text-button" data-action="${register?'login':'signup'}">${t(register?'login':'signup')}</button></p>`);}
function setup(game,match=null){if(!S.user){showAuth('register');return;}S.startIntent={game,match,key:crypto.randomUUID()};openModal(`${modalHead('setupTitle')}<p class="modal-copy">${t(game)} · ${t('fee')}</p>${game==='hokm'?`<p class="modal-copy">${t('hokmSetup')}</p>`:''}<form class="setup-form" data-form="setup"><span class="form-label">${t('difficulty')}</span>${['easy','medium','hard'].map(level=>`<label class="level-option"><input type="radio" name="level" value="${level}" ${level==='medium'?'checked':''}><span><strong>${t(level)}</strong><small>${t(level+'Copy')}</small></span></label>`).join('')}<p class="setup-note">${t(game==='hokm'?'hokmAINote':'hardNote')}</p>${game==='backgammon'?`<label class="checkbox-label"><input type="checkbox" name="cube"><strong>${t('cube')}</strong></label><p class="setup-note">${t('cubeHelp')}</p>`:''}<p class="setup-note">${t('feeNotice')}</p><p class="form-error" role="alert"></p><button class="button primary" type="submit">${t(match?'resume':'start')}${icon('arrow','directional')}</button></form>`);}
async function navigate(view){S.menu=false;S.view=view;if(view==='party'){partyLeaveState();if(S.user)await loadParties();}if(view==='rankings'&&S.user)await loadRankings();if(view==='history'&&S.user)await loadHistory();render();window.scrollTo({top:0,behavior:'instant'});$('#main').focus({preventScroll:true});}
function gamePath(){return `/matches/${S.game.match_id}/${S.gameType==='backgammon'?'bg':S.gameType}`;}
async function refreshGame(){S.game=await api(gamePath());S.selected=null;S.pasur={card:null,capture:[]};S.hokmCard=null;}
// Single-player screens act on /matches/{id}; a group table acts on /parties/{id}/game.
const inParty=()=>S.view==='party'&&S.party.id;
const game=()=>inParty()?S.party.game:S.game;
const act=(kind,data={})=>inParty()?partyGame(kind,data):gameAction(kind,data);
async function gameAction(action,data={}){S.game=await api(gamePath()+'/'+action,{method:'POST',data:{...data,version:S.game.version}});S.selected=null;S.pasur={card:null,capture:[]};S.hokmCard=null;if(S.game.match_status!=='active')await dashboard();}
async function resume(mid){const m=S.history.find(m=>m.id===mid);if(!m)return;if(m.status==='pending'){setup(m.game,m);return;}S.gameType=m.game;try{S.game=await api(`/matches/${mid}/${m.game==='backgammon'?'bg':m.game}`);}catch(e){if(e.code==='not_found'&&m.status==='active'){setup(m.game,m);return;}throw e;}S.selected=null;S.pasur={card:null,capture:[]};S.hokmCard=null;await navigate('game');}
async function savePreferences(){write('pgc_lang',S.lang);write('pgc_theme',S.theme);if(S.user){await api('/settings',{method:'PUT',data:{language:S.lang,theme:S.theme}});S.user.language=S.lang;S.user.theme=S.theme;}}
const actions={
 'menu':()=>{S.menu=!S.menu;render();},'menu-close':()=>{S.menu=false;render();},'modal-close':()=>{if(!S.busy)modal.close();},'login':()=>showAuth('login'),'signup':()=>showAuth('register'),
 'navigate':el=>task(()=>navigate(el.dataset.view)),
 'find-games':()=>$('#collection')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'}),
 'language':()=>task(async()=>{S.lang=S.lang==='fa'?'en':'fa';await savePreferences();}),
 'theme':el=>task(async()=>{S.theme=el.dataset.theme;await savePreferences();toast(t('saved'));}),
 'theme-cycle':()=>task(async()=>{S.theme=themes[(themes.indexOf(S.theme)+1)%themes.length];await savePreferences();}),
 'setup':el=>setup(el.dataset.game),
 'logout':()=>task(async()=>{await api('/logout',{method:'POST'});S.user=null;S.game=null;S.history=[];S.view='lounge';S.startIntent=null;partyLeaveState();S.party.list=[];}),
 'resume':el=>task(()=>resume(Number(el.dataset.mid))),
 'cancel-match':el=>task(async()=>{await api(`/matches/${el.dataset.mid}/cancel`,{method:'POST'});await dashboard();}),
 'refresh':()=>task(async()=>{if(S.view==='rankings')await loadRankings();else await dashboard();}),
 'load-more':()=>task(()=>loadHistory(true)),
 'refill':()=>task(async()=>{await api('/coins/refill',{method:'POST'});await dashboard();toast(t('refilled'));}),
 'refresh-game':()=>task(()=>refreshGame()),
 'resign':()=>openModal(`${modalHead('resignTitle')}<p class="modal-copy">${t('resignCopy')}</p><div class="button-row"><button class="button danger" data-action="confirm-resign">${t('confirmResign')}</button><button class="button" data-action="modal-close">${t('cancel')}</button></div>`),
 'confirm-resign':()=>task(async()=>{await api(gamePath()+'/resign',{method:'POST'});modal.close();await refreshGame();await dashboard();}),
 'bg-roll':()=>task(()=>act('roll')),'bg-double':()=>task(()=>act('double')),'cube-accept':()=>task(()=>act('respond',{accept:true})),'cube-decline':()=>task(()=>act('respond',{accept:false})),
 'bg-point':el=>{const point=el.dataset.point,st=game().state;const candidate=st.legal_moves.filter(m=>String(m.src)===String(S.selected)&&String(m.dst)===point).sort((a,b)=>a.die-b.die)[0];if(S.selected!==null&&candidate){task(()=>act('move',candidate));return;}S.selected=st.legal_moves.some(m=>String(m.src)===point)?(String(S.selected)===point?null:point):null;render();},
 'hand-card':el=>{S.pasur={card:S.pasur.card===el.dataset.card?null:el.dataset.card,capture:[]};render();},
 'table-card':el=>{const c=el.dataset.card;if(!S.pasur.card)return;S.pasur.capture=S.pasur.capture.includes(c)?S.pasur.capture.filter(x=>x!==c):[...S.pasur.capture,c];render();},
 'clear-selection':()=>{S.pasur={card:null,capture:[]};render();},
 'pasur-suggest':()=>{const options=game().state.legal_actions.filter(a=>a.card===S.pasur.card&&a.capture.length);if(!options.length){toast(t('noCapture'));return;}const current=options.findIndex(a=>a.capture.length===S.pasur.capture.length&&a.capture.every(c=>S.pasur.capture.includes(c)));S.pasur.capture=[...options[(current+1)%options.length].capture];render();},
 'pasur-play':()=>task(()=>act('move',{card:S.pasur.card,capture:S.pasur.capture})),
 'hokm-card':el=>{S.hokmCard=S.hokmCard===el.dataset.card?null:el.dataset.card;render();},
 'hokm-play':()=>task(()=>S.view==='party'?partyGame('move',{card:S.hokmCard}):gameAction('move',{card:S.hokmCard})),
 'hokm-trump':el=>task(()=>S.view==='party'?partyGame('trump',{suit:el.dataset.suit}):gameAction('trump',{suit:el.dataset.suit})),
 'hokm-continue':()=>task(()=>S.view==='party'?partyGame('continue'):gameAction('continue')),
 'party-open':el=>task(async()=>{await openParty(Number(el.dataset.id));}),
 'party-back':()=>task(()=>navigate('party')),
 'party-copy-code':()=>copyText(S.party.cur.party.code),
 'party-copy-link':()=>copyText(`${location.origin}/?join=${S.party.cur.party.code}`),
 'party-game':el=>task(()=>partyRoomPost('settings',{game:el.dataset.game})),
 'party-sit':el=>task(()=>partyRoomPost('seat',{seat:Number(el.dataset.seat)})),
 'party-stand':()=>task(()=>partyRoomPost('seat',{seat:null})),
 'party-start':()=>task(()=>partyRoomPost('start')),
 'party-reset':()=>task(()=>partyRoomPost('reset')),
 'party-kick':el=>openModal(`${modalHead('ptKickTitle')}<p class="modal-copy">${t('ptKickCopy',{name:esc(el.dataset.name)})}</p><div class="button-row"><button class="button danger" data-action="party-kick-confirm" data-uid="${el.dataset.uid}">${t('ptKick')}</button><button class="button" data-action="modal-close">${t('cancel')}</button></div>`),
 'party-kick-confirm':el=>task(async()=>{await api(`/parties/${S.party.id}/kick`,{method:'POST',data:{user_id:Number(el.dataset.uid)}});modal.close();await partyPoll();}),
 'party-leave-ask':()=>openModal(`${modalHead('ptLeaveTitle')}<p class="modal-copy">${t('ptLeaveCopy')}</p><div class="button-row"><button class="button danger" data-action="party-leave-confirm">${t('ptLeave')}</button><button class="button" data-action="modal-close">${t('cancel')}</button></div>`),
 'party-leave-confirm':()=>task(async()=>{await api(`/parties/${S.party.id}/leave`,{method:'POST'});modal.close();await navigate('party');}),
 'party-stand-ask':()=>openModal(`${modalHead('ptLeaveTable')}<p class="modal-copy">${t('ptLeaveTableCopy')}</p><div class="button-row"><button class="button danger" data-action="party-stand-confirm">${t('ptLeaveTable')}</button><button class="button" data-action="modal-close">${t('cancel')}</button></div>`),
 'party-stand-confirm':()=>task(async()=>{modal.close();await partyRoomPost('seat',{seat:null});}),
 'party-reset-ask':()=>openModal(`${modalHead('ptEndGame')}<p class="modal-copy">${t('ptEndGameCopy')}</p><div class="button-row"><button class="button danger" data-action="party-reset-confirm">${t('ptEndGame')}</button><button class="button" data-action="modal-close">${t('cancel')}</button></div>`),
 'party-reset-confirm':()=>task(async()=>{modal.close();await partyRoomPost('reset');}),
 'install':()=>task(async()=>{if(S.installPrompt){await S.installPrompt.prompt();await S.installPrompt.userChoice;S.installPrompt=null;}})
};
document.addEventListener('click',event=>{const el=event.target.closest('[data-action]');if(!el||el.disabled||S.busy&&el.dataset.action!=='menu-close')return;actions[el.dataset.action]?.(el);});
document.addEventListener('change',event=>{const key=event.target.dataset.filter;if(!key)return;task(async()=>{if(key==='partyLevel'){await partyRoomPost('settings',{level:event.target.value});return;}if(key==='partyCube'){await partyRoomPost('settings',{cube:event.target.checked});return;}if(key==='language'){S.lang=event.target.value;await savePreferences();}else{S[key]=event.target.value;if(key.startsWith('rank'))await loadRankings();else await loadHistory();}});});
document.addEventListener('submit',event=>{const form=event.target,kind=form.dataset.form;if(!kind)return;event.preventDefault();if(kind==='chat'){sendChat();return;}if(!form.reportValidity())return;const data=Object.fromEntries(new FormData(form));task(async()=>{
 if(kind==='login'||kind==='register'){const j=await api('/'+kind,{method:'POST',data});S.user=j.user;if(kind==='login'){S.lang=j.user.language;S.theme=j.user.theme;}else await savePreferences();await dashboard();modal.close();S.view='lounge';await consumeJoin();}
 else if(kind==='party-create'){const j=await api('/parties',{method:'POST',data});await openParty(j.party.id);}
 else if(kind==='party-join'){const j=await api('/parties/join',{method:'POST',data});await openParty(j.party.id);}
 else if(kind==='setup'){const intent=S.startIntent;if(!intent)return;let match=intent.match;if(!match){match=(await api('/matches',{method:'POST',data:{game:intent.game,idem_key:intent.key}})).match;}else{match=(await api('/matches?limit=100')).matches.find(m=>m.id===match.id)||match;}if(match.status==='pending')await api(`/matches/${match.id}/activate`,{method:'POST'});else if(match.status!=='active')throw new APIError('invalid_state',409);S.gameType=intent.game;S.game=await api(`/matches/${match.id}/${intent.game==='backgammon'?'bg':intent.game}/start`,{method:'POST',data:{level:data.level,...(intent.game==='backgammon'?{cube:data.cube==='on'}:{})}});S.selected=null;S.pasur={card:null,capture:[]};S.hokmCard=null;S.startIntent=null;modal.close();await dashboard();await navigate('game');}
 else if(kind==='password'){await api('/password',{method:'POST',data});toast(t('passwordChanged'));form.reset();}
 });});
modal.addEventListener('cancel',event=>{if(S.busy)event.preventDefault();});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&S.menu){S.menu=false;render();$('.mobile-menu')?.focus();}});
window.addEventListener('offline',()=>{S.offline=true;render();});window.addEventListener('online',()=>{S.offline=false;toast(t('reconnected'));render();});
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();S.installPrompt=event;if(S.view==='settings')render();});
window.addEventListener('appinstalled',()=>{S.installPrompt=null;});
async function init(){try{const invite=new URLSearchParams(location.search).get('join');if(invite){write('pgc_join',invite.slice(0,12));history.replaceState(null,'',location.pathname);}const me=await api('/me');S.user=me.user;if(S.user){S.lang=S.user.language;S.theme=S.user.theme;await dashboard();try{await consumeJoin();}catch(e){toast(messages[S.lang][e.code]?t(e.code):t('error'));}}else if(read('pgc_join','')){render();showAuth('register');}render();}catch(error){render();toast(t(error.code||'error'));}if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}}
render();init();
