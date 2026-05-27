# Agent Harness Studio

AI 에이전트의 하네스(스킬, 메모리, MCP, 훅, 크론, 플러그인, 루트 컨텍스트)를 **시각화·관리·수정**하는 오픈소스 로컬 웹 대시보드입니다. Hermes뿐 아니라 Claude Code, Cursor, Codex, OpenClaw, Gemini/Antigravity, Studio 자체 워크스페이스를 스캔하고, 자연어 대화·사용량 분석·스킬 변환으로 하네스를 정리/재사용할 수 있습니다.

## 핵심 철학: Harness over Model

모델 자체의 성능보다 에이전트의 **하네스** — 스킬, 메모리, 도구, 행동 컨텍스트 — 설계가 실질적인 에이전트 생산성을 결정합니다. Agent Harness Studio는 이 환경을 체계적으로 다듬을 수 있게 합니다.

![Architecture Diagram](docs/assets/architecture.svg)

### 📺 소개 영상

[소개 영상](docs/assets/agent-harness-studio-intro.mp4)에서 스튜디오 작동 모습을 확인하세요.

---

## 주요 기능

### 하네스 스캐너 (Harness Scanner)
여러 로컬 에이전트 워크스페이스를 순회하며 하네스 구성요소를 탐지합니다:
- **스킬 (Skills)** — `skills/**/SKILL.md` YAML frontmatter 파싱, 외부 디렉토리, 비활성 상태 반영
- **스킬 번들 (Skill Bundles)** — `skill-bundles/*.yaml` 워크플로우 팩
- **MCP 서버** — `config.yaml` mcp_servers (stdio + HTTP, transport/auth/tools 메타데이터 포함)
- **훅 (Hooks)** — Shell 훅, 게이트웨이 훅 (`hooks/<name>/HOOK.yaml`), 레거시 훅 파일
- **메모리 (Memory)** — Config, manifest, memories 디렉토리, state 파일
- **크론 작업 (Cron Jobs)** — `cron/jobs.json` 상태 추적
- **플러그인 (Plugins)** — `plugins/*/plugin.yaml` tools/hooks 수 표시
- **루트 컨텍스트 (Root Context)** — AGENTS.md, SOUL.md, system_prompt
- **로그/세션/State DB/체크포인트** — 큰 로그 tail 읽기, sessions/state.db 요약, checkpoint inventory

지원 워크스페이스:
`~/.hermes`, `~/.claude`, `~/.cursor`, `~/.codex`, `~/.openclaw`, `~/.gemini`, `~/.gemini/antigravity`, 이 프로젝트(`agent-harness-studio`) 자체.

### 섹션 대시보드 (Section Dashboard)
전체 하네스를 한눈에 볼 수 있는 섹션 카드:
Skills, Skill Bundles/Subagents, MCP, Hooks, Memory Map, Cron, Plugins/Commands, Context, Config, Logs, Sessions, State DB, Checkpoints, Agent Runner, Diff Audit, Audit Log, Web Context.

### 2단 레이아웃 (2-Column Layout)
- **좌측 패널 (55%)**: 섹션 카드 + 카테고리 상세 + 파일 에디터
- **우측 패널 (45%)**: Chat Molder 대화형 AI

### Chat Molder — 대화형 AI 어시스턴트
질문에 답하고 하네스 아이템을 생성/수정하는 내장 AI 채팅:
- **CHAT 모드**: 하네스 구성에 대한 질문 답변 (한국어)
- **CREATE/UPDATE 모드**: 적절한 YAML frontmatter가 포함된 SKILL.md 파일 생성
- **서버 사이드 스키마 검증**: `normalize_skill_content()`가 frontmatter 오류 자동 수리
- **멀티턴 대화**: 컨텍스트 인식 응답을 위한 대화 히스토리 유지
- **컨텍스트 인식**: 대시보드에서 선택한 섹션/아이템을 인식
- **Hermes 기준 주입**: 모든 LLM 호출에 `nousresearch/hermes-agent` 정식 기준 컨텍스트 포함
- **Pi Agent 모드**: 설치된 `pi` CLI를 이용해 read/grep/find/ls/web_search 기반 read-only 대화를 실행하고 세션을 이어갑니다.

### Usage Telemetry + Smart Diet
Claude Code 세션 로그(`~/.claude/projects/**/*.jsonl`)를 파싱해 Skill/Subagent 사용 빈도를 계산합니다.

- `/api/usage/stats` — Skill/Subagent invocation 통계
- `/api/recommendations` — 사용량 + 토큰 + 수정시각 기반 추천
- Diet 모달의 **Smart** 탭 — `HIGH_VALUE`, `STALE_UNUSED`, `ARCHIVE`, `HEAVY_UNUSED` 배지
- 추천 항목에서 아카이브/복사/Hermes 주입 액션 실행

현재 Claude Code 워크스페이스 기준 검증값: 추천 263개, `HIGH_VALUE:1`, `STALE_UNUSED:72`, `ARCHIVE:190`.

### Cross-Agent Skill Converter
Claude Code Skill을 Hermes Skill로 변환/주입합니다.

- 에디터 내 frontmatter 변환: Hermes ↔ Claude Code
- Claude Skills 목록의 **To Hermes** 버튼
- Skill editor의 **Inject to Hermes** 버튼
- Smart 추천 액션 컬럼의 Hermes 주입 버튼
- `/api/convert/skill/inject` — `dry_run`, overwrite 충돌 방지, companion directory 복사, audit log

### Agent Runner — Pi Coding Agent
설치된 Pi Coding Agent CLI를 Studio 안에서 감지하고 read-only로 실행합니다.

- `/api/agent-runners`, `/api/pi/status` — Pi CLI/provider/model/session 감지
- `/api/pi/preview` — 실행 전 command preview
- `/api/pi/runs` — read-only run 시작 (`read,grep,find,ls`)
- `/api/pi/runs/{id}`, `/log`, `/stop` — 상태/로그/중지
- Chat Molder Pi 모드 — `read,grep,find,ls,web_search`로 대화형 실행

### 하이브리드 웹 스크래퍼 (Hybrid Web Scraper)
웹 콘텐츠를 Markdown으로 추출하는 4단계 폴백 파이프라인:
1. **Firecrawl API** (`FIRECRAWL_API_KEY` 설정 시)
2. **Jina Reader API** (무료, 속도 제한 있음)
3. **TLS Impersonation** (`curl_cffi` — Cloudflare/봇 탐지 우회)
4. **Browser Automation** (Playwright headless Chromium, JS 렌더링 필요 시)

### 파일 편집 (File Editing)
아이템의 **Edit** 버튼 클릭 시 실제 파일 내용을 로드하여 수정 후 저장. `.md`, `.yaml`, `.yml`, `.json`, `.txt`, `.py`, `.sh` 등 모든 텍스트 파일 지원.

### 자동 백업 (Auto Backup)
저장 시 항상 기존 파일의 `.bak.{timestamp}` 사이드카 파일을 먼저 생성합니다.

### 롤백 API (Rollback API)
가장 최근 `.bak.*` 백업으로 원클릭 복원.

### Git 연동 (Git Integration)
- **저장 시 자동 커밋**: 파일 저장마다 git 커밋 생성 (커스텀 메시지 지원)
- **전체 이력 패널**: 파일별 커밋 이력 조회 (해시, 메시지, 날짜, 작성자)
- **파일별 롤백**: 임의 커밋 시점으로 파일 복원
- **자동 .gitignore**: 백업 파일, `.env`, 로그, DB 파일 제외

### 안전 모델 (4중 안전 레이어)

| 레이어 | 보호 범위 | 복구 가능 |
|--------|-----------|-----------|
| `HARNESS_READONLY=1` | 모든 쓰기 API 403 차단 | 해당 없음 |
| `HERMES_HOME=~/.hermes/sandbox` | 실데이터와 물리적 분리 | 아니요 |
| 자동 백업 (`.bak.*`) | 저장 전 마지막 상태 스냅샷 | 네 |
| Git 버전 관리 | 전체 커밋 이력, 임의 시점 복원 | 네 |

### 추가 기능
- **Memory Map**: 모든 메모리 구성 표면의 통합 뷰
- **SOUL.md 에디터**: 3개 내장 프리셋(Developer, Researcher, Writer)으로 페르소나 편집
- **컨텍스트 윈도우 추정기**: 하네스 아이템별 토큰 카운팅, 128K 예산 표시
- **크로스 에이전트 스킬 변환기**: Hermes ↔ Claude Code 형식 간 스킬 변환
- **Claude → Hermes Skill 주입**: 선택한 Claude Skill을 `~/.hermes/skills/{name}/SKILL.md`로 변환 저장
- **Smart Diet**: 사용량 기반 보존/정리/아카이브 추천
- **Diff Audit**: workspace git status/stat 기반 변경 위험도 점검
- **Agent Runner**: Pi Coding Agent 감지, read-only 실행, 로그/감사 표시
- **Sessions/State DB 뷰어**: state.db 세션/테이블 요약과 최근 세션 메시지 확인
- **SQLite 감사 로그**: 모든 저장/롤백/초기화 작업의 변경 이력 추적
- **Chat 내 마크다운 렌더링**: Chat Molder에서 제목, 목록, 표, 인라인 서식 올바르게 표시
- **LaunchAgent**: macOS `launchctl` 자동 시작 + KeepAlive + 헬스 모니터링

---

## 기술 스택

| 컴포넌트 | 기술 | 포트 |
|---------|------|------|
| 백엔드 | FastAPI (Python 3.13+) + uvicorn | 8766 |
| 프론트엔드 | React + Vite | 5173 |
| 스캐너 | Hermes/Claude/Cursor/Codex/OpenClaw/Gemini/Antigravity/Studio scanners | — |
| LLM | 로컬 LLM 프록시 → OpenAI API 폴백 | 20128 |
| 데이터 소스 | `~/.hermes`, `~/.claude`, `~/.cursor`, `~/.codex`, `~/.openclaw`, `~/.gemini`, Studio repo | — |

---

## 아키텍처

```mermaid
graph TD
    subgraph Browser["브라우저 (localhost:5173)"]
        direction LR
        L["좌측 패널<br/>(섹션 카드, 아이템 상세, 에디터)"]
        R["Chat Molder 우측 패널<br/>(자연어 입력, diff 미리보기, Apply)"]
    end

    subgraph Backend["FastAPI 백엔드 (localhost:8766)"]
        API["API 라우터<br/>(/api/scan, /api/save, /api/mold 등)"]
    end
    
    subgraph LocalEnv["로컬 환경"]
        Hermes["~/.hermes<br/>(또는 HERMES_HOME)"]
        LLM["LLM proxy (localhost:20128)<br/>모델: harness-model"]
        Scraper["하이브리드 웹 스크래퍼<br/>(Firecrawl, Jina, TLS, Playwright)"]
    end

    L -->|HTTP Fetch| API
    R -->|HTTP Fetch| API
    
    API -->|파일 읽기/쓰기/스캔| Hermes
    API -->|OpenAI SDK| LLM
    API -->|웹 스크래핑 요청| Scraper
```

### 주요 API 엔드포인트 흐름
| 컴포넌트 | 엔드포인트 | 역할 |
|----------|------------|------|
| **스캐너** | `GET /api/scan` | workspace별 전체 하네스 스캔 |
| **파일IO** | `GET /api/read`<br>`POST /api/save` | 파일 내용 읽기 / 백업+쓰기+git 커밋 |
| **AI 챗** | `POST /api/mold` | OpenAI SDK → LLM proxy 호출 |
| **Git** | `POST /api/git/*` | init, log, diff, rollback 처리 |
| **변환기** | `POST /api/convert/*` | Claude Code ↔ Hermes 스킬 변환 및 주입 |
| **Runner**| `POST /api/pi/runs` | Pi Agent read-only 실행 |

---

## 시작하기 (Quick Start)

### 사전 요구사항
- Python 3.13+
- Node.js & npm
- (선택) LLM proxy on port 20128, 또는 `OPENAI_API_KEY`

### 설치

```bash
# 1. 저장소 클론
git clone https://github.com/misolove/agent-harness-studio.git
cd agent-harness-studio

# 2. 가상환경 생성 및 의존성 설치
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. 프론트엔드 의존성 설치
cd src/ui && npm install && cd ../..

# 4. (선택) 웹 스크래핑용 Playwright 브라우저 설치
playwright install chromium
```

### 실행

```bash
# 백엔드 + 프론트엔드 동시 실행
./run.sh

# 브라우저에서 열기
open http://localhost:5173
```

### 샌드박스 모드

```bash
# 격리된 샌드박스 — 안전한 실험 환경
HERMES_HOME=~/.hermes/sandbox ./run.sh

# 읽기 전용 모드 — 열람만, 쓰기 불가
HARNESS_READONLY=1 ./run.sh

# 실데이터 + Git 버전 관리 (권장)
HERMES_HOME=~/.hermes ./run.sh
```

### 개발 모드

```bash
# 백엔드만 실행 (핫 리로드)
source .venv/bin/activate
HERMES_HOME=~/.hermes/sandbox python -m uvicorn src.server.app:app --port 8766 --reload

# 프론트엔드만 실행 (별도 터미널)
cd src/ui && npx vite
```

---

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HERMES_HOME` | `~/.hermes` | 스캔할 하네스 디렉토리. `~/.hermes/sandbox`로 설정 시 실데이터와 분리 |
| `HARNESS_READONLY` | `0` | `1`로 설정 시 모든 쓰기 API 차단 |
| `OPENAI_API_KEY` | (없음) | LLM proxy 미사용 시 OpenAI API 폴백 |
| `FIRECRAWL_API_KEY` | (없음) | Firecrawl Phase 1 웹 스크래퍼 활성화 |

---

## API 개요

### 핵심 엔드포인트

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `GET` | `/health` | 헬스체크 |
| `GET` | `/api/env` | 환경 정보 (home, sandbox, readonly, git 상태) |
| `GET` | `/api/workspaces` | 지원 워크스페이스 목록 |
| `GET` | `/api/scan` | 전체 하네스 스캔 + 요약 카운트 |
| `GET` | `/api/scan/{section}` | 섹션별 필터링 스캔 |
| `GET` | `/api/read?path=...` | 허용된 agent workspace 파일 내용 읽기 |
| `POST` | `/api/save` | 파일 저장 + 자동 백업 + git 커밋 |
| `POST` | `/api/rollback` | 최근 `.bak.*` 백업으로 복원 |
| `GET` | `/api/reference/hermes` | 정식 Hermes 기준 컨텍스트 |
| `GET` | `/api/usage/stats` | Claude Code Skill/Subagent 사용량 |
| `GET` | `/api/recommendations` | Smart Diet 추천 |
| `POST` | `/api/actions/archive` | 파일/디렉토리 아카이브 이동 |
| `POST` | `/api/actions/copy` | 다른 워크스페이스로 복사 |

### Chat Molder

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `POST` | `/api/mold` | 대화형 AI — CHAT, CREATE_SKILL, UPDATE_SKILL, SUGGESTION 모드 |
| `POST` | `/api/pi/mold` | Pi Agent 기반 Chat Molder run 시작 |
| `GET` | `/api/pi/runs/{id}` | Pi run 상태 조회 |
| `GET` | `/api/pi/runs/{id}/log` | Pi run 로그 tail |

### Git 연동

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `POST` | `/api/git/init` | HERMES_HOME git 초기화 |
| `GET` | `/api/git/log?path=...&limit=...` | 커밋 이력 (파일 필터 옵션) |
| `GET` | `/api/git/diff?commit_hash=...` | 특정 커밋의 변경 내용 |
| `POST` | `/api/git/rollback` | 특정 커밋으로 파일 복원 |
| `GET` | `/api/git/audit` | 현재 워크스페이스 diff audit |

### Agent Runner / Pi

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `GET` | `/api/agent-runners` | 로컬 agent runtime 목록 |
| `GET` | `/api/pi/status` | Pi CLI/config/provider/model 상태 |
| `POST` | `/api/pi/preview` | Pi command preview (실행 없음) |
| `POST` | `/api/pi/runs` | Pi read-only run 시작 |
| `GET` | `/api/pi/runs/{id}` | run 상태 |
| `GET` | `/api/pi/runs/{id}/log` | stdout/stderr tail |
| `POST` | `/api/pi/runs/{id}/stop` | run 중지 |

### 기타

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `POST` | `/api/web/scrape` | 하이브리드 4단계 웹 콘텐츠 추출 |
| `GET` | `/api/audit/logs` | SQLite 감사 추적 |
| `POST` | `/api/convert/skill` | Hermes ↔ Claude Code 스킬 변환 |
| `POST` | `/api/convert/skill/inject` | Claude Skill을 Hermes Skill로 변환/주입 |
| `GET` | `/api/sessions/list` | state.db 세션 목록 |
| `GET` | `/api/sessions/messages` | 특정 세션 메시지 |

> 전체 API 문서: [docs/api.md](docs/api.md)

---

## 프로젝트 구조

```
agent-harness-studio/
├── src/
│   ├── scanner/
│   │   ├── base_scanner.py          # 공통 scanner base
│   │   ├── hermes_scanner.py        # ~/.hermes 상세 스캔 엔진
│   │   ├── claude_scanner.py        # ~/.claude
│   │   ├── codex_scanner.py         # ~/.codex
│   │   ├── cursor_scanner.py        # ~/.cursor
│   │   ├── openclaw_scanner.py      # ~/.openclaw
│   │   ├── gemini_cli_scanner.py    # ~/.gemini
│   │   ├── antigravity_scanner.py   # ~/.gemini/antigravity
│   │   └── studio_scanner.py        # agent-harness-studio 자체
│   ├── server/
│   │   ├── app.py                   # FastAPI 메인 앱 (모든 엔드포인트)
│   │   ├── usage_tracker.py         # Claude/Codex 사용량 파서
│   │   ├── recommender.py           # Smart Diet 추천 엔진
│   │   └── scrapers/                # 하이브리드 웹 스크래퍼 파이프라인
│   │       ├── hybrid.py            # 4단계 오케스트레이터
│   │       ├── firecrawl_scraper.py
│   │       ├── jina_scraper.py
│   │       ├── tls_scraper.py
│   │       └── browser_scraper.py
│   └── ui/
│       └── src/
│           ├── App.jsx              # 메인 React 컴포넌트
│           ├── App.css              # 스타일 (다크 테마)
│           └── ScrapingPipeline.jsx # 웹 스크래핑 결과 표시
├── docs/
│   ├── api.md                       # API 레퍼런스
│   ├── agent-runner-pi.md           # Pi Agent Runner 설계/구현 상태
│   ├── product-assessment-and-skill-converter.md # 제품성 평가 + Skill Converter API
│   ├── usage-telemetry-spec.md      # Usage Telemetry A안 구현 스펙
│   ├── prd.md                       # 제품 요구사항
│   ├── git-safety.md                # Git 안전 가이드
│   ├── firecrawl-vs-insane-search.md # 스크래퍼 비교
│   └── assets/
│       ├── architecture.svg
│       └── agent-harness-studio-intro.mp4
├── AGENTS.md                        # 에이전트 핸드오프 문서
├── ARCHITECTURE.md                  # 기술 아키텍처
├── HANDOFF.md                       # 핸드오프 노트
├── README_EN.md                     # 영문 README
├── requirements.txt                 # Python 의존성
└── run.sh                           # 실행 스크립트 (백엔드 + 프론트엔드)
```

---

## 의존성

```
fastapi>=0.111.0           # HTTP 프레임워크
uvicorn[standard]>=0.30.0  # ASGI 서버
PyYAML>=6.0.0              # YAML 파싱
openai>=1.0.0              # LLM 클라이언트 (LLM proxy / OpenAI 호환)
firecrawl-py>=1.0.0        # Phase 1 웹 스크래퍼
python-dotenv>=1.0.0       # .env 로드
httpx>=0.27.0              # async HTTP (Jina 스크래퍼)
curl_cffi>=0.7.0           # Phase 3 TLS 스크래퍼
playwright>=1.44.0         # Phase 4 브라우저 스크래퍼
markdownify>=0.12.0        # HTML → Markdown 변환
```

---

## LLM 설정

Chat Molder는 기본적으로 로컬 LLM 프록시를 사용하며 자동 폴백을 지원합니다:

1. **기본**: LLM proxy (`http://localhost:20128/v1`)
2. **폴백**: OpenAI API (모델: `gpt-4o`) — `OPENAI_API_KEY` 설정 시
3. **설정 오버라이드**: `~/.hermes/config.yaml`에서 커스텀 `base_url` 지정 가능

모든 LLM 호출에 정식 Hermes Agent 기준 컨텍스트가 포함되므로, 어떤 LLM 백엔드를 사용하더라도 올바른 하네스 스키마를 이해합니다.

```bash
# .env (프로젝트 루트) — 선택
OPENAI_API_KEY=sk-...
```

---

## 알려진 제약사항

- **로컬 LLM 프록시 의존성**: Chat Molder는 로컬 LLM 프록시 또는 OpenAI API 키가 필요합니다. 둘 다 없으면 `/api/mold`에서 500 에러 발생.
- **단일 사용자**: API 인증 없음. localhost 전용.
- **대용량 스킬 디렉토리**: 스킬 수 >100개 시 스캔 속도 저하 가능 (동기 처리).
- **브라우저 스크래퍼**: Phase 4 사용 시 `playwright install chromium` 필요.
- **실시간 파일 감시 없음**: 변경 사항 반영을 위해 수동 새로고침 필요.

---

## 스크린샷

> 현재 UI는 다크 테마 기반 대시보드입니다. 좌측/상단에서 workspace와 섹션을 고르고, 중앙에서 목록·검색·정렬·편집·Smart Diet·Agent Runner를 다루며, 우측 Chat Molder는 LLM 모드와 Pi Agent 모드를 전환할 수 있습니다.

---

## 기여 가이드

기여를 환영합니다! 관심 분야:

- 신규 에이전트 스캐너/runner adapter 추가
- Claude → Hermes 외 추가 skill 변환 경로
- WebSocket/SSE 기반 실시간 파일 감시
- 훅/MCP 활성화 토글 UI
- 하네스 프리셋 갤러리
- diff 나란히 보기 (side-by-side)

변경 사항은 먼저 이슈를 열어 논의해주세요.

---

## 문서

| 문서 | 내용 |
|------|------|
| [AGENTS.md](AGENTS.md) | 에이전트 핸드오프 — 현재 상태, 알려진 이슈, 확장 포인트 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 시스템 아키텍처, 데이터 흐름, 컴포넌트 설명 |
| [HANDOFF.md](HANDOFF.md) | 개발 핸드오프 노트 |
| [docs/api.md](docs/api.md) | 전체 API 엔드포인트 레퍼런스 |
| [docs/agent-runner-pi.md](docs/agent-runner-pi.md) | Pi Coding Agent adapter 설계/구현 상태 |
| [docs/usage-telemetry-spec.md](docs/usage-telemetry-spec.md) | Usage Telemetry A안 구현 스펙 |
| [docs/product-assessment-and-skill-converter.md](docs/product-assessment-and-skill-converter.md) | 제품성 평가와 Skill Converter 구현/API |
| [docs/prd.md](docs/prd.md) | 제품 요구사항 정의서 |
| [docs/git-safety.md](docs/git-safety.md) | Git 연동 안전 가이드 |
| [docs/1pager.md](docs/1pager.md) | 프로젝트 기획 배경 및 목표 |
| [docs/wireframe.md](docs/wireframe.md) | UI/UX 컨셉 제안 |

---

## 라이선스

MIT © [your-name](https://github.com/misolove)
