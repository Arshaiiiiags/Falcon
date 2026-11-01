import {escapeHTML as esc,card,pasurBoard,backgammonBoard} from './games.js';
import {icon} from './icons.js';
import {hokmTable} from './hokm.js';

// Views for groups: list/create/join, the group room (members, lobby table, game) and the chat log.
// The table plays Hokm (4 seats), Pasur or backgammon (2 seats); empty seats are played by the AI.
// Pure functions of (state, t, num); app.js owns the state, polling and API calls.

const TEAMS=[[0,2],[1,3]];
const GAMES=['hokm','pasur','backgammon'];
const SEATS={hokm:4,pasur:2,backgammon:2};

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

function gamePicker(P,t){
 const room=P.cur.room;
 if(!P.cur.party.is_owner)return `<p class="lobby-game"><span class="muted">${t('ptGameLabel')}:</span> <strong>${t(room.game)}</strong></p>`;
 return `<div class="game-picker" role="group" aria-label="${t('ptGameLabel')}">${GAMES.map(g=>`<button class="button small ${room.game===g?'primary':''}" data-action="party-game" data-game="${g}" aria-pressed="${room.game===g}">${t(g)}</button>`).join('')}</div>`;
}

function lobby(P,t){
 const room=P.cur.room,owner=P.cur.party.is_owner,seated=room.seats.some(Boolean),game=room.game,four=game==='hokm';
 const seatsHTML=four
  ?TEAMS.map((seats,n)=>`<div class="team-card team-${n+1}"><h3>${t('ptTeam',{n:n+1})}</h3><small class="muted">${t('ptTeamCopy')}</small>${seats.map(i=>seatCard(P,t,i)).join('')}</div>`).join('')
  :[0,1].map(i=>`<div class="team-card"><h3>${t('ptSeatN',{n:i+1})}</h3>${seatCard(P,t,i)}</div>`).join('');
 const cube=game==='backgammon'?(owner?`<label class="checkbox-label"><input type="checkbox" data-filter="partyCube" ${room.options?.cube?'checked':''}> ${t('cube')}</label>`:`<p class="muted">${t('ptCubeState',{state:t(room.options?.cube?'ptOn':'ptOff')})}</p>`):'';
 return `<section class="panel table-lobby"><h2>${icon('cards')}${t('ptTableOf',{game:t(game)})}</h2>${gamePicker(P,t)}<p class="muted">${t(four?'ptTableCopy':'ptTableCopy2')}</p>
  <div class="teams">${seatsHTML}</div>${cube}
  ${owner?`<div class="lobby-controls"><label class="form-label" for="party-level">${t('ptLevel')}</label><select id="party-level" data-filter="partyLevel">${['easy','medium','hard'].map(l=>`<option value="${l}" ${room.level===l?'selected':''}>${t(l)}</option>`).join('')}</select><button class="button primary" data-action="party-start" ${seated?'':'disabled'}>${t('ptStart')}${icon('arrow','directional')}</button></div>${seated?'':`<p class="muted">${t('ptNeedPlayer')}</p>`}`
  :`<p class="muted lobby-wait">${icon('clock')}${t('ptWaitOwner',{level:t(room.level)})}</p>`}
  <p class="setup-note">${t('ptFree')}</p></section>`;
}

// Two-seat games (Pasur, backgammon): the same board the single-player screens use, plus names and whose turn it is.
function classicStage(P,S,t,num){
 const room=P.cur.room,owner=P.cur.party.is_owner,game=room.game,isBG=game==='backgammon';
 const g=P.game;
 if(!g)return `<section class="panel"><p class="muted">${t('loading')}</p></section>`;
 const st=g.state,active=g.match_status==='active';
 const oppName=st.kinds[1]==='ai'?t('opponent'):st.names[1]||t('opponent');
 const tp=(k,v)=>k==='opponent'?esc(oppName):t(k,v);
 const mine=isBG?(st.must_respond||st.can_roll||(st.turn===0&&st.legal_moves.length>0)):st.turn===0;
 const waiting=active&&!mine;
 const board=isBG?backgammonBoard(g,S.selected,tp,num):pasurBoard(waiting?{...g,match_status:'waiting'}:g,S.pasur,tp,num);
 let hint='';
 if(active){
  if(isBG){
   if(st.must_respond)hint=`<p class="game-hint">${t('doubleOffer',{value:num(st.cube.pending_value)})}</p><div class="button-row"><button class="button primary" data-action="cube-accept">${t('accept')}</button><button class="button" data-action="cube-decline">${t('decline')}</button></div>`;
   else if(st.can_roll)hint=`<div class="button-row"><button class="button primary" data-action="bg-roll">${icon('dice')}${t('roll')}</button>${st.can_double?`<button class="button" data-action="bg-double">${t('double')}</button>`:''}</div>`;
   else if(st.cube.pending_by===0)hint=`<p class="game-hint">${t('ptWaitDouble',{name:esc(oppName)})}</p>`;
   else if(waiting)hint=`<p class="game-hint">${t('ptWaitFor',{name:esc(oppName)})}</p>`;
   else hint=`<p class="game-hint">${t(S.selected!==null?'selectDestination':'selectChecker')}</p>`;
  }else if(waiting)hint=`<p class="game-hint">${t('ptWaitFor',{name:esc(oppName)})}</p>`;
 }
 const last=!isBG?[...(st.events||[])].reverse().find(e=>e.type==='play'&&e.seat===1):null;
 const lastPlay=last?`<div class="last-play" aria-live="polite"><span>${t('ptOppPlayed',{name:esc(oppName)})}</span>${card(last.card)}${last.capture.length?`<span class="muted">+ ${num(last.capture.length)}</span>`:''}${last.sur?`<b>${t('sur')}</b>`:''}</div>`:'';
 const centre=isBG?`<span class="turn-chip">${t(!active?'gameOver':mine?'yourTurn':'ptTheirTurn')}</span>`:`<div class="score-display"><span>${num(st.scores[0])}</span><small>:</small><span>${num(st.scores[1])}</span></div>`;
 const won=st.winner===0,draw=st.draw===true;
 const result=isBG?(st.win_type==='cube_drop'?t('ptCubeDrop',{n:num(st.points_won)}):t('ptBgResult',{n:num(st.points_won)})):t('ptFinalScore2',{a:num(st.scores[0]),b:num(st.scores[1])});
 return `<div class="game-page"><div class="game-topline"><div><h1>${t(game)}</h1><small>${esc(P.cur.party.name)}${st.kinds.includes('ai')?' · '+t('levelLabel',{level:t(room.level)}):''}</small></div></div>
  <div class="player-strip"><div class="player-seat"><div class="avatar">${esc((st.names[0]||'').slice(0,1).toUpperCase())}</div><span><strong dir="auto">${esc(st.names[0]||'')}</strong><small>${t('you')}</small></span></div>${centre}<div class="player-seat"><span><strong dir="auto">${esc(oppName)}</strong><small>${st.kinds[1]==='ai'?t(room.level):t('ptPlayer')}${!isBG?' · '+t('target')+': '+num(st.target_score):''}</small></span><div class="avatar ${st.kinds[1]==='ai'?'ai':''}">${st.kinds[1]==='ai'?icon('dice'):esc((st.names[1]||'').slice(0,1).toUpperCase())}</div></div></div>
  ${lastPlay}${board}
  ${active?`<div class="game-actions"><div>${hint}</div><button class="text-button" data-action="party-stand-ask">${t('ptLeaveTable')}</button>${owner?`<button class="text-button" data-action="party-reset-ask">${t('ptEndGame')}</button>`:''}</div>`
  :`<section class="terminal-panel">${icon('trophy')}<h2>${t(draw?'gameDraw':won?'youWon':'youLost')}</h2><p>${result}</p><div class="button-row">${owner?`<button class="button primary" data-action="party-reset">${t('ptPlayAgain')}</button>`:`<span class="muted">${t('ptWaitAgain')}</span>`}</div></section>`}</div>`;
}

export function partyStage(P,S,t,num){
 const room=P.cur.room,owner=P.cur.party.is_owner;
 if(room.status==='lobby')return lobby(P,t);
 if(room.my_seat===null){
  const sc=room.scores||room.off||[0,0],four=room.game==='hokm';
  const seatsLine=four?`${t('ptTeam',{n:1})} · ${t('ptTeam',{n:2})}`:room.seats.map(x=>esc(x?x.name:t('ptAISeat'))).join(' · ');
  return `<section class="panel table-lobby"><h2>${icon('cards')}${t('ptTableOf',{game:t(room.game)})}</h2><p>${t(room.status==='active'?'ptSpectate':'ptSpectateDone')}</p><div class="score-display"><span>${num(sc[0])}</span><small>:</small><span>${num(sc[1])}</span></div><small class="muted">${seatsLine}</small>${owner?`<div class="button-row"><button class="button" data-action="party-reset-ask">${t(room.status==='active'?'ptEndGame':'ptPlayAgain')}</button></div>`:''}</section>`;
 }
 if(room.game!=='hokm')return classicStage(P,S,t,num);
 const g=P.game;
 if(!g)return `<section class="panel"><p class="muted">${t('loading')}</p></section>`;
 const st=g.state,active=g.match_status==='active';
 return `<div class="game-page hokm-page"><div class="game-topline"><div><h1>${t('hokm')}</h1><small>${esc(P.cur.party.name)} · ${t('levelLabel',{level:t(room.level)})}</small></div></div>${hokmTable(g,S.hokmCard,t,num,S.user.username)}${active?`<div class="game-actions"><button class="text-button" data-action="party-stand-ask">${t('ptLeaveTable')}</button>${owner?`<button class="text-button" data-action="party-reset-ask">${t('ptEndGame')}</button>`:''}</div>`
  :`<section class="terminal-panel">${icon('trophy')}<h2>${t(st.winner===0?'youWon':'youLost')}</h2><p>${t('ptFinalScore',{a:num(st.scores[0]),b:num(st.scores[1])})}</p><div class="button-row">${owner?`<button class="button primary" data-action="party-reset">${t('ptPlayAgain')}</button>`:`<span class="muted">${t('ptWaitAgain')}</span>`}</div></section>`}</div>`;
}

export function partyRoom(P,S,t,num){
 return `${partyHeader(P,t)}<div class="party-layout"><div class="party-main" id="party-stage">${partyStage(P,S,t,num)}</div><aside class="party-side"><section class="panel party-members" id="party-members">${partyMembers(P,t,num)}</section>${chatPanel(P,t,S.lang)}</aside></div>`;
}
