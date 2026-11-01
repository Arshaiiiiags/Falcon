import {escapeHTML as esc} from './games.js';
import {icon} from './icons.js';
import {hokmTable} from './hokm.js';

// Views for groups: list/create/join, the group room (members, lobby table, game) and the chat log.
// Pure functions of (state, t, num); app.js owns the state, polling and API calls.

const TEAMS=[[0,2],[1,3]];

export function partyHome(P,t,num){
 return `<div class="party-grid">
  <section class="panel party-form"><h2>${icon('users')}${t('ptCreate')}</h2>
   <form data-form="party-create"><label class="form-label" for="party-name">${t('ptName')}</label>
   <input id="party-name" name="name" required maxlength="30" autocomplete="off">
   <button class="button primary" type="submit">${t('ptCreateBtn')}${icon('arrow','directional')}</button></form></section>
  <section class="panel party-form"><h2>${icon('chevron','directional')}${t('ptJoin')}</h2>
   <form data-form="party-join"><label class="form-label" for="party-code">${t('ptCode')}</label>
   <input id="party-code" name="code" required minlength="4" maxlength="12" autocomplete="off" autocapitalize="characters" dir="ltr" class="code-input">
   <button class="button primary" type="submit">${t('ptJoinBtn')}${icon('arrow','directional')}</button></form></section>
 </div>
 <section class="recent-section"><div class="section-head"><h2>${t('ptMine')}</h2></div>
 ${P.list.length?`<div class="party-list">${P.list.map(p=>`<article class="panel party-item"><div><h3 dir="auto">${esc(p.name)}</h3><small class="muted">${t('ptMembers',{n:num(p.members)})}${p.room==='active'?' · '+t('ptPlaying'):''}${p.is_owner?' · '+t('ptOwner'):''}</small></div><button class="button" data-action="party-open" data-id="${p.id}">${t('ptOpen')}${icon('arrow','directional')}</button></article>`).join('')}</div>`
 :`<div class="empty-state">${icon('users')}<h3>${t('ptNone')}</h3><p>${t('ptNoneCopy')}</p></div>`}</section>`;
}

export function partyHeader(P,t){
 const c=P.cur.party;
 return `<div class="party-head"><div><h1 dir="auto">${esc(c.name)}</h1><small class="muted">${t('ptCodeLabel')}: <b class="code-chip" dir="ltr">${esc(c.code)}</b></small></div>
  <div class="button-row"><button class="button small" data-action="party-copy-code">${t('ptCopyCode')}</button><button class="button small" data-action="party-copy-link">${t('ptCopyLink')}</button><button class="button small danger-outline" data-action="party-leave-ask">${t('ptLeave')}</button><button class="text-button" data-action="party-back">${icon('arrow','directional')}${t('ptBack')}</button></div></div>`;
}

export function partyMembers(P,t,num){
 const me=P.cur.me,owner=P.cur.party.is_owner;
 return `<h2>${t('ptPeople',{n:num(P.cur.members.length),max:num(P.cur.party.max_members)})}</h2><ul class="member-list">${P.cur.members.map(m=>`<li><span class="presence ${m.online?'on':''}" title="${t(m.online?'ptOnline':'ptOffline')}"></span><span class="avatar">${esc(m.username.slice(0,1).toUpperCase())}</span><strong dir="auto">${esc(m.username)}</strong>${m.user_id===me?`<small class="muted">${t('you')}</small>`:''}${m.owner?`<span class="badge">${t('ptOwner')}</span>`:''}${owner&&m.user_id!==me?`<button class="text-button" data-action="party-kick" data-uid="${m.user_id}" data-name="${esc(m.username)}">${t('ptKick')}</button>`:''}</li>`).join('')}</ul>`;
}

const clock=(S,v)=>{try{return new Intl.DateTimeFormat(S==='fa'?'fa-IR':'en-GB',{hour:'2-digit',minute:'2-digit'}).format(new Date(v.replace(' ','T')+'Z'));}catch{return '';}};

export function partyLog(P,t,lang){
 if(!P.msgs.length)return `<p class="chat-empty muted">${t('ptNoMessages')}</p>`;
 return P.msgs.map(m=>m.kind==='system'
  ?`<div class="msg sys">${t('sys_'+m.body,{name:esc(m.username)})}</div>`
  :`<div class="msg ${m.user_id===P.cur.me?'mine':''}"><div class="msg-meta"><b dir="auto">${esc(m.username)}</b><time>${clock(lang,m.created_at)}</time></div><p dir="auto">${esc(m.body)}</p></div>`).join('');
}

export function chatPanel(P,t,lang){
 return `<section class="panel party-chat" aria-label="${t('ptChat')}"><h2>${icon('chat')}${t('ptChat')}</h2><div id="party-log" class="chat-log" role="log" aria-live="polite" tabindex="0">${partyLog(P,t,lang)}</div>
  <form data-form="chat" class="chat-form"><label class="sr-only" for="chat-input">${t('ptChatPlaceholder')}</label><input id="chat-input" name="text" maxlength="500" autocomplete="off" dir="auto" placeholder="${t('ptChatPlaceholder')}" value="${esc(P.draft||'')}"><button class="button primary" type="submit" aria-label="${t('ptSend')}">${icon('arrow','directional')}</button></form></section>`;
}

function seatCard(P,t,i){
 const room=P.cur.room,seat=room.seats[i],mine=room.my_seat===i,lobby=room.status==='lobby';
 return `<div class="seat-slot ${seat?'taken':''} ${mine?'mine':''}"><span class="avatar ${seat?'':'ai'}">${seat?esc(seat.name.slice(0,1).toUpperCase()):icon('shield')}</span><div><strong dir="auto">${seat?esc(seat.name):t('ptAISeat')}</strong><small>${mine?t('you'):seat?t('ptPlayer'):t('ptAISeatCopy')}</small></div>${lobby?(mine?`<button class="text-button" data-action="party-stand">${t('ptStand')}</button>`:!seat?`<button class="button small" data-action="party-sit" data-seat="${i}">${t('ptSit')}</button>`:''):''}</div>`;
}

function lobby(P,t){
 const room=P.cur.room,owner=P.cur.party.is_owner,seated=room.seats.some(Boolean);
 return `<section class="panel table-lobby"><h2>${icon('cards')}${t('ptTable')}</h2><p class="muted">${t('ptTableCopy')}</p>
  <div class="teams">${TEAMS.map((seats,n)=>`<div class="team-card team-${n+1}"><h3>${t('ptTeam',{n:n+1})}</h3><small class="muted">${t('ptTeamCopy')}</small>${seats.map(i=>seatCard(P,t,i)).join('')}</div>`).join('')}</div>
  ${owner?`<div class="lobby-controls"><label class="form-label" for="party-level">${t('ptLevel')}</label><select id="party-level" data-filter="partyLevel">${['easy','medium','hard'].map(l=>`<option value="${l}" ${room.level===l?'selected':''}>${t(l)}</option>`).join('')}</select><button class="button primary" data-action="party-start" ${seated?'':'disabled'}>${t('ptStart')}${icon('arrow','directional')}</button></div>${seated?'':`<p class="muted">${t('ptNeedPlayer')}</p>`}`
  :`<p class="muted lobby-wait">${icon('clock')}${t('ptWaitOwner',{level:t(room.level)})}</p>`}
  <p class="setup-note">${t('ptFree')}</p></section>`;
}

export function partyStage(P,S,t,num){
 const room=P.cur.room,owner=P.cur.party.is_owner;
 if(room.status==='lobby')return lobby(P,t);
 if(room.my_seat===null){
  const sc=room.scores||[0,0];
  return `<section class="panel table-lobby"><h2>${icon('cards')}${t('ptTable')}</h2><p>${t(room.status==='active'?'ptSpectate':'ptSpectateDone')}</p><div class="score-display"><span>${num(sc[0])}</span><small>:</small><span>${num(sc[1])}</span></div><small class="muted">${t('ptTeam',{n:1})} · ${t('ptTeam',{n:2})}</small>${owner?`<div class="button-row"><button class="button" data-action="party-reset-ask">${t(room.status==='active'?'ptEndGame':'ptPlayAgain')}</button></div>`:''}</section>`;
 }
 const g=P.game;
 if(!g)return `<section class="panel"><p class="muted">${t('loading')}</p></section>`;
 const st=g.state,active=g.match_status==='active';
 return `<div class="game-page hokm-page"><div class="game-topline"><div><h1>${t('hokm')}</h1><small>${esc(P.cur.party.name)} · ${t('levelLabel',{level:t(room.level)})}</small></div></div>${hokmTable(g,S.hokmCard,t,num,S.user.username)}${active?`<div class="game-actions"><button class="text-button" data-action="party-stand-ask">${t('ptLeaveTable')}</button>${owner?`<button class="text-button" data-action="party-reset-ask">${t('ptEndGame')}</button>`:''}</div>`
  :`<section class="terminal-panel">${icon('trophy')}<h2>${t(st.winner===0?'youWon':'youLost')}</h2><p>${t('ptFinalScore',{a:num(st.scores[0]),b:num(st.scores[1])})}</p><div class="button-row">${owner?`<button class="button primary" data-action="party-reset">${t('ptPlayAgain')}</button>`:`<span class="muted">${t('ptWaitAgain')}</span>`}</div></section>`}</div>`;
}

export function partyRoom(P,S,t,num){
 return `${partyHeader(P,t)}<div class="party-layout"><div class="party-main" id="party-stage">${partyStage(P,S,t,num)}</div><aside class="party-side"><section class="panel party-members" id="party-members">${partyMembers(P,t,num)}</section>${chatPanel(P,t,S.lang)}</aside></div>`;
}
