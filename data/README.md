# data

데이터 모델 명세를 두는 곳이에요. 레포 전용이라 PRDstar로 올라가지 않아요.

- 엔티티마다 파일 하나: `data/<entity>.md` (예: `data/metric.md`)
- 필드 표와 근거 정책을 함께 적어요.

```markdown
# Metric

| 필드 | 타입 | 필수 | 설명 | 근거 정책 |
|---|---|---|---|---|
| id | string | ✓ | Metric ID |  |
| name | string | ✓ | 1~50자, Task 안에서 중복 불가 | decision-model/fu-03 |
```

- 정책에 없는 제약은 만들지 않고 `[확인 필요]`로 남겨요.
