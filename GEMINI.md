# Agent Harness Studio — Gemini Coding Guardrails

## 프로젝트 구조 (먼저 파악할 것)

```
src/
  server/
    main.py                ← FastAPI 진입점 (86줄, 14개 라우터 include, 글로벌 예외 핸들러)
    app.py                 ← 하위 호환 리다이렉터 (from .main import app)
    routers/               ← API 엔드포인트 (14개 파일)
      scan.py              ← /api/scan, /api/workspaces
      mold.py              ← /api/mold (Chat Molder)
      files.py             ← /api/read, /api/save, /api/rollback
      git.py               ← /api/git/*
      pi.py                ← /api/pi/*
      convert.py           ← /api/convert/*
      actions.py           ← /api/actions/*
      sessions.py          ← /api/sessions/*
      env.py               ← /api/env
      web.py               ← /api/web/scrape
      audit.py             ← /api/audit/logs
      toggle.py            ← /api/toggle (MCP/훅 enable/disable)
      watch.py             ← /api/watch/events (SSE 파일 감시)
      install.py           ← /api/install/skill (URL 스킬 설치)
    services/              ← 비즈니스 로직 (4개 파일)
      config.py            ← HERMES_HOME, readonly, 경로 검증, 백업
      git.py               ← git 연동 유틸리티
      llm.py               ← LLM 클라이언트 + 비동기 호출
      pi.py                ← Pi Agent 실행 유틸리티
  scanner/                 ← 하네스 스캐너 모음 (hermes_scanner.py 등)
  ui/src/
    App.jsx                ← React 메인 컴포넌트 (2,775줄)
    App.css                ← 스타일
    components/            ← 추출된 UI 컴포넌트 (5개)
    stores/                ← Zustand 상태 관리 (4개)
  server/scrapers/         ← 웹 스크래퍼
.github/
  workflows/
    ci.yml                 ← CI 파이프라인 (pytest + vite build)
tests/                     ← 테스트 스위트 (66개)
  api/
    test_endpoints.py      ← API 엔드포인트 테스트 (18개)
    test_routers.py        ← 라우터 통합 테스트 (26개)
  test_scanner.py          ← 스캐너 테스트 (10개)
  test_services.py         ← 서비스 테스트 (3개)
  test_install.py          ← 스킬 설치 테스트 (9개)
run.sh                     ← LaunchAgent 실행 스크립트
AGENTS.md                  ← 프로젝트 핸드오프 문서 (변경 전 읽을 것)
HANDOFF.md                 ← 세션 간 인계 문서 (변경 전 읽을 것)
```

## 수정 전 반드시 할 것

1. `AGENTS.md` 또는 `HANDOFF.md`를 읽어 현재 상태 파악
2. 수정할 파일 목록과 이유를 먼저 명시
3. 백엔드 수정 시 → `routers/`에서 해당 라우터 + `services/`에서 해당 서비스 확인
4. 프론트엔드(`App.jsx`) 수정 시 → state 의존성 및 `stores/`, `components/` 확인

## 보호 파일 — 명시 요청 없으면 절대 수정 금지

```
package.json
package-lock.json
src/ui/package.json
src/ui/package-lock.json
requirements.txt
.venv/
node_modules/
run.sh                   ← LaunchAgent 실행 스크립트, 수정 시 서비스 중단
~/Library/LaunchAgents/com.user.agent-harness-studio.plist
```

## 검증 명령 (완료 선언 전 실행)

```bash
# 백엔드 문법 검사 (모든 라우터 + 서비스)
source .venv/bin/activate
python -m py_compile src/server/main.py
python -m py_compile src/server/routers/scan.py
python -m py_compile src/server/routers/mold.py

# 프론트엔드 빌드
cd src/ui && npm run build

# 테스트 실행 (66개)
cd ~/agent-harness-studio && source .venv/bin/activate
python -m pytest tests/ -v

# 스캐너 동작 확인
python -m src.scanner.hermes_scanner | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), 'items')"

# API 헬스 체크 (서비스 실행 중일 때)
curl -sf http://localhost:8766/api/scan | python3 -c "import json,sys; print(json.load(sys.stdin)['summary'])"
```

## 완료 보고 형식

```
변경 파일:
  - src/server/routers/{name}.py  → [무엇을 왜]
  - src/server/services/{name}.py → [무엇을 왜]
  - src/ui/src/App.jsx            → [무엇을 왜]
보호 파일 변경: 없음
검증: python -m py_compile ✅ / npm run build ✅ / pytest ✅
```

## 루프 방지

- 같은 파일을 3회 이상 수정 중이면 → 멈추고 근본 원인 보고
- 백엔드·프론트엔드·스캐너 세 영역을 동시에 건드리고 있으면 → 범위 재확인
- `routers/`에서 import 오류 발생 시 → `py_compile`로 먼저 진단
- `services/` 변경 시 → 해당 서비스를 임포트하는 모든 라우터 확인
