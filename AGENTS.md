# Agent Handoff Document — Agent Harness Studio

> 이 문서는 이 프로젝트를 처음 접하는 AI 에이전트(또는 개발자)가 컨텍스트 없이도
> 현재 상태를 파악하고 작업을 이어갈 수 있도록 작성된 핸드오프 문서입니다.
> 마지막 업데이트: 2026-05-31

---

## 1. 프로젝트 개요

**Agent Harness Studio**는 AI 에이전트(Hermes 기반)의 하네스 구성요소를
웹 대시보드에서 시각화·수정할 수 있는 로컬 관리 도구입니다.

- **백엔드**: FastAPI (Python 3.13+), 포트 8766
- **프론트엔드**: React + Vite, 포트 5173
- **LLM**: LLM proxy (`http://localhost:20128/v1`) -> OpenAI API 자동 폴백 지원
- **대상 데이터**: `~/.hermes` 디렉토리 (환경변수 `HERMES_HOME`으로 오버라이드)

---

## 2. 현재 구현 상태 (as of 2026-05-31)

### 아키텍처 리팩토링 완료 (2026-05-31)

기존 모놀리식 구조에서 모듈형 아키텍처로 분리 완료:

| 변경 사항 | 이전 | 이후 |
|-----------|------|------|
| 백엔드 진입점 | `app.py` (2,822줄) | `main.py` (86줄) + 14개 라우터 + 4개 서비스 |
| 상태 관리 | App.jsx 내 useState | Zustand 스토어 4개 (`stores/`) |
| UI 컴포포넌트 | App.jsx 내 인라인 (3,323줄) | `components/` 5개 분리 + App.jsx (2,775줄, ChatPanel/AgentRunnerPanel 연동) |
| LLM 호출 | 동기 OpenAI SDK | 비동기 `httpx.AsyncClient` |
| 테스트 | 없음 | 66개 테스트 (endpoints 18 + routers 26 + install 9 + scanner 10 + services 3) |
| 에러 핸들링 | 개별 라우터별 try/catch | `main.py` 글로벌 예외 핸들러 (HTTP/Value/FileNotFound/Generic) |
| CI | 없음 | `.github/workflows/ci.yml` 파이프라인 |
| `run.sh` | `src.server.app:app` | `src.server.main:app` |

### 작동하는 기능

| 기능 | 파일 | 상태 |
|------|------|------|
| 하네스 스캔 (스킬/메모리/MCP/훅/컨텍스트) | `src/scanner/hermes_scanner.py` | 완료 |
| Hermes 정합성 스캔 보강 (external skills/disabled/bundles/HTTP MCP/gateway hooks) | `src/scanner/hermes_scanner.py` | 완료 |
| 섹션별 대시보드 뷰 | `src/ui/src/App.jsx` | 완료 |
| Chat Molder (자연어 → 하네스 수정 제안) | `src/server/routers/mold.py` → `/api/mold` | 완료 |
| AI 제안 Apply (스킬 파일 저장) | `/api/save` + `handleApply` | 완료 |
| Hybrid Web Scraper (Firecrawl→Jina→TLS→Browser) | `src/server/scrapers/` | 완료 |
| 파일 읽기 API (`/api/read`) | `src/server/routers/files.py` | 완료 |
| 파일 편집 (실제 내용 로드) | `src/ui/src/App.jsx` → `handleEditClick` | 완료 |
| 자동 백업 (저장 전 `.bak.{timestamp}`) | `src/server/services/config.py` → `backup_file()` | 완료 |
| Rollback API (`/api/rollback`) | `src/server/routers/files.py` | 완료 |
| HARNESS_READONLY 모드 | `src/server/services/config.py` | 완료 |
| **Git 연동** (자동 커밋, 이력, 복원) | `src/server/routers/git.py` + `App.jsx` | 완료 |
| Git Init UI (헤더 버튼) | `App.jsx` → `handleGitInit` | 완료 |
| 변경 이력 패널 (History 버튼) | `App.jsx` → `showHistory` + `gitLog` | 완료 |
| 커밋별 파일 복원 (git rollback) | `/api/git/rollback` | 완료 |
| **Memory Map (통합 뷰)** | `App.jsx` + `hermes_scanner.py` | 완료 |
| **SOUL.md Editor (페르소나)** | `App.jsx` + `hermes_scanner.py` | 완료 |
| **Context Window Estimator (토큰)** | `App.jsx` + `hermes_scanner.py` | 완료 |
| **Cross-Agent Skill Converter** | `App.jsx` + `routers/convert.py` | 완료 |
| **SQLite Audit Log (changelog)** | `routers/audit.py` + `App.jsx` | 완료 |
| **LLM proxy 폴백 (OpenAI API)** | `services/llm.py` | 완료 |
| **범용 텍스트 파일 편집 (Universal Edit)** | `App.jsx` + `routers/files.py` | 완료 |
| **Chat Molder 대화형 UI & 마크다운 렌더러** | `components/MarkdownContent.jsx` | 완료 |
| **LLM 응답 파싱 강건성 및 히스토리 유지** | `routers/mold.py` (`parse_molder_json`) | 완료 |
| **다중 에이전트 워크스페이스 지원** | `/api/workspaces` + `App.jsx` | 완료 |
| **오프라인 코드 에디터 (PrismJS)** | `App.jsx` (`react-simple-code-editor`) | 완료 |
| **UI 에러 방어막 (ErrorBoundary)** | `components/EditorErrorBoundary.jsx` | 완료 |
| **비동기 LLM 호출** | `services/llm.py` → `call_llm_async()` | 완료 |
| **훅/MCP enable/disable 토글** | `routers/toggle.py` → `POST /api/toggle` | 완료 |
| **실시간 파일 감시 (SSE)** | `routers/watch.py` → `GET /api/watch/events` (watchdog + polling 폴백) | 완료 |
| **스킬 URL 설치** | `routers/install.py` → `POST /api/install/skill` (GitHub URL 정규화) | 완료 |
| **에러 핸들링 통일** | `main.py` 글로벌 예외 핸들러 (HTTP/Value/FileNotFound/Generic) | 완료 |
| **CI 파이프라인** | `.github/workflows/ci.yml` | 완료 |
| **ChatPanel + AgentRunnerPanel App.jsx 연동** | `stores/useChatStore`, `stores/useAgentRunnerStore` | 완료 |
| 샌드박스 모드 (`HERMES_HOME=~/.hermes/sandbox`) | `run.sh` | 지원됨 |

### 미구현 기능 (PRD 기준)

| 기능 | 우선순위 | 비고 |
|------|----------|------|
| diff 사이드바이사이드 미리보기 | 낮음 | 현재 diff 텍스트만 표시 |
| Claude 하네스 완전 지원 | 중간 | `~/.claude` 구조 부분 스캔, 완전한 편집 미지원 |

---

## 3. 수정된 버그 및 리팩토링 (2026-05-31 업데이트)

### [REFACTOR] 백엔드 모놀리스 분리
- **이전**: `app.py` 단일 파일 2,822줄에 모든 API 로직 포함
- **이후**: `main.py` (86줄) + 14개 라우터 (2,462줄) + 4개 서비스 모듈 (770줄)
- **호환성**: `app.py`는 `from .main import app` 리다이렉터로 유지 (uvicorn 호환)

### [REFACTOR] 프론트엔드 모듈화 + 컴포넌트 연동
- **이전**: `App.jsx` 3,323줄에 모든 상태/컴포넌트 인라인
- **이후**: 4개 Zustand 스토어 + 5개 컴포넌트 분리, App.jsx (2,775줄)
- **ChatPanel/AgentRunnerPanel**: 인라인 JSX를 컴포넌트로 교체, 중복 유틸리티 함수 제거
- **Zustand 스토어**: `useHarnessStore` (99줄), `useEditorStore` (126줄), `useChatStore` (154줄), `useAgentRunnerStore` (88줄)
- **컴포넌트**: `EditorErrorBoundary`, `MarkdownContent`, `MolderMessage`, `ChatPanel`, `AgentRunnerPanel`

### [FEATURE] 글로벌 에러 핸들링
- `main.py`에 4개 글로벌 예외 핸들러 추가: HTTPException, ValueError, FileNotFoundError, Generic Exception
- 개별 라우터의 try/catch 중복 제거

### 이전 수정 사항 (2026-05-25)

### [CRITICAL] Edit 버튼 클릭 시 HTTP 500 오류 (NameError)
- **수정**: `_get_allowed_roots()` 함수 복구 → `services/config.py`의 `get_allowed_roots()`로 이관

### [CRITICAL] Edit 뷰 화이트 스크린 (React Crash)
- **수정**: `react-simple-code-editor` + `prismjs` 교체, `EditorErrorBoundary` 추가 → `components/`로 분리

---

## 4. 아키텍처 결정 사항

### 모듈형 백엔드 (2026-05-31)
- **라우터**: 엔드포인트 정의 + HTTP 처리 (`src/server/routers/`, 14개 파일)
- **서비스**: 비즈니스 로직 + 공유 유틸리티 (`src/server/services/`, 4개 파일)
- **절대 임포트**: `sys.path`에 `src/`와 `src/server/`를 추가하므로 `from services.config import ...` 사용
- **교차 라우터 참조**: `mold.py`에서 `routers.scan`의 `build_response`, `_scan_items_for_workspace` 임포트

### FastAPI + React (Tauri 미사용 이유)
PRD는 Tauri v2(Rust + React)를 권장했으나, Hermes가 FastAPI+React로 구현했습니다.
**이유**: 로컬 MVP 프로토타입으로 FastAPI가 훨씬 빠른 이터레이션이 가능.

### LLM 비동기화
Chat Molder의 LLM 호출이 `httpx.AsyncClient`를 사용한 진정한 비동기로 전환.
`call_llm_async()`는 OpenAI SDK 대신 raw HTTP POST로 스레드 블로킹 없이 동작.

### LLM Proxy
Chat Molder는 로컬 LLM 프록시(`http://localhost:20128/v1`) → OpenAI API 키 폴백 지원.
`services/llm.py`의 `get_llm_client()`가 자동 감지.

### 실시간 파일 감시 (watchdog + SSE)
`routers/watch.py`가 `watchdog` 라이브러리로 `HERMES_HOME` 변경을 감지하고 SSE로 클라이언트에 푸시.
watchdog 미설치 시 폴링 폴백 동작.

### 에러 핸들링 통일
`main.py`의 글로벌 예외 핸들러가 모든 라우터의 에러를 일관된 JSON 포맷으로 응답.
개별 라우터는 비즈니스 로직에 집중하고 에러는 자연스럽게 전파.

---

## 5. 파일 구조

```
agent-harness-studio/
├── .github/
│   └── workflows/
│       └── ci.yml                     # CI 파이프라인 (lint + test)
├── src/
│   ├── scanner/
│   │   └── hermes_scanner.py          # 핵심: ~/.hermes 스캔 엔진 (1,053줄)
│   ├── server/
│   │   ├── main.py                    # FastAPI 진입점 (86줄, 글로벌 에러 핸들러 포함)
│   │   ├── app.py                     # 하위 호환 리다이렉터 (5줄)
│   │   ├── routers/                   # API 엔드포인트 (14개 파일, 2,462줄)
│   │   │   ├── scan.py                #   /api/scan, /api/workspaces (230줄)
│   │   │   ├── mold.py                #   /api/mold (604줄)
│   │   │   ├── pi.py                  #   /api/pi/* (330줄)
│   │   │   ├── git.py                 #   /api/git/* (218줄)
│   │   │   ├── convert.py             #   /api/convert/* (261줄)
│   │   │   ├── files.py               #   /api/read, /api/save, /api/rollback (115줄)
│   │   │   ├── actions.py             #   /api/actions/* (118줄)
│   │   │   ├── install.py             #   /api/install/skill (157줄) [NEW]
│   │   │   ├── watch.py               #   /api/watch/events SSE (164줄) [NEW]
│   │   │   ├── toggle.py              #   /api/toggle enable/disable (100줄) [NEW]
│   │   │   ├── sessions.py            #   /api/sessions/* (70줄)
│   │   │   ├── env.py                 #   /api/env (35줄)
│   │   │   ├── web.py                 #   /api/web/scrape (33줄)
│   │   │   └── audit.py               #   /api/audit/logs (27줄)
│   │   ├── services/                  # 비즈니스 로직 (4개 파일, 770줄)
│   │   │   ├── config.py              #   HERMES_HOME, readonly, 경로 검증, 백업 (132줄)
│   │   │   ├── git.py                 #   git 연동 유틸리티 (102줄)
│   │   │   ├── llm.py                 #   LLM 클라이언트 + 비동기 호출 (256줄)
│   │   │   └── pi.py                  #   Pi Agent 실행 유틸리티 (280줄)
│   │   ├── usage_tracker.py           # Claude/Codex 사용량 파서
│   │   ├── recommender.py             # Smart Diet 추천 엔진
│   │   └── scrapers/                  # Hybrid Web Scraper 파이프라인
│   │       ├── hybrid.py              # Firecrawl→Jina→TLS→Browser 오케스트레이터
│   │       ├── firecrawl_scraper.py
│   │       ├── jina_scraper.py
│   │       ├── tls_scraper.py
│   │       └── browser_scraper.py
│   └── ui/
│       └── src/
│           ├── App.jsx                # 메인 React 앱 (2,775줄, ChatPanel/AgentRunnerPanel 연동)
│           ├── App.css                # 스타일
│           ├── components/            # 추출된 UI 컴포넌트 (5개 파일)
│           │   ├── EditorErrorBoundary.jsx   #   에디터 에러 방어막 (28줄)
│           │   ├── MarkdownContent.jsx       #   마크다운 렌더러 (165줄)
│           │   ├── MolderMessage.jsx         #   채팅 메시지 버블 (67줄)
│           │   ├── ChatPanel.jsx             #   Chat Molder 패널 (415줄)
│           │   └── AgentRunnerPanel.jsx      #   Pi Agent 실행 패널 (250줄)
│           ├── stores/                # Zustand 상태 관리 (4개 파일)
│           │   ├── useHarnessStore.js        #   하네스 스캔 데이터 (99줄)
│           │   ├── useEditorStore.js         #   에디터 상태 + rollback/git (126줄)
│           │   ├── useChatStore.js           #   채팅 상태 + sendMoldWithPi (154줄)
│           │   └── useAgentRunnerStore.js    #   Pi Agent 상태 + preview/submit (88줄)
│           ├── ArchitectureGraph.jsx  # 아키텍처 다이어그램
│           └── ScrapingPipeline.jsx   # Web Context 스크래핑 결과 표시
├── tests/                             # 테스트 스위트 (66개 테스트)
│   ├── conftest.py                    # pytest 설정 + ASGI 클라이언트 fixture
│   ├── pytest.ini                     # asyncio_mode = auto
│   ├── api/
│   │   ├── test_endpoints.py          # API 엔드포인트 테스트 (18개)
│   │   └── test_routers.py            # 라우터 통합 테스트 (26개)
│   ├── test_scanner.py                # 스캐너 테스트 (10개)
│   ├── test_services.py               # 서비스 테스트 (3개)
│   └── test_install.py                # 스킬 설치 테스트 (9개)
├── docs/
│   ├── api.md                         # API 레퍼런스
│   ├── prd.md                         # 제품 요구사항
│   ├── 1pager.md                      # 1-pager 기획서
│   └── wireframe.md                   # UI/UX 와이어프레임
├── AGENTS.md                          # 이 문서 (에이전트 핸드오프)
├── ARCHITECTURE.md                    # 기술 아키텍처 상세
├── README.md                          # 프로젝트 개요 + 시작하기
├── requirements.txt                   # Python 의존성 (watchdog>=4.0.0, pytest>=8.0.0, pytest-asyncio>=0.24.0 추가)
└── run.sh                             # 백엔드 + 프론트엔드 동시 실행
```

---

## 6. 안전 레이어 구조

다음 레이어를 중첩해서 사용합니다:

```
레이어 1: HARNESS_READONLY=1
  → 모든 /api/save, /api/rollback, /api/git/*, /api/toggle, /api/install/* 403 반환
  → UI에서 Save 버튼 비활성화, "READ-ONLY" 배지 표시
  → 가장 강력한 보호. 브라우징 전용 모드.
  → services/config.py의 HARNESS_READONLY 상수로 제어

레이어 2: HERMES_HOME=~/.hermes/sandbox
  → 실데이터와 물리적으로 분리된 디렉토리 사용
  → 쓰기는 허용하지만 실데이터에는 영향 없음

레이어 3: 자동 백업 (save_item)
  → 저장 시 자동으로 {file}.bak.{timestamp} 생성
  → services/config.py의 backup_file() 함수
  → /api/rollback으로 복원 가능

레이어 4: Git 버전 관리 (권장 — 실데이터 수정 시)
  → ~/.hermes를 git repo로 초기화 (UI "Git 연동" 버튼 또는 /api/git/init)
  → 저장마다 자동 커밋 (커밋 메시지 직접 입력 가능)
  → services/git.py의 git_commit_file() 함수
  → History 패널에서 파일별 전체 이력 확인
  → 임의 커밋 시점으로 복원 (git checkout)
```

권장 운영 모드:
- 탐색 전용: `HARNESS_READONLY=1 HERMES_HOME=~/.hermes`
- 샌드박스 수정: `HERMES_HOME=~/.hermes/sandbox`
- **실데이터 수정 (권장)**: `git init ~/.hermes` 후 `HERMES_HOME=~/.hermes`

상세 가이드: [docs/git-safety.md](docs/git-safety.md)

---

## 7. 테스트

```bash
# 전체 테스트 실행 (66개)
source .venv/bin/activate
python -m pytest tests/ -v

# API 엔드포인트 테스트만 (18개)
python -m pytest tests/api/test_endpoints.py -v

# 라우터 통합 테스트만 (26개)
python -m pytest tests/api/test_routers.py -v

# 스킬 설치 테스트만 (9개)
python -m pytest tests/test_install.py -v

# 스캐너 테스트만 (10개)
python -m pytest tests/test_scanner.py -v

# 서비스 테스트만 (3개)
python -m pytest tests/test_services.py -v

# 프론트엔드 빌드 검증
cd src/ui && npx vite build

# 백엔드 단독 테스트 (서버 실행 중)
curl http://localhost:8766/api/scan | python3 -m json.tool
curl http://localhost:8766/api/env

# 스캐너 단독 실행
python src/scanner/hermes_scanner.py
```

테스트 커버리지:
- **엔드포인트 (18개)**: health, workspaces, env, scan (전체 + 섹션별 6개), audit, LLM provider, agent runners, readonly (save/rollback), 파일 읽기, git log, hermes reference
- **라우터 통합 (26개)**: toggle, watch, install, convert, files, git, mold, pi, scan, sessions, actions 등 전 라우터 커버
- **스캐너 (10개)**: 인스턴스 생성, scan_all, skills, MCP, hooks, memory, root_context, plugins, cron, mask_sensitive
- **서비스 (3개)**: allowed_roots, is_git_repo, is_not_git_repo
- **스킬 설치 (9개)**: GitHub URL 정규화, 설치 워크플로우, 에러 케이스

---

## 8. 다음 작업 추천 (우선순위순)

### P1 — 즉시 필요
1. **App.jsx 추가 리팩토링**: ChatPanel/AgentRunnerPanel 연동 완료, 나머지 인라인 JSX도 컴포넌트로 분리 (섹션별 패널, 설정 다이얼로그 등)

### P2 — 주요 기능
2. **diff 사이드바이사이드 미리보기**: 저장 전 변경사항을 좌우 스플릿 뷰로 시각화
3. **App.jsx 나머지 인라인 상태 → Zustand 마이그레이션**: gitLog, showHistory 등 아직 useState에 있는 상태를 useEditorStore로 이관

### P3 — 확장
4. **Claude 하네스 완전 지원**: `~/.claude` 구조 스캔 (`ClaudeScanner` 추가), 편집 기능 지원
5. **다중 에이전트 플랫폼 통합 관리**: Hermes + Claude + 기타 하네스를 단일 대시보드에서 관리

---

## 9. 알려진 제약사항

- **로컬 LLM 프록시 의존성**: Chat Molder는 로컬 LLM 프록시 또는 OpenAI API 키가 필요. 둘 다 없으면 500 에러.
- **단일 사용자 전제**: API 인증 없음. localhost 전용.
- **대용량 스킬 디렉토리**: 스킬 수 > 100이면 스캔 속도 저하 가능 (비동기 처리 미적용).
- **브라우저 스크래퍼**: playwright 브라우저 미설치 시 Phase 4 실패. `playwright install chromium` 필요.
- **watchdog 선택적 의존**: 실시간 감시는 `watchdog` 설치 시에만 동작. 미설치 시 폴링 폴백으로 대체 (성능 저하).
