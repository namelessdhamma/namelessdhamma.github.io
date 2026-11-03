import './app-shell.js';
import {
  LIGHT as L, DARK as K, otherPlayer, usesStack2, usesLadder
} from './ai/constants.js';
import {
  createInitialPosition, clonePosition, topPiece, isLegalMove, getLegalMoves, applyMove
} from './ai/rules.js';
import { chooseMove } from './ai/engine.js';
import { PERSONAS, selectPersonaAtGameStart } from './ai/personas.js';
import { t } from './i18n.js';
import { startTutorial, stopTutorial, tutorialRender } from './tutorial.js';

'use strict';

var rule='C',mode='solo',difficulty='medium',styleChoice='mixed',
    aiPersona='architect',lastPersona='',human=L,computer=K,state,sel=null,
    gameNo=1,gameSeed=1,aiBusy=false,themeChoice='nd';
var history=[],gameFirst=L,lastFocus=null;
var fx=null,calm=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);

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
function personaName(){return t(PERSONAS[aiPersona]?aiPersona:'architect');}
function name(p){return t(p===L?'light':'dark');}
function el(id){return document.getElementById(id);}
function msg(x){el('msg').textContent=x;}
// Тему хранит оболочка меню: так стартовый экран и игра всегда в одной теме.
function loadTheme(){themeChoice=window.SineeMoreAppShell.loadConfig().environmentId;}
function themeLabel(){return themeChoice==='pirate'?'Pirate Chart':themeChoice==='atlantis'?'Atlantis':'ND Premium';}
function applyTheme(){
  document.body.setAttribute('data-theme',themeChoice);
  var tv=el('themeValue');if(tv)tv.textContent=themeLabel();
  markSelected('theme-choice',themeChoice);
  if(themeChoice==='pirate')PIRATE_ART.forEach(function(n){new Image().src='./assets/'+n+'.png';});
  var meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.setAttribute('content',themeChoice==='pirate'?'#2a160e':themeChoice==='atlantis'?'#031923':'#000000');
  try{localStorage.setItem('sinee-more-theme',themeChoice);}catch(e){}
}

function openM(id){lastFocus=document.activeElement;var m=el(id);m.className='modal open';var f=m.querySelector('.selected,.choice,.close');if(f)f.focus();}
function closeM(id){el(id).className='modal';if(lastFocus&&lastFocus.focus)lastFocus.focus();}
function markSelected(attr,val){var a=document.querySelectorAll('[data-'+attr+']');for(var i=0;i<a.length;i++){var on=a[i].getAttribute('data-'+attr)===val;a[i].classList.toggle('selected',on);a[i].setAttribute('aria-pressed',on?'true':'false');}}
function opponentKey(){return mode==='two'?'two':difficulty;}
function opponentLabel(){if(mode==='two')return t('valTwo');return t('valAi',{level:t(difficulty==='easy'||difficulty==='hard'?difficulty:'medium')});}
function ruleLabel(){return t(rule==='C'?'valC':rule==='D'?'valD':'valCD');}
function styleLabel(){return t(styleChoice==='mixed'?'valMixed':styleChoice==='architect'?'valArchitect':styleChoice==='hunter'?'valHunter':styleChoice==='sentinel'?'valSentinel':'valTrickster');}
function updateSettingsUI(){el('rulesValue').textContent=ruleLabel();el('opponentValue').textContent=opponentLabel();el('strategyValue').textContent=mode==='solo'?styleLabel():'—';el('strategy').disabled=mode!=='solo';markSelected('rule',rule);markSelected('opponent',opponentKey());markSelected('style',styleChoice);if(el('themeValue'))el('themeValue').textContent=themeLabel();markSelected('theme-choice',themeChoice);}

function start(first){stopTutorial();endFx(false);gameFirst=first||L;state=empty(gameFirst);history=[];sel=null;aiBusy=false;gameSeed=((Date.now()^(gameNo*2654435761))>>>0)||1;choosePersona();render();if(mode==='solo'&&state.turn===computer)setTimeout(aiTurn,180);}
function resetSession(){gameNo=1;start(L);}
function select(r){if(state.status!=='playing'||aiBusy||(mode==='solo'&&state.turn===computer)||!has(state.remaining[state.turn],r))return;sel=(sel===r?null:r);render();}
function play(c){if(state.status!=='playing'||aiBusy)return;if(sel===null){if(state.board[c].length){var a=state.board[c],s=t('cell',{n:c+1})+': ';for(var i=a.length-1;i>=0;i--)s+=name(a[i].player)+' '+a[i].rank+(i?' → ':'');msg(s);}return;}if(!legal(state,state.turn,sel,c))return;var m={p:state.turn,r:sel,c:c};history.push(m);state=apply(state,m);sel=null;carry(m,function(){if(mode==='solo'&&state.status==='playing'&&state.turn===computer){aiBusy=true;msg(t('thinking'));setTimeout(aiTurn,120);}});}
function aiTurn(){if(mode!=='solo'||state.status!=='playing'||state.turn!==computer){aiBusy=false;return;}var result=chooseMove(state,{rule:rule,difficulty:difficulty,persona:aiPersona,seed:(gameSeed+state.moves*2246822519)>>>0});var move=result&&result.move?{p:result.move.player,r:result.move.rank,c:result.move.cell}:null;if(move){history.push(move);state=apply(state,move);}aiBusy=false;if(move)carry(move,null);else render();}

// Перенос фишки: ход уже сделан, носитель только показывает его.
// Пока фишка летит (fx.hold), клетка показывает то, что было под ней, а победа и итог ждут посадки.
var FX_LAND=800,FX_END=1000;
function ease(u){return u<.5?4*u*u*u:1-Math.pow(-2*u+2,3)/2;}
function lerp(a,b,u){return{x:a.x+(b.x-a.x)*u,y:a.y+(b.y-a.y)*u};}
function centre(r){return{x:r.left+r.width/2,y:r.top+r.height/2};}
function endFx(run){var f=fx;if(!f)return;fx=null;cancelAnimationFrame(f.raf);f.timers.forEach(clearTimeout);if(f.layer&&f.layer.parentNode)f.layer.parentNode.removeChild(f.layer);if(run){render();if(f.done)f.done();}}
function carry(m,done){
  endFx(true);
  fx={c:m.c,hold:true,done:done,timers:[],raf:0,layer:null};
  render();
  var probe=el('board').querySelector('.probe'),btn=el(m.p===L?'lightRes':'darkRes').children[m.r-1],shape=btn&&btn.querySelector('.shape');
  if(calm){endFx(true);var bp=el('board').children[m.c].querySelector('.bp');if(bp&&bp.animate)bp.animate([{opacity:0},{opacity:1}],{duration:220,easing:'ease-out'});return;}
  var pr=probe.getBoundingClientRect(),sr=shape.getBoundingClientRect(),W=Math.max(70,pr.width*1.9);
  var g={src:centre(sr),dst:centre(pr),s0:Math.min(1,sr.width/pr.width),W:W,ph:pr.height,pw:pr.width,cell:probe.parentNode.offsetWidth,dir:m.p===L?1:-1,side:m.p,lift:pr.height*.4,t0:performance.now(),spark:0};
  var layer=document.createElement('div');layer.className='fx';
  g.piece=pieceNode(m.p,m.r);g.piece.style.left=pr.left+'px';g.piece.style.top=pr.top+'px';g.piece.style.paddingTop=getComputedStyle(probe).paddingTop;layer.appendChild(g.piece);
  if(themeChoice==='nd'){g.orb=document.createElement('div');g.orb.className='carrier '+m.p;g.orb.style.width=g.orb.style.height=W+'px';layer.insertBefore(g.orb,g.piece);g.edge={x:g.src.x,y:g.dir>0?innerHeight+W/2:-W/2};}
  else if(themeChoice==='pirate')makeHand(g,layer,PIRATE_HAND[m.p]);
  else if(m.p===L)makeTentacle(g,layer);
  else makeClaw(g,layer);
  document.body.appendChild(layer);fx.layer=layer;fx.g=g;
  fx.timers.push(setTimeout(landFx,FX_LAND),setTimeout(function(){endFx(true);},FX_END));
  drawFx();
}
function landFx(){
  if(!fx)return;var g=fx.g;fx.hold=false;
  if(g.piece.parentNode)g.piece.parentNode.removeChild(g.piece);
  render();
  if(g.orb)spark(g,g.dst,'flash',g.W*.9,200);
}
function spark(g,p,kind,size,ms){var s=document.createElement('div');s.className=kind+' '+g.side;s.style.width=s.style.height=size+'px';var x=p.x-size/2,y=p.y-size/2,dx=(Math.random()-.5)*18,dy=g.dir*(8+Math.random()*14);s.style.transform='translate('+x+'px,'+y+'px)';fx.layer.appendChild(s);var a=kind==='flash'?[{transform:'translate('+x+'px,'+y+'px) scale(.35)',opacity:1},{transform:'translate('+x+'px,'+y+'px) scale(1.2)',opacity:0}]:[{transform:'translate('+x+'px,'+y+'px) scale(1)',opacity:1},{transform:'translate('+(x+dx)+'px,'+(y+dy)+'px) scale(.2)',opacity:0}];if(s.animate)s.animate(a,{duration:ms,easing:'ease-out',fill:'forwards'}).onfinish=function(){if(s.parentNode)s.parentNode.removeChild(s);};}
// Фаза A (0–200 мс): носитель приходит к фишке в полоске; B (до 800): несёт её; C (до 1000): уходит.
function drawFx(){
  if(!fx||!fx.g)return;var g=fx.g,k=performance.now()-g.t0,c,s,u;
  if(k<200){c=g.src;s=g.s0;}
  else if(k<FX_LAND){u=ease((k-200)/(FX_LAND-200));c=lerp(g.src,g.dst,u);s=g.s0+(1-g.s0)*u+.08*Math.sin(Math.PI*u);}
  else{c=g.dst;s=1;}
  if(fx.hold)place(g,c,s);
  if(g.orb)drawOrb(g,k,c);
  if(g.hand)drawHand(g,k,c,s);
  if(g.dact)drawClaw(g,k);
  if(g.tent)drawTentacle(g,k,c,s);
  if(k<FX_END)fx.raf=requestAnimationFrame(drawFx);
}
function place(g,p,s){g.piece.style.transform='translate('+(p.x-g.dst.x)+'px,'+(p.y-g.dst.y)+'px) scale('+s+')';}
function drawOrb(g,k,c){
  var o=c,op=1,os=1,u;
  if(k<200){u=ease(k/200);o=lerp(g.edge,g.src,u);op=u;}
  else if(k>=FX_LAND){u=Math.min(1,(k-FX_LAND)/(FX_END-FX_LAND));o={x:c.x,y:c.y+g.dir*24*u};op=1-u;os=1-.5*u;}
  o={x:o.x,y:o.y-g.lift};
  g.orb.style.opacity=op;g.orb.style.transform='translate('+(o.x-g.W/2)+'px,'+(o.y-g.W/2)+'px) scale('+os+')';
  if(k<FX_LAND&&k-g.spark>30){g.spark=k;spark(g,{x:o.x+(Math.random()-.5)*g.W*.45,y:o.y+(Math.random()-.5)*g.W*.45},'spark',4+Math.random()*4,450);}
}

// Кисть (крюк или перчатка) без руки: влетает из-за края экрана, держит фишку в точке хвата, улетает обратно.
// w — ширина картинки в долях клетки; ratio — её высота к ширине; gx, gy — точка хвата в долях ширины
// и высоты картинки; px, py — где хват на фишке: доли её ширины и высоты от центра.
// Крюк цепляет колпак за верх справа, чтобы стержень не закрывал цифру.
var PIRATE_HAND={light:{w:.26,ratio:3.233,gx:.36,gy:.03,px:.22,py:-.5},dark:{w:.48,ratio:1.933,gx:.56,gy:.93,px:0,py:-.5}};
var PIRATE_ART=['pirate-hook','pirate-glove'];
function makeHand(g,layer,hand){
  var A=g.cell*hand.w,Hh=A*hand.ratio;
  g.hand=document.createElement('div');g.hand.className='hand '+g.side;
  g.hand.style.width=A+'px';g.hand.style.height=Hh+'px';
  g.gripX=A*hand.gx;g.gripY=Hh*hand.gy;g.Hh=Hh;g.px=hand.px;g.py=hand.py;
  layer.appendChild(g.hand);
}
function gripAt(g,c,s){return{x:c.x+g.px*g.pw*s,y:c.y+g.py*g.ph*s};}
function drawHand(g,k,c,s){
  // Точка хвата, при которой картинка целиком за краем экрана.
  var off=g.dir>0?innerHeight+g.gripY+14:g.gripY-g.Hh-14,h=gripAt(g,c,s),u;
  if(k<200){u=ease(k/200);h=lerp({x:g.src.x,y:off},h,u);}
  else if(k>=FX_LAND){u=ease(Math.min(1,(k-FX_LAND)/(FX_END-FX_LAND)));h=lerp(h,{x:h.x,y:off},u);}
  g.hand.style.transform='translate('+(h.x-g.gripX)+'px,'+(h.y-g.gripY)+'px)';
}

// Atlantis, тёмные: клешня краба нарисована кодом и летает как кисть Pirate (makeHand/drawHand).
// Подвижный палец открыт на подлёте, смыкается на верхушке пирамиды и разжимается при посадке.
var ATLANTIS_CLAW={w:.62,ratio:1.95,gx:.5,gy:.949,px:0,py:-.2};
// Ладонь заодно с неподвижным пальцем; подвижный палец (dact) крепится справа на шарнире (26,-70).
var CLAW_PALM='M-18,-182C-38,-160 -50,-110 -42,-70C-36,-40 -22,-10 -4,4L-8,-4L-12,-14L-9,-22L-13,-30L-8,-38L-11,-46L-5,-54L-2,-58L14,-66C32,-74 46,-92 46,-112C46,-146 34,-168 18,-182Z';
// Тёмные кончики пальцев — отдельные фигуры поверх пальцев.
var CLAW_SVG='<svg viewBox="-60 -222 120 234" width="100%" height="100%">'+
  '<defs><linearGradient id="clawShell" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ff9466"/><stop offset=".55" stop-color="#d4462c"/><stop offset="1" stop-color="#7c1c11"/></linearGradient></defs>'+
  '<g stroke="#3b0c07" stroke-width="1.8" stroke-linejoin="round">'+
  '<path fill="url(#clawShell)" d="M-15,-178C-18,-194 -15,-208 -8,-214Q0,-220 8,-214C15,-208 18,-194 15,-178Z"/>'+
  '<path fill="url(#clawShell)" d="'+CLAW_PALM+'"/>'+
  '<path fill="#6e1a0e" stroke="none" d="M-40,-50C-34,-26 -20,-6 -4,4L-8,-4L-12,-14L-9,-22L-13,-30L-8,-38L-11,-46Z"/>'+
  '<path fill="#1e0805" stroke="none" d="M-31,-22C-24,-10 -14,-2 -4,4L-8,-4L-12,-14L-10,-20Z"/>'+
  '<g class="dact"><path fill="#c13d25" d="M12,-64C22,-80 40,-86 44,-72C48,-44 34,-10 6,8L9,-2L13,-12L9,-20L14,-28L9,-36L13,-44L6,-52Z"/>'+
  '<path fill="#6e1a0e" stroke="none" d="M45,-46C42,-24 28,-6 6,8L9,-2L13,-12L9,-20L14,-28L9,-36L13,-44Z"/>'+
  '<path fill="#1e0805" stroke="none" d="M37,-20C30,-8 20,0 6,8L9,-2L13,-12L11,-18Z"/></g>'+
  '</g>'+
  '<path d="M-16,-180Q0,-186 16,-180" fill="none" stroke="#3b0c07" stroke-width="2.5"/>'+
  '<path d="M12,-170C28,-140 30,-106 18,-78" fill="none" stroke="#5e140b" stroke-width="3" opacity=".4"/>'+
  '<path fill="#ffb58f" opacity=".45" d="M-21,-120a2.5,2.5 0 1,0 5,0a2.5,2.5 0 1,0 -5,0M-9,-150a2.5,2.5 0 1,0 5,0a2.5,2.5 0 1,0 -5,0M-29,-96a2.5,2.5 0 1,0 5,0a2.5,2.5 0 1,0 -5,0M-11,-96a2.5,2.5 0 1,0 5,0a2.5,2.5 0 1,0 -5,0M-3,-124a2.5,2.5 0 1,0 5,0a2.5,2.5 0 1,0 -5,0"/>'+
  '<path fill="#5e140b" opacity=".5" d="M21,-122a3,3 0 1,0 6,0a3,3 0 1,0 -6,0M19,-160a3,3 0 1,0 6,0a3,3 0 1,0 -6,0M27,-100a3,3 0 1,0 6,0a3,3 0 1,0 -6,0"/>'+
  '<ellipse cx="-26" cy="-124" rx="5" ry="28" fill="#fff" opacity=".22" transform="rotate(8 -26 -124)"/>'+
  '</svg>';
function makeClaw(g,layer){makeHand(g,layer,ATLANTIS_CLAW);g.hand.innerHTML=CLAW_SVG;g.dact=g.hand.querySelector('.dact');}
function drawClaw(g,k){
  var a=k<120?1:k<200?1-ease((k-120)/80):k<FX_LAND?0:ease(Math.min(1,(k-FX_LAND)/80));
  g.dact.setAttribute('transform','rotate('+(-30*a)+' 26 -70)');
}

// Atlantis, светлые: щупальце рисуется кодом каждый кадр. Основание за нижним краем экрана,
// тело изгибается и колышется, кончик обвивает подножие пирамиды под цифрой; присоски смотрят на фишку.
// На подлёте щупальце вырастает до фишки, после посадки втягивается обратно.
function svgEl(tag,cls,parent){var e=document.createElementNS('http://www.w3.org/2000/svg',tag);if(cls)e.setAttribute('class',cls);if(parent)parent.appendChild(e);return e;}
function makeTentacle(g,layer){
  g.tent=svgEl('svg','tentacle');
  g.tp={};['body','belly','shine','rims','cups'].forEach(function(n){g.tp[n]=svgEl('path',n,g.tent);});
  g.W0=g.cell*.42;g.base={x:g.src.x-g.cell*.1,y:innerHeight+g.W0};
  // С какой стороны щупальце подходит и обвивает фишку, решается один раз (1 — справа): иначе тело прыгает,
  // когда кончик пересекает основание, а подход с дальней стороны перечёркивает цифру.
  g.bow=g.base.x>=g.dst.x?1:-1;
  layer.appendChild(g.tent);
}
function bez(a,b,c,d,v){var m=1-v;return{x:m*m*m*a.x+3*m*m*v*b.x+3*m*v*v*c.x+v*v*v*d.x,y:m*m*m*a.y+3*m*m*v*b.y+3*m*v*v*c.y+v*v*v*d.y};}
// Полоса вдоль осевой линии: сдвиг off и полуширина half — в долях толщины.
function band(P,N,Wd,off,half){var a='',b='',i,o,h;for(i=0;i<P.length;i++){o=Wd[i]*off;h=Wd[i]*half;a+=(i?'L':'M')+(P[i].x+N[i].x*(o+h)).toFixed(1)+','+(P[i].y+N[i].y*(o+h)).toFixed(1);b='L'+(P[i].x+N[i].x*(o-h)).toFixed(1)+','+(P[i].y+N[i].y*(o-h)).toFixed(1)+b;}return a+b+'Z';}
function drawTentacle(g,k,c,s){
  var p=k<200?ease(k/200):k<FX_LAND?1:1-ease(Math.min(1,(k-FX_LAND)/(FX_END-FX_LAND)));
  var rx=g.pw*.56*s,ry=g.ph*.2*s,o={x:c.x,y:c.y+g.ph*.5*s-ry*.5},J={x:o.x+g.bow*rx,y:o.y},B=g.base;
  var c1={x:B.x+g.bow*g.cell*.9,y:B.y-(B.y-J.y)*.45},c2={x:J.x+g.bow*g.cell*.15,y:J.y-g.cell*.45};
  var dx=J.x-B.x,dy=J.y-B.y,dl=Math.hypot(dx,dy)||1,wx=dy/dl,wy=-dx/dl,amp=g.cell*.15,P=[],i,v,q,f;
  for(i=0;i<=40;i++){v=i/40;q=bez(B,c1,c2,J,v);f=amp*Math.sin(v*6-k*.009)*Math.sin(Math.PI*v);P.push({x:q.x+wx*f,y:q.y+wy*f});}
  for(i=1;i<=16;i++){f=Math.PI-i/16*(Math.PI+1);P.push({x:o.x-g.bow*rx*Math.cos(f),y:o.y+ry*Math.sin(f)});}
  // Длина вдоль линии; рисуем только долю p от основания.
  var S=[0];for(i=1;i<P.length;i++)S.push(S[i-1]+Math.hypot(P[i].x-P[i-1].x,P[i].y-P[i-1].y));
  var Lp=S[S.length-1]*p,Q=[P[0]],QL=[0];
  for(i=1;i<P.length&&S[i]<Lp;i++){Q.push(P[i]);QL.push(S[i]);}
  if(i<P.length&&Lp>S[i-1]){f=(Lp-S[i-1])/(S[i]-S[i-1]);Q.push(lerp(P[i-1],P[i],f));QL.push(Lp);}
  if(Q.length<3){for(q in g.tp)g.tp[q].setAttribute('d','');return;}
  // Нормаль смотрит внутрь витка: туда же обращены присоски. Толщина сходит на нет к кончику,
  // а в витке не больше его высоты, чтобы виток не наползал на цифру.
  var N=[],Wd=[],Lt=S[S.length-1],sd=-g.bow;
  for(i=0;i<Q.length;i++){var a=Q[Math.max(0,i-1)],b=Q[Math.min(Q.length-1,i+1)],tx=b.x-a.x,ty=b.y-a.y,tl=Math.hypot(tx,ty)||1;N.push({x:sd*ty/tl,y:-sd*tx/tl});Wd.push(Math.min(3+(g.W0-3)*Math.pow((Lp-QL[i])/Lt,.8),Math.max(3,1.2*ry)+Math.max(0,S[40]-QL[i])*.35));}
  g.tp.body.setAttribute('d',band(Q,N,Wd,0,.5));
  g.tp.belly.setAttribute('d',band(Q,N,Wd,.25,.22));
  g.tp.shine.setAttribute('d',band(Q,N,Wd,-.27,.07));
  // Присоски в два ряда у внутреннего края, от кончика к основанию; между точками линии — по интерполяции.
  var rims='',cups='',n=0,l=Lp-5,j=Q.length-1,w,x,y,r,e,nx,ny;
  while(l>0){while(j>1&&QL[j-1]>l)j--;f=(l-QL[j-1])/(QL[j]-QL[j-1]);
    w=Wd[j-1]+(Wd[j]-Wd[j-1])*f;nx=N[j-1].x+(N[j].x-N[j-1].x)*f;ny=N[j-1].y+(N[j].y-N[j-1].y)*f;
    e=w*(n++%2?.34:.45);r=w*.13;x=Q[j-1].x+(Q[j].x-Q[j-1].x)*f+nx*e;y=Q[j-1].y+(Q[j].y-Q[j-1].y)*f+ny*e;l-=Math.max(3,w*.3);
    if(r<.8||y-r>innerHeight)continue;
    rims+='M'+(x-r).toFixed(1)+','+y.toFixed(1)+'a'+r.toFixed(1)+','+r.toFixed(1)+' 0 1,0 '+(2*r).toFixed(1)+',0a'+r.toFixed(1)+','+r.toFixed(1)+' 0 1,0 '+(-2*r).toFixed(1)+',0';
    r*=.5;cups+='M'+(x-r).toFixed(1)+','+y.toFixed(1)+'a'+r.toFixed(1)+','+r.toFixed(1)+' 0 1,0 '+(2*r).toFixed(1)+',0a'+r.toFixed(1)+','+r.toFixed(1)+' 0 1,0 '+(-2*r).toFixed(1)+',0';}
  g.tp.rims.setAttribute('d',rims);g.tp.cups.setAttribute('d',cups);
}

function boardPieceSize(r){return{w:30+r*6.2,h:22+r*4.6};}
function pieceNode(p,r){var d=document.createElement('div'),z=boardPieceSize(r);d.className='bp '+p;d.style.width=z.w+'px';d.style.height=z.h+'px';d.textContent=r;return d;}
function renderRes(p,id){var box=el(id),r,b,chosen;box.innerHTML='';for(r=1;r<=9;r++){b=document.createElement('button');chosen=sel===r&&state.turn===p;b.className='pieceBtn '+p+(chosen?' sel':'')+(has(state.remaining[p],r)?'':' used');b.style.setProperty('--rank',r);b.setAttribute('aria-label',t('piece',{side:name(p),r:r}));b.setAttribute('aria-pressed',chosen?'true':'false');b.disabled=!has(state.remaining[p],r)||state.status!=='playing'||(mode==='solo'&&p===computer)||state.turn!==p||aiBusy;b.innerHTML='<span>'+r+'</span><i class="shape"></i>';(function(rr){b.onclick=function(){select(rr);};})(r);box.appendChild(b);}}
function fitBoard(){var app=document.querySelector('.app'),board=el('board');if(!app||!board)return;var kids=Array.prototype.slice.call(app.children),used=0;for(var i=0;i<kids.length;i++){var n=kids[i];if(n===board)continue;var st=getComputedStyle(n);used+=n.offsetHeight+(parseFloat(st.marginTop)||0)+(parseFloat(st.marginBottom)||0);}var ast=getComputedStyle(app),gap=parseFloat(ast.rowGap||ast.gap||0)||0;used+=gap*(kids.length-1)+(parseFloat(ast.paddingTop)||0)+(parseFloat(ast.paddingBottom)||0)+8;var maxW=Math.min(app.clientWidth-2,window.innerWidth-14,540);var maxH=Math.min(window.innerHeight-used,window.innerHeight*.62);var size=Math.min(maxW,maxH);if(size<210)size=210;board.style.width=size+'px';board.style.height=size+'px';}
function render(){updateSettingsUI();el('turn').textContent=state.status==='playing'?t('turn',{side:name(state.turn)}):(state.status==='draw'?t('draw'):t('win',{side:name(state.turn)}));el('dn').className='side dark'+(state.turn===K?' activeName':'');el('ln').className='side light'+(state.turn===L?' activeName':'');el('dh').textContent=mode==='solo'?t('computer',{name:personaName()}):'';el('lh').textContent=mode==='solo'?t('you'):'';renderRes(K,'darkRes');renderRes(L,'lightRes');var b=el('board');b.innerHTML='';var lastCell=history.length?history[history.length-1].c:-1,hold=!!(fx&&fx.hold);for(var c=0;c<9;c++){var e=document.createElement('button');e.className='cell';if(sel!==null&&legal(state,state.turn,sel,c))e.className+=' legal';if(!hold&&state.winLine&&state.winLine.indexOf(c)>=0)e.className+=' win';if(c===lastCell)e.className+=' last';var tp=top(state,c);var depth=state.board[c].length,inc=null;if(hold&&c===fx.c){inc=tp;depth--;tp=depth?state.board[c][depth-1]:null;}e.setAttribute('aria-label',t('cell',{n:c+1})+' · '+(tp?name(tp.player)+' '+tp.rank:t('empty')));if(tp){e.className+=' '+tp.player;if(depth>1)e.className+=' stacked';e.appendChild(pieceNode(tp.player,tp.rank));}if(depth>1){var d=document.createElement('span');d.className='depth';d.textContent='×'+depth;e.appendChild(d);}if(inc){var pr=pieceNode(inc.player,inc.rank);pr.className+=' probe';e.appendChild(pr);}(function(cc){e.onclick=function(){play(cc);};})(c);b.appendChild(e);}el('undo').disabled=!history.length||aiBusy;el('next').disabled=state.status==='playing'||aiBusy||!!fx;if(fx&&state.status!=='playing'){el('end').className='end';}else if(state.status==='playing'){el('end').className='end';if(!aiBusy)msg((mode==='solo'&&state.turn===computer)?t('computerTurn'):t('pick',{side:name(state.turn)}));}else{el('end').className='end open';el('endTitle').textContent=state.status==='draw'?t('draw'):t('win',{side:name(state.turn)});el('endInfo').textContent=t('moves',{n:state.moves});msg(t('over'));}fitBoard();tutorialRender({sel:sel,moved:history.length>0,over:state.status!=='playing'&&!fx});}
function undo(){if(!history.length||aiBusy)return;endFx(false);var h=history.slice(),n=1;if(mode==='solo'&&h.length>=2&&h[h.length-1].p===computer)n=2;h=h.slice(0,-n);var s=empty(gameFirst),i;history=[];for(i=0;i<h.length;i++){var next=apply(s,h[i]);if(!next)break;s=next;history.push(h[i]);}state=s;sel=null;render();}

el('rules').onclick=function(){openM('rulesM');};
el('opponent').onclick=function(){openM('opponentM');};
el('strategy').onclick=function(){if(mode==='solo')openM('strategyM');};
el('theme').onclick=function(){openM('themeM');};
el('undo').onclick=undo;
el('reset').onclick=function(){if(confirm(t('resetConfirm')))start(L);};
el('next').onclick=function(){if(state.status!=='playing'){gameNo++;start(gameNo%2?L:K);}};

document.addEventListener('keydown',function(e){if(e.key==='Escape'){var m=document.querySelector('.modal.open');if(m)closeM(m.id);}});
var cs=document.querySelectorAll('[data-close]');for(var i=0;i<cs.length;i++)cs[i].onclick=function(){closeM(this.getAttribute('data-close'));};
var rs=document.querySelectorAll('[data-rule]');for(i=0;i<rs.length;i++)rs[i].onclick=function(){rule=this.getAttribute('data-rule');closeM('rulesM');resetSession();};
var os=document.querySelectorAll('[data-opponent]');for(i=0;i<os.length;i++)os[i].onclick=function(){var v=this.getAttribute('data-opponent');if(v==='two'){mode='two';}else{mode='solo';difficulty=v;}closeM('opponentM');resetSession();};
var ss=document.querySelectorAll('[data-style]');for(i=0;i<ss.length;i++)ss[i].onclick=function(){styleChoice=this.getAttribute('data-style');closeM('strategyM');resetSession();};
// Тема из игры сохраняется и в настройки стартового меню, чтобы «Начать игру» её не сбросил.
var ts=document.querySelectorAll('[data-theme-choice]');for(i=0;i<ts.length;i++)ts[i].onclick=function(){endFx(true);themeChoice=this.getAttribute('data-theme-choice');applyTheme();var sh=window.SineeMoreAppShell;if(sh)sh.saveConfig(Object.assign(sh.loadConfig(),{environmentId:themeChoice}));closeM('themeM');fitBoard();};
window.addEventListener('sinee-more:lang',function(){render();if(aiBusy)msg(t('thinking'));});
window.addEventListener('sinee-more:tutorial',function(){startTutorial(resetSession);});

window.addEventListener('sinee-more:product-config',function(event){
  var config=event&&event.detail?event.detail:null;
  if(config&&config.environmentId&&(config.environmentId==='nd'||config.environmentId==='pirate'||config.environmentId==='atlantis')){
    endFx(true);
    themeChoice=config.environmentId;
    applyTheme();
    fitBoard();
  }
});

loadTheme();
applyTheme();
start(L);
window.addEventListener('resize',fitBoard);
setTimeout(fitBoard,0);
