---
description: 레포의 마일스톤 글을 PRDstar 복제본에 올린다 (바뀐 문서만)
argument-hint: <slug> [요청자 이름]
---

요청: $ARGUMENTS

CLAUDE.md "PRDstar 연동 › push" 절차를 순서대로 따른다.

- 대상: `milestones/<slug>`. 없으면 `milestones/` 목록을 보여 주고 묻는다.
- 요청자 이름(`--by`)을 모르면 묻는다. 배포 후 마일스톤이면 이 이름으로 정책 버전과 Changelog가 붙는다.
- 작업 폴더는 `.prdstar-work/<slug>`를 비우고 새로 만든다.
- `apply`가 충돌(exit 3)로 멈추면 쓰지 않고, 충돌 항목과 `/prdstar-pull <slug>`로 받아 합치는 방법을 알려 준다.
- 끝나면 짧게 보고한다: 올린 항목(Background · 명세 · 정책 코드), 새 정책 버전 · Changelog 줄, 커밋 여부, PRDstar 링크(`<url>#<msId>`).
