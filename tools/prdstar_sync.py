#!/usr/bin/env python3
"""Datumo-Spec 레포(마일스톤 Markdown) ↔ PRDstar(db 문서) 연동 도구.

레포가 원본이다. PRDstar에는 레포의 글(Background · 명세 · 정책)을 올리고,
보드 화면 · 영역 · 데모 · Q&A · 버전처럼 PRDstar에서만 다루는 것은 PRDstar 쪽 값을 그대로 둔다.

명령
  new <slug> --title T [--area A]          templates/로 milestones/<slug> 만들기
  add-spec <ms_dir> --type feature|doc|link --title T   다음 번호·정책 코드로 명세 파일 추가
  check [<ms_dir>...]                      형식 검사 (없으면 milestones/ 전부)
  prep <dl_dir> -o <work>                  ArtifactData list(out_dir) 결과 → 작업 폴더(base/mine)
  init <ms_dir> -o <work>                  PRDstar에 아직 없는 마일스톤용 빈 작업 폴더 + ms 목록 문서
  apply <ms_dir> <work> [--force]          레포 글을 work/mine에 얹기. PRDstar에서 바뀐 글과 겹치면 멈춤
  batches <plan> <work>                    plan.json writes에 if_version을 붙여 50개씩 한 줄로 출력
  extract <work> <ms_dir>                  PRDstar 내용 → 레포 파일 (pull)
  mark-synced <ms_dir> <work>              올리기(push)가 끝난 뒤 동기화 기준 기록

작업 순서는 CLAUDE.md의 "PRDstar 연동"을 따른다.
"""
import argparse, copy, glob, hashlib, json, os, re, shutil, sys, uuid
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'prdstar'))
import prdstar, msdoc  # noqa: E402  (milestone-doc-work 스킬 스크립트 사본)

CONFIG = os.path.join(ROOT, 'prdstar.config.json')
STATE = '.prdstar.json'
STATUSES = ('', 'plan', 'design', 'dev', 'qa', 'ready', 'done')
SECTIONS = [('background', '진행 배경'), ('features', '주요 기능 요약'), ('persona', '페르소나 및 사용 시나리오'), ('goal', '달성 목표')]
DEFAULT_ROLES = ['기획', '디자인', '백개발', '프론트개발', 'QA']
BG_KEYS = ('title', 'area', 'status', 'summary')
LINK_KEYS = ('notion', 'figma')
FEAT_KEYS = {'feature': ('title', 'feature', 'screen', 'section', 'loc', 'desc'),
             'doc': ('title', 'loc', 'desc'),
             'link': ('title', 'url', 'desc')}
CODE_PREFIX = {'feature': 'fu', 'doc': 'do'}
SPEC_NAME = re.compile(r'^(\d{2,3})-(.+)\.md$')
POLICY = re.compile(r'^## ([A-Za-z]{2,4}-\d{1,4})(?:[ \t]+(.*?))?[ \t]*$', re.M)
SEC_HEAD = re.compile(r'^## (.+?)[ \t]*$', re.M)
FM = re.compile(r'\A---\n(.*?)\n---[ \t]*(?:\n|\Z)', re.S)


# ---------- 공통 ----------
def die(msg, code=1):
    print(msg, file=sys.stderr); sys.exit(code)

def config():
    if not os.path.exists(CONFIG): die('prdstar.config.json이 없어요: ' + CONFIG)
    return json.load(open(CONFIG, encoding='utf-8'))

def norm(s):
    s = '' if s is None else str(s)
    return '\n'.join(l.rstrip() for l in s.replace('\r', '').split('\n')).strip('\n')

def h(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

def rid(p, n=9):
    return p + '-' + uuid.uuid4().hex[:n]

def setv(obj, key, val):
    """글이 실제로 달라졌을 때만 바꾼다(빈 줄·끝 공백 차이로 버전이 새로 붙지 않게)."""
    val = '' if val is None else val
    if key not in obj and val == '': return
    if norm(obj.get(key)) != norm(val): obj[key] = val

def jload(p, default=None):
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else default

def jsave(p, o):
    with open(p, 'w', encoding='utf-8') as f: json.dump(o, f, ensure_ascii=False, indent=1); f.write('\n')


# ---------- frontmatter ----------
def fm_parse(text, path):
    m = FM.match(text.replace('\r', ''))
    if not m: return [], text.replace('\r', '')
    pairs = []
    for i, ln in enumerate(m.group(1).split('\n'), 2):
        if not ln.strip() or ln.lstrip().startswith('#'): continue
        k, sep, v = ln.partition(':')
        if not sep: die('%s:%d frontmatter 줄에 ":"가 없어요: %s' % (path, i, ln))
        v = v.strip()
        if v.startswith('"'):
            try: v = json.loads(v)
            except ValueError: die('%s:%d 따옴표 값을 읽지 못했어요: %s' % (path, i, ln))
        pairs.append((k.strip(), v))
    return pairs, text.replace('\r', '')[m.end():]

def fm_val(v):
    v = '' if v is None else str(v)
    if v != v.strip() or '\n' in v or v[:1] in ('"', '#'): return json.dumps(v, ensure_ascii=False)
    return v

def fm_dump(pairs):
    return '---\n' + ''.join('%s: %s\n' % (k, fm_val(v)) if fm_val(v) else '%s:\n' % k for k, v in pairs) + '---\n'

def blocks(body, rx):
    """'## 제목' 단위로 나눈다. (머리글 앞 글, [(match, 본문)])"""
    ms = list(rx.finditer(body))
    pre = body[:ms[0].start()] if ms else body
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        out.append((m, norm(body[m.end():end])))
    return norm(pre), out


# ---------- 레포 읽기 ----------
def read_milestone(d):
    p = os.path.join(d, 'milestone.md')
    if not os.path.exists(p): die('milestone.md가 없어요: ' + d)
    pairs, body = fm_parse(open(p, encoding='utf-8').read(), p)
    bg = {'links': {}, 'roles': [], 'sections': []}
    for k, v in pairs:
        if k in BG_KEYS: bg[k] = v
        elif k in LINK_KEYS: bg['links'][k] = v
        elif k.startswith('link.'): bg['links'][k[5:]] = v
        else: bg['roles'].append((k, v))
    pre, secs = blocks(body, SEC_HEAD)
    bg['pre'] = pre
    bg['sections'] = [(m.group(1).strip(), b) for m, b in secs]
    feats = []
    sd = os.path.join(d, 'specs')
    for name in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        if not SPEC_NAME.match(name): continue
        fp = os.path.join(sd, name)
        fpairs, fbody = fm_parse(open(fp, encoding='utf-8').read(), fp)
        f = dict(fpairs); f['_file'] = fp
        f.setdefault('type', 'feature')
        fpre, items = blocks(fbody, POLICY)
        f['_pre'] = fpre
        f['items'] = [(m.group(1), (m.group(2) or '').strip(), b) for m, b in items]
        feats.append(f)
    return {'bg': bg, 'features': feats, 'dir': d}

def read_state(d):
    return jload(os.path.join(d, STATE), {}) or {}


# ---------- 내용 ↔ 단위(충돌 검사용) ----------
def units(c):
    U = {}
    b = c.get('background') or {}
    U['bg'] = h({'f': [norm(b.get(k)) for k in BG_KEYS],
                 'l': {k: norm(v) for k, v in sorted((b.get('links') or {}).items()) if norm(v)},
                 'r': [[r.get('role'), norm(r.get('name'))] for r in b.get('roles') or []],
                 's': [[s.get('title'), norm(s.get('body'))] for s in b.get('sections') or []]})
    feats = (c.get('spec') or {}).get('features') or []
    U['order'] = h([f.get('id') for f in feats])
    for f in feats:
        t = f.get('type') or 'feature'
        U['feat:' + f['id']] = h({'t': t, 'k': [norm(f.get(k)) for k in FEAT_KEYS.get(t, FEAT_KEYS['feature'])],
                                  'i': [it.get('code') for it in f.get('items') or []]})
        for it in f.get('items') or []:
            U['item:' + str(it.get('code'))] = h([f['id'], norm(it.get('title')), norm(it.get('body'))])
    return U

def unit_label(k, c):
    if k == 'bg': return 'Background(제목·영역·상태·담당·링크·섹션)'
    if k == 'order': return '명세 순서'
    for f in (c.get('spec') or {}).get('features') or []:
        if k == 'feat:' + f['id']: return '명세 "%s"(%s)' % (f.get('title', ''), f['id'])
    return '정책 ' + k.split(':', 1)[1]


# ---------- 레포 글을 PRDstar 내용에 얹기 ----------
def compose(c, repo):
    c = copy.deepcopy(c)
    b = c.setdefault('background', {})
    rb = repo['bg']
    for k in BG_KEYS: setv(b, k, rb.get(k, ''))
    links = b.setdefault('links', {})
    for k, v in rb['links'].items(): setv(links, k, v)
    for k in list(links):
        if k not in rb['links'] and norm(links[k]): links[k] = ''
    old_roles = {r.get('role'): r for r in b.get('roles') or []}
    roles = []
    for role, name in rb['roles']:
        r = copy.deepcopy(old_roles.get(role) or {'id': rid('ro', 4), 'role': role, 'name': ''})
        setv(r, 'name', name); roles.append(r)
    if [r.get('role') for r in roles] != [r.get('role') for r in b.get('roles') or []] or any(
            norm(x.get('name')) != norm(y.get('name')) for x, y in zip(roles, b.get('roles') or [])):
        b['roles'] = roles
    old_secs = {s.get('title'): s for s in b.get('sections') or []}
    defaults = dict((t, i) for i, t in SECTIONS)
    secs = []
    for title, body in rb['sections']:
        s = copy.deepcopy(old_secs.get(title) or {'id': defaults.get(title) or rid('sec', 6), 'title': title, 'hint': '', 'body': ''})
        setv(s, 'body', body); secs.append(s)
    b['sections'] = secs

    sp = c.setdefault('spec', {})
    old = sp.get('features') or []
    by_id = {f['id']: f for f in old}
    by_code = {it.get('code'): it for f in old for it in f.get('items') or []}
    new_ids = {}
    out = []
    for rf in repo['features']:
        t = rf.get('type', 'feature')
        ef = by_id.get(rf.get('id') or '')
        if ef is None:
            ef = {'id': rf.get('id') or rid('ft'), 'type': t, 'title': '', 'desc': '', 'screens': [], 'items': []}
            if t == 'feature': ef.update({'feature': '', 'screen': '', 'section': '', 'loc': ''})
            if t == 'doc': ef['loc'] = ''
            if t == 'link': ef['url'] = ''
            if not rf.get('id'): new_ids[rf['_file']] = ef['id']
        f = copy.deepcopy(ef); f['type'] = t
        for k in FEAT_KEYS[t]: setv(f, k, rf.get(k, ''))
        items = []
        for code, title, body in rf['items']:
            ei = by_code.get(code)
            it = copy.deepcopy(ei) if ei else {'id': rid('it'), 'code': code, 'title': '', 'body': ''}
            if not ei and t == 'feature': it['marks'] = []
            setv(it, 'title', title); setv(it, 'body', body); items.append(it)
        f['items'] = items
        out.append(f)
    sp['features'] = out
    return c, new_ids

def write_ids(new_ids):
    for path, fid in new_ids.items():
        pairs, body = fm_parse(open(path, encoding='utf-8').read(), path)
        pairs = [('id', fid)] + [(k, v) for k, v in pairs if k != 'id']
        open(path, 'w', encoding='utf-8').write(fm_dump(pairs) + ('\n' + body.lstrip('\n') if body.strip() else ''))


# ---------- PRDstar 내용 → 레포 파일 ----------
def slug(s, fallback):
    s = re.sub(r'[\\/:*?"<>|#%&{}$!\'`@+=,;\[\]()]+', '', (s or '').strip())
    s = re.sub(r'\s+', '-', s).strip('-.')[:40].strip('-.')
    return s or fallback

def write_milestone(d, c, ms_id, url):
    os.makedirs(os.path.join(d, 'specs'), exist_ok=True)
    b = c.get('background') or {}
    pairs = [(k, b.get(k, '')) for k in BG_KEYS]
    links = b.get('links') or {}
    pairs += [(k, links.get(k, '')) for k in LINK_KEYS]
    pairs += [('link.' + k, v) for k, v in links.items() if k not in LINK_KEYS and norm(v)]
    pairs += [(r.get('role', ''), r.get('name', '')) for r in b.get('roles') or []]
    body = ''.join('## %s\n\n%s' % (s.get('title', ''), (norm(s.get('body')) + '\n\n') if norm(s.get('body')) else '')
                   for s in b.get('sections') or [])
    open(os.path.join(d, 'milestone.md'), 'w', encoding='utf-8').write(fm_dump(pairs) + '\n' + body.rstrip('\n') + '\n')

    sd = os.path.join(d, 'specs')
    have = {}
    for name in os.listdir(sd):
        m = SPEC_NAME.match(name)
        if not m: continue
        fp = os.path.join(sd, name)
        fid = dict(fm_parse(open(fp, encoding='utf-8').read(), fp)[0]).get('id')
        if fid: have[fid] = (fp, m.group(2))
        else: print('주의: id 없는(아직 올리지 않은) 명세는 그대로 뒀어요:', fp)
    feats = (c.get('spec') or {}).get('features') or []
    keep = set()
    for i, f in enumerate(feats, 1):
        t = f.get('type') or 'feature'
        rest = have[f['id']][1] if f['id'] in have else slug(f.get('title'), f['id'])
        fp = os.path.join(sd, '%02d-%s.md' % (i, rest))
        if f['id'] in have and have[f['id']][0] != fp: os.remove(have[f['id']][0])
        fpairs = [('id', f['id']), ('type', t)] + [(k, f.get(k, '')) for k in FEAT_KEYS.get(t, FEAT_KEYS['feature'])]
        fbody = ''.join('## %s%s\n\n%s' % (it.get('code', ''), (' ' + it['title'].strip()) if (it.get('title') or '').strip() else '',
                                            (norm(it.get('body')) + '\n\n') if norm(it.get('body')) else '')
                        for it in f.get('items') or [])
        open(fp, 'w', encoding='utf-8').write(fm_dump(fpairs) + ('\n' + fbody.rstrip('\n') + '\n' if fbody else ''))
        keep.add(fp)
    for fid, (fp, _) in have.items():
        if fp not in keep and os.path.exists(fp): os.remove(fp); print('PRDstar에 없는 명세를 지웠어요:', fp)
    st = read_state(d); st.update({'url': url, 'msId': ms_id}); jsave(os.path.join(d, STATE), st)


# ---------- 검사 ----------
def check_dir(d, cfg):
    errs, warns = [], []
    repo = read_milestone(d)
    bg = repo['bg']
    if not norm(bg.get('title')): errs.append('milestone.md: title이 비어 있어요')
    if bg.get('status', '') not in STATUSES: errs.append('milestone.md: status는 %s 중 하나예요 (지금: %s)' % ('|'.join(STATUSES[1:]), bg.get('status')))
    if bg.get('pre'): errs.append('milestone.md: 첫 "## 섹션" 앞에 글이 있어요(올라가지 않아요)')
    names = [t for t, _ in bg['sections']]
    for _, t in SECTIONS:
        if t not in names: warns.append('milestone.md: "## %s" 섹션이 없어요' % t)
    if len(set(names)) != len(names): errs.append('milestone.md: 같은 이름의 섹션이 두 번 있어요')
    codes, ids = {}, {}
    for f in repo['features']:
        rel = os.path.relpath(f['_file'], ROOT); t = f.get('type')
        if t not in FEAT_KEYS: errs.append('%s: type은 feature|doc|link 중 하나예요 (지금: %s)' % (rel, t)); continue
        if not norm(f.get('title')): errs.append(rel + ': title이 비어 있어요')
        if f.get('id'):
            if f['id'] in ids: errs.append('%s: id %s가 %s와 겹쳐요' % (rel, f['id'], ids[f['id']]))
            ids[f['id']] = rel
        if f['_pre']: errs.append(rel + ': 첫 정책(## fu-01 …) 앞에 글이 있어요. 설명은 frontmatter desc에 쓰세요')
        for m in SEC_HEAD.finditer(fm_parse(open(f['_file'], encoding='utf-8').read(), f['_file'])[1]):
            if not POLICY.match(m.group(0)): warns.append('%s: "%s"는 정책 머리글(## 코드 제목)이 아니라 앞 정책 본문에 들어가요' % (rel, m.group(0)))
        if t == 'link':
            if not norm(f.get('url')): errs.append(rel + ': 링크 명세에는 url이 필요해요')
            if f['items']: errs.append(rel + ': 링크 명세에는 정책을 쓰지 않아요')
        elif not f['items']: warns.append(rel + ': 정책이 하나도 없어요')
        for code, title, body in f['items']:
            pre = code.split('-')[0]
            if t in CODE_PREFIX and pre != CODE_PREFIX[t]: warns.append('%s: %s 명세의 정책 코드는 %s-NN을 써요 (%s)' % (rel, t, CODE_PREFIX[t], code))
            if code in codes: errs.append('%s: 정책 코드 %s가 %s와 겹쳐요' % (rel, code, codes[code]))
            codes[code] = rel
            if not norm(title): warns.append('%s: %s 제목이 비어 있어요' % (rel, code))
            if title in ('정책 제목', '섹션 제목') or norm(body) == '- [확인 필요]': warns.append('%s: %s가 템플릿 그대로예요' % (rel, code))
    st = read_state(d)
    if st.get('url') and cfg and st['url'] != cfg.get('url'):
        warns.append('%s: 연결된 PRDstar(%s)가 prdstar.config.json(%s)과 달라요' % (STATE, st['url'], cfg.get('url')))
    return errs, warns


# ---------- 명령 ----------
def cmd_new(a):
    d = os.path.join(ROOT, 'milestones', a.slug)
    if os.path.exists(d): die('이미 있어요: ' + d)
    os.makedirs(os.path.join(d, 'specs'))
    t = open(os.path.join(ROOT, 'templates', 'milestone.md'), encoding='utf-8').read()
    pairs, body = fm_parse(t, 'templates/milestone.md')
    pairs = [(k, a.title if k == 'title' else (a.area or '') if k == 'area' else 'plan' if k == 'status' else v) for k, v in pairs]
    open(os.path.join(d, 'milestone.md'), 'w', encoding='utf-8').write(fm_dump(pairs) + '\n' + body.lstrip('\n'))
    for n in ('plan.md', 'tasks.md'):
        shutil.copy(os.path.join(ROOT, 'templates', n), os.path.join(d, n))
    open(os.path.join(d, 'specs', '.gitkeep'), 'w').close()
    print('만들었어요:', os.path.relpath(d, ROOT))

def cmd_add_spec(a):
    d = a.ms_dir; repo = read_milestone(d); sd = os.path.join(d, 'specs'); os.makedirs(sd, exist_ok=True)
    nums = [int(SPEC_NAME.match(n).group(1)) for n in os.listdir(sd) if SPEC_NAME.match(n)]
    n = max(nums or [0]) + 1
    fp = os.path.join(sd, '%02d-%s.md' % (n, slug(a.title, 'spec')))
    t = open(os.path.join(ROOT, 'templates', 'spec-%s.md' % a.type), encoding='utf-8').read()
    pairs, body = fm_parse(t, 'template')
    pairs = [(k, a.title if k == 'title' else v) for k, v in pairs]
    if a.type in CODE_PREFIX:
        pre = CODE_PREFIX[a.type]
        used = [int(c.split('-')[1]) for f in repo['features'] for c, _, _ in f['items'] if c.startswith(pre + '-')]
        nxt = max(used or [0]) + 1
        body = re.sub(r'^## %s-01' % pre, '## %s-%02d' % (pre, nxt), body, flags=re.M)
    open(fp, 'w', encoding='utf-8').write(fm_dump(pairs) + ('\n' + body.lstrip('\n') if body.strip() else ''))
    print('추가했어요:', os.path.relpath(fp, ROOT))

def cmd_check(a):
    cfg = jload(CONFIG)
    dirs = a.dirs or sorted(p for p in glob.glob(os.path.join(ROOT, 'milestones', '*')) if os.path.isdir(p))
    bad = 0
    for d in dirs:
        errs, warns = check_dir(d, cfg)
        print('[%s] %s' % ('오류' if errs else '확인', os.path.relpath(d, ROOT)))
        for e in errs: print('  오류:', e)
        for w in warns: print('  주의:', w)
        bad += len(errs)
    if not dirs: print('검사할 마일스톤이 없어요.')
    sys.exit(1 if bad else 0)

LIST_ROW = re.compile(r'^- "([^"]+)"\s+\d+ bytes\s+version (\d+)', re.M)
LIST_MORE = re.compile(r'"([^"]+)" (\d+)(?=[,\]])')

def cmd_prep(a):
    """ArtifactData list(out_dir)로 받은 폴더 → prdstar.py 작업 폴더. 문서 버전(if_version)은 list 결과 글에만 있어서
    그 글을 저장한 파일(--listing)에서 읽는다."""
    dd = prdstar.find_docs_dir(a.dl)
    for f in os.listdir(dd):
        if f.endswith('.json') and '@' in f: os.rename(os.path.join(dd, f), os.path.join(dd, f.replace('@', '~')))
    docs = {f[:-5] for f in os.listdir(dd) if f.endswith('.json')}
    versions = {}
    if a.listing:
        txt = open(a.listing, encoding='utf-8').read()
        for rx in (LIST_ROW, LIST_MORE):
            for m in rx.finditer(txt):
                if m.group(1) in docs: versions[m.group(1)] = int(m.group(2))
    missing = sorted(docs - set(versions))
    if missing: print('주의: 버전을 모르는 문서 %d개(이 문서를 고치면 batches에서 멈춰요): %s' % (len(missing), ', '.join(missing[:8])))
    prdstar.cmd_pull(SimpleNamespace(docs=a.dl, files=None, no_files=True, out=a.out))
    jsave(os.path.join(a.out, 'versions.json'), versions)

def cmd_init(a):
    repo = read_milestone(a.ms_dir); st = read_state(a.ms_dir); cfg = config()
    ms = st.get('msId') or ('ms-' + uuid.uuid4().hex[:10])
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):   # prdstar.py가 찍는 listDoc 대신 아래(상태 포함)를 쓴다
        prdstar.cmd_init(SimpleNamespace(title=repo['bg'].get('title', ''), area=repo['bg'].get('area', ''), guide=None, ms=ms, out=a.out))
    jsave(os.path.join(a.out, 'versions.json'), {})
    st.update({'url': cfg['url'], 'msId': ms}); jsave(os.path.join(a.ms_dir, STATE), st)
    now = msdoc.now()
    print(json.dumps({'listDoc': {'collection': 'ms', 'doc_id': ms, 'data': {
        'title': repo['bg'].get('title', ''), 'area': repo['bg'].get('area', ''), 'status': repo['bg'].get('status') or 'plan',
        'createdAt': now, 'createdBy': None, 'active': True, 'deployedAt': None, 'updatedAt': now}}}, ensure_ascii=False, indent=1))

def cmd_apply(a):
    w = a.work; cfg = config(); st = read_state(a.ms_dir)
    if st.get('url') and st['url'] != cfg['url'] and not a.force:
        die('이 마일스톤은 다른 PRDstar(%s)에 연결돼 있어요. prdstar.config.json(%s)을 확인하세요.' % (st['url'], cfg['url']), 3)
    errs, _ = check_dir(a.ms_dir, cfg)
    if errs: die('형식 오류가 있어 멈췄어요:\n  ' + '\n  '.join(errs))
    repo = read_milestone(a.ms_dir)
    mine_p = os.path.join(w, 'mine', 'content.json'); cur = jload(mine_p)
    composed, new_ids = compose(cur, repo)
    pu, ru = units(cur), units(composed)
    syn = (st.get('synced') or {}).get('units')
    is_new = not (cur.get('spec') or {}).get('features') and not norm((cur.get('background') or {}).get('title')) or json.load(open(os.path.join(w, 'pull.json'))).get('new')
    conflicts = []
    if syn is not None:
        for k in sorted(set(pu) | set(syn)):
            if pu.get(k) != syn.get(k) and ru.get(k) != pu.get(k): conflicts.append(unit_label(k, cur if k in pu else composed))
    elif not is_new:
        conflicts.append('이 마일스톤을 PRDstar에서 받아 온(pull) 기록이 없어요')
    if conflicts and not a.force:
        die('PRDstar에서 바뀐 글이 레포와 달라 멈췄어요. 먼저 pull로 받아 git diff로 합친 뒤 다시 올리세요:\n  ' + '\n  '.join(conflicts), 3)
    changed = sorted(k for k in set(pu) | set(ru) if pu.get(k) != ru.get(k))
    jsave(mine_p, composed); write_ids(new_ids)
    b = composed['background']
    print(json.dumps({'msId': json.load(open(os.path.join(w, 'pull.json')))['msId'], 'changed': [unit_label(k, composed if k in ru else cur) for k in changed],
                      'removed': [unit_label(k, cur) for k in changed if k not in ru], 'newSpecIds': {os.path.relpath(p, ROOT): i for p, i in new_ids.items()},
                      'forced': bool(conflicts), 'listPatch': {'title': b.get('title', ''), 'area': b.get('area', ''), 'status': b.get('status') or 'plan', 'updatedAt': msdoc.now()}},
                     ensure_ascii=False, indent=1))

def cmd_batches(a):
    plan = jload(os.path.join(a.plan, 'plan.json'))
    if plan['uploads']: die('올릴 파일이 있어요. prdstar.py finalize를 먼저 하세요.')
    vers = jload(os.path.join(a.work, 'versions.json'), {})
    existing = {f[:-5] for f in os.listdir(os.path.join(a.work, 'docs')) if f.endswith('.json')} if os.path.isdir(os.path.join(a.work, 'docs')) else set()
    unknown = sorted(x['doc_id'] for x in plan['writes'] if x['doc_id'] in existing and x['doc_id'] not in vers)
    if unknown: die('PRDstar에 이미 있는데 버전을 모르는 문서예요. list 결과 글을 저장해 prep --listing으로 다시 하세요: ' + ', '.join(unknown))
    ws = []
    for x in plan['writes']:
        x = dict(x)
        if x['doc_id'] in vers: x['if_version'] = vers[x['doc_id']]
        if x.get('file_path'): x['file_path'] = os.path.abspath(x['file_path'])
        ws.append(x)
    for i in range(0, len(ws), 50): print(json.dumps(ws[i:i + 50], ensure_ascii=False))

def cmd_extract(a):
    w = a.work; cfg = config()
    c = jload(os.path.join(w, 'mine', 'content.json')); ms = jload(os.path.join(w, 'pull.json'))['msId']
    st = read_state(a.ms_dir) if os.path.isdir(a.ms_dir) else {}
    if st.get('msId') and st['msId'] != ms and not a.force: die('다른 마일스톤(%s)에 연결된 폴더예요.' % st['msId'], 3)
    os.makedirs(a.ms_dir, exist_ok=True)
    write_milestone(a.ms_dir, c, ms, cfg['url'])
    dev = open(os.path.join(w, 'mine', 'devspec.md'), encoding='utf-8').read()
    dp = os.path.join(a.ms_dir, 'devspec.md')
    if norm(dev): open(dp, 'w', encoding='utf-8').write(dev.rstrip('\n') + '\n')
    for n in ('plan.md', 'tasks.md'):
        if not os.path.exists(os.path.join(a.ms_dir, n)): shutil.copy(os.path.join(ROOT, 'templates', n), os.path.join(a.ms_dir, n))
    # 받은 그대로를 다시 읽어 기준으로 삼는다(레포 표기로 바뀐 글이 다음 push 때 충돌로 보이지 않게)
    composed, _ = compose(c, read_milestone(a.ms_dir))
    st = read_state(a.ms_dir); st['synced'] = {'at': msdoc.now(), 'units': units(c)}
    jsave(os.path.join(a.ms_dir, STATE), st)
    drift = sorted(k for k in set(units(c)) | set(units(composed)) if units(c).get(k) != units(composed).get(k))
    print('받았어요:', os.path.relpath(a.ms_dir, ROOT), '(msId %s)' % ms)
    if drift: print('주의: 레포 표기로 옮기며 달라진 항목:', ', '.join(drift))

def cmd_mark_synced(a):
    c = jload(os.path.join(a.work, 'mine', 'content.json'))
    st = read_state(a.ms_dir); st['synced'] = {'at': msdoc.now(), 'units': units(c)}
    jsave(os.path.join(a.ms_dir, STATE), st); print('동기화 기준을 기록했어요:', os.path.relpath(os.path.join(a.ms_dir, STATE), ROOT))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    x = sp.add_parser('new'); x.add_argument('slug'); x.add_argument('--title', required=True); x.add_argument('--area'); x.set_defaults(f=cmd_new)
    x = sp.add_parser('add-spec'); x.add_argument('ms_dir'); x.add_argument('--type', choices=['feature', 'doc', 'link'], default='feature'); x.add_argument('--title', required=True); x.set_defaults(f=cmd_add_spec)
    x = sp.add_parser('check'); x.add_argument('dirs', nargs='*'); x.set_defaults(f=cmd_check)
    x = sp.add_parser('prep'); x.add_argument('dl'); x.add_argument('-o', '--out', required=True); x.add_argument('--listing', help='ArtifactData list 결과 글을 저장한 파일(문서 버전)'); x.set_defaults(f=cmd_prep)
    x = sp.add_parser('init'); x.add_argument('ms_dir'); x.add_argument('-o', '--out', required=True); x.set_defaults(f=cmd_init)
    x = sp.add_parser('apply'); x.add_argument('ms_dir'); x.add_argument('work'); x.add_argument('--force', action='store_true'); x.set_defaults(f=cmd_apply)
    x = sp.add_parser('batches'); x.add_argument('plan'); x.add_argument('work'); x.set_defaults(f=cmd_batches)
    x = sp.add_parser('extract'); x.add_argument('work'); x.add_argument('ms_dir'); x.add_argument('--force', action='store_true'); x.set_defaults(f=cmd_extract)
    x = sp.add_parser('mark-synced'); x.add_argument('ms_dir'); x.add_argument('work'); x.set_defaults(f=cmd_mark_synced)
    a = p.parse_args(); a.f(a)

if __name__ == '__main__':
    main()
