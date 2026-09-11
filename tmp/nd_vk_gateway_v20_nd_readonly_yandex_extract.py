import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ba4b4a9430559450d916ab184f048b52f4d7b4eb/tmp/nd_vk_gateway_v17_nd_readonly_complete.py'
outer=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="print('ND_V17_BOOTSTRAP',flush=True)"
if marker not in outer: raise RuntimeError('V17 bootstrap marker not found')

inject=r'''
import re as _re
_new_docx="""def docx_text(data):
    try:
        import xml.etree.ElementTree as ET
        chunks=[]
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names=[n for n in z.namelist() if n=='word/document.xml' or n.startswith('word/header') or n.startswith('word/footer') or n in ('word/footnotes.xml','word/endnotes.xml','word/comments.xml')]
            for name in names:
                try: root=ET.fromstring(z.read(name))
                except Exception: continue
                for p in root.iter():
                    if p.tag.rsplit('}',1)[-1] != 'p': continue
                    parts=[]
                    for el in p.iter():
                        local=el.tag.rsplit('}',1)[-1]
                        if local=='t' and el.text: parts.append(el.text)
                        elif local=='tab': parts.append('\\t')
                        elif local in ('br','cr'): parts.append('\\n')
                    txt=''.join(parts).strip()
                    if txt: chunks.append(txt)
        return '\\n'.join(chunks).strip()
    except Exception:return ''
"""
_pat=r"def docx_text\(data\):\n    try:\n.*?    except Exception:return ''\n"
code,_n=_re.subn(_pat,lambda m:_new_docx,code,count=1,flags=_re.S)
if _n!=1: raise RuntimeError('V20 docx parser substitution failed')
code=code.replace("for score,p,item in cand[:2]:","for score,p,item in cand[:24]:",1)
code=code.replace("if text:out.append(('Yandex Disk: '+p,text[:7000]))","if text and len(text.strip())>=40:out.append(('Yandex Disk: '+p,text[:7000]))",1)
code=code.replace("ND_VK_GATEWAY_V17_ND_READONLY_COMPLETE_START","ND_VK_GATEWAY_V20_ND_READONLY_YANDEX_EXTRACT_START",1)
'''
outer=outer.replace(marker,inject+"\nprint('ND_V20_BOOTSTRAP',flush=True)",1)
print('ND_V20_OUTER',flush=True)
exec(compile(outer,'nd_vk_gateway_v20_outer.py','exec'))
