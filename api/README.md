# api

API 명세를 두는 곳이에요. 레포 전용이라 PRDstar로 올라가지 않아요.

- 도메인마다 OpenAPI 3.1 YAML 파일 하나: `api/<domain>.yaml` (예: `api/evaluation.yaml`)
- 오퍼레이션마다 근거 정책을 `x-policy`에 적어요. 형식은 `<마일스톤 slug>/<정책 코드>`.

```yaml
paths:
  /tasks/{taskId}/metrics:
    post:
      summary: Metric 추가
      x-policy: [decision-model/fu-01, decision-model/fu-03]
```

- 정책에 없는 동작(오류 코드, 한도 등)은 만들지 않고 `description`에 `[확인 필요]`로 남겨요.
