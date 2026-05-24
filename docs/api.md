# API Reference — Agent Harness Studio

Base URL: `http://127.0.0.1:8766`

---

## GET /api/env

현재 서버 환경 정보를 반환합니다.

**Response:**
```json
{
  "hermes_home": "/Users/letitbe/.hermes/sandbox",
  "is_sandbox": true,
  "is_readonly": false
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `hermes_home` | string | 현재 스캔 대상 디렉토리 절대 경로 |
| `is_sandbox` | bool | `hermes_home` 이름이 `sandbox`이면 true |
| `is_readonly` | bool | `HARNESS_READONLY=1`이면 true. 쓰기 API 전부 차단됨 |

---

## GET /api/scan

전체 하네스 스캔 결과를 반환합니다.

**Response:**
```json
{
  "summary": {
    "skills": 12,
    "bundles": 2,
    "memory": 3,
    "mcp": 5,
    "context": 2,
    "hooks": 4,
    "config": 1,
    "web": 0
  },
  "items": [ ... ],
  "total": 27
}
```

---

## GET /api/scan/{section}

특정 섹션의 스캔 결과만 반환합니다.

**Path params:** `section` — `skills | bundles | memory | mcp | context | hooks | config | cron | plugins`

**Response:** `/api/scan`과 동일한 envelope, 해당 타입만 필터링됨.

**Error (404):**
```json
{"detail": "Unknown section 'xyz'. Valid sections: ['skills', 'memory', 'mcp', 'context', 'hooks', 'config']"}
```

---

## Item 스키마

`items` 배열의 각 원소:

```json
{
  "type": "Skill",
  "name": "my-skill",
  "source_path": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md",
  "state": "ACTIVE",
  "summary": "짧은 설명",
  "metadata": {
    "tags": ["productivity"],
    "category": "general",
    "has_references": true
  }
}
```

| 필드 | 설명 |
|------|------|
| `type` | `Skill`, `Skill Bundle`, `MCP Server`, `Hook`, `Cron Job`, `Plugin`, `Memory Config`, `Memory Manifest`, `Memory Directory`, `Memory State`, `Root Context` |
| `state` | `ACTIVE`, `INACTIVE`, `PAUSED`, `DONE`, `ERROR` 등. 파싱 실패나 깨진 경로는 `ERROR` |
| `source_path` | 절대 경로. `/api/read`, `/api/save`, `/api/rollback` 호출 시 사용 |

### Hermes-specific metadata

- `Skill`: `source` (`local`/`external`), path/frontmatter category, `platforms`, `metadata.hermes.requires_*`, disabled scope
- `Skill Bundle`: referenced `skills`, `skills_count`, `has_instruction`
- `MCP Server`: `transport` (`stdio`/`http`), `enabled`, masked `env`/`headers`, `auth`, `tools`, `sampling`, timeout fields
- `Hook`: `hook_system` (`shell`/`gateway`/`file`), events or command metadata
- `Plugin`: `kind`, `platforms`, `provides_tools`, `provides_hooks`, `hooks`

---

## GET /api/read

하네스 파일 내용을 읽어 반환합니다. `HERMES_HOME` 외부 경로는 403.

**Query params:** `path` — 파일 절대 경로 (URL 인코딩 필요)

**Request:**
```
GET /api/read?path=%2FUsers%2Fletitbe%2F.hermes%2Fskills%2Fmy-skill%2FSKILL.md
```

**Response (200):**
```json
{
  "content": "---\nname: my-skill\n...",
  "path": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md"
}
```

**Errors:**
- `403` — `HERMES_HOME` 외부 경로
- `404` — 파일 없음
- `500` — 읽기 실패

---

## POST /api/save

파일을 저장합니다. 기존 파일이 있으면 저장 전 자동 백업(`.bak.{timestamp}`)을 생성합니다.

`HARNESS_READONLY=1`이면 `403` 반환.

**Request body (JSON):**
```json
{
  "path": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md",
  "content": "---\nname: my-skill\n..."
}
```

**Response (200):**
```json
{
  "status": "saved",
  "path": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md",
  "backup": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md.bak.20260524_153012"
}
```

`backup`이 `null`이면 원본 파일이 없었던 경우 (신규 생성).

**Errors:**
- `403` — 읽기 전용 모드 또는 `HERMES_HOME` 외부 경로
- `500` — 쓰기 실패

---

## POST /api/rollback

파일을 가장 최근 백업(`.bak.{timestamp}`)으로 복원합니다.

`HARNESS_READONLY=1`이면 `403` 반환.

**Request body (JSON):**
```json
{
  "path": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md"
}
```

**Response (200):**
```json
{
  "status": "rolled_back",
  "from_backup": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md.bak.20260524_153012",
  "remaining_backups": 0
}
```

복원에 사용된 백업 파일은 자동 삭제됩니다. 더 오래된 백업이 남아있으면 `remaining_backups > 0`.

**Errors:**
- `403` — 읽기 전용 모드 또는 경로 위반
- `404` — 백업 파일 없음
- `500` — 복원 실패

---

## POST /api/mold

자연어 프롬프트를 받아 하네스 수정 제안을 반환합니다.
서버는 매 호출마다 `nousresearch/hermes-agent`를 canonical reference로 삼는
Hermes 구조 요약과 현재 `HERMES_HOME` 스캔 스냅샷을 시스템 문맥에 주입합니다.
따라서 모델이 바뀌어도 skills, skill bundles, memory, MCP, hooks, cron, plugins,
root context의 기본 위치와 스키마를 같은 기준으로 해석합니다.

**Request body (JSON):**
```json
{
  "prompt": "새로운 스킬 만들어줘",
  "context": "Skills",
  "history": [
    {"role": "user", "text": "이전 메시지"},
    {"role": "assistant", "text": "이전 응답"}
  ]
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `prompt` | 필수 | 현재 사용자 입력 |
| `context` | 선택 | 현재 선택된 섹션 타이틀 (LLM 컨텍스트용) |
| `history` | 선택 | 이전 대화 히스토리 (최대 10개 사용) |

**Response — CHAT 모드 (질문/답변):**
```json
{
  "status": "success",
  "action": "CHAT",
  "name": "",
  "message": "스킬은 ~/.hermes/skills/ 에 저장됩니다.",
  "content": "",
  "diff": "",
  "diff_summary": ""
}
```

**Response — CREATE_SKILL 모드:**
```json
{
  "status": "success",
  "action": "CREATE_SKILL",
  "name": "my-new-skill",
  "description": "새 스킬 설명",
  "message": "다음과 같이 스킬을 생성했습니다.",
  "content": "---\nname: my-new-skill\n...",
  "diff": "+++ b/skills/my-new-skill/SKILL.md\n+---\n+name: my-new-skill\n...",
  "diff_summary": "새 스킬 SKILL.md 생성"
}
```

**action 값:**
| action | 설명 |
|--------|------|
| `CHAT` | 대화 응답. `content` 없음 |
| `CREATE_SKILL` | 새 스킬 생성. `content`에 전체 SKILL.md 내용 |
| `UPDATE_SKILL` | 기존 스킬 수정 |
| `UPDATE_CONFIG` | config.yaml 수정 제안 |
| `ADD_MCP` | MCP 서버 추가 제안 |
| `SUGGESTION` | 수동 작업 안내 (파일 생성 불필요) |

LLM 응답이 JSON 파싱 실패 시 원본 텍스트를 `message`로 반환 (fallback CHAT).

**Error:**
- `500` — LLM 호출 실패 (9router 미실행 등)

---

## GET /api/reference/hermes

Chat Molder에 항상 주입되는 Hermes canonical reference 컨텍스트를 반환합니다.

**Response (200):**
```json
{
  "reference_url": "https://github.com/NousResearch/hermes-agent",
  "source": "nousresearch/hermes-agent",
  "context": "# Canonical Hermes Agent Reference\n..."
}
```

---

## POST /api/web/scrape

URL에서 콘텐츠를 스크래핑합니다. Firecrawl → Jina → TLS → Browser 순으로 시도.

**Request body (JSON):**
```json
{
  "url": "https://example.com/article"
}
```

**Response (성공):**
```json
{
  "status": "ok",
  "source": "jina",
  "content": "# Article Title\n\n...",
  "url": "https://example.com/article",
  "phase_used": "jina"
}
```

**Response (실패):**
```json
{
  "status": "error",
  "message": "All scraping phases failed.",
  "url": "https://example.com/article"
}
```

`source` / `phase_used` 값: `firecrawl`, `jina`, `tls`, `browser`

---

---

## Git API

> Git API는 `HERMES_HOME`이 git 저장소일 때만 실제 동작합니다.  
> git repo가 아닌 경우 `/api/git/log`는 `{"is_git_repo": false}`를 반환하고,  
> `/api/git/init` 외 나머지는 빈 결과를 반환합니다.

### POST /api/git/init

`HERMES_HOME`을 git 저장소로 초기화하고 첫 커밋을 생성합니다.
`.gitignore`(`*.bak.*`, `.env`, `*.log`)도 자동 생성됩니다.

`HARNESS_READONLY=1`이면 `403` 반환.

**Response (성공):**
```json
{
  "status": "initialized",
  "initial_commit": "a1b2c3d",
  "branch": "main"
}
```

**Response (이미 git repo인 경우):**
```json
{
  "status": "already_git_repo",
  "branch": "main"
}
```

---

### GET /api/git/log

커밋 이력을 반환합니다. `path` 파라미터로 특정 파일의 이력만 필터링 가능합니다.

**Query params:**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `path` | (없음) | 필터링할 파일 절대 경로 (URL 인코딩) |
| `limit` | `30` | 최대 반환 커밋 수 |

**Response:**
```json
{
  "is_git_repo": true,
  "commits": [
    {
      "hash": "a1b2c3d4e5f6...",
      "short_hash": "a1b2c3d",
      "message": "harness-studio: edit my-skill",
      "date": "2026-05-24 15:30:12 +0900",
      "author": "letitbe"
    }
  ]
}
```

**Response (git repo 아닌 경우):**
```json
{"is_git_repo": false, "commits": []}
```

---

### GET /api/git/diff

특정 커밋에서 변경된 내용(unified diff)을 반환합니다.

**Query params:**

| 파라미터 | 필수 | 설명 |
|---------|------|------|
| `commit_hash` | 필수 | 조회할 커밋 해시 (full 또는 short) |
| `path` | 선택 | 특정 파일로 diff 범위 제한 |

**Response:**
```json
{
  "diff": "commit a1b2c3d\nAuthor: ...\n\n--- a/skills/my-skill/SKILL.md\n+++ b/skills/my-skill/SKILL.md\n..."
}
```

**Error (404):** 커밋 해시를 찾을 수 없는 경우

---

### POST /api/git/rollback

파일을 특정 커밋 시점의 상태로 복원합니다.  
복원 전 현재 상태를 `.bak.*`으로 백업하고, 복원 후 자동으로 새 커밋을 생성합니다.

`HARNESS_READONLY=1`이면 `403` 반환.

**Request body (JSON):**
```json
{
  "path": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md",
  "commit_hash": "a1b2c3d"
}
```

**Response (200):**
```json
{
  "status": "restored",
  "to_commit": "a1b2c3d",
  "backup": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md.bak.20260524_153012"
}
```

복원 후 생성되는 커밋 메시지: `harness-studio: rollback {rel} to {short_hash}`

**Errors:**
- `403` — 읽기 전용 모드 또는 경로 위반
- `500` — git checkout 실패 (이 경우 backup에서 자동 복구)

---

## /api/env 업데이트 (Git 정보 포함)

Git 연동 후 `/api/env` 응답에 필드가 추가됩니다:

```json
{
  "hermes_home": "/Users/letitbe/.hermes",
  "is_sandbox": false,
  "is_readonly": false,
  "is_git_repo": true,
  "git_branch": "main",
  "git_commit_count": 42
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `is_git_repo` | bool | HERMES_HOME이 git repo인지 여부 |
| `git_branch` | string\|null | 현재 브랜치명 |
| `git_commit_count` | int\|null | 전체 커밋 수 |

---

## /api/save 업데이트 (Git 자동 커밋)

Git 연동 후 `/api/save` 요청에 `commit_message` 필드 추가 가능:

**Request body (JSON):**
```json
{
  "path": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md",
  "content": "---\nname: my-skill\n...",
  "commit_message": "feat: add python code review step"
}
```

`commit_message`를 비우면 자동 생성: `harness-studio: save skills/my-skill/SKILL.md`

**Response (Git 연동 시):**
```json
{
  "status": "saved",
  "path": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md",
  "backup": "/Users/letitbe/.hermes/skills/my-skill/SKILL.md.bak.20260524_153012",
  "git": {
    "committed": true,
    "hash": "a1b2c3d",
    "message": "feat: add python code review step"
  }
}
```

**Response (Git 미연동 시):**
```json
{
  "status": "saved",
  "path": "...",
  "backup": "...",
  "git": null
}
```

---

## GET /health

헬스체크. 항상 200.

```json
{"status": "ok"}
```
