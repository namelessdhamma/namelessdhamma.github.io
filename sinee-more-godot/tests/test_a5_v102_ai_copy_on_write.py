from copy import deepcopy
from pathlib import Path
import hashlib
import re
LINES=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
WEIGHTS=[2,3,2,3,5,3,2,3,2]

def legal_dest(b,p,r,c,rule):
 s=b[c]
 return not s or (s[-1][0]!=p and r>s[-1][1] and not(rule in ('C','CD') and len(s)>=2))
def legal(b,res,p,rule):return [(r,c) for r in range(1,10) if res[p-1][r-1] for c in range(9) if legal_dest(b,p,r,c,rule)]
def win(b,p,rule):
 for line in LINES:
  ranks=[b[c][-1][1] if b[c] and b[c][-1][0]==p else -1 for c in line]
  if -1 not in ranks and (rule=='C' or ranks[0]<ranks[1]<ranks[2] or ranks[0]>ranks[1]>ranks[2]):return line
 return []
def after(b,res,p,m):
 nb=deepcopy(b);nr=deepcopy(res);r,c=m;nb[c].append((p,r));nr[p-1][r-1]=False;return nb,nr
def wins_after(b,p,rule,c,r):
 for line in LINES:
  if c not in line:continue
  ranks=[r if cell==c else (b[cell][-1][1] if b[cell] and b[cell][-1][0]==p else -1) for cell in line]
  if -1 not in ranks and (rule=='C' or ranks[0]<ranks[1]<ranks[2] or ranks[0]>ranks[1]>ranks[2]):return True
 return False
def threats(b,res,p,rule):
 already=bool(win(b,p,rule));return sum(1 for r,c in legal(b,res,p,rule) if already or wins_after(b,p,rule,c,r))
def choose(b,res,p,rule,d=3,persona=0):
 cand=legal(b,res,p,rule)
 if not cand:return None
 if d>=2:
  for m in cand:
   if wins_after(b,p,rule,m[1],m[0]):return m
 enemy=3-p;best=None;bs=-float('inf')
 for r,c in cand:
  covered=bool(b[c]);nb,nr=after(b,res,p,(r,c));won=bool(win(nb,p,rule));s=WEIGHTS[c]*3+(10-r)*.65
  if covered:s+=9
  if persona==1 and covered:s+=3
  if persona==2:s+=2*WEIGHTS[c]
  if d==1:s+=((c*7+r*3)%11)*.4
  else:
   ew=threats(nb,nr,enemy,rule);s-=ew*(22000 if d==3 else 12000)
   if d==3:
    s+=threats(nb,nr,p,rule)*(90 if persona==2 else 200)
    if persona==2:s-=ew*6000
  if won and d>=2:s+=1000000
  if s>bs:bs=s;best=(r,c)
 return best

def simulate(rule,world):
 score=[0,0];roundnum=1;total=0;ai_turns=0
 for rounds in range(1,13):
  b=[[] for _ in range(9)];res=[[True]*9,[True]*9];turn=1 if roundnum%2 else 2;moves=0;won=0
  while moves<18:
   options=legal(b,res,turn,rule)
   if not options:
    other=3-turn
    if not legal(b,res,other,rule):break
    turn=other;continue
   if turn==1:m=options[(roundnum*17+moves*7)%len(options)]
   else:m=choose(b,res,2,rule);ai_turns+=1
   b,res=after(b,res,turn,m);moves+=1
   if win(b,turn,rule):won=turn;score[turn-1]+=1;break
   turn=3-turn
  total+=moves
  if score[0]>=3 or score[1]>=3:return score,rounds,total,ai_turns
  roundnum+=1
 return score,rounds,total,ai_turns


ROOT = Path(__file__).resolve().parents[1]
AI = (ROOT / "scripts" / "ai_opponent.gd").read_text(encoding="utf-8")


def cow_after(board, reserves, player, move):
    rank, cell = move
    next_board = board.copy()
    next_reserves = reserves.copy()
    next_board[cell] = board[cell].copy()
    next_reserves[player - 1] = reserves[player - 1].copy()
    next_board[cell].append((player, rank))
    next_reserves[player - 1][rank - 1] = False
    return next_board, next_reserves


def test_gd_cow_changes_only_target_stack_and_active_reserve():
    function = AI.split("func _after_move(", 1)[1].split("\nfunc ", 1)[0]
    assert "board.duplicate()" in function
    assert "reserves.duplicate()" in function
    assert "board[cell].duplicate()" in function
    assert "reserves[player - 1].duplicate()" in function
    assert ".duplicate(true)" not in function
    assert "next_board[cell].append" in function
    assert "next_reserves[player - 1][rank - 1] = false" in function


def test_gd_self_test_proves_value_and_live_state_isolation():
    self_test = AI.split("func self_test()", 1)[1]
    for evidence in ["AI copy-on-write diverged from deep-copy oracle",
                     "AI hypothetical move mutated live board or reserve",
                     "AI target stack was aliased to live state",
                     "AI active reserve was aliased to live state"]:
        assert evidence in self_test
    assert "assert(ai_engine.self_test()" in (ROOT / "scripts" / "main.gd").read_text()


def test_copy_on_write_matches_deep_clone_all_rules_players_and_legal_moves():
    boards = [
        [[] for _ in range(9)],
        [[(1, 1)], [(2, 2)], [], [], [(1, 3), (2, 5)], [], [], [], []],
        [[(2, 1)], [(2, 2)], [], [(1, 1)], [], [], [], [], []],
        [[(1, 2), (2, 5)], [(1, 3)], [], [], [], [], [], [], []],
    ]
    reserves = [[True] * 9, [True] * 9]
    checked = 0
    for board in boards:
        for mode in ("C", "D", "CD"):
            for player in (1, 2):
                for move in legal(board, reserves, player, mode):
                    frozen = deepcopy((board, reserves))
                    actual = cow_after(board, reserves, player, move)
                    expected = after(board, reserves, player, move)
                    assert actual == expected
                    assert (board, reserves) == frozen
                    actual[0][move[1]].append((player, 10))
                    actual[1][player - 1][move[0] - 1] = True
                    assert (board, reserves) == frozen
                    checked += 1
    assert checked >= 500


def test_reference_21_full_matches_remain_deterministic():
    expected = {"C": ([0, 3], 3, 17, 9),
                "D": ([0, 3], 3, 31, 16),
                "CD": ([0, 3], 3, 23, 12)}
    for world in range(7):
        for mode in ("C", "D", "CD"):
            assert simulate(mode, world) == expected[mode]


def test_shared_main_and_approved_art_binding_unchanged():
    # An old full-main SHA pinned a pre-UI version and falsely failed every
    # later legitimate touch/world change. Verify the actual stable bindings.
    main = (ROOT / "scripts" / "main.gd").read_text()
    assert 'const AIOpponent = preload("res://scripts/ai_opponent.gd")' in main
    assert 'const WorldVisuals = preload("res://scripts/world_visuals.gd")' in main
    assert 'const PerspectiveGeometry = preload("res://scripts/perspective_board_geometry.gd")' in main
    assert 'var ai_engine = AIOpponent.new()' in main
    assert 'world_visuals.apply_world(self, current_world)' in main
    assert 'var menu_path := "res://assets/a5_menu_plates/world_%02d.png" % current_world' in main
    assert (ROOT / "tools" / "approved_seven_world_manifest.json").exists()
