# Agent Harness Studio — Handoff Document

> 다음 에이전트가 이어받을 수 있도록 작성된 핸드오프 문서.
> **작업할 때마다 업데이트할 것.**
> Last updated: 2026-05-27 (문서 동기화 완료)

---

## ✅ 최근 완료 — Usage Telemetry A안

**상태**: 구현 및 검증 완료
**문서**: [`docs/usage-telemetry-spec.md`](docs/usage-telemetry-spec.md)
**핵심**: Claude Code 세션 jsonl을 파싱해 Skill/Subagent 사용 빈도 추적 → 추천 엔진 → 🥗 Diet 모달의 "📊 Smart" 탭에 통합

구현 파일:
- `src/server/usage_tracker.py` — Claude Code `~/.claude/projects/**/*.jsonl` 사용량 파서, Codex history 요약, 기타 워크스페이스 graceful unsupported
- `src/server/recommender.py` — HIGH_VALUE / STALE_UNUSED / ARCHIVE / HEAVY_UNUSED 추천 엔진
- `src/server/app.py` — `/api/usage/stats`, `/api/recommendations`, 내부 full-scan helper
- `src/scanner/claude_scanner.py` — Skill `metadata.skill_id`, 중첩 `agents/**/*.md` subagent 재귀 스캔
- `src/ui/src/App.jsx`, `src/ui/src/App.css` — Diet 모달 Smart 탭, 추천 배지, 추천/일괄 아카이브 UI

검증 결과:
- `/api/recommendations?workspace=/Users/letitbe/.claude&days=30` → 263개 추천, `HIGH_VALUE:1`, `STALE_UNUSED:72`, `ARCHIVE:190`
- `/api/recommendations?workspace=/Users/letitbe/.cursor&days=30` → unsupported + 빈 추천 리스트
- 임시 파일로 `/api/actions/archive` 스모크 테스트 완료: 원본 이동 + archive 경로 생성 확인
- `python3 -m py_compile src/server/app.py src/server/usage_tracker.py src/server/recommender.py src/scanner/claude_scanner.py`
- `cd src/ui && npm run build`

참고: Smart 탭의 `STALE_UNUSED`는 현재 로컬 데이터에 90일 이상 미수정 항목이 없어, 분석 창(`days`, 기본 30일)보다 오래 수정되지 않았고 호출이 0인 항목을 선제 정리 후보로 분류한다. 기존 Diet 모달의 `오래된 (90일+)` 탭 기준은 그대로 유지된다.

추가 문서:
- [`docs/product-assessment-and-skill-converter.md`](docs/product-assessment-and-skill-converter.md) — 현재 유용성 평가, 한계, Skill Converter 설계/구현/API 사용법.

---

## ✅ 최근 완료 — Skill Converter 1차 구현

**목표**: Claude Code Skill 중 괜찮은 것을 선택해 Hermes Skill로 변환/주입.

구현 파일:
- `src/server/app.py`
  - `/api/convert/skill` 내부 변환 로직 정리
  - `/api/convert/skill/inject` 추가
  - `dry_run`, overwrite 충돌 방지, companion directory copy, audit log, Hermes git commit 시도
- `src/ui/src/App.jsx`
  - Claude Skills 목록에 **To Hermes** 버튼 추가
  - Skill editor에 **Inject to Hermes** 버튼 추가
  - Smart 추천 액션 컬럼에 Hermes 주입 버튼 추가
- `docs/product-assessment-and-skill-converter.md`
  - 제품성 평가와 Skill Converter 방향/구현 상태/API 사용법 기록

검증 결과:
- `python3 -m py_compile src/server/app.py`
- `cd src/ui && npm run build`
- `_convert_skill_content()` 단독 테스트: `allowed-tools` → `metadata.hermes.requires_tools`
- `/api/convert/skill` smoke test 통과
- `/api/convert/skill/inject` dry-run smoke test:
  - source: `/Users/letitbe/.claude/skills/agency-client-interview/SKILL.md`
  - target: `/Users/letitbe/.hermes/skills/agency-client-interview/SKILL.md`
  - 실제 파일 쓰기 없음

---

## ✅ 최근 완료 — 문서 동기화

다음 문서가 현재 구현 상태 기준으로 업데이트됨:
- `README.md`
  - 멀티 워크스페이스, Smart Diet, Skill Converter, Pi Agent Runner, Sessions/State DB/Diff Audit 설명 반영
  - API overview와 프로젝트 구조에 신규 모듈/문서 추가
- `docs/api.md`
  - `/api/workspaces`, usage/recommendations, actions, skill inject, Pi runner, sessions, git audit 문서화
  - `/api/read`의 `max_bytes`/`tail` 파라미터와 확장된 scan section 반영
- `docs/1pager.md`
  - 2026-05-27 현재 구현 현황/검증값 섹션 추가
- `docs/prd.md`
  - 초기 Hermes 단일 MVP 문서에 현재 멀티 워크스페이스/Usage/Skill Converter/Pi Runner 구현 현황 주석 추가
- `docs/wireframe.md`
  - 실제 구현 UI(Type A 기반)와 추가된 섹션/Chat Molder Pi 모드 반영
- `docs/git-safety.md`
  - workspace 기반 Git API와 Diff Audit 현황 추가
- `docs/firecrawl-vs-insane-search.md`
  - 하이브리드 scraper가 구현 완료된 상태로 업데이트
- `docs/agent-runner-pi.md`
  - Pi read-only run, Chat Molder Pi mode, 현재/계획 API 구분 업데이트
- `docs/product-assessment-and-skill-converter.md`
  - 제품성 평가, Skill Converter UX/API/검증 결과 기록
- `HANDOFF.md`
  - Usage Telemetry, Skill Converter, 문서 동기화 상태를 최신화

---

## 1. 프로젝트 개요

**Agent Harness Studio** — 로컬 AI 에이전트 하네스(Hermes/Claude Code/Cursor/Codex/OpenClaw/Gemini/Antigravity/Studio 자체)를 스캔·편집·감사하는 웹 대시보드.

| 컴포넌트 | 기술 | 포트 |
|---------|------|------|
| Backend | FastAPI (Python) + uvicorn | 8766 |
| Frontend | React + Vite | 5173 |
| 데이터 소스 | `~/.hermes`, `~/.claude`, `~/.cursor`, `~/.codex`, `~/.openclaw`, `~/.gemini`, Studio repo | — |

**실행 방법:**
```bash
cd ~/agent-harness-studio
source .venv/bin/activate
# LaunchAgent로 자동 실행됨 (com.letitbe.agent-harness-studio)
# 수동 실행: ./run.sh
```

**주요 파일:**
- `src/scanner/base_scanner.py` — 공통 scanner base와 기본 log/session/state/checkpoint surface
- `src/scanner/hermes_scanner.py` — `~/.hermes` 전용 상세 스캔 로직
- `src/scanner/claude_scanner.py`, `codex_scanner.py`, `cursor_scanner.py`, `openclaw_scanner.py`, `gemini_cli_scanner.py`, `antigravity_scanner.py`, `studio_scanner.py` — 워크스페이스별 스캐너
- `src/server/app.py` — FastAPI 엔드포인트
- `src/server/usage_tracker.py`, `src/server/recommender.py` — Usage Telemetry + Smart Diet 추천 엔진
- `src/ui/src/App.jsx` — React 메인 컴포넌트
- `src/ui/src/App.css` — 스타일
- `docs/agent-runner-pi.md` — Pi Coding Agent adapter 설계/핸드오프
- `docs/product-assessment-and-skill-converter.md` — 제품성 평가 + Skill Converter 설계/구현 상태
- `docs/usage-telemetry-spec.md` — Usage Telemetry A안 구현 스펙
- `~/Library/LaunchAgents/com.letitbe.agent-harness-studio.plist` — macOS LaunchAgent

---

## 2. 현재 스캐너 지원 섹션

| 섹션 ID | Type 문자열 | 소스 |
|---------|------------|------|
| `skills` | `Skill` | 각 워크스페이스의 skills/rules/agents/docs 등 스킬성 항목 |
| `bundles` | `Skill Bundle` | Hermes `skill-bundles/*.yaml` |
| `memory` | `Memory Config`, `Memory Manifest`, `Memory Directory`, `Memory State` | config/memory/state 계열 파일과 디렉토리 |
| `mcp` | `MCP Server` | Hermes config.yaml `mcp_servers` 등 |
| `context` | `Root Context` | AGENTS.md/CLAUDE.md/GEMINI.md/커서 룰/시스템 프롬프트 |
| `hooks` | `Hook` | hook 설정, gateway hooks, Codex hooks 등 |
| `cron` | `Cron Job` | cron/jobs 계열 정의 |
| `plugins` | `Plugin` | 플러그인/extension/package 정의 |
| `logs` | `Log File` | logs/log/sessions/runs/traces 계열 대용량 로그 tail 지원 |
| `sessions` | `Session Summary` | Hermes state.db sessions 집계, Claude/Codex 세션성 파일 요약 |
| `statedb` | `State DB` | state.db/kanban.db/harness_studio.db/sqlite 파일 |
| `checkpoints` | `Checkpoint` | Hermes checkpoint store 등 |
| `agent-runners` | `Agent Runner` | Pi Coding Agent 상태/실행 surface |
| `config` | `Config`, cross-section | 설정성 항목 합산 |
| `web` | — | 플레이스홀더 (미구현) |

---

## 3. 완료된 작업 (이번 세션)

### 3.1 버그 수정
- [x] **LaunchAgent HERMES_HOME 오류**: sandbox → `~/.hermes` 수정, ThrottleInterval=10 추가
- [x] **run.sh 포트 정리**: 8766/5173 stale process kill 블록 추가
- [x] **Config 카드 count=0**: frontend에서 items 배열 직접 카운트하도록 수정
- [x] **카드 숫자 잘림/저대비**: `overflow:hidden` 제거, `.card-count` 스타일 개선 (흰 글자 + 보라 배경)
- [x] **Hooks=0**: `config.yaml hooks.*` 형식 파싱 추가 (`_scan_hooks`)
- [x] **MCP 깨진 서버 ACTIVE 표시**: 절대경로 존재 확인, `command` 없으면 ERROR 표시
- [x] **Memory Directory 오탐**: `memory/` → `memories/` + `memory/` 둘 다 체크

### 3.2 신규 기능
- [x] **Cron Jobs 섹션 추가**: `cron/jobs.json` 파싱, 상태(ACTIVE/PAUSED/DONE) 표시
- [x] **Plugins 섹션 추가**: `plugins/*/plugin.yaml` 파싱, tools/hooks 수 표시
- [x] **Memory 파일 내용 보기**: Memory Directory 아이템 클릭 시 .md 파일 서브행 + View 버튼
- [x] **Memory Manifest View 버튼**: `memory_manifest.md` 직접 열기 버튼 추가

### 3.3 프론트엔드 및 시스템 안정화 (2026-05-25 긴급 반영)
- [x] **다중 워크스페이스 지원**: `app.py` 경로 검증 함수(`_get_allowed_roots`) 누락(NameError) 복구 및 `~/.hermes`, `~/.claude`, `~/.cursor` 등 범용 지원
- [x] **오프라인 코드 에디터 교체**: CDN 차단 및 ESM 오류를 유발하던 `@monaco-editor/react`를 `react-simple-code-editor` + `prismjs`로 마이그레이션
- [x] **UI 에러 방어막(ErrorBoundary) 도입**: 에디터 컴포넌트 렌더링 실패 시 화면 전체가 사라지는(White Screen) 현상을 막기 위해 `<EditorErrorBoundary>` 래퍼 추가
- [x] **Vite 접속 불가 현상(아예 안나와) 해결**: `run.sh`에서 Vite 실행 인자를 `--host 0.0.0.0`으로 고정하여 IPv6 의존 이슈 원천 차단

### 3.4 Hermes 정합성 보강 (2026-05-25)
- [x] **MCP HTTP 서버 정상 처리**: `url` 기반 MCP는 `command` 없이도 ACTIVE, `enabled:false`는 INACTIVE
- [x] **MCP metadata 확장**: `tools.include/exclude`, `headers`, `auth`, `sampling`, timeout 계열 마스킹/표시
- [x] **Gateway Hook 구조 지원**: `hooks/<name>/HOOK.yaml + handler.py` 파싱
- [x] **Skill external_dirs/disabled 반영**: `skills.external_dirs`, `skills.disabled`, `skills.platform_disabled` 스캔
- [x] **Skill Bundle 섹션 추가**: `skill-bundles/*.yaml` 파싱 및 UI 카드 표시
- [x] **Plugin hooks 필드 보강**: `provides_hooks`와 `hooks` 둘 다 카운트
- [x] **Chat Molder Hermes 기준 문맥 주입**: 모든 LLM 호출에 `nousresearch/hermes-agent` reference, canonical harness surfaces, 현재 스캔 스냅샷을 system/user context로 전달

---

### 3.5 Antigravity Safe Coding Harness (2026-05-25)
- [x] **`~/.gemini/GEMINI.md` 전역 룰 작성**: 수정 전 컨텍스트 읽기, 보호 파일 목록, 검증 후 완료 선언, side-effect audit 보고 형식
- [x] **`minimal-change-coding` 스킬 생성**: `~/.gemini/skills/minimal-change-coding/SKILL.md` — Phase 1(Pre-flight) → Phase 2(Edit) → Phase 3(Verification) → Phase 4(Diff Report) 4단계 프로토콜
- [x] **Studio Diff Audit 백엔드**: `GET /api/git/audit?workspace=...` — git status 파싱, 보호 파일 감지, risk(clean/low/medium/high) 산출
- [x] **Studio Diff Audit UI**: "🔍 Diff Audit" 섹션 카드 추가, risk 배지 + 변경 파일 목록 + protected 표시 + git stat 블록 표시
- [x] **프로젝트 `GEMINI.md` 생성**: 데스크탑 앱용 프로젝트 루트 컨텍스트 파일 — 보호 파일 목록, 검증 명령, 완료 보고 형식, 루프 방지 규칙 포함

---

---

## 3.6 신규 기능 (2026-05-25 세션2)
- [x] **Sessions 대시보드** — `state.db` sessions 테이블 집계: 세션수(536), 메시지수(34k+), 툴 호출, 추정비용, 토큰, 모델 분포 바차트, 최근 세션 5개
- [x] **State DB 뷰어** — `state.db` / `kanban.db` / `harness_studio.db` 테이블 구조·행 수 표시
- [x] **Cron Job 상세 확장** — ▼ 토글 버튼으로 next_run_at, last_run_at, completed_count, last_error 인라인 표시
- [x] **MCP ERROR 강조** — ERROR 상태 서버 상단 정렬 + 빨간 ⚠ 배지 (state_reason 툴팁)
- [x] **스캐너 `_scan_sessions()` + `_scan_statedb()` 추가** — `hermes_scanner.py` + `app.py` SECTION_TYPE_MAP 등록
- [x] **카드 숫자 의미화** — Sessions 카드는 실제 세션 수(536) 표시, State DB 카드는 파일 수 표시

---

## 3.7 Agent Runner 기초 연동 (2026-05-26)
- [x] **Pi Coding Agent 감지 API** — `GET /api/agent-runners`, `GET /api/pi/status`
  - `pi` CLI 경로, 버전, RPC/JSON/print mode, `~/.pi/agent` 설정·auth·models·sessions 상태 표시
  - 로컬 확인 결과: `/opt/homebrew/bin/pi`, version `0.75.5`
  - 최신 Pi 설정: `defaultProvider=zai`, `defaultModel=glm-5.1` (`~/.pi/agent/settings.json`)
- [x] **Pi 안전 command preview API** — `POST /api/pi/preview`
  - 실제 실행은 하지 않고 `will_execute:false`로 명령만 반환
  - 기본 preview는 `pi --tools read,grep,find,ls --no-session --mode rpc ...`
  - 쓰기/edit/bash 실행 API는 아직 의도적으로 비활성화
- [x] **Agent Runner UI 섹션** — 사이드바 카드 + 상태 패널
  - 설치 상태, 버전, auth 상태, 세션 수, capability chip, 안전 실행 단계, RPC command preview 표시
- [x] **설계 핸드오프 문서 추가** — `docs/agent-runner-pi.md`
  - 로컬 설치 Pi CLI/RPC 우선, SDK/source embedding은 2차 선택으로 정리
  - read-only → gated write → SDK/source integration 단계 정의

---

## 3.8 Pi runs read-only mode + UI 완성 (2026-05-26)
- [x] **`/api/pi/status` provider_info 확장** — `_pi_read_settings()` 헬퍼로 `~/.pi/agent/settings.json` 직접 파싱
  - `defaultProvider`, `defaultModel`, `packages`, `lastChangelogVersion` 반환
- [x] **`POST /api/pi/runs`** — read-only mode 실행 API
  - `mode=read_only` 강제, BLOCKED_TOOLS(`write,edit,bash`) 차단
  - 명령: `pi --tools read,grep,find,ls --no-session --mode rpc <prompt>`
  - pre-audit(`_capture_git_audit`) 캡처 후 `threading.Thread`로 서브프로세스 실행
  - stdout: JSON RPC event 스트리밍, stderr: 파일 직접 리디렉트(deadlock 방지)
  - 완료 시 post-audit 자동 캡처, `meta.json` 디스크 저장
- [x] **`GET /api/pi/runs/{run_id}`** — 실행 상태 조회 (메모리 우선, 디스크 fallback)
- [x] **`GET /api/pi/runs/{run_id}/log`** — stdout.log + stderr.log tail (기본 200줄)
- [x] **`POST /api/pi/runs/{run_id}/stop`** — SIGTERM 전송
- [x] **런 데이터 저장 경로**: `~/.hermes/harness-studio-runs/pi/{run_id}/`
  - `meta.json`, `events.jsonl`, `stdout.log`, `stderr.log`, `pre-audit.json`, `post-audit.json`
- [x] **Agent Runner UI — Provider/Model 표시**
  - stats grid에 Provider(`zai`), Model(`glm-5.1`) 추가 (App.jsx)
- [x] **Agent Runner UI — Run (read-only) 섹션 추가**
  - 프롬프트 textarea, Run 버튼, 폴링(2s) 상태 표시, stdout+stderr 인라인 로그, post-audit 표시
  - 상태: `piRunPrompt`, `piRunId`, `piRunMeta`, `piRunLog`, `piRunPolling`
  - `submitPiRun()`, `fetchPiRunLog()`, `useEffect` 폴링 훅 추가 (App.jsx)
- [x] **대량 항목 정렬 UI 추가**
  - Skills/Logs/MCP/Plugins 등 일반 리스트 섹션에 검색 옆 sort select 추가
  - 이름 A-Z/Z-A, 최신순/오래된순, 상태순, 타입순
  - Skills는 기존 category 그룹을 유지하고 그룹 내부 정렬 적용
- [ ] **다음 단계** — SSE(`GET /api/pi/runs/{id}/events`) 스트리밍으로 폴링 대체
- [ ] **다음 단계** — gated write mode (명시적 토글 + 확인 후만 활성화)

---

## 3.9 Chat Molder — Pi Agent 완전 연동 (2026-05-26)

**목표:** Chat Molder 대화창에서 Pi Coding Agent를 통해 web_search·파일 읽기·세션 연속성 제공

### Backend (`app.py`)

- [x] **`MOLD_TOOLS = "read,grep,find,ls,web_search"`** — Chat Molder 전용 툴셋 (web_search 포함)
- [x] **`PI_SESSIONS_DIR`** — `~/.hermes/harness-studio-runs/pi/sessions/` (세션 파일 저장)
- [x] **`POST /api/pi/mold`** 완전 재작성
  - `session_file` 파라미터: 없으면 `mold-{ts}-{hex}.jsonl` 신규 생성, 있으면 기존 세션 이어받기
  - 첫 턴: 하네스 컨텍스트(workspace, 편집 중 파일 등) 포함 full prompt + `--session <path> --print`
  - 후속 턴: 사용자 메시지만 + `--session <path> --continue --print`
  - `is_new_session` 플래그 반환 (프론트에서 세션 초기화 감지용)
  - 응답: `{ run_id, status, session_file, is_new_session }`

### Frontend (`App.jsx`)

- [x] **LLM / Pi Agent 토글** — Chat Molder 헤더에 버튼 그룹 추가 (`piMode` state)
- [x] **"새 대화" 버튼** — Pi 모드 + 세션 존재 시 표시, 클릭 시 `piMoldSessionFile=null` + 이력 초기화
- [x] **`handleMoldWithPi()`** — Pi 모드 전송 핸들러
  - 사용자 메시지를 `chatHistory`에 즉시 추가 후 `POST /api/pi/mold` 호출
  - 응답의 `session_file`을 `piMoldSessionFile` state에 저장 (연속성 유지)
- [x] **`piMoldRef` 폴링 이펙트** — 2초마다 `/api/pi/runs/{id}` + `/log` 조회
  - 완료 시 stdout을 `chatHistory` assistant 메시지로 추가
  - **파일 경로 자동 추출**: 두 가지 정규식 패턴으로 Pi 응답 내 파일 경로 탐지
    - `` `/{path}.ext` `` 또는 `` `~/{path}.ext` `` 형식
    - `파일:`, `File:`, `경로:` 등 레이블 뒤 경로
  - `mentionedFiles` 배열을 메시지에 첨부
- [x] **Pi 응답 버블**
  - `Pi Agent (read · grep · find · ls · web_search)` 배지 표시
  - `mentionedFiles` 있으면 "📄 {파일명}" 버튼 렌더링 — 클릭 시 `fetchFileContent()` 호출하여 Studio 에디터에서 열기
- [x] **로딩 버블** — "Pi Agent 실행 중 (read · grep · find · ls)…" 표시
- [x] **전송 버튼** — `piMoldPolling` 중 비활성화 + "Pi 실행 중…" 텍스트

### CSS (`App.css`)

- [x] `.pi-mode-toggle`, `.pi-toggle-btn`, `.pi-toggle-btn.active` 스타일 추가
- [x] `.chat-title-block` flexbox 전환

### 검증 결과 (curl end-to-end)

| 테스트 | 결과 |
|--------|------|
| 첫 번째 턴 (신규 세션) | ✅ Pi가 하네스 컨텍스트 기반 자기소개 (192개 스킬 등) |
| 두 번째 턴 (세션 연속) | ✅ "192개"를 이전 대화에서 기억하여 정확히 답변 |
| web_search 실제 동작 | ✅ Claude Code 최신 버전 v2.1.148 실시간 검색 성공 |

### 제약사항 (유지)

- `write/edit/bash`는 BLOCKED_TOOLS 목록 — gated write mode 전까지 비활성
- Pi 소스 fork/embed 없음 — 설치된 `/opt/homebrew/bin/pi` CLI를 subprocess로 호출
- ZAI_API_KEY: `~/hermes-memory-pointer-architecture/.env`에서 자동 로드 (`_get_pi_subprocess_env()`)

---

## 4. 알려진 미구현 사항 (다음 작업 후보)

### 4.1 스캐너 갭
- [ ] **Checkpoints** — `checkpoints/store/` (Git-like 내부 저장소, 표시 방법 검토 필요)
- [ ] **SOUL.md** — `~/.hermes/SOUL.md` Root Context에 포함되어야 할 수 있음 (스캐너에 이미 반영됨, UI 확인)

### 4.2 UI/UX 개선
- [ ] **Plugin 상세 보기** — provides_tools 목록 펼쳐보기
- [x] **검색/정렬** — 일반 섹션 검색 + 이름/날짜/상태/타입 정렬
- [ ] **Skills count 192개** — 카테고리 접기 + 정렬은 지원됨. 더 많아지면 페이지네이션/가상 리스트 검토
- [ ] **Sessions JSONL 뷰어** — 개별 세션 클릭 시 메시지 스레드 표시

### 4.3 Web Context 섹션
- `web` 섹션은 현재 URL scraping placeholder만 있음 (실제 저장/활용 미구현)

### 4.4 Agent Runner / Pi
- [x] `~/.pi/agent/settings.json`의 `defaultProvider/defaultModel`을 `/api/pi/status`와 UI에 직접 표시 ✅
- [x] `POST /api/pi/runs` read-only mode 구현: `pi --tools read,grep,find,ls --no-session --mode rpc` ✅
- [x] Pi stdout/stderr/RPC events를 `~/.hermes/harness-studio-runs/pi/{run_id}/`에 저장 ✅
- [x] run 전후 `GET /api/git/audit` 자동 캡처 및 diff summary 표시 ✅
- [ ] SSE(`GET /api/pi/runs/{id}/events`)로 Pi run events를 UI에 스트리밍 (현재: 2초 폴링)
- [ ] gated write mode는 명시적 토글/확인 전까지 만들지 말 것

---

## 5. 아키텍처 핵심 사항

### Scanner 구조
```python
_scanner_for_workspace(workspace)
├── ~/.hermes              → HermesScanner
├── ~/.claude              → ClaudeScanner
├── ~/.cursor              → CursorScanner
├── ~/.codex               → CodexScanner
├── ~/.openclaw            → OpenClawScanner
├── ~/.gemini              → GeminiCliScanner
├── ~/.gemini/antigravity  → AntigravityScanner
└── project root           → StudioScanner

HermesScanner keeps the richest surface:
skills/bundles/memory/mcp/context/hooks/cron/plugins/logs/sessions/statedb/checkpoints.
Other scanners normalize their native files into the same item schema so the UI can reuse one dashboard.
```

### API 엔드포인트
```
GET  /api/workspaces            → 감지 가능한 agent workspace 목록
GET  /api/scan                  → 전체 스캔 결과 + summary
GET  /api/scan/{section}        → 섹션별 필터링
GET  /api/read?path=...         → 파일 내용 읽기(max_bytes/tail 지원)
POST /api/save                  → 파일 저장 (+ git commit 시도)
POST /api/rollback              → 백업 복원
POST /api/mold                  → Chat Molder (LLM 제안)
GET  /api/reference/hermes      → Molder에 주입되는 Hermes reference context
GET  /api/usage/stats           → Skill/Subagent 사용량 telemetry
GET  /api/recommendations       → Usage-aware Smart Diet 추천
POST /api/actions/archive       → 항목 archive 이동
POST /api/actions/copy          → 항목 다른 workspace로 copy
POST /api/convert/skill         → Claude/Hermes skill 변환 preview
POST /api/convert/skill/inject  → Claude skill을 Hermes skill로 dry-run/write 주입
GET  /api/agent-runners          → local agent runtime status list
GET  /api/pi/status              → Pi CLI/config/capability status (provider_info 포함)
POST /api/pi/preview             → safe Pi command preview only (no execution)
POST /api/pi/runs                → Pi read-only run 시작 (mode=read_only 강제)
GET  /api/pi/runs/{id}           → run 상태 조회
GET  /api/pi/runs/{id}/log       → stdout+stderr tail
POST /api/pi/runs/{id}/stop      → SIGTERM 전송
POST /api/pi/mold                → Chat Molder Pi Agent mode
GET  /api/sessions/list          → state.db sessions 목록
GET  /api/sessions/messages      → session messages
GET  /api/git/audit              → workspace git diff/risk audit
```

### SECTION_TYPE_MAP (app.py)
```python
{
  "skills": ["Skill"],
  "bundles": ["Skill Bundle"],
  "memory": ["Memory Config", "Memory Manifest", "Memory Directory", "Memory State"],
  "mcp":    ["MCP Server"],
  "context":["Root Context"],
  "hooks":  ["Hook"],
  "cron":   ["Cron Job"],
  "plugins":["Plugin"],
  "logs":   ["Log File"],
  "sessions": ["Session Summary"],
  "statedb": ["State DB"],
  "checkpoints": ["Checkpoint"],
  "agent-runners": ["Agent Runner"],
  "config": ["Config", "Memory Config", "Root Context", "MCP Server"],
}
```

---

## 6. 테스트 방법

```bash
# 스캐너 직접 실행
cd ~/agent-harness-studio
source .venv/bin/activate
python -m src.scanner.hermes_scanner | python3 -c "
import json, sys
from collections import Counter
d = json.load(sys.stdin)
print(Counter(x['type'] for x in d))
"

# API 헬스 체크
curl -sf http://127.0.0.1:8766/api/scan | python3 -m json.tool | grep summary

# 프론트엔드
open http://localhost:5173
```

---

## 7. 환경 정보

- Python venv: `~/agent-harness-studio/.venv`
- Node modules: `~/agent-harness-studio/src/ui/node_modules`
- LaunchAgent logs: `~/Library/Logs/agent-harness-studio/stdout.log`
- HERMES_HOME: `~/.hermes`
- Git repo: `~/.hermes` (모든 변경이 커밋으로 기록됨)
