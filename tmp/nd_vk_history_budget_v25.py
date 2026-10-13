"""Bounded, stateless VK conversation history selector (Porfirchik V20.7.25)."""

def select_recent_vk_messages(items, current_text='', max_messages=10, budget=14000):
    turns=[]
    for item in reversed(items):
        if not isinstance(item,dict):
            continue
        message=str(item.get('text') or '').strip()
        if not message:
            continue
        if message.lower() in ('/reset','/сброс'):
            turns=[]
            continue
        if message.startswith('/'):
            continue
        role='assistant' if str(item.get('out') or '0')=='1' else 'user'
        turns.append({'role':role,'content':message[:5000]})
    current=str(current_text or '').strip()
    if turns and current and turns[-1]['role']=='user' and turns[-1]['content']==current[:5000]:
        turns.pop()
    turns=turns[-max_messages:]
    count=len(turns)
    sizes=[min(len(t['content']),1500 if i>=count-4 else 900) for i,t in enumerate(turns)]
    spare=max(0,budget-sum(sizes))
    while spare:
        progress=False
        for i in range(count-1,-1,-1):
            amount=min(spare,256,len(turns[i]['content'])-sizes[i])
            if amount>0:
                sizes[i]+=amount
                spare-=amount
                progress=True
        if not progress:
            break
    answer=[]
    for turn,size in zip(turns,sizes):
        content=turn['content']
        if len(content)>size:
            marker=' …[сокращено]… '
            if size>len(marker)+20:
                keep=size-len(marker)
                first=keep*2//5
                content=content[:first]+marker+content[-(keep-first):]
            else:
                content=content[-size:] if size>0 else ''
        if content:
            answer.append({'role':turn['role'],'content':content})
    return answer

def selftest():
    original=[{'text':str(i)+':'+'x'*4900,'out':i%2} for i in range(14)]
    selected=select_recent_vk_messages(list(reversed(original)))
    assert len(selected)==10
    assert sum(len(x['content']) for x in selected)<=14000
    assert [int(x['content'].split(':')[0]) for x in selected]==list(range(4,14))
    assert len(select_recent_vk_messages([
        {'text':'now','out':0},{'text':'previous','out':1}], 'now'))==1
    assert len(select_recent_vk_messages([
        {'text':'after','out':0},{'text':'/reset','out':0},
        {'text':'before','out':1}]))==1

if __name__=='__main__':
    selftest()
    print('VK_HISTORY_BUDGET_SELFTEST_PASS')
