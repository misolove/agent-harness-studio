# Agent Harness Studio — Gemini Coding Guardrails

## 프로젝트 구조 (먼저 파악할 것)

```
src/
  server/app.py          ← FastAPI 백엔드 (포트 8766) — 핵심 파일
  scanner/               ← 하네스 스캐너 모음 (hermes_scanner.py 등)
  ui/src/App.jsx         ← React 메인 컴포넌트 — 핵심 파일
  ui/src/App.css         ← 스타일
  scrapers/              ← 웹 스크래퍼
run.sh                   ← LaunchAgent 실행 스크립트
AGENTS.md                ← 프로젝트 핸드오프 문서 (변경 전 읽을 것)
HANDOFF.md               ← 세션 간 인계 문서 (변경 전 읽을 것)
```

## 수정 전 반드시 할 것

1. `AGENTS.md` 또는 `HANDOFF.md`를 읽어 현재 상태 파악
2. 수정할 파일 목록과 이유를 먼저 명시
3. 백엔드(`app.py`) 수정 시 → 영향받는 프론트엔드 엔드포인트 호출 확인
4. 프론트엔드(`App.jsx`) 수정 시 → state 의존성 확인

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
# 백엔드 문법 검사
source .venv/bin/activate && python -m py_compile src/server/app.py

# 프론트엔드 빌드
cd src/ui && npm run build

# 스캐너 동작 확인
python -m src.scanner.hermes_scanner | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d), 'items')"

# API 헬스 체크 (서비스 실행 중일 때)
curl -sf http://localhost:8766/api/scan | python3 -c "import json,sys; print(json.load(sys.stdin)['summary'])"
```

## 완료 보고 형식

```
변경 파일:
  - src/server/app.py     → [무엇을 왜]
  - src/ui/src/App.jsx    → [무엇을 왜]
보호 파일 변경: 없음
검증: python -m py_compile ✅ / npm run build ✅
```

## 루프 방지

- 같은 파일을 3회 이상 수정 중이면 → 멈추고 근본 원인 보고
- 백엔드·프론트엔드·스캐너 세 영역을 동시에 건드리고 있으면 → 범위 재확인
- `app.py`에서 import 오류 발생 시 → `py_compile`로 먼저 진단
