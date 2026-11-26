---
description: 템플릿으로 새 마일스톤을 만들고 Background 초안을 채운다
argument-hint: <제목> | <Feature / Subfeature> | <자료 링크(선택)>
---

요청: $ARGUMENTS

1. 제목·기능 영역·자료 링크를 나눈다. 영문 소문자와 `-`로 slug를 정한다. `milestones/`에 같은 slug나 같은 제목이 있으면 멈추고 묻는다.
2. `python3 tools/prdstar_sync.py new <slug> --title "<제목>" --area "<영역>"`
3. 자료(노션 · 문서)가 있으면 읽고 `milestones/<slug>/milestone.md`의 Background 네 섹션과 frontmatter(summary · notion · figma · 담당)를 채운다. CLAUDE.md "작성 규칙"을 따르고, 원문 문장을 살려 옮기며 자료에 없는 값은 `[확인 필요]`로 둔다.
4. 자료에 기능 명세가 있으면 `python3 tools/prdstar_sync.py add-spec milestones/<slug> --type feature --title "<기능>"`으로 파일을 만들고 정책을 옮긴다(원래 번호·문장 유지).
5. `python3 tools/prdstar_sync.py check milestones/<slug>`를 통과시킨다.
6. 무엇을 채웠는지와 `[확인 필요]` 목록을 짧게 보고하고, PRDstar 복제본에 올릴지(`/prdstar-push <slug>`) 묻는다.
