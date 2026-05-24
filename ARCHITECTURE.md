# Architecture — Agent Harness Studio

## 시스템 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                        브라우저 (localhost:5173)                  │
│  ┌──────────────────────┐    ┌──────────────────────────────┐   │
│  │   Sidebar (Inspector) │    │    Chat Molder (우측 패널)    │   │
│  │  - 7개 섹션 카드       │    │  - 자연어 입력               │   │
│  │  - 아이템 리스트        │    │  - diff 미리보기             │   │
│  │  - 파일 에디터          │    │  - Apply / Rollback          │   │
│  └──────────┬───────────┘    └───────────────┬──────────────┘   │
└─────────────┼───────────────────────────────┼──────────────────┘
              │  HTTP (fetch)                  │  HTTP (fetch)
              ▼                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI 백엔드 (localhost:8766)                │
│                                                                 │
│  GET  /api/scan          → HermesScanner.scan_all()            │
│  GET  /api/scan/{section}→ HermesScanner + 타입 필터           │
│  GET  /api/read          → Path.read_text()                    │
│  POST /api/save          → backup + Path.write_text()          │
│  POST /api/rollback      → .bak.* 복원                         │
│  POST /api/mold          → OpenAI SDK → 9router               │
│  POST /api/web/scrape    → HybridScraper                       │
│  GET  /api/env           → HERMES_HOME, is_sandbox, is_readonly│
└──────────┬──────────────────────────────────────┬──────────────┘
           │                                      │
           ▼                                      ▼
┌──────────────────────┐            ┌─────────────────────────────┐
│   ~/.hermes (또는     │            │  9router (localhost:20128)   │
│   $HERMES_HOME)      │            │  - 로컬 LLM 프록시           │
│                      │            │  - 모델명: "letitbe"          │
│  skills/             │            │  - OpenAI API 호환           │
│  memory/             │            └─────────────────────────────┘
│  hooks/              │
│  config.yaml         │            ┌─────────────────────────────┐
│  AGENTS.md           │            │  Web Scraper 파이프라인       │
└──────────────────────┘            │  Phase 1: Firecrawl API      │
                                    │  Phase 2: Jina Reader API    │
                                    │  Phase 3: TLS (curl_cffi)    │
                                    │  Phase 4: Playwright 브라우저 │
                                    └─────────────────────────────┘
```

---

## 컴포넌트 상세

### 1. HermesScanner (`src/scanner/hermes_scanner.py`)

`~/.hermes` 디렉토리를 순회하며 5종류의 하네스 컴포넌트를 탐지합니다.

**스캔 항목:**

| 타입 | 소스 | 탐지 방법 |
|------|------|-----------|
| `Skill` | `skills/**/SKILL.md` | rglob + YAML frontmatter 파싱 |
| `Memory Config` | `config.yaml` → `memory` 섹션 | yaml.safe_load |
| `Memory Manifest` | `memory_manifest.md` | 존재 여부 확인 |
| `Memory Directory` | `memory/` 디렉토리 | 파일 카운트 |
| `Memory State` | `state/` 디렉토리 | 파일 목록 |
| `MCP Server` | `config.yaml` → `mcp_servers` | transport 휴리스틱 탐지 |
| `Root Context` | `AGENTS.md`, `config.yaml` | 존재 여부 + 섹션 확인 |
| `Hook` | `hooks/` 디렉토리 | 파일명으로 hook_type 추론 |

**보안:**
- 민감 키 자동 마스킹: `SECRET`, `API_KEY`, `TOKEN`, `PASSWORD`, `KEY`, `CRED`, `AUTH` → `"REDACTED"`
- `mask_env_dict()` 로 MCP 서버 env 섹션 처리

**출력 스키마 (공통):**
```json
{
  "type": "Skill | MCP Server | Hook | ...",
  "name": "skill-name",
  "source_path": "/abs/path/to/file",
  "state": "ACTIVE | ERROR",
  "summary": "짧은 설명",
  "metadata": { ... }
}
```

---

### 2. FastAPI 백엔드 (`src/server/app.py`)

**주요 글로벌 변수:**
```python
HERMES_HOME = Path(os.environ.get("HERMES_HOME", "~/.hermes"))
HARNESS_READONLY = os.environ.get("HARNESS_READONLY", "") in ("1", "true", "yes")
```

**안전 헬퍼:**
- `_assert_within_hermes(path)`: path가 HERMES_HOME 외부이면 403
- `_backup(path)`: 저장 전 `.bak.{timestamp}` 사이드카 생성

**Chat Molder 프롬프트 구조:**
```
system: MOLDER_SYSTEM_PROMPT (한국어 응답, JSON 전용)
user[0]: [{context_str}]\n\n{history[0].text}
assistant[0]: {history[0].response}
...
user[N]: [{context_str}]\n\n{current_prompt}
```
응답은 항상 JSON: `{"action": "CHAT|CREATE_SKILL|UPDATE_SKILL|...", "message": "...", ...}`

**LLM 클라이언트:**
`get_llm_client()` — `~/.hermes/config.yaml`에서 base_url 읽기 시도, 없으면 `http://127.0.0.1:20128/v1` 기본값.

**`normalize_skill_content()`:**
LLM이 생성한 SKILL.md의 frontmatter 스키마 오류를 자동 수리:
- `hermese:` → `hermes:`
- frontmatter 없으면 기본 템플릿 래핑
- `metadata.hermes` 섹션 없으면 추가

---

### 3. React 프론트엔드 (`src/ui/src/App.jsx`)

**레이아웃:**
```
app-layout (flex-row)
├── sidebar-container (좌측)
│   ├── app-header (브랜드 + env 배지)
│   ├── harness-overview (7개 섹션 카드)
│   └── content-area
│       ├── detail-panel (섹션 선택 시)
│       │   └── item-row (아이템 목록)
│       └── editor-panel (Edit 클릭 시)
│           ├── panel-header (Save/Rollback/Cancel)
│           └── textarea (code-editor)
└── chat-container (우측)
    ├── chat-messages (대화 히스토리)
    │   └── chat-bubble (user/assistant)
    │       └── chat-proposal (diff + Apply 버튼)
    └── chat-footer (입력창 + Send)
```

**주요 상태:**
| 상태 | 타입 | 설명 |
|------|------|------|
| `summary` | object | 섹션별 카운트 (`{skills: 5, mcp: 3, ...}`) |
| `items` | array | 전체 스캔 결과 |
| `selectedSection` | string | 현재 선택된 섹션 ID |
| `editingItem` | object | 편집 중인 아이템 |
| `editContent` | string | 편집기 내용 (실제 파일 내용) |
| `editLoading` | bool | 파일 로딩 중 여부 |
| `lastBackup` | string\|null | 마지막 저장 시 생성된 백업 경로 |
| `chatHistory` | array | 채팅 히스토리 `[{role, text, data?}]` |
| `molderResponse` | object | 마지막 LLM 응답 |
| `envInfo` | object | `{hermes_home, is_sandbox, is_readonly}` |

**데이터 흐름 (편집):**
```
handleEditClick(item)
  → fetch GET /api/read?path={item.source_path}
  → setEditContent(data.content)
  → 사용자 편집
  → handleSave()
    → fetch POST /api/save {path, content}
    → 서버: _backup() + write_text()
    → setLastBackup(data.backup)
    → (선택) handleRollback()
      → fetch POST /api/rollback {path}
      → 서버: 최신 .bak.* 복원 + 삭제
```

---

### 4. Hybrid Web Scraper (`src/server/scrapers/`)

4단계 폴백 파이프라인:

```
Phase 1: Firecrawl API
  → firecrawl-py SDK, FIRECRAWL_API_KEY 필요
  → 성공 시 마크다운 반환

Phase 2: Jina Reader API
  → https://r.jina.ai/{url} GET 요청
  → 무료, 속도 제한 있음

Phase 3: TLS Fingerprint (curl_cffi)
  → 브라우저 TLS 지문 스푸핑으로 Bot 차단 우회
  → markdownify로 HTML → MD 변환

Phase 4: Playwright 브라우저 자동화
  → headless Chromium
  → JavaScript 렌더링 필요한 SPA 대응
  → playwright install chromium 선행 필요
```

성공한 Phase 정보는 `response.phase_used`로 반환.

---

## 환경 변수 전체 목록

| 변수 | 기본값 | 사용처 |
|------|--------|--------|
| `HERMES_HOME` | `~/.hermes` | 스캔 대상 디렉토리 |
| `HARNESS_READONLY` | `0` | `1`이면 모든 쓰기 차단 |
| `FIRECRAWL_API_KEY` | (없음) | Firecrawl Phase 1 활성화 |
| `OPENAI_API_KEY` | (없음) | 9router 대체 (미구현, 향후) |

---

## 의존성

```
fastapi          # HTTP 프레임워크
uvicorn          # ASGI 서버
pyyaml           # config.yaml 파싱
openai           # LLM 클라이언트 (9router 호환)
python-dotenv    # .env 로드
httpx            # async HTTP (Jina 스크래퍼)
firecrawl-py     # Phase 1 스크래퍼
curl_cffi        # Phase 3 TLS 스크래퍼
playwright       # Phase 4 브라우저 스크래퍼
markdownify      # HTML → Markdown 변환
```
