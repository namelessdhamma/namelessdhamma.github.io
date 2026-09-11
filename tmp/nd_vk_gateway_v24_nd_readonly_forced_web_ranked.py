import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/6ec4778330768aa15e01b1d66efacb5722e9f053/tmp/nd_vk_gateway_v17b_nd_readonly_forced_web.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="print('ND_V17B_BOOTSTRAP',flush=True)"
if marker not in outer: raise RuntimeError('V17B bootstrap marker not found')

inject=r'''
old_score="""        score=sum(3 for t in terms if t in pl)
        if any(x in pl for x in ('черновик','проработка')):score+=1
        cand.append((score,p,item))
"""
new_score="""        name=(item.get('name') or p.rsplit('/',1)[-1]).lower()
        nums={n.lstrip('0') or '0' for n in re.findall(r'[0-9]+',name)}
        score=0
        for t in terms:
            if t.isdigit():
                if (t.lstrip('0') or '0') in nums: score+=40
            else:
                if t in name: score+=6
                elif t in pl: score+=1
        if 'черновик' in terms and ('черновик' in name or '/черновик' in pl): score+=8
        if 'чистовик' in terms and ('чистовик' in name or 'чистов' in pl): score+=10
        if 'проработка' in terms and ('проработка' in name or 'проработка' in pl): score+=8
        cand.append((score,p,item))
"""
if old_score not in code: raise RuntimeError('V24 scoring block not found')
code=code.replace(old_score,new_score,1)
code=code.replace("cand.sort(key=lambda x:(x[0],x[1]),reverse=True)","cand.sort(key=lambda x:(x[0],x[1]),reverse=True)\n    print('ND_RO_YANDEX_TOP',json.dumps([{'score':x[0],'name':(x[2].get('name') or x[1].rsplit('/',1)[-1]),'size':x[2].get('size')} for x in cand[:8]],ensure_ascii=False),flush=True)",1)
code=code.replace("ND_VK_GATEWAY_V24_ND_READONLY_FORCED_WEB_START","ND_VK_GATEWAY_V24_ND_READONLY_FORCED_WEB_RANKED_START",1)
'''
outer=outer.replace(marker,inject+"\nprint('ND_V24_BOOTSTRAP',flush=True)",1)
print('ND_V24_OUTER',flush=True)
exec(compile(outer,'nd_vk_gateway_v24_outer.py','exec'))
