import random
LINES=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
WEIGHTS=[2,3,2,3,5,3,2,3,2]
def legal(b,r,p,rule):
 out=[]
 for rank in range(1,10):
  if not r[p-1][rank-1]:continue
  for cell in range(9):
   s=b[cell]
   if s:
    t=s[-1]
    if t[0]==p or rank<=t[1] or rule in ('C','CD') and len(s)>=2:continue
   out.append((rank,cell))
 return out
def win(b,p,rule):
 for line in LINES:
  t=[b[i][-1] if b[i] else None for i in line]
  if all(z is not None and z[0]==p for z in t):
   ranks=[z[1] for z in t]
   if rule=='C' or ranks[0]<ranks[1]<ranks[2] or ranks[0]>ranks[1]>ranks[2]:return True
 return False
def apply(b,r,p,m):
 b=[x.copy() for x in b];r=[x.copy() for x in r];rank,cell=m;b[cell].append((p,rank));r[p-1][rank-1]=False;return b,r
def winning_replies(b,r,p,rule):
 return sum(win(apply(b,r,p,m)[0],p,rule) for m in legal(b,r,p,rule))
def choose(b,r,p,rule,diff,persona):
 moves=legal(b,r,p,rule)
 if not moves:return None
 enemy=3-p;best=None;bestscore=float('-inf')
 for rank,cell in moves:
  covered=bool(b[cell]);nb,nr=apply(b,r,p,(rank,cell));iswin=win(nb,p,rule)
  score=WEIGHTS[cell]*3+(10-rank)*.65
  if covered:score+=9
  if persona==1 and covered:score+=3
  if persona==2:score+=2*WEIGHTS[cell]
  if diff==1:score+=((cell*7+rank*3)%11)*.4
  else:
   ew=winning_replies(nb,nr,enemy,rule)
   score-=ew*(22000 if diff==3 else 12000)
   if diff==3:
    score+=winning_replies(nb,nr,p,rule)*(90 if persona==2 else 200)
    if persona==2:score-=ew*6000
  if iswin and diff>=2:score+=1000000
  if score>bestscore:bestscore=score;best=(rank,cell)
 return best

def play(rule,ai_difficulty,seed=0):
 rng=random.Random(seed);b=[[] for _ in range(9)];r=[[True]*9 for _ in range(2)];p=1
 for i in range(19):
  moves=legal(b,r,p,rule)
  if not moves:
   p=3-p;moves=legal(b,r,p,rule)
   if not moves:return 0,i
  m=choose(b,r,p,rule,ai_difficulty,0) if p==2 else rng.choice(moves)
  if m not in moves:raise ValueError('illegal')
  b,r=apply(b,r,p,m)
  if win(b,p,rule):return p,i+1
  p=3-p
 raise ValueError('too many moves')
if __name__=='__main__':
 for rule in ['C','D','CD']:
  for diff in [1,2,3]:
   w=[0,0,0]; steps=[]
   for seed in range(20):
    winner,step=play(rule,diff,seed);w[winner]+=1;steps.append(step)
   print(rule,diff,'draw/human/ai',w,'mean_moves',round(sum(steps)/len(steps),1))
