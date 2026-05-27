# Agent Handoff Document — Agent Harness Studio

> 이 문서는 이 프로젝트를 처음 접하는 AI 에이전트(또는 개발자)가 컨텍스트 없이도
> 현재 상태를 파악하고 작업을 이어갈 수 있도록 작성된 핸드오프 문서입니다.
> 마지막 업데이트: 2026-05-25

---

## 1. 프로젝트 개요

**Agent Harness Studio**는 AI 에이전트(Hermes 기반)의 하네스 구성요소를
웹 대시보드에서 시각화·수정할 수 있는 로컬 관리 도구입니다.

- **백엔드**: FastAPI (Python 3.13+), 포트 8766
- **프론트엔드**: React + Vite, 포트 5173
- **LLM**: LLM proxy (`http://localhost:20128/v1`) -> OpenAI API 자동 폴백 지원
- **대상 데이터**: `~/.hermes` 디렉토리 (환경변수 `HERMES_HOME`으로 오버라이드)

---

## 2. 현재 구현 상태 (as of 2026-05-25)

### 작동하는 기능

| 기능 | 파일 | 상태 |
|------|------|------|
| 하네스 스캔 (스킬/메모리/MCP/훅/컨텍스트) | `src/scanner/hermes_scanner.py` | 완료 |
| Hermes 정합성 스캔 보강 (external skills/disabled/bundles/HTTP MCP/gateway hooks) | `src/scanner/hermes_scanner.py` | 완료 (2026-05-25 추가) |
| 섹션별 대시보드 뷰 | `src/ui/src/App.jsx` | 완료 |
| Chat Molder (자연어 → 하네스 수정 제안) | `src/server/app.py` → `/api/mold` | 완료 |
| AI 제안 Apply (스킬 파일 저장) | `/api/save` + `handleApply` | 완료 |
| Hybrid Web Scraper (Firecrawl→Jina→TLS→Browser) | `src/server/scrapers/` | 완료 |
| 파일 읽기 API (`/api/read`) | `src/server/app.py` | 완료 (2026-05-24 추가) |
| 파일 편집 (실제 내용 로드) | `src/ui/src/App.jsx` → `handleEditClick` | 완료 (2026-05-24 버그 수정) |
| 자동 백업 (저장 전 `.bak.{timestamp}`) | `/api/save` | 완료 (2026-05-24 추가) |
| Rollback API (`/api/rollback`) | `src/server/app.py` | 완료 (2026-05-24 추가) |
| HARNESS_READONLY 모드 | `src/server/app.py` | 완료 (2026-05-24 추가) |
| **Git 연동** (자동 커밋, 이력, 복원) | `src/server/app.py` + `App.jsx` | 완료 (2026-05-24 추가) |
| Git Init UI (헤더 버튼) | `App.jsx` → `handleGitInit` | 완료 (2026-05-24 추가) |
| 변경 이력 패널 (History 버튼) | `App.jsx` → `showHistory` + `gitLog` | 완료 (2026-05-24 추가) |
| 커밋별 파일 복원 (git rollback) | `/api/git/rollback` | 완료 (2026-05-24 추가) |
| **Memory Map (통합 뷰)** | `App.jsx` + `app.py` | 완료 (2026-05-25 추가) |
| **SOUL.md Editor (페르소나)** | `App.jsx` + `hermes_scanner.py` | 완료 (2026-05-25 추가) |
| **Context Window Estimator (토큰)** | `App.jsx` + `hermes_scanner.py` | 완료 (2026-05-25 추가) |
| **Cross-Agent Skill Converter** | `App.jsx` + `app.py` | 완료 (2026-05-25 추가) |
| **SQLite Audit Log (changelog)** | `app.py` + `App.jsx` | 완료 (2026-05-25 추가) |
| **LLM proxy 폴백 (OpenAI API)** | `app.py` | 완료 (2026-05-25 추가) |
| **범용 텍스트 파일 편집 (Universal Edit)** | `App.jsx` + `app.py` | 완료 (2026-05-25 추가) |
| **Chat Molder 대화형 UI & 마크다운 렌더러** | `App.jsx` (`MarkdownContent`) | 완료 (2026-05-25 개선) |
| **LLM 응답 파싱 강건성 및 히스토리 유지** | `app.py` (`parse_molder_json`) | 완료 (2026-05-25 개선) |
| **다중 에이전트 워크스페이스 지원** | `/api/workspaces` + `App.jsx` | 완료 (2026-05-25 추가) |
| **오프라인 코드 에디터 (PrismJS)** | `App.jsx` (`react-simple-code-editor`) | 완료 (2026-05-25 추가) |
| **UI 에러 방어막 (ErrorBoundary)** | `App.jsx` (`EditorErrorBoundary`) | 완료 (2026-05-25 추가) |
| 샌드박스 모드 (`HERMES_HOME=~/.hermes/sandbox`) | `run.sh` | 지원됨. 기본 run.sh는 실데이터 `~/.hermes` |

### 미구현 기능 (PRD 기준)

| 기능 | 우선순위 | 비고 |
|------|----------|------|
| 훅/MCP 활성화 토글 (enable/disable) | 높음 | UI에 없음. config.yaml 직접 수정 필요 |
| 실시간 파일 감시 (WebSocket/SSE) | 중간 | 현재 수동 새로고침만 지원 |
| 스킬 URL 설치 | 중간 | PRD에 명시됨 |
| diff 사이드바이사이드 미리보기 | 낮음 | 현재 diff 텍스트만 표시 |

---

## 3. 수정된 버그 (2026-05-25 업데이트)

### [CRITICAL] Edit 버튼 클릭 시 HTTP 500 오류 (NameError)
- **증상**: 다른 워크스페이스(예: `.codex`)의 파일을 열 때 HTTP 500 에러 발생.
- **원인**: `app.py`에서 다중 경로 보안 검증을 위한 `_get_allowed_roots()` 함수가 누락됨.
- **수정**: 해당 함수를 복구하여 `~/.hermes`, `~/.claude`, `~/.cursor`, `~/.codex` 등 여러 에이전트 경로를 안전하게 지원하도록 조치.

### [CRITICAL] Edit 뷰 화이트 스크린 (React Crash)
- **증상**: 에디터 모듈 로드 실패나 구문 분석 에러 시 전체 UI가 사라지는 현상.
- **원인**:
  - `@monaco-editor/react` 사용 시 CDN 차단 또는 CJS 객체 매핑(default export) 문제로 인한 React 렌더링 실패.
  - `import` 구문 위치(클래스 선언부 하단)로 인한 모듈 로더 SyntaxError.
- **수정**:
  - 외부 CDN 의존성이 없는 완전 로컬 모듈(`react-simple-code-editor` + `prismjs`)로 교체.
  - 에디터 컴포넌트 렌더링을 래핑하는 `<EditorErrorBoundary>` 컴포넌트를 추가하여 화면 전체가 죽지 않고 에러 메시지와 재시도 버튼만 표시되도록 안전성 대폭 강화.

---

## 3.1. 이전 수정 사항 (2026-05-24)

### [CRITICAL] handleEditClick 더미 내용 덮어쓰기
- **증상**: Edit 버튼 클릭 시 실제 파일 내용 대신 더미 템플릿을 에디터에 로드
- **원인**: `/api/read` 엔드포인트 없음 + `setEditContent`에 하드코딩된 문자열
- **수정**: `/api/read` 엔드포인트 추가 + `handleEditClick`을 async fetch로 변경

### [MINOR] handleApply 하드코딩 경로
- **증상**: `envInfo`가 로드되지 않은 상태에서 `~/.hermes` 하드코딩 사용
- **수정**: `envInfo?.hermes_home` 없을 때 에러 메시지 표시로 변경

### [MINOR] build_response config 카운팅
- **증상**: config 타입 아이템마다 다른 카테고리 합산값으로 덮어씀
- **수정**: `summary.get("config", 0) + 1`로 단순 카운팅

---

## 4. 아키텍처 결정 사항

### FastAPI + React (Tauri 미사용 이유)
PRD는 Tauri v2(Rust + React)를 권장했으나, Hermes가 FastAPI+React로 구현했습니다.
**이유**: 로컬 MVP 프로토타입으로 FastAPI가 훨씬 빠른 이터레이션이 가능.
Tauri 마이그레이션은 프로덕션 배포 단계에서 고려 가능.

### Hermes 전용 스캐너 (Claude 하네스 미지원)
`HermesScanner`는 `~/.hermes` 구조를 전제로 설계됨.
Claude Code의 `~/.claude` 구조(CLAUDE.md, rules/, skills/, hooks/)와 다릅니다.
두 에이전트를 모두 지원하려면 스캐너 추상화 레이어 필요.

### LLM Proxy
Chat Molder는 OpenAI SDK를 로컬 LLM 프록시(`http://localhost:20128/v1`)에 연결.
로컬 LLM 프록시가 없으면 LLM 기능 전체 불가. OpenAI API 키 폴백 필요.

---

## 5. 파일 구조

```
agent-harness-studio/
├── src/
│   ├── scanner/
│   │   └── hermes_scanner.py      # 핵심: ~/.hermes 스캔 엔진
│   ├── server/
│   │   ├── app.py                 # FastAPI 메인 앱 (모든 API 엔드포인트)
│   │   └── scrapers/              # Hybrid Web Scraper 파이프라인
│   │       ├── hybrid.py          # Firecrawl→Jina→TLS→Browser 오케스트레이터
│   │       ├── firecrawl_scraper.py
│   │       ├── jina_scraper.py
│   │       ├── tls_scraper.py
│   │       └── browser_scraper.py
│   └── ui/
│       └── src/
│           ├── App.jsx            # 메인 React 앱 (사이드바 + 채팅)
│           ├── App.css            # 스타일
│           └── ScrapingPipeline.jsx  # Web Context 스크래핑 결과 표시
├── docs/
│   ├── api.md                     # API 레퍼런스
│   ├── prd.md                     # 제품 요구사항
│   ├── 1pager.md                  # 1-pager 기획서
│   └── wireframe.md               # UI/UX 와이어프레임
├── AGENTS.md                      # 이 문서 (에이전트 핸드오프)
├── ARCHITECTURE.md                # 기술 아키텍처 상세
├── README.md                      # 프로젝트 개요 + 시작하기
├── requirements.txt               # Python 의존성
└── run.sh                         # 백엔드 + 프론트엔드 동시 실행
```

---

## 6. 안전 레이어 구조

다음 레이어를 중첩해서 사용합니다:

```
레이어 1: HARNESS_READONLY=1
  → 모든 /api/save, /api/rollback, /api/git/* 403 반환
  → UI에서 Save 버튼 비활성화, "READ-ONLY" 배지 표시
  → 가장 강력한 보호. 브라우징 전용 모드.

레이어 2: HERMES_HOME=~/.hermes/sandbox
  → 실데이터와 물리적으로 분리된 디렉토리 사용
  → 쓰기는 허용하지만 실데이터에는 영향 없음
  → run.sh 기본값

레이어 3: 자동 백업 (save_item)
  → 저장 시 자동으로 {file}.bak.{timestamp} 생성
  → /api/rollback으로 복원 가능
  → 레이어 1, 2 없이 실데이터에 쓸 때 최후 안전망

레이어 4: Git 버전 관리 (권장 — 실데이터 수정 시)
  → ~/.hermes를 git repo로 초기화 (UI "Git 연동" 버튼 또는 /api/git/init)
  → 저장마다 자동 커밋 (커밋 메시지 직접 입력 가능)
  → History 패널에서 파일별 전체 이력 확인
  → 임의 커밋 시점으로 복원 (git checkout)
  → 복원 후 자동으로 새 커밋 생성 → 이력 단절 없음
```

권장 운영 모드:
- 탐색 전용: `HARNESS_READONLY=1 HERMES_HOME=~/.hermes`
- 샌드박스 수정: `HERMES_HOME=~/.hermes/sandbox`
- **실데이터 수정 (권장)**: `git init ~/.hermes` 후 `HERMES_HOME=~/.hermes`
  → 모든 변경이 커밋으로 기록되어 언제든 복원 가능

상세 가이드: [docs/git-safety.md](docs/git-safety.md)

---

## 7. 다음 작업 추천 (우선순위순)

### P1 — 즉시 필요
1. **훅/MCP/컨텍스트 Edit 버튼 추가**: 스킬 외 다른 타입도 편집 가능하게
2. **LLM 프록시 폴백**: 로컬 LLM 프록시가 없을 때 OpenAI API 키로 자동 폴백

### P2 — 주요 기능
3. **변경 이력 UI**: `.bak.*` 파일 목록을 UI에서 보여주고 선택 롤백 가능하게
4. **훅/MCP enable/disable 토글**: config.yaml의 해당 섹션 comment/uncomment
5. **실시간 파일 감시**: `watchdog` 라이브러리 + SSE로 변경 사항 자동 반영

### P3 — 확장
6. **Claude 하네스 지원**: `~/.claude` 구조 스캔 (`ClaudeScanner` 추가)
7. **스킬 URL 설치**: GitHub URL → 스킬 설치 워크플로우
8. **LLM async화**: `/api/mold`의 OpenAI 호출을 `httpx.AsyncClient`로

---

## 8. 테스트 방법

```bash
# 백엔드 단독 테스트
curl http://localhost:8766/api/scan | python3 -m json.tool
curl http://localhost:8766/api/env

# 샌드박스에서 스킬 생성 테스트
curl -X POST http://localhost:8766/api/save \
  -H "Content-Type: application/json" \
  -d '{"path": "~/.hermes/sandbox/skills/test-skill/SKILL.md", "content": "---\nname: test-skill\n---\n\nTest"}'

# 읽기 전용 모드 확인
HARNESS_READONLY=1 curl -X POST http://localhost:8766/api/save \
  -H "Content-Type: application/json" \
  -d '{"path": "/tmp/test", "content": "x"}'
# → 403 반환 확인

# 스캐너 단독 실행
python src/scanner/hermes_scanner.py
```

---

## 9. 알려진 제약사항

- **로컬 LLM 프록시 의존성**: Chat Molder는 로컬 LLM 프록시가 실행 중이어야 작동. 없으면 500 에러.
- **단일 사용자 전제**: API 인증 없음. localhost 전용.
- **대용량 스킬 디렉토리**: 스킬 수 > 100이면 스캔 속도 저하 가능 (비동기 처리 미적용).
- **브라우저 스크래퍼**: playwright 브라우저 미설치 시 Phase 4 실패. `playwright install chromium` 필요.
