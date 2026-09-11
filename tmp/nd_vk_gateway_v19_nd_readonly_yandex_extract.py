import urllib.request
BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/ba4b4a9430559450d916ab184f048b52f4d7b4eb/tmp/nd_vk_gateway_v17_nd_readonly_complete.py'
code=urllib.request.urlopen(BASE,timeout=30).read().decode('utf-8')
marker="print('ND_V17_BOOTSTRAP',flush=True)"
if marker not in code: raise RuntimeError('V17 bootstrap marker not found')

patch=r'''
old_docx="""def docx_text(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml=z.read('word/document.xml').decode('utf-8','replace')
        xml=xml.replace('</w:p>','\n').replace('</w:tr>','\n')
        return html.unescape(re.sub(r'<[^>]+>','',xml))
    except Exception:return ''
"""
new_docx="""def docx_text(data):
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
                        elif local=='tab': parts.append('\t')
                        elif local in ('br','cr'): parts.append('\n')
                    txt=''.join(parts).strip()
                    if txt: chunks.append(txt)
        return '\n'.join(chunks).strip()
    except Exception:return ''
"""
if old_docx not in code: raise RuntimeError('docx parser block not found')
code=code.replace(old_docx,new_docx,1)
code=code.replace("for score,p,item in cand[:2]:","for score,p,item in cand[:24]:",1)
code=code.replace("if text:out.append(('Yandex Disk: '+p,text[:7000]))","if text and len(text.strip())>=40:out.append(('Yandex Disk: '+p,text[:7000]))",1)
code=code.replace("ND_VK_GATEWAY_V17_ND_READONLY_COMPLETE_START","ND_VK_GATEWAY_V19_ND_READONLY_YANDEX_EXTRACT_START",1)
'''
code=code.replace(marker,patch+"\nprint('ND_V19_BOOTSTRAP',flush=True)",1)
print('ND_V19_OUTER',flush=True)
exec(compile(code,'nd_vk_gateway_v19_outer.py','exec'))
