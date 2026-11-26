---
description: PRDstar 복제본의 마일스톤 내용을 레포로 받는다
argument-hint: <slug 또는 msId>
---

요청: $ARGUMENTS

CLAUDE.md "PRDstar 연동 › pull" 절차를 따른다.

- slug면 `milestones/<slug>/.prdstar.json`의 `msId`를 쓴다. msId만 받았거나 대상이 없으면 ArtifactData `list`(collection `ms`)로 목록을 보여 주고 고른다. 레포에 없는 마일스톤이면 새 slug 폴더로 받는다.
- 받기 전에 `git status`를 보고, 커밋하지 않은 변경이 있으면 먼저 커밋할지 묻는다(받기는 파일을 덮어쓴다).
- 받은 뒤 `git diff --stat`과 바뀐 정책 코드를 짧게 보고한다. 레포에만 있던 변경이 덮였으면 알려 주고 합칠지 묻는다.
