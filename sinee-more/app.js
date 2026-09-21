import {
  LIGHT as L, DARK as K, otherPlayer, usesStack2, usesLadder
} from './ai/constants.js';
import {
  createInitialPosition, clonePosition, topPiece, isLegalMove, getLegalMoves, applyMove
} from './ai/rules.js';
import { chooseMove } from './ai/engine.js';
import { PERSONAS, selectPersonaAtGameStart } from './ai/personas.js';

'use strict';

var rule='C',mode='solo',difficulty='medium',styleChoice='mixed',
    aiPersona='architect',lastPersona='',human=L,computer=K,state,sel=null,
    gameNo=1,gameSeed=1,aiBusy=false,themeChoice='nd';
var history=[],gameFirst=L,lastFocus=null;

function empty(first){return createInitialPosition(first||L);}
function clone(s){return clonePosition(s);}
function other(p){return otherPlayer(p);}
function top(s,c){return topPiece(s,c);}
function has(a,x){return a.indexOf(x)>=0;}
function useStack2(){return usesStack2(rule);}
function useLadder(){return usesLadder(rule);}
function probeTurn(s,p){if(s.turn===p)return s;var n=clonePosition(s);n.turn=p;return n;}
function legal(s,p,r,c){return isLegalMove(probeTurn(s,p),{player:p,rank:r,cell:c},rule);}
function moves(s,p){return getLegalMoves(probeTurn(s,p),p,rule).map(function(m){return{p:m.player,r:m.rank,c:m.cell};});}
function apply(s,m){return applyMove(probeTurn(s,m.p),{player:m.p,rank:m.r,cell:m.c},rule);}
function choosePersona(){aiPersona=selectPersonaAtGameStart(styleChoice,lastPersona,Math.random);lastPersona=aiPersona;}
function personaName(){return (PERSONAS[aiPersona]||PERSONAS.architect).name;}
function name(p){return p===L?'СВЕТЛЫЕ':'ТЁМНЫЕ';}
function el(id){return document.getElementById(id);}
function msg(x){el('msg').textContent=x;}
function loadTheme(){try{var v=localStorage.getItem('sinee-more-theme');if(v==='pirate'||v==='atlantis'||v==='nd')themeChoice=v;}catch(e){}}
function themeLabel(){return themeChoice==='pirate'?'Pirate Chart':themeChoice==='atlantis'?'Atlantis':'ND Premium';}
function applyTheme(){
  document.body.setAttribute('data-theme',themeChoice);
  var tv=el('themeValue');if(tv)tv.textContent=themeLabel();
  markSelected('theme-choice',themeChoice);
  var meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.setAttribute('content',themeChoice==='pirate'?'#2a160e':themeChoice==='atlantis'?'#031923':'#000000');
  try{localStorage.setItem('sinee-more-theme',themeChoice);}catch(e){}
}

function openM(id){lastFocus=document.activeElement;var m=el(id);m.className='modal open';var f=m.querySelector('.selected,.choice,.close');if(f)f.focus();}
function closeM(id){el(id).className='modal';if(lastFocus&&lastFocus.focus)lastFocus.focus();}
function markSelected(attr,val){var a=document.querySelectorAll('[data-'+attr+']');for(var i=0;i<a.length;i++){var on=a[i].getAttribute('data-'+attr)===val;a[i].classList.toggle('selected',on);a[i].setAttribute('aria-pressed',on?'true':'false');}}
function opponentKey(){return mode==='two'?'two':difficulty;}
function opponentLabel(){if(mode==='two')return 'Другой игрок';return 'ИИ · '+(difficulty==='easy'?'лёгкий':difficulty==='hard'?'сложный':'средний');}
function ruleLabel(){return rule==='C'?'C · стек 2':rule==='D'?'D · лестница':'CD · стек 2 + лестница';}
function styleLabel(){return styleChoice==='mixed'?'Смешанная':styleChoice==='architect'?'Архитектор':styleChoice==='hunter'?'Охотник':styleChoice==='sentinel'?'Страж':'Ловкач';}
function updateSettingsUI(){el('rulesValue').textContent=ruleLabel();el('opponentValue').textContent=opponentLabel();el('strategyValue').textContent=mode==='solo'?styleLabel():'—';el('strategy').disabled=mode!=='solo';markSelected('rule',rule);markSelected('opponent',opponentKey());markSelected('style',styleChoice);if(el('themeValue'))el('themeValue').textContent=themeLabel();markSelected('theme-choice',themeChoice);}

function start(first){gameFirst=first||L;state=empty(gameFirst);history=[];sel=null;aiBusy=false;gameSeed=((Date.now()^(gameNo*2654435761))>>>0)||1;choosePersona();render();if(mode==='solo'&&state.turn===computer)setTimeout(aiTurn,180);}
function resetSession(){gameNo=1;start(L);}
function select(r){if(state.status!=='playing'||aiBusy||(mode==='solo'&&state.turn===computer)||!has(state.remaining[state.turn],r))return;sel=(sel===r?null:r);render();}
function play(c){if(state.status!=='playing'||aiBusy)return;if(sel===null){if(state.board[c].length){var a=state.board[c],s='Клетка '+(c+1)+': ';for(var i=a.length-1;i>=0;i--)s+=name(a[i].player)+' '+a[i].rank+(i?' → ':'');msg(s);}return;}if(!legal(state,state.turn,sel,c))return;var m={p:state.turn,r:sel,c:c};history.push(m);state=apply(state,m);sel=null;render();if(mode==='solo'&&state.status==='playing'&&state.turn===computer){aiBusy=true;msg('Компьютер думает…');setTimeout(aiTurn,120);}}
function aiTurn(){if(mode!=='solo'||state.status!=='playing'||state.turn!==computer){aiBusy=false;return;}var result=chooseMove(state,{rule:rule,difficulty:difficulty,persona:aiPersona,seed:(gameSeed+state.moves*2246822519)>>>0});var move=result&&result.move?{p:result.move.player,r:result.move.rank,c:result.move.cell}:null;if(move){history.push(move);state=apply(state,move);}aiBusy=false;render();}

function boardPieceSize(r){return{w:30+r*6.2,h:22+r*4.6};}
function pieceNode(p,r){var d=document.createElement('div'),z=boardPieceSize(r);d.className='bp '+p;d.style.width=z.w+'px';d.style.height=z.h+'px';d.textContent=r;return d;}
function renderRes(p,id){var box=el(id),r,b,chosen;box.innerHTML='';for(r=1;r<=9;r++){b=document.createElement('button');chosen=sel===r&&state.turn===p;b.className='pieceBtn '+p+(chosen?' sel':'');b.style.setProperty('--rank',r);b.setAttribute('aria-label',name(p)+' · фигура '+r);b.setAttribute('aria-pressed',chosen?'true':'false');b.disabled=!has(state.remaining[p],r)||state.status!=='playing'||(mode==='solo'&&p===computer)||state.turn!==p||aiBusy;b.innerHTML='<span>'+r+'</span><i class="shape"></i>';(function(rr){b.onclick=function(){select(rr);};})(r);box.appendChild(b);}}
function fitBoard(){var app=document.querySelector('.app'),board=el('board');if(!app||!board)return;var kids=Array.prototype.slice.call(app.children),used=0;for(var i=0;i<kids.length;i++){var n=kids[i];if(n===board)continue;var st=getComputedStyle(n);used+=n.offsetHeight+(parseFloat(st.marginTop)||0)+(parseFloat(st.marginBottom)||0);}var ast=getComputedStyle(app),gap=parseFloat(ast.rowGap||ast.gap||0)||0;used+=gap*(kids.length-1)+(parseFloat(ast.paddingTop)||0)+(parseFloat(ast.paddingBottom)||0)+8;var maxW=Math.min(app.clientWidth-2,window.innerWidth-14,540);var maxH=Math.min(window.innerHeight-used,window.innerHeight*.62);var size=Math.min(maxW,maxH);if(size<210)size=210;board.style.width=size+'px';board.style.height=size+'px';}
function render(){updateSettingsUI();el('turn').textContent=state.status==='playing'?'ХОД: '+name(state.turn):(state.status==='draw'?'НИЧЬЯ':name(state.turn)+' ПОБЕДИЛИ');el('dn').className='side dark'+(state.turn===K?' activeName':'');el('ln').className='side light'+(state.turn===L?' activeName':'');el('dh').textContent=mode==='solo'?'КОМПЬЮТЕР · '+personaName():'';el('lh').textContent=mode==='solo'?'ВЫ':'';renderRes(K,'darkRes');renderRes(L,'lightRes');var b=el('board');b.innerHTML='';var lastCell=history.length?history[history.length-1].c:-1;for(var c=0;c<9;c++){var e=document.createElement('button');e.className='cell';if(sel!==null&&legal(state,state.turn,sel,c))e.className+=' legal';if(state.winLine&&state.winLine.indexOf(c)>=0)e.className+=' win';if(c===lastCell)e.className+=' last';var t=top(state,c);var depth=state.board[c].length;e.setAttribute('aria-label','Клетка '+(c+1)+(t?' · '+name(t.player)+' '+t.rank:' · пусто'));if(t){e.className+=' '+t.player;if(depth>1)e.className+=' stacked';e.appendChild(pieceNode(t.player,t.rank));}if(depth>1){var d=document.createElement('span');d.className='depth';d.textContent='×'+depth;e.appendChild(d);}(function(cc){e.onclick=function(){play(cc);};})(c);b.appendChild(e);}el('undo').disabled=!history.length||aiBusy;el('next').disabled=state.status==='playing'||aiBusy;if(state.status==='playing'){el('end').className='end';if(!aiBusy)msg((mode==='solo'&&state.turn===computer)?'Ход компьютера.':name(state.turn)+': выберите размер.');}else{el('end').className='end open';el('endTitle').textContent=state.status==='draw'?'НИЧЬЯ':name(state.turn)+' ПОБЕДИЛИ';el('endInfo').textContent=state.moves+' ходов';msg('Партия завершена.');}fitBoard();}
function undo(){if(!history.length||aiBusy)return;var h=history.slice(),n=1;if(mode==='solo'&&h.length>=2&&h[h.length-1].p===computer)n=2;h=h.slice(0,-n);var s=empty(gameFirst),i;history=[];for(i=0;i<h.length;i++){var next=apply(s,h[i]);if(!next)break;s=next;history.push(h[i]);}state=s;sel=null;render();}

el('rules').onclick=function(){openM('rulesM');};
el('opponent').onclick=function(){openM('opponentM');};
el('strategy').onclick=function(){if(mode==='solo')openM('strategyM');};
el('theme').onclick=function(){openM('themeM');};
el('undo').onclick=undo;
el('reset').onclick=function(){if(confirm('Сбросить текущую партию?'))start(L);};
el('next').onclick=function(){if(state.status!=='playing'){gameNo++;start(gameNo%2?L:K);}};

document.addEventListener('keydown',function(e){if(e.key==='Escape'){var m=document.querySelector('.modal.open');if(m)closeM(m.id);}});
var cs=document.querySelectorAll('[data-close]');for(var i=0;i<cs.length;i++)cs[i].onclick=function(){closeM(this.getAttribute('data-close'));};
var rs=document.querySelectorAll('[data-rule]');for(i=0;i<rs.length;i++)rs[i].onclick=function(){rule=this.getAttribute('data-rule');closeM('rulesM');resetSession();};
var os=document.querySelectorAll('[data-opponent]');for(i=0;i<os.length;i++)os[i].onclick=function(){var v=this.getAttribute('data-opponent');if(v==='two'){mode='two';}else{mode='solo';difficulty=v;}closeM('opponentM');resetSession();};
var ss=document.querySelectorAll('[data-style]');for(i=0;i<ss.length;i++)ss[i].onclick=function(){styleChoice=this.getAttribute('data-style');closeM('strategyM');resetSession();};
var ts=document.querySelectorAll('[data-theme-choice]');for(i=0;i<ts.length;i++)ts[i].onclick=function(){themeChoice=this.getAttribute('data-theme-choice');applyTheme();closeM('themeM');fitBoard();};

loadTheme();
applyTheme();
start(L);
window.addEventListener('resize',fitBoard);
setTimeout(fitBoard,0);
