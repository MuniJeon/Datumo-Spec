#!/usr/bin/env python3
"""마일스톤 문서(index.html, 템플릿 v2) 데이터 블록 도구.

블록 (index.html 안, <script id="msdoc-app"> 앞):
  <script type="application/json" id="msdoc-content">  Background / Design Brief / Final Spec 내용
  <script type="application/json" id="msdoc-meta">     배포 여부, Changelog(log)
  <script type="text/markdown"   id="msdoc-guide">     작업 지침
명령:
  unpack HTML DIR                 DIR/content.json, meta.json, guide.md 로 꺼냄
  pack HTML DIR -o OUT            DIR 의 파일을 HTML 블록에 다시 넣음
  merge BASE MINE LATEST_HTML -o OUT --by NAME [--log TEXT]
                                  최신본 위에 내 변경만 얹음. 배포 후라면 바뀐 정책마다 버전과 Changelog 를 자동으로 남김
  deploy HTML -o OUT --by NAME    배포 완료 처리 (모든 정책 v1)
  new TEMPLATE_HTML -o OUT --by NAME [--name 제목] [--template-url URL]   빈 새 문서
  summary HTML                    구성 요약
  check HTML                      구조 검사 (개발 명세가 오래됐으면 주의 표시)
  devspec-status HTML             개발 명세가 Final Spec 기준 최신인지, 바뀐 정책 코드
  devspec-stamp DIR --by 이름     DIR/devspec.md에 지금 정책 기준 표시를 남김 (내용을 고친 뒤)
  flow HTML [--final|--brief] [--version 이름]   데모 화면 흐름(data-go)과 끊긴 곳
  coverage HTML [--version 이름]  데모 영역(data-mark)을 쓰는 정책, 영역 없는 정책, 요구사항 위치 확인
  brief-dup DIR --name 이름 --by 이름 [--source 버전]   Design Brief 버전 복제 (unpack한 폴더에서)
"""
import os, argparse, copy, datetime, json, re, sys, uuid, os

BLOCK = r'(<script type="{t}" id="{id}">)(.*?)(</script>)'
def now(): return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
def uid(p): return f'{p}-{uuid.uuid4().hex[:8]}'
def jdump(o): return json.dumps(o, ensure_ascii=False, indent=1).replace('<', '\\u003c')
def md_in(t): return re.sub(r'</script', r'<\\/script', t, flags=re.I)
def md_out(t): return re.sub(r'<\\/script', '</script', t, flags=re.I)
def data_end(html): return html.index('<script id="msdoc-app">')

def find(html, t, id_):
    m = re.compile(BLOCK.format(t=re.escape(t), id=re.escape(id_)), re.S).search(html, 0, data_end(html))
    if not m: sys.exit(f'블록을 찾지 못했어요: {id_} (이 템플릿 문서가 아닐 수 있어요)')
    return m

def read(html):
    c = json.loads(find(html, 'application/json', 'msdoc-content').group(2))
    m = json.loads(find(html, 'application/json', 'msdoc-meta').group(2))
    g = md_out(find(html, 'text/markdown', 'msdoc-guide').group(2))
    if c.get('schema') != 2: sys.exit('템플릿 v2 문서가 아니에요 (schema != 2)')
    migrate(c)
    return c, m, g

def migrate(c):
    """예전 형식을 새 형식으로 바꾼다. 페이지의 migrate()와 같은 규칙.
    - brief.demo/reqs → brief.versions[{id:'bv-1', name:'초기 버전', demo, reqs}]
    - 정책마다 frames → 기능별 screens + 정책별 marks"""
    if not isinstance(c.get('final'), dict): c['final'] = {'figma': [], 'demo': {'w': 1280, 'h': 800, 'start': None, 'screens': []}}
    c['final'].setdefault('figma', []); c['final'].setdefault('demo', {'w': 1280, 'h': 800, 'start': None, 'screens': []})
    b = c.get('brief')
    if b is not None and not isinstance(b.get('versions'), list):
        b['versions'] = [{'id': 'bv-1', 'name': '초기 버전', 'createdAt': None, 'demo': b.pop('demo', None) or {'w': 390, 'h': 844, 'start': None, 'screens': []}, 'reqs': b.pop('reqs', [])}]
    for f in c.get('spec', {}).get('features', []):
        if not isinstance(f.get('screens'), list):
            f['screens'] = []; x = 0
            for it in f['items']:
                for fr in it.get('frames', []):
                    sc = dict(fr); sc['x'] = x; sc['y'] = 0; x += (fr.get('w') or 360) + 420
                    sc['next'] = [n if isinstance(n, dict) else {'to': n, 'label': ''} for n in fr.get('next', [])]
                    f['screens'].append(sc)
                it['marks'] = [{'id': uid('mk'), 'screen': fr['id'], 'rect': {'x': 0, 'y': 0, 'w': 100, 'h': 100}} for fr in it.get('frames', [])]
                it.pop('frames', None)
        for sc in f['screens']:
            sc['next'] = [n if isinstance(n, dict) else {'to': n, 'label': ''} for n in sc.get('next', [])]
        for it in f['items']:
            it.setdefault('marks', [])

def write(html, c, m, g, set_title=False):
    for t, id_, val in (('application/json', 'msdoc-content', jdump(c)), ('application/json', 'msdoc-meta', jdump(m)), ('text/markdown', 'msdoc-guide', md_in(g))):
        mm = find(html, t, id_)
        html = html[:mm.start(2)] + val + html[mm.end(2):]
    if not set_title: return html  # 문서 제목(<title>)은 사용자가 정한 값을 그대로 둔다
    title = (c.get('background') or {}).get('title') or '마일스톤 문서'
    return re.sub(r'<title>.*?</title>', '<title>' + title.replace('&', '&amp;').replace('<', '&lt;') + ' 기획 문서</title>', html, count=1)


# ---------- dev spec block (optional, Claude-oriented backend notes) ----------
DEV_HEAD = re.compile(r'^<!--\s*devspec\s+(\{.*?\})\s*-->\s*\n?', re.S)

def read_dev(html):
    m = re.compile(BLOCK.format(t=re.escape('text/markdown'), id='msdoc-devspec'), re.S).search(html, 0, data_end(html))
    return md_out(m.group(2)) if m else ''

def write_dev(html, dev):
    rx = re.compile(BLOCK.format(t=re.escape('text/markdown'), id='msdoc-devspec'), re.S)
    m = rx.search(html, 0, data_end(html))
    if m: return html[:m.start(2)] + md_in(dev) + html[m.end(2):]
    g = find(html, 'text/markdown', 'msdoc-guide')
    return html[:g.end(3)] + '\n<script type="text/markdown" id="msdoc-devspec">' + md_in(dev) + '</script>' + html[g.end(3):]

def load_dev(d):
    p = os.path.join(d, 'devspec.md')
    return open(p).read() if os.path.exists(p) else None

def djb(text):
    x = 5381
    for ch in text: x = (x * 33 + ord(ch)) & 0xffffffff
    return format(x, '08x')

def spec_hashes(c):
    items = {}
    for f in c.get('spec', {}).get('features', []):
        for it in f.get('items', []):
            if it.get('code'): items[it['code']] = djb(json.dumps([f.get('feature') or '', f.get('screen') or '', it.get('title') or '', it.get('body') or ''], ensure_ascii=False, separators=(',', ':')))
    keys = sorted(items)
    return djb(json.dumps([[k, items[k]] for k in keys], ensure_ascii=False, separators=(',', ':'))), items

def dev_parse(src):
    m = DEV_HEAD.match(src or '')
    head = None
    if m:
        try: head = json.loads(m.group(1))
        except Exception: head = None
    return head, (src[m.end():] if m else (src or ''))

def dev_status(c, src):
    head, body = dev_parse(src); h, items = spec_hashes(c)
    if not body.strip(): return ('empty' if items else 'none'), [], [], []
    if not head: return 'stale', [], sorted(items), []
    if head.get('hash') == h: return 'fresh', [], [], []
    old = head.get('items') or {}
    return 'stale', [k for k in sorted(items) if k in old and old[k] != items[k]], [k for k in sorted(items) if k not in old], [k for k in sorted(old) if k not in items]

def cmd_dev_stamp(a):
    c = json.load(open(os.path.join(a.dir, 'content.json'))); migrate(c)
    src = load_dev(a.dir) or ''; head, body = dev_parse(src)
    h, items = spec_hashes(c)
    hd = {'hash': h, 'items': items, 'at': now(), 'by': a.by}
    open(os.path.join(a.dir, 'devspec.md'), 'w').write('<!-- devspec ' + json.dumps(hd, ensure_ascii=False) + ' -->\n' + body.lstrip())
    print('개발 명세를 정책', len(items), '개 기준으로 표시했어요')

def cmd_dev_status(a):
    html = open(a.html).read(); c, m, g = read(html)
    st, ch, ad, rm = dev_status(c, read_dev(html))
    print({'fresh': '개발 명세: 최신', 'empty': '개발 명세: 비어 있음', 'none': '개발 명세: 정책 없음', 'stale': '개발 명세: 갱신 필요'}[st])
    if ch: print('  수정된 정책:', ', '.join(ch))
    if ad: print('  추가된 정책:', ', '.join(ad))
    if rm: print('  삭제된 정책:', ', '.join(rm))

def unpack(html, d):
    c, m, g = read(html); os.makedirs(d, exist_ok=True)
    json.dump(c, open(os.path.join(d, 'content.json'), 'w'), ensure_ascii=False, indent=1)
    json.dump(m, open(os.path.join(d, 'meta.json'), 'w'), ensure_ascii=False, indent=1)
    open(os.path.join(d, 'guide.md'), 'w').write(g)
    open(os.path.join(d, 'devspec.md'), 'w').write(read_dev(html))

def load_dir(d):
    return (json.load(open(os.path.join(d, 'content.json'))), json.load(open(os.path.join(d, 'meta.json'))), open(os.path.join(d, 'guide.md')).read())

# ---------- 3-way merge ----------
def is_idlist(x): return isinstance(x, list) and len(x) > 0 and all(isinstance(i, dict) and 'id' in i for i in x)

def merge(b, m, l, path, cf):
    if m == b: return copy.deepcopy(l)
    if l == b or l == m: return copy.deepcopy(m)
    if isinstance(b, dict) and isinstance(m, dict) and isinstance(l, dict):
        out = {}
        for k in dict.fromkeys(list(l.keys()) + list(m.keys())):
            bk, mk, lk = b.get(k), m.get(k), l.get(k)
            if k not in m and k in b and lk == bk: continue
            if k not in l and k in b and mk == bk: continue
            out[k] = merge(bk, mk, lk, path + [k], cf)
        return out
    if isinstance(m, list) and isinstance(l, list) and (is_idlist(m) or is_idlist(l) or is_idlist(b or [])):
        b = b or []
        bi = {x['id']: x for x in b}; mi = {x['id']: x for x in m}; li = {x['id']: x for x in l}
        order = [x['id'] for x in l]
        if [x['id'] for x in b] == order and [x['id'] for x in m] != order:
            order = [x['id'] for x in m] + [i for i in order if i not in mi]
        order = [i for i in order if not (i in bi and i not in mi)]
        for idx, x in enumerate(m):
            i = x['id']
            if i in order: continue
            if i in bi and i not in li:
                if x != bi[i]: cf.append({'path': path + [{'id': i}], 'reason': '다른 사람이 지운 항목을 내가 고침'})
                continue
            pred = next((y['id'] for y in reversed(m[:idx]) if y['id'] in order), None)
            order.insert(order.index(pred) + 1 if pred else 0, i)
        out = []
        for i in order:
            if i in mi and i in li: out.append(merge(bi.get(i), mi[i], li[i], path + [{'id': i}], cf))
            elif i in li: out.append(copy.deepcopy(li[i]))
            else: out.append(copy.deepcopy(mi[i]))
        return out
    cf.append({'path': path, 'reason': '같은 칸을 양쪽에서 고침', 'mine': m, 'latest': l})
    return copy.deepcopy(l)

PRE = re.compile(r'^(\s*(?:#{1,4}\s+|[-*]\s+|\d+[.)]\s+|>\s?)?)(.*)$', re.S)
def change_summary(prev, nu, ui_changed):
    import difflib
    parts = []
    if not prev: parts.append('정책 추가')
    else:
        if prev.get('title') != nu.get('title'): parts.append('제목: ' + (nu.get('title') or ''))
        if prev.get('body') != nu.get('body'):
            a, b = (prev.get('body') or '').split('\n'), (nu.get('body') or '').split('\n')
            ch = []
            for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
                if op in ('replace', 'insert'): ch += [('n', t) for t in b[j1:j2] if t.strip()]
                elif op == 'delete': ch += [('d', t) for t in a[i1:i2] if t.strip()]
            if ch:
                k, t = ch[0]; t = PRE.match(t).group(2).strip('| ').strip()
                t = ('삭제: ' if k == 'd' else '') + t
                if len(t) > 44: t = t[:42] + '…'
                parts.append(t + (f' 외 {len(ch) - 1}곳' if len(ch) > 1 else ''))
    if ui_changed: parts.append('UI 예시 수정')
    s = ', '.join(parts)
    return (s[:58] + '…') if len(s) > 60 else (s or '수정')

def items_of(c):
    return {it['id']: (f, it) for f in c['spec']['features'] for it in f['items']}

def stamp_versions(base_c, merged_c, meta, by):
    """배포 후: 내 변경으로 바뀐 정책마다 버전 추가 + Changelog 기록."""
    t = now(); added = []
    bi = items_of(base_c)
    for f in merged_c['spec']['features']:
        for it in f['items']:
            vs = it.setdefault('versions', [])
            last = vs[-1] if vs else None
            text_changed = (not last) or last.get('title') != it.get('title') or last.get('body') != it.get('body')
            old = bi.get(it['id'], (None, None))[1]
            ui_changed = old is not None and json.dumps(old.get('marks', []), sort_keys=True) != json.dumps(it.get('marks', []), sort_keys=True)
            if not text_changed and not ui_changed: continue
            summary = change_summary(last, it, ui_changed)
            if text_changed:
                vs.append({'n': (last['n'] if last else 0) + 1, 'at': t, 'title': it.get('title', ''), 'body': it.get('body', ''), 'by': by})
            e = {'at': t, 'by': by, 'featureId': f['id'], 'itemId': it['id'], 'code': it.get('code', '-'), 'v': vs[-1]['n'] if vs else None, 'text': summary}
            meta.setdefault('log', []).append(e); added.append(e)
    mi = items_of(merged_c)
    for iid, (f, it) in bi.items():
        if iid not in mi and it.get('versions'):
            e = {'at': t, 'by': by, 'featureId': f['id'], 'itemId': iid, 'code': it.get('code', '-'), 'text': '정책 삭제: ' + (it.get('title') or '')}
            meta.setdefault('log', []).append(e); added.append(e)
    return added

def cmd_merge(a):
    bc, bm, bg = load_dir(a.base); mc, mm, mg = load_dir(a.mine)
    html = open(a.latest).read(); lc, lm, lg = read(html)
    cf = []
    c = merge(bc, mc, lc, [], cf)
    if mg == bg: g = lg
    elif lg == bg or lg == mg: g = mg
    else: g = lg; cf.append({'path': ['guide'], 'reason': '작업 지침을 양쪽에서 고침'})
    bd, md_, ld = load_dev(a.base) or '', load_dev(a.mine), read_dev(html)
    if md_ is None or md_ == bd: dv = ld
    elif ld == bd or ld == md_: dv = md_
    else: dv = ld; cf.append({'path': ['devspec'], 'reason': '개발 명세를 양쪽에서 고침'})
    meta = copy.deepcopy(lm); stamped = []
    if lm.get('deployedAt') and not cf:
        stamped = stamp_versions(lc, c, meta, a.by)
    if a.log: meta.setdefault('log', []).append({'at': now(), 'by': a.by, 'code': '-', 'text': a.log})
    meta['saveId'] = 'c-' + uuid.uuid4().hex[:8]; meta['updatedAt'] = now()
    if not cf: open(a.out, 'w').write(write_dev(write(html, c, meta, g), dv))
    print(json.dumps({'changed_since_base': {'content': lc != bc, 'guide': lg != bg, 'devspec': ld != bd, 'log_added_by_others': len(lm.get('log', [])) - len(bm.get('log', []))},
                      'deployed': bool(lm.get('deployedAt')), 'changelog_added': stamped, 'conflicts': cf}, ensure_ascii=False, indent=1, default=str))
    if cf: sys.exit(1)

def cmd_deploy(a):
    html = open(a.html).read(); c, m, g = read(html)
    if m.get('deployedAt'): sys.exit('이미 배포 완료된 문서예요: ' + m['deployedAt'])
    t = now()
    for f in c['spec']['features']:
        for it in f['items']:
            it['versions'] = [{'n': 1, 'at': t, 'title': it.get('title', ''), 'body': it.get('body', ''), 'by': a.by}]
    m['deployedAt'] = t; m['deployedBy'] = a.by
    m.setdefault('log', []).append({'at': t, 'by': a.by, 'code': '-', 'text': '배포 완료, 모든 정책을 v1로 기록'})
    m['saveId'] = 'c-' + uuid.uuid4().hex[:8]; m['updatedAt'] = t
    open(a.out, 'w').write(write(html, c, m, g)); print('배포 완료 처리:', t)

def blank():
    return {'schema': 2,
            'background': {'title': '', 'summary': '',
                           'roles': [{'id': uid('ro'), 'role': r, 'name': ''} for r in ['기획', '디자인', '백개발', '프론트개발', 'QA']],
                           'sections': [{'id': 'background', 'title': '진행 배경', 'hint': '이 마일스톤을 왜 지금 하는지 적어 주세요.', 'body': ''},
                                        {'id': 'features', 'title': '주요 기능 요약', 'hint': '이번에 만드는 핵심 기능을 짧게 적어 주세요.', 'body': ''},
                                        {'id': 'persona', 'title': '페르소나 및 사용 시나리오', 'hint': '누가 어떤 상황에서 쓰는지 적어 주세요.', 'body': ''},
                                        {'id': 'goal', 'title': '달성 목표', 'hint': '끝났을 때 확인할 수 있는 목표를 적어 주세요.', 'body': ''}]},
            'brief': {'versions': [{'id': 'bv-1', 'name': '초기 버전', 'createdAt': now(), 'demo': {'w': 390, 'h': 844, 'start': None, 'screens': []}, 'reqs': []}]},
            'final': {'figma': [], 'demo': {'w': 1280, 'h': 800, 'start': None, 'screens': []}},
            'spec': {'features': []}}  # feature: {id, feature, screen, screens: [], items: []}

def cmd_new(a):
    html = open(a.template).read(); c, m, g = read(html)
    c = blank()
    if a.name: c['background']['title'] = a.name
    t = now()
    m = {'template': 'milestone-doc', 'templateVersion': 2, 'docId': 'doc-' + uuid.uuid4().hex[:10], 'isTemplate': False,
         'saveId': 'c-' + uuid.uuid4().hex[:8], 'updatedAt': t, 'createdAt': t, 'createdBy': a.by, 'createdFrom': a.template_url or '',
         'deployedAt': None, 'log': []}
    open(a.out, 'w').write(write_dev(write(html, c, m, g, set_title=True), '')); print('새 문서', m['docId'])

def cmd_summary(a):
    c, m, g = read(open(a.html).read()); b = c['background']
    print('제목:', b['title'] or '(없음)', '| 템플릿 원본' if m.get('isTemplate') else '', '| 배포:', m.get('deployedAt') or '배포 전', '| Changelog', len(m.get('log', [])), '줄')
    print('담당:', ', '.join(f"{r['role']}={r['name'] or '-'}" for r in b['roles']))
    print('Background:', ', '.join(f"{s['title']}({'O' if s['body'].strip() else '빈칸'})" for s in b['sections']))
    for v in c['brief']['versions']:
        d = v['demo']
        print(f"Design Brief 버전 [{v['id']}] {v.get('name')} — 데모 {d['w']}x{d['h']} 시작={d.get('start')} 화면:", ', '.join(f"{s['id']}({s['name']})" for s in d['screens']) or '없음')
        for i, r in enumerate(v['reqs'], 1):
            print(f"  요구사항 {i} [{r['id']}] {r['title']} → 화면 {r.get('screen') or '-'} / mark {r.get('mark') or '-'} / pin {'O' if r.get('pin') else '-'}")
    fd = c['final']
    print('Final Design Figma:', ', '.join(f"{x.get('name')}({'스냅샷 있음' if x.get('assetId') else '미리보기 전'})" for x in fd['figma']) or '없음')
    print(f"Final Design 데모 {fd['demo']['w']}x{fd['demo']['h']} 시작={fd['demo'].get('start')} 화면:", ', '.join(f"{s['id']}({s['name']})" for s in fd['demo']['screens']) or '없음')
    for f in c['spec']['features']:
        if f.get('type') == 'link': print(f"Final Spec 링크 [{f['id']}] {f.get('title') or '-'} → {f.get('url')}"); continue
        print(f"Final Spec [{f['id']}] {f.get('title') or '-'} ({f.get('feature') or 'Feature'} / {f.get('screen') or 'Page'}{' / ' + f['section'] if f.get('section') else ''})")
        names = {sc['id']: sc.get('name') or '화면' for sc in f.get('screens', [])}
        for sc in f.get('screens', []):
            print(f"  화면 [{sc['id']}] {sc.get('name')} ({sc.get('kind')}, {sc.get('w')}px, x={sc.get('x')}, y={sc.get('y')}) → " + (', '.join(f"{names.get(n['to'], '?')}({n.get('label', '')})" for n in sc.get('next', [])) or '-'))
        for it in f['items']:
            vs = it.get('versions', [])
            mk = ', '.join(f"{names.get(m['screen'], '없는 화면')}:{m.get('mark') or '영역'}" for m in it.get('marks', []))
            print(f"  {it['code']} [{it['id']}] {it['title']} / 영역 {mk or '-'} / 버전 {('v' + str(vs[-1]['n'])) if vs else '-'}")

def cmd_check(a):
    c, m, g = read(open(a.html).read()); errs = []; ids = []
    def walk(o):
        if isinstance(o, dict):
            if 'id' in o: ids.append(o['id'])
            for k, v in o.items():
                if k in ('step', 'stepRef') and isinstance(v, dict): continue  # Final Spec 화면이 가리키는 저장된 화면 참조
                walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    cc = copy.deepcopy(c)
    for v in cc['brief']['versions'] + [{'demo': cc['final']['demo']}]:
        for sc in v['demo']['screens']:
            sc.pop('id', None)  # 데모 화면 id는 버전마다 같아도 된다 (data-go가 가리킴)
            sc.pop('steps', None)  # 저장된 화면 id는 데모(버전·HTML)마다 따로라 서로 같아도 된다
    walk(cc)
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup: errs.append(f'id 중복: {dup}')
    vids = [v['id'] for v in c['brief']['versions']]
    if len(vids) != len(set(vids)): errs.append(f'데모 버전 id 중복: {vids}')
    for v in c['brief']['versions']:
        d = v['demo']; sids = {s['id'] for s in d['screens']}; tag = f"[{v.get('name')}] "
        if d['screens'] and d.get('start') not in sids: errs.append(tag + '데모 시작 화면(start)이 화면 목록에 없음')
        for s in d['screens']:
            for go in re.findall(r'data-go="([^"]+)"', s.get('html', '')):
                if go != '@back' and go not in sids: errs.append(tag + f"데모 {s['id']}: 없는 화면으로 이동 data-go=\"{go}\"")
            if not s.get('app') and re.search(r'<script|\son\w+=', s.get('html', ''), re.I): errs.append(tag + f"데모 {s['id']}: 스크립트나 on* 속성은 실행되지 않음")
        for r in v['reqs']:
            if r.get('screen') and r['screen'] not in sids: errs.append(tag + f"요구사항 {r['id']}: 없는 데모 화면 {r['screen']}")
            if r.get('mark'):
                scr = next((s for s in d['screens'] if s['id'] == r.get('screen')), None)
                if scr and not (r['mark'] in (scr.get('marks') or {})) and f'data-mark="{r["mark"]}"' not in scr.get('html', ''): errs.append(tag + f"요구사항 {r['id']}: 화면 {r['screen']}에 data-mark=\"{r['mark']}\" 없음")
            p = r.get('pin')
            if p and not (0 <= p['x'] <= 100 and 0 <= p['y'] <= 100): errs.append(tag + f"요구사항 {r['id']}: pin 범위 밖")
    fdd = c['final']['demo']; fdids = {s['id'] for s in fdd['screens']}
    if fdd['screens'] and fdd.get('start') not in fdids: errs.append('Final Design 데모 시작 화면(start)이 목록에 없음')
    for s in fdd['screens']:
        for go in re.findall(r'data-go="([^"]+)"', s.get('html', '')):
            if go != '@back' and go not in fdids: errs.append(f"Final Design 데모 {s['id']}: 없는 화면으로 이동 data-go=\"{go}\"")
    for x in c['final']['figma']:
        if not re.search(r'figma\.com/.+node-id=', x.get('figmaUrl') or ''): errs.append(f"Final Design Figma {x.get('id')}: node-id가 있는 프레임 링크가 아님")
    codes = [it['code'] for f in c['spec']['features'] for it in f['items']]
    if len(codes) != len(set(codes)): errs.append(f'정책 코드 중복: {codes}')
    for f in c['spec']['features']:
        sids = {sc['id']: sc for sc in f.get('screens', [])}
        for sc in f.get('screens', []):
            if sc.get('kind') not in ('demo', 'html', 'image', 'figma'): errs.append(f"화면 {sc['id']}: kind는 demo, html, image, figma 중 하나")
            if sc.get('kind') == 'demo' and sc.get('demoScreen') not in fdids: errs.append(f"화면 {sc['id']}: Final Design 데모에 없는 화면 {sc.get('demoScreen')}")
            if sc.get('kind') == 'figma' and not re.search(r'figma\.com/.+node-id=', sc.get('figmaUrl') or ''): errs.append(f"화면 {sc['id']}: figma 링크에 node-id가 없음")
            for n in sc.get('next', []):
                if n.get('to') not in sids: errs.append(f"화면 {sc['id']}: 없는 화면으로 화살표")
        for it in f['items']:
            if len({m.get('screen') for m in it.get('marks', [])}) > 1: errs.append(f"{it['code']}: 정책 하나는 화면 하나에만 연결해야 함 (화면별로 정책을 나눌 것)")
            for m in it.get('marks', []):
                sc = sids.get(m.get('screen'))
                if not sc: errs.append(f"{it['code']} {m['id']}: 없는 화면을 가리킴"); continue
                html = sc.get('html', '') if sc.get('kind') == 'html' else next((d.get('html', '') for d in fdd['screens'] if d['id'] == sc.get('demoScreen')), '') if sc.get('kind') == 'demo' else None
                if m.get('mark') and html is not None and f'data-mark="{m["mark"]}"' not in html: errs.append(f"{it['code']}: 화면 {sc['id']}에 data-mark=\"{m['mark']}\" 없음")
                r = m.get('rect')
                if not m.get('mark') and not (r and all(0 <= r[k] <= 100 for k in 'xywh')): errs.append(f"{it['code']} {m['id']}: mark나 rect(0~100%)가 필요함")
            if m.get('deployedAt') and not it.get('versions'): errs.append(f"{it['code']}: 배포 후인데 버전이 없음")
    html_ = open(a.html).read(); st, ch, ad, rm = dev_status(c, read_dev(html_))
    if st == 'stale': print('주의: 개발 명세가 Final Spec보다 오래됐어요 (' + ', '.join(x for x in ['수정 ' + ','.join(ch) if ch else '', '추가 ' + ','.join(ad) if ad else '', '삭제 ' + ','.join(rm) if rm else ''] if x) + ')')
    if st == 'empty': print('주의: 개발 명세가 비어 있어요')
    print('\n'.join(errs) if errs else '문제 없음'); sys.exit(1 if errs else 0)


# ---------- situation helpers ----------
def _brief_ver(c, ver):
    vs = c['brief']['versions']
    if not ver: return vs[-1]
    for v in vs:
        if v['id'] == ver or v.get('name') == ver: return v
    sys.exit('Design Brief 버전을 찾지 못했어요: ' + ver)

def _flow(demo, label):
    scr = demo['screens']; ids = [x['id'] for x in scr]; start = demo.get('start') or (ids[0] if ids else None)
    edges = []
    for x in scr:
        for m in re.finditer(r'<([a-z0-9]+)[^>]*data-go="([^"]+)"[^>]*>(.*?)</\1>', x.get('html', ''), re.S | re.I):
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(3))).strip()[:24]
            edges.append((x['id'], m.group(2), txt))
        for g in re.findall(r'data-auto-go="([^"]+)"', x.get('html', '')): edges.append((x['id'], g, '(자동 이동)'))
    print(f'{label}: 화면 {len(ids)}개, 시작 {start}')
    for x in scr:
        outs = [f"{t}({txt or '-'})" for a, t, txt in edges if a == x['id']]
        print(f"  {x['id']} [{x.get('name')}] → " + (', '.join(dict.fromkeys(outs)) or '없음'))
    seen, todo = set(), [start] if start else []
    while todo:
        n = todo.pop()
        if n in seen or n not in ids: continue
        seen.add(n); todo += [t for a, t, _ in edges if a == n and t != '@back']
    bad = sorted({t for a, t, _ in edges if t != '@back' and t not in ids})
    unreach = [i for i in ids if i not in seen]
    if bad: print('  ! 없는 화면으로 이동:', bad)
    if unreach: print('  ! 시작에서 갈 수 없는 화면:', unreach)
    if not bad and not unreach: print('  흐름 문제 없음')
    return not bad and not unreach

def cmd_flow(a):
    c, m, g = read(open(a.html).read())
    ok = True
    if a.final or not a.brief:
        ok &= _flow(c['final']['demo'], 'Final Design 데모')
    if a.brief or not a.final:
        v = _brief_ver(c, a.version); ok &= _flow(v['demo'], f"Design Brief 데모 [{v.get('name')}]")
    sys.exit(0 if ok else 1)

def cmd_coverage(a):
    c, m, g = read(open(a.html).read())
    fd = c['final']['demo']; used = {}
    for f in c['spec']['features']:
        sc = {x['id']: x for x in f.get('screens', [])}
        for it in f['items']:
            for mk in it.get('marks', []):
                x = sc.get(mk['screen'])
                if x and x.get('kind') == 'demo' and mk.get('mark'): used.setdefault((x['demoScreen'], mk['mark']), []).append(it['code'])
    print('Final Design 데모의 영역(data-mark)과 쓰는 정책')
    for s in fd['screens']:
        names = list(dict.fromkeys(re.findall(r'data-mark="([^"]+)"', s.get('html', ''))))
        print(f"  {s['id']} [{s.get('name')}]: " + (', '.join(f"{n}={'/'.join(used.get((s['id'], n), [])) or '미사용'}" for n in names) or '영역 없음'))
    miss = [(k, v) for k, v in used.items() if not any(s['id'] == k[0] and f'data-mark="{k[1]}"' in s.get('html', '') for s in fd['screens'])]
    for (sid, mk), codes in miss: print(f"  ! {'/'.join(codes)}: 데모 {sid}에 data-mark=\"{mk}\"가 없음")
    unused_scr = [s['id'] for s in fd['screens'] if not any(x.get('kind') == 'demo' and x.get('demoScreen') == s['id'] for f in c['spec']['features'] for x in f.get('screens', []))]
    if unused_scr: print('  Final Spec에서 아직 안 쓰는 데모 화면:', unused_scr)
    nomark = [it['code'] for f in c['spec']['features'] for it in f['items'] if not it.get('marks')]
    if nomark: print('  영역이 없는 정책:', nomark)
    v = _brief_ver(c, a.version)
    print(f"Design Brief [{v.get('name')}] 요구사항")
    sids = {s['id']: s for s in v['demo']['screens']}
    for i, r in enumerate(v['reqs'], 1):
        s = sids.get(r.get('screen')); st = '화면 없음' if not s else ('OK' if (r.get('pin') or (r.get('mark') and (r['mark'] in (s.get('marks') or {}) or f'data-mark="{r["mark"]}"' in s.get('html', '')))) else '번호 위치 없음')
        print(f"  {i}. {r.get('title') or '(제목 없음)'} → {r.get('screen') or '-'}:{r.get('mark') or ('pin' if r.get('pin') else '-')} {st}")
    noreq = [s for s in sids if not any(r.get('screen') == s for r in v['reqs'])]
    if noreq: print('  요구사항이 없는 데모 화면:', noreq)

def cmd_brief_dup(a):
    p = os.path.join(a.dir, 'content.json'); c = json.load(open(p)); migrate(c)
    src = _brief_ver(c, a.source)
    nv = copy.deepcopy(src); nv['id'] = uid('bv'); nv['name'] = a.name; nv['createdAt'] = now(); nv['from'] = src['id']; nv['by'] = a.by
    nv['reqs'] = []  # 복제는 데모만, 요구사항은 비운다(페이지의 '지금 버전 복제하기'와 같음)
    vs = c['brief']['versions']; vs.insert(vs.index(src) + 1, nv)
    json.dump(c, open(p, 'w'), ensure_ascii=False, indent=1); print('새 버전', nv['id'], nv['name'], '←', src.get('name'))

def cmd_demo_export(a):
    """데모를 상단 위치 막대·하단 도구가 들어간 독립 HTML로 뽑는다(페이지 '내보내기'와 같은 형식). 다시 올리면 그대로 들어온다."""
    c, m, g = read(open(a.html, encoding='utf-8').read())
    if a.brief is not None:
        vs = c['brief']['versions']; v = next((x for x in vs if x.get('name') == a.brief or x['id'] == a.brief), vs[-1] if not a.brief else None)
        if not v: raise SystemExit('버전을 찾지 못했어요: ' + a.brief)
        demo, name = v['demo'], (v.get('name') or 'Design Brief') + ' · Design Brief'
    else:
        demo, name = c['final']['demo'], (c['background'].get('title') or 'Final Design') + ' · Final Design'
    flows = [{'id': f['id'], 'name': f.get('name', ''), 'app': True, 'html': f.get('html', ''), 'marks': f.get('marks') or {}, 'steps': f.get('steps') or []} for f in demo.get('screens', []) if f.get('app')]
    if not flows: raise SystemExit('앱 데모(HTML)가 없어요.')
    data = {'kind': 'msdoc-demo-export', 'v': 1, 'name': a.name or name, 'w': demo.get('w', 1280), 'h': demo.get('h', 800), 'start': demo.get('start') or flows[0]['id'], 'flows': flows, 'exportedAt': now()}
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'demo-viewer.html'), encoding='utf-8').read()
    import html as _h
    out = tpl.replace('__TITLE__', _h.escape(data['name'])).replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'))
    open(a.out, 'w', encoding='utf-8').write(out); print('추출:', a.out, f"HTML {len(flows)}개, 저장된 화면 {sum(len(f['steps']) for f in flows)}개")

# ---- 페이지 코드(화면 스크립트·스타일) 다루기 ----
CODE_PATS = [('app.js', r'(<script id="msdoc-app">)(.*?)(</script>)'), ('style.css', r'(<style id="msdoc-style">)(.*?)(</style>)')]

def cmd_code_out(a):
    html = open(a.html, encoding='utf-8').read(); os.makedirs(a.dir, exist_ok=True)
    for fn, pat in CODE_PATS:
        m = re.search(pat, html, re.S); open(os.path.join(a.dir, fn), 'w', encoding='utf-8').write(m.group(2))
    print('꺼냄:', a.dir, '(app.js, style.css)')

def _put_code(html, parts):
    for fn, pat in CODE_PATS:
        if fn not in parts: continue
        m = re.search(pat, html, re.S); html = html[:m.start(2)] + parts[fn] + html[m.end(2):]
    return html

def cmd_code_in(a):
    html = open(a.html, encoding='utf-8').read(); parts = {}
    for fn, _ in CODE_PATS:
        f = os.path.join(a.dir, fn)
        if os.path.exists(f): parts[fn] = open(f, encoding='utf-8').read()
    open(a.out, 'w', encoding='utf-8').write(_put_code(html, parts)); print('넣음:', a.out)

def cmd_transplant(a):
    """src의 페이지 코드(스크립트·스타일)를 latest에 옮긴다. 데이터 블록은 latest 그대로."""
    src = open(a.src, encoding='utf-8').read(); parts = {}
    for fn, pat in CODE_PATS: parts[fn] = re.search(pat, src, re.S).group(2)
    open(a.out, 'w', encoding='utf-8').write(_put_code(open(a.latest, encoding='utf-8').read(), parts)); print('코드 옮김:', a.out)

def cmd_screens(a):
    c, m, g = read(open(a.html, encoding='utf-8').read())
    def show(label, demo):
        print(f'== {label}')
        for fl in demo.get('screens', []):
            if not fl.get('app'): print(f"  [{fl['id']}] {fl.get('name')} (정적 화면)"); continue
            print(f"  [{fl['id']}] {fl.get('name')} — HTML {len(fl.get('html',''))//1024}KB, 저장된 화면 {len(fl.get('steps') or [])}")
            for st in fl.get('steps') or []:
                w = st.get('where') or {}; path = ' › '.join(v or 'Default' for v in [w.get('product'), w.get('menu'), w.get('page'), w.get('overlay'), w.get('state')])
                alias = '  (HTML 원래 위치: ' + ' › '.join((st['srcWhere'].get(k) or 'Default') for k in ['product','menu','page','overlay','state']) + ')' if st.get('srcWhere') else ''
                print(f"    {st['id']}: {path} | Figma {'O' if st.get('figma') else '-'} | 이동 {len(st.get('trail') or [])}단계{alias}")
    if a.brief is not None:
        for v in c['brief']['versions']:
            if not a.brief or v.get('name') == a.brief or v['id'] == a.brief: show('Design Brief · ' + (v.get('name') or v['id']), v['demo'])
    else: show('Final Design', c['final']['demo'])

def main():
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest='cmd', required=True)
    x = sp.add_parser('unpack'); x.add_argument('html'); x.add_argument('dir')
    x = sp.add_parser('pack'); x.add_argument('html'); x.add_argument('dir'); x.add_argument('-o', '--out', required=True)
    x = sp.add_parser('merge'); x.add_argument('base'); x.add_argument('mine'); x.add_argument('latest'); x.add_argument('-o', '--out', required=True); x.add_argument('--by', required=True); x.add_argument('--log')
    x = sp.add_parser('deploy'); x.add_argument('html'); x.add_argument('-o', '--out', required=True); x.add_argument('--by', required=True)
    x = sp.add_parser('new'); x.add_argument('template'); x.add_argument('-o', '--out', required=True); x.add_argument('--by', required=True); x.add_argument('--name'); x.add_argument('--template-url')
    x = sp.add_parser('summary'); x.add_argument('html')
    x = sp.add_parser('check'); x.add_argument('html')
    x = sp.add_parser('flow'); x.add_argument('html'); x.add_argument('--final', action='store_true'); x.add_argument('--brief', action='store_true'); x.add_argument('--version')
    x = sp.add_parser('coverage'); x.add_argument('html'); x.add_argument('--version')
    x = sp.add_parser('devspec-stamp'); x.add_argument('dir'); x.add_argument('--by', required=True)
    x = sp.add_parser('devspec-status'); x.add_argument('html')
    x = sp.add_parser('code-out'); x.add_argument('html'); x.add_argument('dir')
    x = sp.add_parser('code-in'); x.add_argument('html'); x.add_argument('dir'); x.add_argument('-o', '--out', required=True)
    x = sp.add_parser('transplant'); x.add_argument('src'); x.add_argument('latest'); x.add_argument('-o', '--out', required=True)
    x = sp.add_parser('demo-export'); x.add_argument('html'); x.add_argument('-o', '--out', required=True); x.add_argument('--brief', nargs='?', const='', default=None); x.add_argument('--name')
    x = sp.add_parser('screens'); x.add_argument('html'); x.add_argument('--brief', nargs='?', const='', default=None)
    x = sp.add_parser('brief-dup'); x.add_argument('dir'); x.add_argument('--name', required=True); x.add_argument('--by', required=True); x.add_argument('--source')
    a = p.parse_args()
    if a.cmd == 'unpack': unpack(open(a.html).read(), a.dir); print('꺼냈어요:', a.dir)
    elif a.cmd == 'pack':
        out = write(open(a.html).read(), *load_dir(a.dir)); dv = load_dev(a.dir)
        if dv is not None: out = write_dev(out, dv)
        open(a.out, 'w').write(out); print('넣었어요:', a.out)
    else: {'merge': cmd_merge, 'deploy': cmd_deploy, 'new': cmd_new, 'summary': cmd_summary, 'check': cmd_check, 'flow': cmd_flow, 'coverage': cmd_coverage, 'brief-dup': cmd_brief_dup, 'devspec-stamp': cmd_dev_stamp, 'devspec-status': cmd_dev_status, 'code-out': cmd_code_out, 'code-in': cmd_code_in, 'transplant': cmd_transplant, 'screens': cmd_screens, 'demo-export': cmd_demo_export}[a.cmd](a)

if __name__ == '__main__': main()
