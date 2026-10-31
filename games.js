import {icon} from './icons.js';
export const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const suits={C:'♣',D:'♦',H:'♥',S:'♠'};
export function card(id,{selected=false,action='',disabled=false,back=false}={}){
 if(back)return '<span class="card-back" aria-hidden="true"></span>';
 const suit=suits[id?.[0]],rank=id?.slice(1);
 if(!suit||!['A','2','3','4','5','6','7','8','9','10','J','Q','K'].includes(rank))return '';
 const content=`<img src="/card-${id}.webp" alt="${rank} ${suit}" width="320" height="448" draggable="false">`;
 return action?`<button type="button" class="playing-card ${selected?'selected':''}" data-action="${action}" data-card="${id}" aria-pressed="${selected}" ${disabled?'disabled':''}>${content}</button>`:`<span class="playing-card">${content}</span>`;
}
export function dice(value,t){
 const positions={1:[5],2:[1,9],3:[1,5,9],4:[1,3,7,9],5:[1,3,5,7,9],6:[1,3,4,6,7,9]};
 return `<span class="die" role="img" aria-label="${t('die',{n:value})}">${Array.from({length:9},(_,i)=>`<i class="${positions[value]?.includes(i+1)?'pip':''}"></i>`).join('')}</span>`;
}
export function backgammonBoard(game,selected,t,num){
 const st=game.state,active=game.match_status==='active';
 const moves=active?st.legal_moves:[];
 const sources=new Set(moves.map(m=>String(m.src)));
 const destinations=new Set(moves.filter(m=>String(m.src)===String(selected)).map(m=>String(m.dst)));
 function point(i,bottom=false){
  const count=Math.abs(st.points[i]),human=st.points[i]>0;
  const source=sources.has(String(i)),destination=selected!==null&&destinations.has(String(i));
  const label=destination?t('moveTo',{point:num(i+1)}):t('checkerLabel',{point:num(i+1),count:num(count),side:t(human?'you':'opponent')});
  return `<button class="point ${bottom?'bottom-point':'top-point'} ${i%2?'dark-point':''} ${source?'movable':''} ${destination?'destination':''} ${String(selected)===String(i)?'selected':''}" data-action="bg-point" data-point="${i}" aria-label="${escapeHTML(label)}" ${!source&&!destination?'disabled':''}><span class="point-number">${num(i+1)}</span>${Array.from({length:Math.min(count,5)},(_,j)=>`<span class="checker ${human?'ivory':'ebony'}">${count>5&&j===4?`<b>${num(count)}</b>`:''}</span>`).join('')}</button>`;
 }
 const bar=`<span class="board-bar" aria-hidden="true"></span>`;
 return `<div class="board-meta"><span><i class="small-checker ebony"></i>${t('opponent')} <b>${num(st.off[1])}</b> ${t('off')}</span><span class="cube-indicator" title="${t('cube')}">${st.cube.enabled?'×'+num(st.cube.value):'✧'}</span></div><div class="backgammon-board" role="group" aria-label="${t('backgammon')}"><div class="board-row">${Array.from({length:6},(_,i)=>point(i+12)).join('')}${bar}${Array.from({length:6},(_,i)=>point(i+18)).join('')}</div><div class="board-center"><span class="board-rosette">✧</span><div class="dice-tray" aria-live="polite">${(st.dice.length?st.dice:st.roll).map(d=>dice(d,t)).join('')}</div><span class="board-rosette">✧</span></div><div class="board-row">${Array.from({length:6},(_,i)=>point(11-i,true)).join('')}${bar}${Array.from({length:6},(_,i)=>point(5-i,true)).join('')}</div></div><div class="board-meta"><span><i class="small-checker ivory"></i>${t('you')} <b>${num(st.off[0])}</b> ${t('off')}</span><div class="board-tools"><button class="button small ${selected==='bar'?'selected':''}" data-action="bg-point" data-point="bar" ${!sources.has('bar')?'disabled':''} aria-label="${t('barLabel',{n:num(st.bar[0])})}">${t('bar')} ${num(st.bar[0])}</button><span class="muted">${t('opponent')}: ${num(st.bar[1])}</span><button class="button small ${destinations.has('off')?'primary':''}" data-action="bg-point" data-point="off" ${!destinations.has('off')?'disabled':''}>${t('off')} ${icon('arrow')}</button></div></div>`;
}
export function pasurBoard(game,selection,t,num){
 const st=game.state,active=game.match_status==='active';
 const possible=selection.card?(st.legal_actions||[]).filter(a=>a.card===selection.card):[];
 const valid=possible.some(a=>a.capture.length===selection.capture.length&&a.capture.every(c=>selection.capture.includes(c)));
 return `<div class="pasur-board"><div class="opponent-seat"><div class="avatar ai">${icon('dice')}</div><span>${t('opponent')}<small>${t('captured')}: ${num(st.captured_count[1])} · ${t('sur')}: ${num(st.sur[1])}</small></span><div class="opponent-hand">${Array.from({length:st.opponent_hand_count},()=>card(null,{back:true})).join('')}</div></div><div class="table-label"><span>${t('table')}</span><span>${t('round')} ${num(st.round)} · ${t('deck')}: ${num(st.deck_count)}</span></div><div class="table-cards">${st.table.length?st.table.map(c=>card(c,{selected:selection.capture.includes(c),action:'table-card',disabled:!active||!selection.card})).join(''):`<p class="empty-table">✧<span>${t('emptyTable')}</span></p>`}</div><div class="hand-label"><span>${t('yourHand')}</span><span>${t('captured')}: ${num(st.captured_count[0])} · ${t('sur')}: ${num(st.sur[0])}</span></div><div class="your-hand">${st.hand.map(c=>card(c,{selected:selection.card===c,action:'hand-card',disabled:!active})).join('')}</div></div>${active?`<div class="pasur-controls"><p class="muted">${t(selection.card?'captureHint':'pasurHint')}</p><div class="button-row"><button class="button primary" data-action="pasur-play" ${!valid?'disabled':''}>${t(selection.capture.length?'capture':'playCard')} ${icon('arrow')}</button><button class="button" data-action="pasur-suggest" ${!selection.card?'disabled':''}>${t('legalCapture')}</button><button class="text-button" data-action="clear-selection" ${!selection.card?'disabled':''}>${t('clear')}</button></div></div>`:''}`;
}
