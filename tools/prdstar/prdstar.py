#!/usr/bin/env python3
"""PRDstar 저장 구조(db 문서 + 파일 저장소)를 Claude가 읽고 고치기 위한 도구.
페이지의 저장 계층(store)과 같은 규칙으로 문서를 조립(implode)하고 나눈다(explode).

db:  ms/{msId}                      마일스톤 목록(제목·기능 영역·배포일)
     ms/{msId}/d/{docId}            meta · log · bg · guide · dev · root · brief · ver~{vid} · req~{vid}~{rid}
                                    final · spec · feat~{fid} · item~{fid}~{iid} · files
파일: 데모 HTML(text/plain), 기능별 스냅샷 묶음(application/json). 문서에는 {"$f": assetId}로 가리킨다.
"""
import argparse, copy, glob, hashlib, json, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msdoc  # stamp_versions, now, migrate

def cj(o): return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
def jsj(o): return json.dumps(o, ensure_ascii=False, separators=(',', ':'))  # JS JSON.stringify와 같은 글자
def h40(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()[:40]
def isref(v): return isinstance(v, dict) and '$f' in v and len(v) == 1

def load_docs(d):
    docs = {}
    for f in glob.glob(os.path.join(d, '*.json')):
        o = json.load(open(f, encoding='utf-8')); docs[os.path.basename(f)[:-5]] = o.get('data', o) if isinstance(o, dict) and set(o) >= {'data'} and len(o) <= 4 else o
    return docs

def find_docs_dir(root):
    hits = [p for p in glob.glob(os.path.join(root, '**', 'd'), recursive=True) if os.path.isdir(p) and glob.glob(os.path.join(p, '*.json'))]
    if not hits: raise SystemExit('문서 폴더(ms/<msId>/d)를 찾지 못했어요: ' + root)
    return hits[0]

class Files:
    def __init__(self, d, nofiles): self.d, self.nofiles, self.missing = d, nofiles, set()
    def get(self, aid):
        if self.nofiles: return None
        for f in glob.glob(os.path.join(self.d or '', aid + '*')):
            return open(f, encoding='utf-8').read()
        self.missing.add(aid); return None

def implode(D, F):
    c = copy.deepcopy(D.get('root') or {}); c['background'] = copy.deepcopy(D.get('bg') or {})
    def demo_in(demo):
        d = copy.deepcopy(demo or {'screens': []})
        for s in d.get('screens') or []:
            if isref(s.get('html')):
                t = F.get(s['html']['$f'])
                if t is not None: s['html'] = t   # 파일 없이 열면 {"$f": id} 그대로 둔다
        return d
    br = copy.deepcopy(D.get('brief') or {}); order = br.pop('order', [])
    vids = order + [k[4:] for k in sorted(D) if k.startswith('ver~') and k[4:] not in order]
    br['versions'] = []
    for vid in vids:
        vv = copy.deepcopy(D.get('ver~' + vid))
        if not vv: continue
        ro = vv.pop('reqOrder', []); pre = 'req~' + vid + '~'
        rids = ro + [k[len(pre):] for k in sorted(D) if k.startswith(pre) and k[len(pre):] not in ro]
        vv['reqs'] = [copy.deepcopy(D[pre + r]) for r in rids if pre + r in D]; vv['demo'] = demo_in(vv.get('demo')); br['versions'].append(vv)
    c['brief'] = br
    fin = copy.deepcopy(D.get('final') or {'figma': [], 'demo': {'screens': []}}); fin['demo'] = demo_in(fin.get('demo')); c['final'] = fin
    sp = copy.deepcopy(D.get('spec') or {}); fo = sp.pop('order', [])
    fids = fo + [k[5:] for k in sorted(D) if k.startswith('feat~') and k[5:] not in fo]
    sp['features'] = []
    for fid in fids:
        ff = copy.deepcopy(D.get('feat~' + fid))
        if not ff: continue
        io = ff.pop('itemOrder', []); pre = 'item~' + fid + '~'
        iids = io + [k[len(pre):] for k in sorted(D) if k.startswith(pre) and k[len(pre):] not in io]
        ff['items'] = [copy.deepcopy(D[pre + i]) for i in iids if pre + i in D]
        snap = ff.pop('snap', None); tx = F.get(snap['$f']) if isref(snap) else None
        if isref(snap) and tx is None: ff['_snap'] = snap   # 스냅샷 묶음을 받지 않았으면 그대로 둔다
        snaps = json.loads(tx) if tx else {}
        for s in ff.get('screens') or []:
            z = snaps.get(s['id'])
            if z:
                if z.get('html') is not None: s['html'] = z['html']
                if z.get('base') is not None: s['base'] = z['base']
        sp['features'].append(ff)
    c['spec'] = sp
    meta = copy.deepcopy(D.get('meta') or {}); meta['log'] = copy.deepcopy((D.get('log') or {}).get('entries', []))
    return c, meta, (D.get('guide') or {}).get('text', ''), (D.get('dev') or {}).get('text', '')

def explode(c, meta, guide, dev, base_map, up):
    """up(text, ext) → {"$f": id 또는 '@hash'}; base_map = {hash: id}"""
    D, used = {}, set()
    id2h = {v: k for k, v in base_map.items()}
    def ref(text, ext):
        hx = h40(text); used.add(hx)
        return {'$f': base_map[hx]} if hx in base_map else up(text, ext, hx)
    m = {k: v for k, v in meta.items() if k != 'log'}; D['meta'] = m; D['log'] = {'entries': meta.get('log', [])}
    D['bg'] = c['background']; D['guide'] = {'text': guide or ''}; D['dev'] = {'text': dev or ''}
    D['root'] = {k: v for k, v in c.items() if k not in ('background', 'brief', 'final', 'spec')}
    def demo_out(demo):
        d = {k: v for k, v in (demo or {}).items() if k != 'screens'}; d['screens'] = []
        for s in (demo or {}).get('screens') or []:
            x = dict(s)
            if isinstance(x.get('html'), str) and len(x['html']) > 2000: x['html'] = ref(x['html'], 'txt')
            elif isref(x.get('html')) and x['html']['$f'] in id2h: used.add(id2h[x['html']['$f']])
            d['screens'].append(x)
        return d
    br = {k: v for k, v in c['brief'].items() if k != 'versions'}; vers = c['brief'].get('versions', []); br['order'] = [v['id'] for v in vers]; D['brief'] = br
    for v in vers:
        vv = {k: x for k, x in v.items() if k != 'reqs'}; reqs = v.get('reqs', []); vv['reqOrder'] = [r['id'] for r in reqs]; vv['demo'] = demo_out(v.get('demo'))
        D['ver~' + v['id']] = vv
        for r in reqs: D['req~' + v['id'] + '~' + r['id']] = r
    fin = dict(c['final']); fin['demo'] = demo_out(c['final'].get('demo')); D['final'] = fin
    sp = {k: v for k, v in c['spec'].items() if k != 'features'}; feats = c['spec'].get('features', []); sp['order'] = [f['id'] for f in feats]; D['spec'] = sp
    for f in feats:
        ff = {k: v for k, v in f.items() if k not in ('items', '_snap')}; items = f.get('items', []); ff['itemOrder'] = [i['id'] for i in items]; snaps = {}; scr = []
        for s in f.get('screens') or []:
            x = dict(s)
            if x.get('html') is not None or x.get('base') is not None:
                snaps[s['id']] = {'html': x.get('html'), 'base': x.get('base')}; x.pop('html', None); x.pop('base', None)
            scr.append(x)
        ff['screens'] = scr
        if snaps: ff['snap'] = ref(jsj(snaps), 'json')
        elif isref(f.get('_snap')): ff['snap'] = f['_snap']; used.add(id2h.get(f['_snap']['$f'], ''))
        else: ff['snap'] = None
        D['feat~' + f['id']] = ff
        for it in items: D['item~' + f['id'] + '~' + it['id']] = it
    D['files'] = {'map': {hx: base_map.get(hx, '@' + hx) for hx in sorted(used) if hx}}
    return D

def cmd_pull(a):
    dd = find_docs_dir(a.docs); D = load_docs(dd); F = Files(a.files, a.no_files)
    c, meta, g, dev = implode(D, F)
    if F.missing:
        print('받아야 할 파일 ' + str(len(F.missing)) + '개 — Artifact read(url, path=<id>, out_dir=' + (a.files or '<files 폴더>') + ')로 받은 뒤 다시 실행하거나, 글만 고칠 거면 --no-files로 실행하세요:')
        for x in sorted(F.missing): print('  ' + x)
        sys.exit(2)
    w = a.out; os.makedirs(w, exist_ok=True)
    for sub in ('base', 'mine'):
        p = os.path.join(w, sub); os.makedirs(p, exist_ok=True)
        json.dump(c, open(os.path.join(p, 'content.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        json.dump(meta, open(os.path.join(p, 'meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        open(os.path.join(p, 'guide.md'), 'w', encoding='utf-8').write(g); open(os.path.join(p, 'devspec.md'), 'w', encoding='utf-8').write(dev)
    shutil.rmtree(os.path.join(w, 'docs'), ignore_errors=True); shutil.copytree(dd, os.path.join(w, 'docs'))
    json.dump({'msId': os.path.basename(os.path.dirname(dd)), 'noFiles': bool(a.no_files)}, open(os.path.join(w, 'pull.json'), 'w'))
    print('꺼냈어요:', w, '(base/ = 받은 그대로, mine/ = 여기를 고치세요)', '파일 없이' if a.no_files else '')

def cmd_push(a):
    w = a.work; info = json.load(open(os.path.join(w, 'pull.json')))
    L = lambda s, n: open(os.path.join(w, s, n), encoding='utf-8').read()
    bc, bm = json.loads(L('base', 'content.json')), json.loads(L('base', 'meta.json'))
    mc, mm = json.loads(L('mine', 'content.json')), json.loads(L('mine', 'meta.json'))
    mg, mdv = L('mine', 'guide.md'), L('mine', 'devspec.md')
    msdoc.migrate(mc)
    stamped = []
    if mm.get('deployedAt'): stamped = msdoc.stamp_versions(bc, mc, mm, a.by)   # 배포 후: 바뀐 정책마다 새 버전 + Changelog
    if a.major and stamped:   # 주요 변경: 이번에 붙은 Changelog 줄과 새 버전에 major 표시(Changelog 기본 필터에 보임)
        nlog=len(stamped); [e.__setitem__('major', True) for e in mm.get('log', [])[-nlog:]]
        for f in mc['spec']['features']:
            for it in f.get('items', []):
                if it.get('versions') and it['code'] in [x if isinstance(x,str) else x.get('code') for x in stamped]: it['versions'][-1]['major'] = True
    if a.log: mm.setdefault('log', []).append({'at': msdoc.now(), 'by': a.by, 'code': '-', 'text': a.log})
    mm['updatedAt'] = msdoc.now()
    BD = load_docs(os.path.join(w, 'docs')); base_map = (BD.get('files') or {}).get('map', {})
    out = a.out; shutil.rmtree(out, ignore_errors=True); os.makedirs(os.path.join(out, 'docs')); os.makedirs(os.path.join(out, 'upload'))
    uploads = []
    def up(text, ext, hx):
        p = os.path.join(out, 'upload', hx + '.' + ext); open(p, 'w', encoding='utf-8').write(text); uploads.append({'hash': hx, 'file': p}); return {'$f': '@' + hx}
    D = explode(mc, mm, mg, mdv, base_map, up)
    col = 'ms/' + info['msId'] + '/d'; writes = []
    for k, v in D.items():
        if k == 'meta' and cj({x: y for x, y in v.items() if x != 'updatedAt'}) == cj({x: y for x, y in (BD.get('meta') or {}).items() if x != 'updatedAt'}): continue
        if cj(v) != cj(BD.get(k)):
            p = os.path.join(out, 'docs', k + '.json'); json.dump(v, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
            if len(cj(v).encode()) > 250 * 1024: raise SystemExit(k + ' 문서가 250KB를 넘어요')
            writes.append({'op': 'set', 'collection': col, 'doc_id': k, 'file_path': p})
    for k in BD:
        if k not in D: writes.append({'op': 'delete', 'collection': col, 'doc_id': k})
    json.dump({'msId': info['msId'], 'writes': writes, 'uploads': uploads}, open(os.path.join(out, 'plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps({'writes': len(writes), 'docs': [w_['doc_id'] for w_ in writes], 'uploads': [u['file'] for u in uploads], 'changelog_added': stamped}, ensure_ascii=False, indent=1))
    if uploads: print('먼저 파일을 올리세요: Artifact publish(url, asset=true, file_path=<upload 파일>) → 받은 id로 `finalize --id <hash>=<id>`')
    else: print('올릴 파일이 없어요. plan.json의 writes를 write_db batch(50개씩)로 쓰세요.')

def cmd_finalize(a):
    plan = json.load(open(os.path.join(a.plan, 'plan.json'), encoding='utf-8')); ids = dict(x.split('=', 1) for x in a.id)
    miss = [u['hash'] for u in plan['uploads'] if u['hash'] not in ids]
    if miss: raise SystemExit('id가 없는 파일: ' + ', '.join(miss))
    for w in plan['writes']:
        if w.get('file_path'):
            t = open(w['file_path'], encoding='utf-8').read()
            for hx, aid in ids.items(): t = t.replace('"@' + hx + '"', '"' + aid.replace('/_blob/', '') + '"')
            open(w['file_path'], 'w', encoding='utf-8').write(t)
    plan['uploads'] = []; json.dump(plan, open(os.path.join(a.plan, 'plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('파일 id를 넣었어요. plan.json의 writes를 write_db batch(50개씩)로 쓰세요.')

def cmd_batches(a):
    plan = json.load(open(os.path.join(a.plan, 'plan.json'), encoding='utf-8'))
    if plan['uploads']: raise SystemExit('먼저 finalize로 파일 id를 넣으세요.')
    ws = plan['writes']
    for i in range(0, len(ws), 50): print(json.dumps(ws[i:i + 50], ensure_ascii=False))

def cmd_tohtml(a):
    """검사 도구(msdoc check·summary·screens·coverage)를 쓰려고 꺼낸 내용을 임시 HTML로 묶는다(게시용 아님)."""
    d = os.path.join(a.work, a.side); L = lambda n: open(os.path.join(d, n), encoding='utf-8').read()
    shell = ('<!doctype html><html><head><title>PRDstar</title></head><body>\n'
             '<script type="application/json" id="msdoc-content">{}</script>\n<script type="application/json" id="msdoc-meta">{}</script>\n'
             '<script type="text/markdown" id="msdoc-guide"></script>\n<script type="text/markdown" id="msdoc-devspec"></script>\n<script id="msdoc-app"></script>\n</body></html>')
    html = msdoc.write(shell, json.loads(L('content.json')), json.loads(L('meta.json')), L('guide.md'))
    open(a.out, 'w', encoding='utf-8').write(msdoc.write_dev(html, L('devspec.md'))); print('임시 HTML:', a.out)

def cmd_deploy(a):
    """배포 완료: mine의 모든 정책을 v1로 기록하고 배포일·Changelog를 남긴다(그다음 push)."""
    d = os.path.join(a.work, 'mine'); c = json.load(open(os.path.join(d, 'content.json'), encoding='utf-8')); m = json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))
    if m.get('deployedAt'): raise SystemExit('이미 배포 완료된 마일스톤이에요: ' + m['deployedAt'])
    t = msdoc.now()
    for f in c['spec']['features']:
        for it in f.get('items', []): it['versions'] = [{'n': 1, 'at': t, 'title': it.get('title', ''), 'body': it.get('body', ''), 'by': a.by}]
    m['deployedAt'] = t; m['deployedBy'] = a.by; m.setdefault('log', []).append({'at': t, 'by': a.by, 'code': '-', 'text': '배포 완료, 모든 정책을 v1로 기록'})
    json.dump(c, open(os.path.join(d, 'content.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1); json.dump(m, open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('배포 완료로 표시했어요:', t, '→ 이제 push하세요(ms 목록 문서의 deployedAt도 update)')

def cmd_init(a):
    """새 마일스톤용 작업 폴더: 기본값(빈 내용)으로 mine을 만들고, push하면 모든 문서가 쓰기 대상이 된다."""
    import random, string
    ms = a.ms or ('ms-' + ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10)))
    c = msdoc.blank(); c['background']['title'] = a.title; c['background']['area'] = a.area or ''
    g = open(a.guide, encoding='utf-8').read() if a.guide else ''
    w = a.out; os.makedirs(os.path.join(w, 'docs'), exist_ok=True)
    for sub in ('base', 'mine'):
        d = os.path.join(w, sub); os.makedirs(d, exist_ok=True)
        json.dump(c if sub == 'mine' else {}, open(os.path.join(d, 'content.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        json.dump({'isTemplate': False, 'deployedAt': None, 'log': []}, open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        open(os.path.join(d, 'guide.md'), 'w', encoding='utf-8').write(g); open(os.path.join(d, 'devspec.md'), 'w', encoding='utf-8').write('')
    json.dump({'msId': ms, 'noFiles': False, 'new': True}, open(os.path.join(w, 'pull.json'), 'w'))
    print(json.dumps({'msId': ms, 'listDoc': {'collection': 'ms', 'doc_id': ms, 'data': {'title': a.title, 'area': a.area or '', 'createdAt': msdoc.now(), 'createdBy': None, 'active': True, 'deployedAt': None}}}, ensure_ascii=False, indent=1))
    print('먼저 위 listDoc을 write_db set으로 만든 뒤, mine을 채우고 push하세요.')

RULES_RX = re.compile(r'const CLAUDE_RULES_MD=(".*?");\n', re.S)
def cmd_rules_sync(a):
    """references/claude-rules.md(원본)를 페이지 코드의 CLAUDE_RULES_MD 상수에 넣는다. 규칙을 바꿨으면 꼭 실행하고 페이지를 게시한다."""
    src = a.rules or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'references', 'claude-rules.md')
    md = open(src, encoding='utf-8').read(); html = open(a.html, encoding='utf-8').read()
    lit = json.dumps(md, ensure_ascii=False).replace('</', '<\\/')
    if not RULES_RX.search(html): raise SystemExit('페이지에 CLAUDE_RULES_MD 상수가 없어요.')
    html = RULES_RX.sub(lambda m: 'const CLAUDE_RULES_MD=' + lit + ';\n', html, count=1)
    st = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'references', 'prdstar-structure.md')
    srx = re.compile(r'const PRDSTAR_STRUCTURE_MD=(".*?");\n', re.S)
    if os.path.exists(st) and srx.search(html):
        slit = json.dumps(open(st, encoding='utf-8').read(), ensure_ascii=False).replace('</', '<\\/')
        html = srx.sub(lambda m: 'const PRDSTAR_STRUCTURE_MD=' + slit + ';\n', html, count=1)
    open(a.out, 'w', encoding='utf-8').write(html); print('규칙을 넣었어요:', a.out, len(md), '자')

def cmd_pagecheck(a):
    """게시 전 확인: 고친 페이지(new)가 원래 페이지(old)의 CSS·코드를 잃지 않았는지. 줄었으면 게시하지 않는다."""
    import re as _re
    def info(path):
        t = open(path, encoding='utf-8').read()
        ms = _re.search(r'<style id="msdoc-style">(.*?)</style>', t, _re.S); ap = _re.search(r'<script id="msdoc-app">(.*?)</script>', t, _re.S)
        outside = [m for m in _re.finditer(r'<style([^>]*)>(.*?)</style>', t[:ms.start()] if ms else t, _re.S) if len(m.group(2)) > 2000]
        sels = set(_re.findall(r'\.([a-zA-Z][\w-]{2,})\s*[{,:\s]', (ms.group(1) if ms else '') + ''.join(m.group(2) for m in outside)))
        return {'css': len(ms.group(1)) if ms else 0, 'outside': sum(len(m.group(2)) for m in outside), 'app': len(ap.group(1)) if ap else 0, 'sels': sels, 'title': (_re.findall(r'<title>([^<]*)</title>', t) or [''])[0]}
    o, n = info(a.old), info(a.new); bad = []
    lost = sorted(o['sels'] - n['sels'])
    if lost: bad.append('없어진 CSS 클래스 ' + str(len(lost)) + '개: ' + ', '.join(lost[:20]))
    if n['css'] + n['outside'] < (o['css'] + o['outside']) * 0.98: bad.append('CSS가 줄었어요: %d → %d' % (o['css'] + o['outside'], n['css'] + n['outside']))
    if n['app'] < o['app'] * 0.98: bad.append('앱 코드가 줄었어요: %d → %d' % (o['app'], n['app']))
    if n['outside']: bad.append('msdoc-style 바깥에 CSS가 %d자 있어요. #msdoc-style 안으로 옮기세요(도구가 바깥 CSS를 잃어버려요).' % n['outside'])
    if o['title'] != n['title']: bad.append('페이지 제목이 바뀌었어요: %s → %s' % (o['title'], n['title']))
    print('\n'.join(bad) if bad else '이상 없어요. 게시해도 돼요.'); sys.exit(1 if bad else 0)

def main():
    p = argparse.ArgumentParser(description=__doc__); sp = p.add_subparsers(dest='cmd', required=True)
    x = sp.add_parser('pull', help='read_db로 받은 문서 → 고칠 수 있는 content/meta/guide/devspec'); x.add_argument('docs'); x.add_argument('--files'); x.add_argument('--no-files', action='store_true'); x.add_argument('-o', '--out', required=True)
    x = sp.add_parser('push', help='mine과 base를 비교해 쓸 문서·올릴 파일 계획'); x.add_argument('work'); x.add_argument('-o', '--out', required=True); x.add_argument('--by', required=True); x.add_argument('--log'); x.add_argument('--major', action='store_true', help='배포 후 정책 변경을 주요 변경으로 표시')
    x = sp.add_parser('finalize', help='올린 파일 id를 계획에 넣기'); x.add_argument('plan'); x.add_argument('--id', action='append', default=[])
    x = sp.add_parser('batches', help='write_db batch용 묶음(50개씩) 출력'); x.add_argument('plan')
    x = sp.add_parser('tohtml', help='검사용 임시 HTML'); x.add_argument('work'); x.add_argument('--side', default='mine'); x.add_argument('-o', '--out', required=True)
    x = sp.add_parser('init', help='새 마일스톤 작업 폴더'); x.add_argument('--title', required=True); x.add_argument('--area'); x.add_argument('--guide'); x.add_argument('--ms'); x.add_argument('-o', '--out', required=True)
    x = sp.add_parser('rules-sync', help='규칙 원본을 페이지 코드에 넣기'); x.add_argument('html'); x.add_argument('--rules'); x.add_argument('-o', '--out', required=True)
    x = sp.add_parser('pagecheck', help='게시 전 페이지 비교(CSS·코드 손실 막기)'); x.add_argument('old'); x.add_argument('new')
    x = sp.add_parser('deploy', help='배포 완료 처리(mine)'); x.add_argument('work'); x.add_argument('--by', required=True)
    a = p.parse_args(); {'pull': cmd_pull, 'push': cmd_push, 'finalize': cmd_finalize, 'batches': cmd_batches, 'tohtml': cmd_tohtml, 'deploy': cmd_deploy, 'init': cmd_init, 'rules-sync': cmd_rules_sync, 'pagecheck': cmd_pagecheck}[a.cmd](a)

if __name__ == '__main__': main()
