# Datumo-Spec

DATUMO 기능 스펙을 정의하는 저장소예요. 마일스톤의 Background · 기능 명세 · 정책을 Markdown으로 쓰고 git으로 관리하며,
**PRDstar 복제본**에 올려 보드 · 데모 · Q&A와 함께 봐요.

- PRDstar 복제본: https://claude.ai/artifact/9GcCWwJKHmYdAWccFLN4m3 (`prdstar.config.json`)
- 레포가 원본이에요. 글은 레포에서 고치고 올려요(push). PRDstar에서 고친 글은 받아서(pull) git diff로 합쳐요.

## 구조

```
milestones/<slug>/        마일스톤 하나
  milestone.md            제목 · 영역 · 상태 · 담당 · 링크 + Background 네 섹션
  specs/NN-<이름>.md       명세 하나(기능 · 문서 · 링크)와 그 정책
  plan.md · tasks.md      AI 개발용 구현 계획 · 작업 목록 (레포 전용)
  devspec.md              PRDstar AI용 텍스트 명세 (받기만 함)
api/ · data/              API · 데이터 모델 명세 (레포 전용)
templates/                템플릿
tools/                    PRDstar 연동 · 검사 도구
```

## 명세 예시

`milestones/decision-model/specs/01-Metric-추가.md`

```markdown
---
id: ft-017b3a6dd
type: feature
title: Metric 추가
feature: Criteria
screen: Task Detail
section: Metric
loc:
desc:
---

## fu-01 Metric 추가 진입

- Task Detail의 Metric 섹션에서 `+ Add Metric`을 누르면 Metric 추가 모달이 열린다.

| 상태 | 처리 |
|---|---|
| 기본 | 버튼 활성 |
| 한도 초과 | 버튼 비활성 |
```

- 정책 머리글은 `## <코드> <제목>`. 기능 명세는 `fu-NN`, 문서 명세는 `do-NN`. 코드는 한 번 붙이면 바꾸지 않아요.
- `id`는 처음 올릴 때 도구가 넣어요.

## Claude Code에서 쓰기

| 명령 | 하는 일 |
|---|---|
| `/ms-new <제목> \| <영역> \| <자료 링크>` | 템플릿으로 마일스톤을 만들고 Background 초안을 채워요 |
| `/prdstar-push <slug>` | 레포 글을 PRDstar 복제본에 올려요 (PRDstar 쪽 변경과 겹치면 멈춰요) |
| `/prdstar-pull <slug 또는 msId>` | PRDstar 복제본 내용을 레포로 받아요 |
| `/ms-plan <slug>` | 정책을 근거로 `plan.md` · `tasks.md`를 써요 |

PRDstar에 읽고 쓰려면 claude.ai 계정에 연결된 Claude Code(ArtifactData 도구)가 필요해요.

## 직접 쓰는 도구 명령

```bash
python3 tools/prdstar_sync.py new <slug> --title "제목" --area "Feature / Subfeature"
python3 tools/prdstar_sync.py add-spec milestones/<slug> --type feature --title "기능 이름"
python3 tools/prdstar_sync.py check
```

자세한 연동 절차는 `CLAUDE.md`에 있어요.
