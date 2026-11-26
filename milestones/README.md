# milestones

마일스톤 하나 = 폴더 하나(`milestones/<slug>/`). slug는 영문 소문자와 `-`로 짧게 지어요(예: `decision-model`).

새로 만들기:

```bash
python3 tools/prdstar_sync.py new <slug> --title "제목" --area "Feature / Subfeature"
```

| 파일 | 내용 | PRDstar |
|---|---|---|
| `milestone.md` | frontmatter: `title` · `area` · `status`(plan · design · dev · qa · ready · done) · `summary` · `notion` · `figma` · 담당(`기획:` 등) / 본문: Background 네 섹션 | 올림 |
| `specs/NN-<이름>.md` | 명세 하나와 그 정책 | 올림 |
| `devspec.md` | AI용 텍스트 명세 | 받기만 |
| `plan.md` · `tasks.md` | 구현 계획 · 작업 목록 | 레포 전용 |
| `.prdstar.json` | 연결 정보 · 동기화 기준 | 도구 전용 |
