# PRDstar Structure

저장소는 2개예요. **db 1개**(문서 저장소, 컬렉션 8개)와 **파일 저장소 1개**. 페이지 HTML에는 화면 코드만 있어요.

| # | 저장소 · 컬렉션 | 단위 | 쓰는 곳 |
|---|---|---|---|
| 1 | db `ms` | 마일스톤 1개 = 문서 1개 | 마일스톤 선택기, 저장소 탭 |
| 2 | db `ms/{msId}/d` | 마일스톤 내용 조각 1개 = 문서 1개 | 모든 탭 |
| 3 | db `disc` | Q&A 질문 1개 | Q&A 탭, 정책 아래 Q&A |
| 4 | db `disc/{tid}/msgs` | Q&A 메시지 1개 | Q&A 창 |
| 5 | db `reqmsg` | 요구사항 대화 메시지 1개 | Design Brief 요구사항 "대화" |
| 6 | db `work` | Claude 작업 1건 | 상단 "Claude 작업 중" |
| 7 | db `feedback` | 의견 1건 | PRDstar 창 "의견 제출" |
| 8 | db `toolLog` | 도구 변경 기록 1건 | PRDstar 창 "Changelog" |
| 9 | 파일 저장소 | 파일 1개 (text/plain · application/json) | 데모 HTML, Final Spec 스냅샷 묶음 |

한도: db 문서 하나 256KB · 아티팩트 db 문서 25,000개 · 파일 하나 20MB · 파일 5,000개 · 1,024MB.
문서는 last-writer-wins(나중에 쓴 쪽이 남음), 트랜잭션 없음. 관계는 문서 안 id와 순서 배열로 이어요.

---

## 1. `ms/{msId}` — 마일스톤 목록
```
msId            string  PK   "ms-" + 영문 소문자·숫자 9~10자
title           string       마일스톤 제목
area            string       기능 영역 "Feature / Subfeature"
createdAt       string       ISO 시각
createdBy       string|null  만든 사람 id
active          bool         false면 목록에서 숨김
deployedAt      string|null  배포 완료 시각
updatedAt       string       마지막 저장
importedSaveId  string?      예전 문서에서 가져온 저장본 id
status          string       plan|design|dev|qa|ready|done (기획중·디자인중·개발중·QA중·배포준비중·배포완료, bg.status와 같음)
```
```json
{"title":"판단형 모델 (Jev + Davi) 추가","area":"Evaluation / Criteria","createdAt":"2026-10-21T09:52:20.710Z",
 "createdBy":"u_Rnjr0F…","active":true,"deployedAt":"2026-10-21T01:50:56.731Z","updatedAt":"2026-10-21T10:12:03Z"}
```

## 2. `ms/{msId}/d/{docId}` — 마일스톤 내용
문서 이름(docId)으로 종류를 나눠요. 마일스톤을 열 때 이 컬렉션 하나만 구독해요.

| docId | 1개/여러 개 | 내용 |
|---|---|---|
| `meta` | 1 | 배포·저장 정보 |
| `log` | 1 | Changelog `{entries:[]}` |
| `bg` | 1 | Background |
| `guide` | 1 | 예전 작업 지침(쓰지 않음) |
| `dev` | 1 | AI용 텍스트 명세 `{text}` |
| `root` | 1 | 그 밖의 최상위 값 `{schema:2}` |
| `brief` | 1 | Design Brief 공통 + 버전 순서 (예전 데이터 보관, 화면에서는 쓰지 않음) |
| `ver~{vid}` | N | Design Brief 버전 (요구사항 제외) |
| `req~{vid}~{rid}` | N | 요구사항 |
| `final` | 1 | Final Design |
| `spec` | 1 | Final Spec 공통 + 기능 순서 |
| `feat~{fid}` | N | Final Spec 기능·링크 명세 |
| `item~{fid}~{iid}` | N | 정책 |
| `files` | 1 | 파일 해시 → 파일 id |

### `meta`
```
saveId, updatedAt, deployedAt, deployedById, createdAt, createdBy, isTemplate:false
```
```json
{"saveId":"s-v2raaj3uc","deployedAt":"2026-10-21T01:50:56.731Z","deployedById":"u_Rnjr0F…","isTemplate":false}
```

### `log`
```
entries[]  {at, by|byId, code, text, featureId?, itemId?, v?, major?}   Changelog 화면은 명세 변경(featureId·itemId·정책 코드가 있는 줄)만 보이고, 기본은 major만
```
```json
{"entries":[{"at":"2026-10-21T01:50:56Z","byId":"u_Rnjr0F…","code":"-","text":"배포 완료, 모든 정책을 v1로 기록"},
            {"at":"2026-10-21T03:10:00Z","by":"전문휘","code":"fu-01","v":2,"text":"제목: Task Metric 목록"}]}
```

### `bg`
```
title, summary, area, status(plan|design|dev|qa|ready|done, 없으면 배포 여부로 done/plan)
links       {notion, figma}
roles[]     {id, role, name}
sections[]  {id: background|features|persona|goal, title, hint, body(Markdown)}
```
```json
{"title":"판단형 모델 (Jev + Davi) 추가","area":"Evaluation / Criteria",
 "roles":[{"id":"ro-1","role":"기획","name":"전문휘"}],
 "sections":[{"id":"background","title":"진행 배경","body":"`주요 배경`\n- 최근 등장한 판단형 모델…"}]}
```

### `brief`
```json
{"order":["bv-1","bv-yok4m4mml","bv-ds1020"]}
```

### `ver~{vid}` — Design Brief 버전
```
id, name, createdAt, from?, byId?
reqOrder[]   요구사항 id 순서
demo {w, h, start, screens[]}
  screens[] = 데모 HTML  {id, name, app:true, html:{"$f":파일id}, marks:{이름:선택자}, steps[]}
    steps[] = 저장된 화면 {id, name, desc, where{product,menu,page,overlay,state}, srcWhere?, figma?, trail[], fp[]}
```
```json
{"id":"bv-1","name":"최초 전달버전","reqOrder":["rq-fpjgeryq","rq-v00vkr16"],
 "demo":{"w":1280,"h":800,"start":"app","screens":[{"id":"app","name":"Metric Setting","app":true,
   "html":{"$f":"f7928ccd09ac8f3e9f2c17dc5c1a5ba6"},"marks":{"add-metric":"#addMetric"},
   "steps":[{"id":"h1","where":{"product":"Evaluation","menu":"Criteria","page":"Task Detail","overlay":"","state":""},
             "figma":"https://www.figma.com/design/…?node-id=5111-84596","trail":[{"t":"go","s":"task"}]}]}]}}
```

### `req~{vid}~{rid}` — 요구사항
```
id, title, detail, screen(데모 id), step(저장된 화면 id), mark | pin{x,y,a}, status: todo|done|cancel,
at, byId, locs[] {id, title, ver, screen, step, label, pin|mark}
```
```json
{"id":"rq-fpjgeryq","title":"Metric 추가 진입","detail":"Task Detail의 Metric 섹션에서 + Add Metric을 눌러…",
 "screen":"app","step":"h1","mark":"add-metric","pin":null,"status":"todo","locs":[]}
```

### `final`
```
figma[]   예전 Figma 링크
demo      ver~의 demo와 같은 구조
briefUrl  Design Brief 아티팩트 주소 | null   (Final Design "Design Brief 바로가기")
```

### `spec`
```json
{"order":["ft-q7bost3t","ft-qcmdclv8","ft-0xoodl9h"]}
```

### `feat~{fid}` — 기능·링크 명세
```
id, type: feature|link, title, feature, screen, section, desc, cover, url(링크)
itemOrder[]  정책 id 순서
screens[]    보드 화면 {id, name, kind, w, x, y, desc?, next[]}
             kind "html": 예전 Final Design 스냅샷(새로 만들지 않음, 편집하면 figma로 전환) step{flow,id} (본문은 snap 파일에)
             kind "figma": Figma 화면 {figmaUrl, w, h} — 이미지는 저장하지 않고 볼 때마다 보는 사람의 Figma 연결로 불러옴(예전 assetId는 연결 없을 때만 대신 보임)
             kind "image" {assetId} · "demo" {demoScreen} · "diagram" {html}
snap         {"$f":파일id} | null   {screenId:{html,base}} 묶음
```
```json
{"id":"ft-q7bost3t","type":"feature","title":"Metric 추가","feature":"Criteria","screen":"Task Detail",
 "itemOrder":["it-kzu7ubgi","it-f57ws73f"],
 "screens":[{"id":"s-task","name":"Task Detail","kind":"html","w":1920,"x":0,"y":0,"step":{"flow":"app","id":"h1"},"next":[]}],
 "snap":{"$f":"c087cae18a850d65de03a841cc3f033c"}}
```

### `item~{fid}~{iid}` — 정책
```
id, code(fu-01…), title, body(Markdown)
marks[]     {id, screen, rect{x,y,w,h} | mark, to?}   영역 하나 · rect는 화면 크기에 대한 백분율(0~100), mark는 데모 HTML의 data-mark 이름
versions[]  {n, at, title, body, by, major?}          배포 후에만 · major = 수정할 때 "주요 변경" 체크
```
```json
{"id":"it-kzu7ubgi","code":"fu-01","title":"Task Metric 목록",
 "body":"- 저장한 판단형 Metric은 목록 맨 위에 `Custom · Decision Model`로 추가된다.\n- …",
 "marks":[{"id":"mk-evps4nruq","screen":"s-task","mark":"metric-list"}],
 "versions":[{"n":1,"at":"2026-10-21T01:50:56Z","title":"Task Metric 목록","body":"…"}]}
```

### `files`
```json
{"map":{"1030ce095aa4159a37a95d60ddddbea2684fba10":"f7928ccd09ac8f3e9f2c17dc5c1a5ba6"}}
```
키 = 내용의 SHA-256 앞 40자, 값 = 파일 id. 같은 내용은 버전끼리 파일 하나를 함께 써요.

---

## 3. `disc/{tid}` — Q&A
```
ms        마일스톤 id (없으면 처음 옮긴 마일스톤)
fid       기능 id      itemId  정책 id | null     pin {screen,x,y} | null
status    open | pending | resolved
title, by, claude(bool), owner?, createdAt, resolution?, resolvedAt?
```
```json
{"ms":"ms-bqxzfh4px","fid":"ft-0yxgq1zl0","itemId":"it-w7eodrmtq","pin":null,"status":"resolved",
 "title":"판단형 모델을 Davi만 쓸지","by":"u_9Bb6c…","claude":false,"createdAt":"2026-10-21T02:13:04Z",
 "resolution":"fu-27: Q&A에서 합의된 내용 반영","resolvedAt":"2026-10-21T03:00:00Z"}
```

## 4. `disc/{tid}/msgs/{mid}` — Q&A 메시지
```json
{"by":"u_Rnjr0F…","claude":false,"text":"Jev는 다음 배포로 미뤄요.","at":"2026-10-21T02:20:11Z"}
```

## 5. `reqmsg/{id}` — 요구사항 대화
```json
{"key":"bv-1__rq-fpjgeryq","by":"u_Rnjr0F…","text":"진입 위치는 그대로 두는 게 좋겠어요.","at":"2026-10-21T04:00:00Z"}
```

## 6. `work/{id}` — Claude 작업 중
```json
{"requester":"전문휘","summary":"fu-05 문구 수정","startedAt":"2026-10-21T05:00:00Z","ms":"ms-bqxzfh4px"}
```

## 7. `feedback/{id}` — 의견 제출
```json
{"text":"Q&A 배지 위치를 맞춰 주세요.","by":"u_Rnjr0F…","at":"2026-10-21T06:00:00Z"}
```

## 8. `toolLog/{id}` — 도구 Changelog
```json
{"text":"저장소 탭 추가","requester":"전문휘","by":"u_Rnjr0F…","at":"2026-10-21T07:00:00Z"}
```

## 9. 파일 저장소
| 종류 | 형식 | 가리키는 곳 |
|---|---|---|
| 데모 HTML | text/plain (HTML 원문) | `ver~` · `final`의 `demo.screens[].html` |
| Final Spec 스냅샷 묶음 | application/json `{screenId:{html,base}}` | `feat~`의 `snap` |

페이지는 `/_blob/{파일id}`로 받아요. 문서에는 `{"$f": 파일id}`만 저장해요.
