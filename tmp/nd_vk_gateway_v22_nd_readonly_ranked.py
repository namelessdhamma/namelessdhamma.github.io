import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ba4b4a9430559450d916ab184f048b52f4d7b4eb/tmp/nd_vk_gateway_v17_nd_readonly_complete.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="print('ND_V17_BOOTSTRAP',flush=True)"
if marker not in outer: raise RuntimeError('V17 bootstrap marker not found')

inject=r'''
old_score="""        score=sum(3 for t in terms if t in pl)
        if any(x in pl for x in ('черновик','проработка')):score+=1
        cand.append((score,p,item))
"""
new_score="""        name=(item.get('name') or p.rsplit('/',1)[-1]).lower()
        score=0
        for t in terms:
            if t.isdigit():
                if re.search(r'(?<!\\d)'+re.escape(t)+r'(?!\\d)',name): score+=40
                elif t in name: score+=3
            else:
                if t in name: score+=6
                elif t in pl: score+=1
        if 'черновик' in terms and ('черновик' in name or '/черновик' in pl): score+=8
        if 'чистовик' in terms and ('чистовик' in name or 'чистов' in pl): score+=10
        if 'проработка' in terms and ('проработка' in name or 'проработка' in pl): score+=8
        cand.append((score,p,item))
"""
if old_score not in code: raise RuntimeError('V22 scoring block not found')
code=code.replace(old_score,new_score,1)
code=code.replace("cand.sort(key=lambda x:(x[0],x[1]),reverse=True)","cand.sort(key=lambda x:(x[0],x[1]),reverse=True)\n    print('ND_RO_YANDEX_TOP',json.dumps([{'score':x[0],'name':(x[2].get('name') or x[1].rsplit('/',1)[-1]),'size':x[2].get('size')} for x in cand[:6]],ensure_ascii=False),flush=True)",1)
code=code.replace("ND_VK_GATEWAY_V17_ND_READONLY_COMPLETE_START","ND_VK_GATEWAY_V22_ND_READONLY_RANKED_START",1)
'''
outer=outer.replace(marker,inject+"\nprint('ND_V22_BOOTSTRAP',flush=True)",1)
print('ND_V22_OUTER',flush=True)
exec(compile(outer,'nd_vk_gateway_v22_outer.py','exec'))
