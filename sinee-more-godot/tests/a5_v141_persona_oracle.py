"""Independent test-only Python oracle for Godot v141 AI. Never loaded by game."""
from itertools import product
LINES=((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))
WEIGHTS=(2,3,2,3,5,3,2,3,2)
def legal(board,res,player,rule):
 return [(r,c) for r in range(1,10) if res[player-1][r-1] for c in range(9) if not board[c] or (board[c][-1][0]!=player and r>board[c][-1][1] and (rule=='D' or len(board[c])<2))]
def win(board,player,rule):
 for l in LINES:
  if all(board[c] and board[c][-1][0]==player for c in l):
   r=[board[c][-1][1] for c in l]
   if rule=='C' or r[0]<r[1]<r[2] or r[0]>r[1]>r[2]:return True
 return False
def after(board,res,player,move):
 r,c=move
 b=board.copy();b[c]=board[c].copy()+[(player,r)]
 z=res.copy();z[player-1]=res[player-1].copy();z[player-1][r-1]=False
 return b,z
def win_place(board,player,rule,move):
 r,c=move
 for line in LINES:
  if c not in line:continue
  if all(i==c or (board[i] and board[i][-1][0]==player) for i in line):
   ranks=[r if i==c else board[i][-1][1] for i in line]
   if rule=='C' or ranks[0]<ranks[1]<ranks[2] or ranks[0]>ranks[1]>ranks[2]:return True
 return False
def replies(board,res,player,rule):
 already=win(board,player,rule)
 return sum(already or win_place(board,player,rule,m) for m in legal(board,res,player,rule))
def choose(board,res,player,rule,difficulty,persona):
 cand=legal(board,res,player,rule)
 if not cand:return None
 if difficulty>=2:
  for m in cand:
   if win_place(board,player,rule,m):return m
 enemy=3-player;best=None;bs=float('-inf')
 spent_count=sum(not available for row in res for available in row) if difficulty==1 else 0
 for rank,cell in cand:
  covered=bool(board[cell]);nb,nr=after(board,res,player,(rank,cell));winning=win(nb,player,rule)
  if difficulty==1:
   score=WEIGHTS[cell]*.4+(10-rank)*.5-(3 if covered else 0)+((cell*7+rank*3+spent_count*5)%17)*2
   if persona==1 and covered:score+=2.0+rank*.2
   elif persona==2:score+=WEIGHTS[cell]*(rank-1)*.04
   if winning:score+=2
  else:
   score=WEIGHTS[cell]*3+(10-rank)*.65+(9 if covered else 0)
   if persona==1 and covered:score+=18.0+rank*.9
   elif persona==2:score+=WEIGHTS[cell]*(rank-1)*.15
   enemy_wins=replies(nb,nr,enemy,rule)
   score-=enemy_wins*(22000 if difficulty==3 else 12000)
   if difficulty==3:
    score+=replies(nb,nr,player,rule)*(90 if persona==2 else 200)
    if persona==2:score-=enemy_wins*6000
  if winning and difficulty>=2:score+=1000000
  if score>bs:bs=score;best=(rank,cell)
 return best

def match(rule,world):
 score=[0,0];round_no=1;rounds=0;total=0;ai=0
 while max(score)<3 and rounds<12:
  board=[[] for _ in range(9)];res=[[True]*9 for _ in range(2)];turn=1 if round_no%2 else 2;moves=0;over=False
  while not over and moves<18:
   opts=legal(board,res,turn,rule)
   if not opts:
    other=3-turn
    if legal(board,res,other,rule):turn=other;continue
    over=True;break
   if turn==1:m=opts[(round_no*17+moves*7)%len(opts)]
   else:m=choose(board,res,2,rule,3,0);ai+=1
   board,res=after(board,res,turn,m);moves+=1
   if win(board,turn,rule):score[turn-1]+=1;over=True
   else:
    turn=3-turn
    if not legal(board,res,turn,rule):
     other=3-turn
     if legal(board,res,other,rule):turn=other
     else:over=True
  total+=moves;rounds+=1;round_no+=1
 return score,rounds,total,ai
if __name__=='__main__':
 for w,r in product(range(7),('C','D','CD')):
  s,n,t,ai=match(r,w);print(w,r,s,n,t,ai)

def match_variant(rule, difficulty, persona, seed, max_rounds=12):
 import random
 rng=random.Random(seed)
 score=[0,0];round_no=1;rounds=0;ai_moves=0
 while max(score)<3 and rounds<max_rounds:
  board=[[] for _ in range(9)];res=[[True]*9 for _ in range(2)];turn=1 if round_no%2 else 2;moves=0
  while moves<18:
   opts=legal(board,res,turn,rule)
   if not opts:
    other=3-turn
    if legal(board,res,other,rule):turn=other;continue
    break
   if turn==1:m=rng.choice(opts)
   else:m=choose(board,res,2,rule,difficulty,persona);ai_moves+=1
   board,res=after(board,res,turn,m);moves+=1
   if win(board,turn,rule):score[turn-1]+=1;break
   turn=3-turn
   if not legal(board,res,turn,rule):
    other=3-turn
    if legal(board,res,other,rule):turn=other
    else:break
  rounds+=1;round_no+=1
 return score,rounds,ai_moves
if __name__=='__main__':
 import time
 t=time.time()
 for rule,d,p in product(('C','D','CD'),(1,2,3),(0,1,2)):
  results=[match_variant(rule,d,p,seed) for seed in range(8)]
  wins=sum(1 for s,_,_ in results if s[1]==3);losses=sum(1 for s,_,_ in results if s[0]==3)
  print('AI',rule,d,p,'wins',wins,'losses',losses,'unresolved',8-wins-losses)
 print('elapsed',round(time.time()-t,1))
if __name__=='__main__':
 import random
 rng=random.Random(321)
 for rule in ('C','D','CD'):
  states=[]
  for trial in range(400):
   board=[[] for _ in range(9)];res=[[True]*9 for _ in range(2)];turn=1
   for j in range(rng.randint(1,12)):
    opts=legal(board,res,turn,rule)
    if not opts:
     turn=3-turn;opts=legal(board,res,turn,rule)
     if not opts:break
    board,res=after(board,res,turn,rng.choice(opts))
    if win(board,turn,rule):break
    turn=3-turn
   if not win(board,1,rule) and not win(board,2,rule) and legal(board,res,2,rule):states.append((board,res))
  choices=[tuple(choose(b,r,2,rule,d,p) for d,p in ((1,0),(2,0),(3,0),(3,1),(3,2))) for b,r in states]
  print('DIVERGENCE',rule,'states',len(choices),'easy_vs_hard',sum(x[0]!=x[2] for x in choices),'normal_vs_hard',sum(x[1]!=x[2] for x in choices),'hard_balanced_vs_aggressive',sum(x[2]!=x[3] for x in choices),'hard_balanced_vs_defensive',sum(x[2]!=x[4] for x in choices))
