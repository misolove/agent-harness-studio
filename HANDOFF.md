# Agent Harness Studio — Handoff Document

> 다음 에이전트가 이어받을 수 있도록 작성된 핸드오프 문서.
> **작업할 때마다 업데이트할 것.**
> Last updated: 2026-05-25

---

## 1. 프로젝트 개요

**Agent Harness Studio** — `~/.hermes` Hermes agent harness를 시각화·편집하는 로컬 웹 대시보드.

| 컴포넌트 | 기술 | 포트 |
|---------|------|------|
| Backend | FastAPI (Python) + uvicorn | 8766 |
| Frontend | React + Vite | 5173 |
| 데이터 소스 | `~/.hermes/` (HERMES_HOME) | — |

**실행 방법:**
```bash
cd /Users/letitbe/letitbe/agent-harness-studio
source .venv/bin/activate
# LaunchAgent로 자동 실행됨 (com.letitbe.agent-harness-studio)
# 수동 실행: ./run.sh
```

**주요 파일:**
- `src/scanner/hermes_scanner.py` — `~/.hermes` 스캔 로직
- `src/server/app.py` — FastAPI 엔드포인트
- `src/ui/src/App.jsx` — React 메인 컴포넌트
- `src/ui/src/App.css` — 스타일
- `~/Library/LaunchAgents/com.letitbe.agent-harness-studio.plist` — macOS LaunchAgent

---

## 2. 현재 스캐너 지원 섹션

| 섹션 ID | Type 문자열 | 소스 |
|---------|------------|------|
| `skills` | `Skill` | `~/.hermes/skills/**/SKILL.md` + `skills.external_dirs` |
| `bundles` | `Skill Bundle` | `~/.hermes/skill-bundles/*.yaml` |
| `memory` | `Memory Config`, `Memory Manifest`, `Memory Directory`, `Memory State` | config.yaml, memory_manifest.md, memories/, state/ |
| `mcp` | `MCP Server` | config.yaml `mcp_servers` (stdio + HTTP, enabled/tools/auth metadata) |
| `context` | `Root Context` | AGENTS.md, config.yaml system_prompt |
| `hooks` | `Hook` | config.yaml shell hooks + `hooks/<name>/HOOK.yaml` gateway hooks + legacy hook files |
| `cron` | `Cron Job` | `cron/jobs.json` |
| `plugins` | `Plugin` | `plugins/*/plugin.yaml` |
| `config` | (cross-section) | Memory Config + Root Context + MCP Server 합산 |
| `web` | — | 플레이스홀더 (미구현) |

---

## 3. 완료된 작업 (이번 세션)

### 3.1 버그 수정
- [x] **LaunchAgent HERMES_HOME 오류**: sandbox → `/Users/letitbe/.hermes` 수정, ThrottleInterval=10 추가
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

### 3.3 Hermes 정합성 보강 (2026-05-25)
- [x] **MCP HTTP 서버 정상 처리**: `url` 기반 MCP는 `command` 없이도 ACTIVE, `enabled:false`는 INACTIVE
- [x] **MCP metadata 확장**: `tools.include/exclude`, `headers`, `auth`, `sampling`, timeout 계열 마스킹/표시
- [x] **Gateway Hook 구조 지원**: `hooks/<name>/HOOK.yaml + handler.py` 파싱
- [x] **Skill external_dirs/disabled 반영**: `skills.external_dirs`, `skills.disabled`, `skills.platform_disabled` 스캔
- [x] **Skill Bundle 섹션 추가**: `skill-bundles/*.yaml` 파싱 및 UI 카드 표시
- [x] **Plugin hooks 필드 보강**: `provides_hooks`와 `hooks` 둘 다 카운트
- [x] **Chat Molder Hermes 기준 문맥 주입**: 모든 LLM 호출에 `nousresearch/hermes-agent` reference, canonical harness surfaces, 현재 스캔 스냅샷을 system/user context로 전달

---

## 4. 알려진 미구현 사항 (다음 작업 후보)

### 4.1 스캐너 갭
- [ ] **Sessions 요약** — `sessions/sessions.json` (958개 JSONL 세션 파일 존재, 집계 정보만 표시하면 됨)
- [ ] **Checkpoints** — `checkpoints/store/` (Git-like 내부 저장소, 표시 방법 검토 필요)
- [ ] **State DB** — `state.db` SQLite (kanban.db, state.db 등 SQLite 파일들)
- [ ] **SOUL.md** — `~/.hermes/SOUL.md` Root Context에 포함되어야 할 수 있음

### 4.2 UI/UX 개선
- [ ] **Cron Job 상세 보기** — next_run_at, last_error 등 메타데이터 표시
- [ ] **Plugin 상세 보기** — provides_tools 목록 펼쳐보기
- [ ] **MCP ERROR 서버 강조** — ERROR 상태 서버 상단 정렬 또는 빨간 배지
- [ ] **검색/필터** — 섹션 내 아이템 검색
- [ ] **Skills count 192개** — 너무 많아 페이지네이션 필요할 수 있음

### 4.3 Web Context 섹션
- `web` 섹션은 현재 URL scraping placeholder만 있음 (실제 저장/활용 미구현)

---

## 5. 아키텍처 핵심 사항

### HermesScanner 구조
```python
HermesScanner(hermes_dir="~/.hermes")
├── _scan_skills()        → local/external SKILL.md YAML frontmatter + disabled 상태
├── _scan_skill_bundles() → skill-bundles/*.yaml
├── _scan_memory()        → config memory + manifest + memories/ + state/
├── _scan_mcp()           → config.yaml mcp_servers, stdio/HTTP, enabled/tools/auth metadata
├── _scan_root_context()  → AGENTS.md + config system_prompt
├── _scan_hooks()         → shell hooks + gateway HOOK.yaml + legacy hook files
├── _scan_cron()          → cron/jobs.json
└── _scan_plugins()       → plugins/*/plugin.yaml
```

### API 엔드포인트
```
GET  /api/scan              → 전체 스캔 결과 + summary
GET  /api/scan/{section}    → 섹션별 필터링
GET  /api/read?path=...     → 파일 내용 읽기
POST /api/save              → 파일 저장 (+ git commit)
POST /api/rollback          → 백업 복원
POST /api/mold              → Chat Molder (AI 제안)
GET  /api/reference/hermes  → Molder에 주입되는 Hermes reference context
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
  "config": ["Memory Config", "Root Context", "MCP Server"],
}
```

---

## 6. 테스트 방법

```bash
# 스캐너 직접 실행
cd /Users/letitbe/letitbe/agent-harness-studio
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

- Python venv: `/Users/letitbe/letitbe/agent-harness-studio/.venv`
- Node modules: `/Users/letitbe/letitbe/agent-harness-studio/src/ui/node_modules`
- LaunchAgent logs: `~/Library/Logs/agent-harness-studio/stdout.log`
- HERMES_HOME: `/Users/letitbe/.hermes`
- Git repo: `~/.hermes` (모든 변경이 커밋으로 기록됨)
