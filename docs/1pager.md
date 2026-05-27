# [26.05.24] Agent Harness Studio (Personal Project)

## 1. 프로젝트 한 줄 요약

AI 에이전트의 하네스(메모리·스킬·훅·MCP·루트 컨텍스트)를 웹 대시보드에서 한눈에 보고, LLM 채팅창에서 자연어로 수정하면 즉시 반영되는 오픈소스 하네스 컨트롤 타워.

## 2. 대상

| 대상 | 상황/특징 |
|------|-----------|
| AI 에이전트 파워 유저 | Claude Code, Hermes, Cursor, Codex, OpenClaw, Gemini/Antigravity 등을 매일 쓰지만 하네스 설정이 분산되어 관리 피로가 큼 |
| 개발자/인프라 엔지니어 | 에이전트 인프라를 구축하며, 팀원 전체가 일관된 Harness를 유지보수해야 함 |
| 비개발자 (PM/기획자) | 코딩 없이 "말로" 자신의 업무용 에이전트 성격과 기능을 조정하고 싶음 |
| 오픈소스 커뮤니티 | 자신의 Harness 구성(스킬 셋, 프롬프트, 훅)을 공유하고, 다른 사람의 구성을 가져와 쓰고 싶음 |

## 3. 문제 정의

### 고객 문제

- **하네스가 분산되어 있다.** 스킬은 `~/.hermes/skills/`, 메모리는 `config.yaml` + Mem0 + Memory Manifest, 훅은 `hooks/`, MCP는 `mcp_servers:` 섹션, 루트 컨텍스트는 `AGENTS.md`에 흩어져 있어 전체 상태를 한눈에 파악할 수 없다.
- **수정하려면 파일을 직접 찾아가야 한다.** 특정 스킬의 트리거를 바꾸려면 `SKILL.md`를 열어 frontmatter를 YAML로 수정해야 하고, MCP 서버를 추가하려면 `config.yaml`을 수동 편집해야 한다.
- **어떤 메모리가 심어져 있는지 모른다.** Memory Manifest, Mem0, Built-in Memory, User Profile이 각각 다른 형태로 존재하여 "이 에이전트가 지금 뭘 알고 있는지"를 직관적으로 보거나 검색하기 어렵다.
- **변경 결과를 바로 확인할 수 없다.** 스킬을 수정하고 저장해도 세션을 새로 시작해야 반영되는 경우가 많고, 에이전트가 실제로 그 변경을 어떻게 해석하는지 즉각 피드백이 없다.
- **좋은 구성을 공유하거나 가져오기 어렵다.** 내가 튜닝한 프롬프트/스킬/훅 셋을 팀원이나 커뮤니티에 배포하는 과정이 번거롭다.

### 비즈니스 문제

- **에이전트 도입의 병목은 "하네스 튜닝"이다.** 모델 성능은 이미 충분히 좋지만, 각 팀/개인의 워크플로우에 맞게 에이전트를 세팅하는 비용이 높아 도입이 지연된다.
- **Anthropic 공식 블로그에서도 강조:** "The harness matters as much as the model." 그런데 하네스를 관리하는 통합 도구는 아직 없다.
- **팀 단위로 하네스를 표준화하기 어렵다.** 한 사람이 튜닝한 스킬/훅을 다른 팀원이 복제하는 게 수동이고, 버전이 갈라진다.

### 데이터 기반 현황

| 항목 | 수치/상태 | 비고 |
|------|-----------|------|
| 하네스 설정 파일 위치 | 최소 5개 경로 분산 | AGENTS.md, config.yaml, skills/, .env, mcp_servers |
| 에이전트 종류 | Claude Code, Hermes, Cursor, Codex, OpenClaw, Gemini/Antigravity 등 7+ | 각각 하네스 포맷이 다름 |
| 설정 변경 → 반영까지 | 세션 재시작 필요 (30초~수분) | 즉각 피드백 불가 |
| Anthropic 블로그 발표 | 2026.05.14 "Harness matters" 공식화 | 하네스 관리 도구의 필요성 업계 공감대 형성 중 |

### Root Cause

**Case 1: 파일 시스템이 유일한 인터페이스**
하네스 구성요소가 전부 파일(YAML, MD, JSON)로 존재하며, 이를 읽고 수정하는 유일한 방법이 텍스트 에디터이다. 구조적 시각화나 자연어 편집 인터페이스가 없다.

**Case 2: 에이전트별 포맷 파편화**
Claude Code는 `CLAUDE.md` + `~/.claude/skills/`, Hermes는 `AGENTS.md` + `~/.hermes/skills/`, Codex는 `AGENTS.md` + `.codex/agents/` 등 포맷이 다르지만, 개념적 구조는 같다. 이 공통 모델을 추상화하는 레이어가 없다.

**Case 3: 피드백 루프 단절**
설정을 바꾸고 → 에이전트를 실행하고 → 결과를 보고 → 다시 수정하는 사이클에 지연이 크다. "이 프롬프트가 에이전트에게 어떻게 해석되는지"를 라이브로 보는 수단이 없다.

## 4. 목표

| 항목 | 목표 수치 |
|------|-----------|
| 하네스 상태 가시성 | 5개 분산 파일 → 1개 대시보드 화면에서 100% 파악 |
| 설정 변경 방식 | 파일 직접 편집 → 자연어 채팅으로 90% 커버 |
| 변경 → 반영 시간 | 세션 재시작(30초~수분) → 실시간(3초 이내) |
| 에이전트 지원 | Hermes, Claude Code, Cursor, Codex, OpenClaw, Gemini/Antigravity, Studio 자체 1차 스캔 완료 |
| 오픈소스 커뮤니티 | 첫 달 GitHub Star 500+, Harness 템플릿 공유 마켓플레이스 |

## 4.1 현재 구현 현황 (2026-05-27)

MVP는 단순 Hermes inspector를 넘어 **local agent ops console** 성격으로 확장되었다.

완료된 축:
- **멀티 워크스페이스 스캔**: Hermes, Claude Code, Cursor, Codex, OpenClaw, Gemini CLI, Antigravity, Harness Studio 자체.
- **관측 표면 확장**: Skills, Skill Bundles/Subagents, MCP, Hooks, Memory, Cron, Plugins/Commands, Context, Config, Logs, Sessions, State DB, Checkpoints, Diff Audit.
- **안전 편집**: `/api/read`, `/api/save`, 자동 `.bak.*`, git init/log/diff/rollback, SQLite audit log, READONLY 모드.
- **Usage Telemetry A안**: Claude Code jsonl 세션 로그를 파싱해 Skill/Subagent invocation 집계.
- **Smart Diet**: 사용량 + 토큰 + 수정시각 기반 `HIGH_VALUE`, `STALE_UNUSED`, `ARCHIVE`, `HEAVY_UNUSED` 추천.
- **Skill Converter 1차**: Claude Code Skill 선택 → Hermes metadata로 변환 → `~/.hermes/skills/{name}/SKILL.md` 주입.
- **Agent Runner 1차**: 설치된 Pi Coding Agent CLI 감지, provider/model 표시, read-only run, 로그 tail, pre/post diff audit.
- **Chat Molder 고도화**: LLM mode와 Pi Agent mode를 모두 지원하고, Pi mode는 `read,grep,find,ls,web_search`로 세션 연속 대화 가능.

최근 검증값:
- Claude Code Smart 추천: 263개 (`HIGH_VALUE:1`, `STALE_UNUSED:72`, `ARCHIVE:190`)
- Cursor 등 미지원 telemetry workspace: unsupported + 빈 추천 리스트로 graceful degrade
- Skill Converter dry-run: `agency-client-interview` → `~/.hermes/skills/agency-client-interview/SKILL.md`
- `python3 -m py_compile src/server/app.py`
- `cd src/ui && npm run build`

## 5. 현황 및 분석

- **Anthropic 공식 블로그 (2026.05.14)**: 하네스 5계층(CLAUDE.md, Hooks, Skills, Plugins, MCP) 구조를 공식화. "모델보다 하네스가 중요하다"고 선언.
- **OpenAI Codex Subagents (2026.05)**: TOML 기반 커스텀 에이전트 정의, path-scoped skills 등 하네스 고도화 추세.
- **Karpathy LLM Wiki (2026.04)**: SCHEMA.md + index.md + log.md로 지식 베이스를 구조화하는 패턴 제안. 하네스의 "지식 레이어"에 해당.
- **Hermes Agent**: 이미 Skills, Memory, MCP, Hooks를 갖춘 가장 완성도 높은 오픈소스 에이전트 중 하나. 하지만 관리 UI가 없음.
- **경쟁 도구**: Cursor, Windsurf 등은 설정 UI가 있지만, 자연어 편집이나 하네스 전체 시각화에 집중하지 않음.

## 6. 해결방안

### Phase 1: Harness Inspector (시각화)

- 웹 대시보드에서 에이전트의 현재 하네스 전체를 시각화
- 6개 패널: Memory | Skills | Hooks | MCP Servers | Root Context | Agent Config
- 각 패널에서 항목 클릭 → 상세 뷰 (파일 원문 + LLM 해석)
- 실시간 동기화: 파일 시스템 watch → 변경 감지 → 자동 갱신

### Phase 2: Chat-based Molding (자연어 편집)

- 대시보드 내장 챗봇에 "메모리에 '나는 한국어를 선호한다' 추가해줘"라고 말하면 즉시 반영
- "스킬 X의 트리거를 '보안 리뷰'로 바꿔줘" → SKILL.md frontmatter 자동 수정
- "MCP 서버로 QMD 추가해줘" → config.yaml 자동 업데이트 + 연결 테스트
- 변경 전후 diff를 챗봇이 설명하고, "적용할까요?" 컨펌 후 반영 (안전장치)

### Phase 3: Cross-Agent Abstraction (멀티 에이전트)

- Hermes ↔ Claude Code ↔ Codex 간 하네스 포맷 변환 레이어
- 공통 하네스 모델(Common Harness Model) 정의
- "Hermes용으로 튜닝한 이 스킬 셋을 Claude Code용으로 변환해줘"

### Phase 4: Community Marketplace

- 자신의 하네스 구성(프리셋)을 공개/비공개로 공유
- 다른 사용자의 프리셋을 1클릭 임포트
- 커뮤니티 평점 + 사용 통계

## 7. 리스크

| 영향도 | 리스크 | 대응 방안 |
|--------|--------|-----------|
| 상 | 에이전트별 포맷 파편화 → 추상화 레이어 복잡도 폭발 | 2026-05-27 현재 BaseScanner + workspace별 scanner로 1차 정규화 완료. 다음은 섹션별 공통 capability contract를 문서화 |
| 상 | 자연어 편집이 YAML/MD 문법을 정확히 수정하지 못함 | LLM 기반 파싱 + 적용 전 diff 컨펌 + 롤백 체크포인트 |
| 중 | 파일 watch 동기화 지연/누락 | 파일시스템 이벤트 + 주기적 폴링 하이브리드 |
| 중 | 보안: .env(API 키) 노출 위험 | 대시보드에서 API 키는 마스킹 표시, 채팅으로는 키 값 직접 수정 불가 |
| 하 | 오픈소스 커뮤니티 초기 활성화 어려움 | Hermes 커뮤니티 + 긱뉴스 + r/LocalLLaMA 등 타겟 홍보 |

## 8. 중요도 및 긴급도

- **중요도: 상** — "Harness over Model"이 업계 트렌드로 확정되는 시점에, 하네스 관리 도구는 핵심 인프라가 됨.
- **긴급도: 중** — 경쟁 도구(Cursor, Windsurf 등)가 설정 UI를 강화하고 있어 6개월 내 선점이 유리함.
