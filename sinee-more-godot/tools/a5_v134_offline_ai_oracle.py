LINES=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
WEIGHTS=[2,3,2,3,5,3,2,3,2]
def legal_dest(b,p,r,c,rule):
 s=b[c];return not s or (s[-1][0]!=p and r>s[-1][1] and not(rule in ('C','CD') and len(s)>=2))
def moves(b,res,p,rule):
 return [(r,c) for r in range(1,10) if res[p-1][r-1] for c in range(9) if legal_dest(b,p,r,c,rule)]
def win(b,p,rule):
 for line in LINES:
  if all(b[c] and b[c][-1][0]==p for c in line):
   ranks=[b[c][-1][1] for c in line]
   if rule=='C' or ranks[0]<ranks[1]<ranks[2] or ranks[0]>ranks[1]>ranks[2]:return line
 return []
def wins_after(b,p,rule,c,r):
 for line in LINES:
  if c not in line:continue
  if all(k==c or (b[k] and b[k][-1][0]==p) for k in line):
   ranks=[r if k==c else b[k][-1][1] for k in line]
   if rule=='C' or ranks[0]<ranks[1]<ranks[2] or ranks[0]>ranks[1]>ranks[2]:return True
 return False
def winning_replies(b,res,p,rule):
 already=bool(win(b,p,rule))
 return sum(already or wins_after(b,p,rule,c,r) for r,c in moves(b,res,p,rule))
def after(b,res,p,r,c):
 b2=[s[:] for s in b];re=[row[:] for row in res];b2[c].append((p,r));re[p-1][r-1]=False;return b2,re
def ai_choose(b,res,p,rule,difficulty=3,persona=0):
 cand=moves(b,res,p,rule)
 if not cand:return None
 if difficulty>=2:
  for r,c in cand:
   if wins_after(b,p,rule,c,r):return r,c
 enemy=3-p;best=None;best_score=float('-inf')
 for r,c in cand:
  covered=bool(b[c]);nb,nr=after(b,res,p,r,c)
  score=WEIGHTS[c]*3+(10-r)*0.65+(9 if covered else 0)
  if persona==1:score+=3 if covered else 0
  if persona==2:score+=2*WEIGHTS[c]
  if difficulty==1:score+=((c*7+r*3)%11)*0.4
  else:
   enemy_wins=winning_replies(nb,nr,enemy,rule)
   score-=enemy_wins*(22000 if difficulty==3 else 12000)
   if difficulty==3:
    own_threats=winning_replies(nb,nr,p,rule)
    score+=own_threats*(90 if persona==2 else 200)
    if persona==2:score-=enemy_wins*6000
  if win(nb,p,rule) and difficulty>=2:score+=1000000
  if score>best_score:best_score=score;best=r,c
 return best

def simulate(rule, max_rounds=12):
 scores=[0,0];rnd=1;results=[]
 while max(scores)<3 and rnd<=max_rounds:
  b=[[] for _ in range(9)];res=[[True]*9 for _ in range(2)];turn=1 if rnd%2 else 2;movecount=0;victor=0;trace=[]
  while movecount<18:
   opts=moves(b,res,turn,rule)
   if not opts:
    other=3-turn
    if not moves(b,res,other,rule):break
    turn=other;opts=moves(b,res,turn,rule)
   r,c=opts[(rnd*17+movecount*7)%len(opts)] if turn==1 else ai_choose(b,res,2,rule)
   b,res=after(b,res,turn,r,c);movecount+=1;trace.append((turn,r,c))
   if win(b,turn,rule):victor=turn;scores[turn-1]+=1;break
   other=3-turn
   if moves(b,res,other,rule):turn=other
   elif not moves(b,res,turn,rule):break
  results.append({'round':rnd,'winner':victor,'moves':movecount,'score':scores[:], 'trace':trace})
  rnd+=1
 return results
if __name__=='__main__':
 for rule in ['C','D','CD']:
  rows=simulate(rule)
  print(rule,'rounds',len(rows),'score',rows[-1]['score'],'winners',[x['winner'] for x in rows],'moves',[x['moves'] for x in rows])
