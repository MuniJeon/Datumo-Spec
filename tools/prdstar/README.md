# tools/prdstar

PRDstar 저장 구조(db 문서 + 파일)를 다루는 도구와 규칙의 사본이에요. claude.ai `milestone-doc-work` 스킬에서 복사했어요.

| 파일 | 내용 |
|---|---|
| `prdstar.py` | db 문서 ↔ 내용(content.json) 조립 · 나누기, 바뀐 문서만 쓰는 계획(push), 배포 후 정책 버전 · Changelog |
| `msdoc.py` | `prdstar.py`가 쓰는 공용 함수(버전 기록, 빈 내용 등) |
| `claude-rules.md` | PRDstar Claude 작업 규칙(명세 작성 규칙의 원본) |
| `prdstar-structure.md` | PRDstar 저장 구조 · 스키마 |

스킬이 갱신되면 같은 파일을 다시 복사해요. 레포 전용 변환은 `tools/prdstar_sync.py`에 있어요.

## 원본과 다른 점 (PRDstar 복제본)

- **배포 완료 잠금:** 배포 완료된 마일스톤은 복제본 페이지에서 고칠 수 없어요(보기 · Q&A만). 바꿀 내용은 새 마일스톤으로 만들어요. `claude-rules.md`의 Final Spec 규칙도 이에 맞춰 바꿨어요. 원본 스킬 파일을 다시 복사할 때 이 줄을 지키세요.
- **빈 저장소:** 마일스톤이 하나도 없으면 오류 대신 빈 홈을 보여 줘요.
