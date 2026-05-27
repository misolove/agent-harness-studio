# [PRD] Agent Harness Studio

> 작성일: 2026.05.24  
> 작성자: Lerippi + Hermes  
> 문서 상태: Draft  
> 문서 버전: v0.1

> 구현 현황 업데이트(2026-05-27): 초기 PRD는 Hermes 단일 MVP를 출발점으로 작성되었지만, 현재 앱은 Hermes/Claude Code/Cursor/Codex/OpenClaw/Gemini/Antigravity/Studio 자체까지 스캔한다. 또한 Logs, Sessions, State DB, Checkpoints, Usage Telemetry A안, Smart Diet, Claude→Hermes Skill Converter, Pi Coding Agent 기반 Agent Runner/Chat Molder Pi mode가 1차 구현되었다. 상세 API는 `docs/api.md`, 제품성/컨버터 평가는 `docs/product-assessment-and-skill-converter.md`, Pi adapter는 `docs/agent-runner-pi.md`를 기준으로 본다.

---

# 0. 문서 개요

## 0-1. 프로젝트 요약

Agent Harness Studio는 Hermes, Claude Code, Cursor, Codex, OpenClaw, Gemini/Antigravity 같은 AI 에이전트의 하네스 구성요소를 웹 대시보드에서 시각화하고, LLM/Pi Agent 채팅창을 통해 자연어로 조사·수정하면 실제 설정 파일과 런타임에 즉시 반영되도록 하는 오픈소스 하네스 컨트롤 타워다.

여기서 하네스는 다음을 포함한다.

- Memory: 사용자 프로필, 장기 기억, 프로젝트별 기억, manifest pointer
- Skills: SKILL.md, frontmatter, trigger, linked files, scripts/templates
- Hooks: pre/post tool hook, session hook, quality gate, notification hook
- MCP: mcp server 목록, transport, auth, tool schema, 연결 상태
- Root Context: AGENTS.md, CLAUDE.md, system/developer prompt, project rules
- Agents/Subagents: agent profile, role, model, tool permissions, routing rule
- Config: model provider, fallback, gateway, environment variables, safety policy

핵심 가치는 “Harness over Model” 철학을 제품화하는 것이다. 모델을 바꾸기보다 에이전트의 작업 환경, 기억, 도구, 규칙, 검증 루프를 조정하는 것이 실제 성능을 더 크게 바꾼다는 전제에서 출발한다.

## 0-2. 배경

### 현재 상황

AI 에이전트 운영자는 이미 다양한 설정 파일과 디렉터리를 다룬다.

- Hermes: `~/.hermes/config.yaml`, `~/.hermes/skills/`, memory store, MCP servers, AGENTS.md
- Claude Code: `CLAUDE.md`, `~/.claude/skills/`, hooks, plugins
- Codex: `AGENTS.md`, `.codex/agents/*.toml`, subagent profiles
- Cursor / OpenClaw / Gemini / Antigravity / 기타 에이전트: 각자 다른 config, memory, tool registry

하지만 개념적으로는 모두 비슷한 하네스 구조를 가진다. 문제는 이를 한눈에 보고, 안전하게 수정하고, 변경 결과를 즉시 확인하는 도구가 부족하다는 점이다.

### 문제 정의

1. 하네스 구성요소가 파일 시스템과 여러 DB에 분산되어 있다.
2. 사용자는 어떤 memory/skill/hook/MCP가 현재 활성인지 직관적으로 알기 어렵다.
3. 수정하려면 YAML/Markdown/TOML을 직접 편집해야 한다.
4. 변경 후 에이전트가 실제로 어떻게 해석하는지 확인하는 피드백 루프가 느리다.
5. 좋은 하네스 구성을 팀/커뮤니티에 재사용 가능한 단위로 공유하기 어렵다.

### 사용자 Voice

> “내가 하고 싶은 것은 Hermes와 같은 에이전트들의 하네스(메모리, 스킬, 훅, MCP 등)를 한눈에 일목요연하게 보고 이를 직관적으로 수정하면 LLM 채팅창에서 바로 반영될 수 있게 해주는 거야.”

---

# 1. 목표

## 1-1. 프로젝트 목표

### 사용자 가치

- 에이전트가 현재 어떤 기억, 규칙, 도구, 스킬을 가지고 있는지 한 화면에서 이해한다.
- 파일을 직접 열지 않고 자연어로 하네스를 수정한다.
- 변경 전/후 diff와 예상 영향도를 보고 안전하게 적용한다.
- 자신의 하네스 구성을 재사용 가능한 preset으로 export/import한다.

### 제품 가치

- AI 에이전트 파워 유저를 위한 “운영 콘솔” 카테고리를 선점한다.
- Hermes 우선 MVP에서 출발하되, 현재는 Claude Code/Cursor/Codex/OpenClaw/Gemini/Antigravity까지 확장된 멀티 워크스페이스 콘솔로 발전시킨다.
- BaseScanner 기반 Common Harness Model을 점진적으로 정의한다.

### 운영 가치

- 하네스 변경 이력을 audit log로 남긴다.
- 위험한 변경은 checkpoint/rollback 가능하게 한다.
- MCP 연결 상태, skill parse 오류, memory 충돌을 자동 진단한다.

## 1-2. 성공 기준

### 정량 목표

- MVP 기준 지원 하네스 영역: Memory, Skills, MCP, Root Context, Config 최소 5개
- 설정 변경 커버리지: Hermes 주요 설정의 70% 이상 자연어 수정 가능
- 변경 반영 시간: 3초 이내 UI 갱신, 10초 이내 validation 결과 표시
- 첫 공개 후 30일: GitHub Star 500+, 외부 issue/PR 20건 이상
- 사용성: 신규 파워 유저가 10분 이내 자신의 Hermes 상태를 이해하고 첫 변경 완료

### 정성 목표

- “에이전트가 뭘 알고 있고 뭘 할 수 있는지”가 투명해진다.
- 하네스 수정이 두려운 파일 편집이 아니라 대화형 조형 작업이 된다.
- 하네스 구성이 개인 자산이자 오픈소스 공유 단위가 된다.

---

# 2. KPI 및 측정지표

## 2-1. 핵심 KPI

- Activation: 첫 실행 후 10분 내 successful harness scan 완료율
- First Edit Success: 첫 자연어 변경 요청이 validation 통과 후 적용되는 비율
- Inspection Depth: 사용자당 조회한 하네스 패널 수
- Change Safety: rollback 없이 성공 적용된 변경 비율
- Community Adoption: GitHub star, fork, preset 공유 수, 외부 PR 수

## 2-2. 보조 지표

- Scan latency: 전체 하네스 스캔 시간
- Validation latency: 변경 diff 생성 후 검증 완료 시간
- Error recovery rate: validation 실패 후 자동 수정 제안 성공률
- Imported preset count: 외부 하네스 프리셋 import 횟수
- Repeat usage: 7일 내 재방문/재실행 비율

## 2-3. 모니터링 지표

- 파일 parse 실패 수
- YAML/Markdown/TOML validation 실패 수
- MCP 연결 실패 수
- 권한 오류 수
- 위험 변경 차단 수
- rollback 실행 수
- LLM edit proposal reject rate

---

# 3. 사용자 및 이해관계자

## 3-1. 대상 사용자

### Primary: Agent Power User / Developer

- Hermes, Claude Code, Cursor, Codex, OpenClaw, Gemini/Antigravity 등을 매일 사용한다.
- 여러 에이전트 설정을 직접 수정해본 경험이 있다.
- 메모리/스킬/훅/MCP를 튜닝해 생산성을 높이고 싶다.

### Secondary: AI Workflow Builder / PM

- 코딩 전문가는 아니지만 업무용 에이전트를 직접 조정하고 싶다.
- 설정 파일보다 채팅 기반 UX를 선호한다.
- 팀/조직 단위로 에이전트 하네스를 표준화하고 싶다.

### Community User

- 공개 레포에서 하네스 템플릿을 가져와 자신의 환경에 적용하고 싶다.
- 좋은 스킬, hook, MCP bundle을 공유하고 싶다.

## 3-2. 이해관계자

- Product Owner: 레리삐
- Core Maintainer: 초기 Hermes 기반 구현자
- OSS Contributor: agent adapter, UI, MCP connector 기여자
- End User: 로컬 AI 에이전트 사용자
- Security Reviewer: 로컬 파일/secret 접근 정책 검토자

---

# 4. 정책 정의

## 4-1. 기본 정책

### Local-first 정책

- 기본 동작은 로컬 머신의 에이전트 설정을 읽고 수정한다.
- 클라우드 동기화는 MVP 범위 밖이다.
- 오픈소스 공개 시에도 사용자의 secret/config 원문이 외부로 전송되지 않는 구조를 우선한다.

### Human-in-the-loop 정책

- 위험 변경은 반드시 diff preview와 사용자 승인 후 적용한다.
- `모두 원해` 같은 명시적 auto mode는 batch 작업에 한해 적용하되, secret 노출/삭제/권한 변경은 예외적으로 승인 필요 상태로 둔다.

### Secret 보호 정책

- API key, token, password, private key는 UI에서 마스킹한다.
- LLM context로 secret 원문을 전달하지 않는다.
- secret 변경은 “값 존재 여부/유효성/마스킹된 prefix”만 표시한다.

### Rollback 정책

- 모든 write 작업 전 snapshot을 생성한다.
- 변경 단위마다 patch id를 부여한다.
- 사용자는 최근 변경을 1-click rollback 할 수 있어야 한다.

## 4-2. 상태값 정의

### Harness Item State

- ACTIVE: 현재 로드 가능하고 유효함
- INACTIVE: 존재하지만 현재 비활성
- ERROR: parse/validation/connection 오류
- STALE: 파일은 있으나 최근 사용 흔적이 없거나 참조가 깨짐
- SECRET_MASKED: 값이 존재하지만 보안상 표시 제한
- EXTERNAL: 외부 MCP/DB 등 로컬 파일 밖 리소스

### Change Proposal State

- DRAFT: LLM이 변경안을 생성했으나 적용 전
- VALIDATING: 문법/스키마/연결 검증 중
- READY: 적용 가능
- BLOCKED: 위험 또는 오류로 차단
- APPLIED: 적용 완료
- ROLLED_BACK: 롤백 완료

## 4-3. 예외 정책

- 파일 권한 없음: read-only 모드로 전환하고 해결 방법 표시
- parse 실패: 원문 파일, 오류 위치, 자동 수정 제안 표시
- MCP 연결 실패: command/env/transport 단위 진단
- memory 충돌: 중복/상충 memory 후보를 보여주고 merge/delete/keep 선택 제공
- LLM 변경안 불확실: confidence 낮으면 자동 적용 금지

---

# 5. 서비스 구조

## 5-1. 서비스 흐름

```text
앱 실행
 → 로컬 에이전트 프로필 탐지
 → 하네스 스캔
 → 대시보드 시각화
 → 사용자가 패널 탐색 또는 채팅 요청
 → LLM이 변경 proposal 생성
 → diff + 영향도 + validation 표시
 → 사용자 승인
 → 파일/DB/MCP 설정 반영
 → 재스캔 및 런타임 반영 확인
 → audit log 기록
```

## 5-2. 핵심 화면

- Dashboard: 전체 하네스 상태 요약
- Memory Panel: 메모리 저장소, pointer, 충돌/중복 진단
- Skills Panel: skill 목록, trigger, frontmatter, linked files, 활성 조건
- MCP Panel: MCP server 목록, 연결 상태, tool schema
- Hooks Panel: hook 목록, 실행 타이밍, 최근 실행 로그
- Root Context Panel: AGENTS.md/CLAUDE.md/프로젝트 규칙
- Chat Molder: 자연어 변경 인터페이스
- Diff & Review: 변경안, 영향도, validation, 승인/거절
- Audit Log: 변경 이력, rollback

## 5-3. MVP 범위

### In Scope

- Hermes 단일 프로필 우선 지원 (완료 후 멀티 워크스페이스로 확장됨)
- 로컬 `~/.hermes` 경로 스캔 및 `~/.claude`, `~/.cursor`, `~/.codex`, `~/.openclaw`, `~/.gemini`, Studio repo 스캔
- skills 읽기/검색/수정
- 대량 skill/log/session 목록의 검색/정렬
- built-in memory/user profile 읽기 및 추가/삭제 proposal
- config.yaml 일부 섹션 읽기/수정
- MCP server 목록 및 연결 상태 표시
- AGENTS.md/root context 읽기와 section-level 수정 proposal
- 자연어 변경 → patch proposal → validation → apply, 또는 Pi Agent read-only 조사
- Usage Telemetry 기반 Smart Diet 추천
- Claude Code Skill → Hermes Skill 변환/주입
- snapshot/rollback

### Out of Scope

- 클라우드 계정/팀 SaaS
- 모든 에이전트 포맷 완전 지원
- secret 원문 편집
- 자동 대규모 refactor
- 원격 서버의 config 직접 수정
- 완전 자동 self-modifying agent

---

# 6. 상세 요구사항

## 6-1. 기능 요구사항

### FR-001. Harness Scan

- 사용자의 로컬 환경에서 Hermes/Claude/Cursor/Codex/OpenClaw/Gemini/Antigravity config, skills, memory, MCP, root context를 탐지한다.
- 각 항목은 source path, type, state, summary, last modified를 가진다.
- parse 오류가 있으면 오류 위치와 원문 snippet을 저장한다.

### FR-002. Dashboard Overview

- 전체 하네스 건강도를 표시한다.
- 영역별 active/error/stale 개수를 카드로 보여준다.
- critical issue를 상단에 노출한다.

### FR-003. Memory Inspector

- built-in memory, user profile, manifest pointer, Mem0/AgentMemory 연결 후보를 구분 표시한다.
- 중복/상충 memory를 자동 탐지한다.
- memory 추가/수정/삭제 proposal을 생성할 수 있다.

### FR-004. Skills Inspector

- 모든 skill의 name, description, category, trigger, linked files를 표시한다.
- SKILL.md frontmatter validation을 수행한다.
- 자연어로 trigger/description/body를 수정할 수 있다.
- linked file 추가/수정/삭제 proposal을 지원한다.

### FR-005. MCP Inspector

- MCP server 목록과 transport(stdio/http), command, env dependency, tool count를 표시한다.
- connection test를 실행한다.
- 실패 시 command not found, auth missing, timeout, schema error를 구분한다.

### FR-006. Root Context Inspector

- AGENTS.md, CLAUDE.md, project rules를 section 단위로 파싱한다.
- 중요한 hard rule, preference, project convention을 요약한다.
- 자연어 수정 시 관련 section만 patch proposal로 만든다.

### FR-007. Chat Molder

- 사용자는 “스킬 X 트리거를 보안 리뷰에도 반응하게 해줘”처럼 요청한다.
- 시스템은 target detection → change proposal → diff → validation 순으로 처리한다.
- 사용자가 승인하면 적용한다.

### FR-008. Diff & Validation

- 모든 변경은 unified diff 또는 structured diff로 표시한다.
- validation은 최소 문법 검증, schema 검증, dry-run scan을 포함한다.
- 실패 시 자동 수정안 또는 수동 해결 가이드를 제공한다.

### FR-009. Snapshot & Rollback

- 변경 전 파일 snapshot을 저장한다.
- 변경 단위마다 patch id와 설명을 기록한다.
- 최근 변경은 UI에서 rollback 가능해야 한다.

### FR-010. Preset Export/Import

- 사용자는 선택한 memory/skills/hooks/MCP config를 preset으로 export할 수 있다.
- import 시 충돌 여부를 보여주고 merge 전략을 선택하게 한다.

## 6-2. 데이터 요구사항

### HarnessItem

- id
- type: memory | skill | hook | mcp | root_context | config | agent
- source_path
- display_name
- summary
- state
- raw_ref
- parsed_metadata
- last_modified
- diagnostics

### ChangeProposal

- id
- user_request
- target_items
- proposed_patch
- risk_level
- validation_result
- state
- created_at
- applied_at

### AuditEvent

- id
- actor: user | assistant | system
- action
- target
- before_snapshot_ref
- after_snapshot_ref
- diff_ref
- result
- timestamp

## 6-3. 운영 요구사항

- 로컬 앱 실행 로그 제공
- scan/debug export bundle 제공
- crash 발생 시 secret 제외 diagnostic bundle 생성
- OSS issue template에 diagnostic bundle 첨부 가이드 제공

---

# 7. UX/UI 고려사항

## UX 원칙

1. 전체 상태가 먼저 보이고, 세부 파일은 나중에 본다.
2. 자연어 편집은 항상 diff와 함께 제공한다.
3. 위험한 변경은 빠르게 하되 되돌리기 쉽게 한다.
4. secret은 존재만 알리고 노출하지 않는다.
5. 초보자에게는 “무엇을 바꾸면 어떤 효과가 나는지” 설명한다.
6. 파워 유저에게는 원문 파일과 patch를 즉시 제공한다.

## 주요 인터랙션

- 카드 클릭: 해당 하네스 영역 상세 열기
- 채팅 입력: 변경 요청 또는 질문
- Diff Review: Apply / Edit Proposal / Reject / Rollback
- Health badge: Active, Warning, Error, Stale
- Quick actions: Add Memory, Create Skill, Test MCP, Export Preset

## Empty/Error State

- Hermes 미설치: 설치/설정 가이드 표시
- skills 없음: starter skill 생성 CTA
- MCP 없음: recommended MCP bundle 제안
- parse error: 오류 위치와 자동 수정 CTA
- no permission: chmod/권한 가이드 표시

---

# 8. 기술 고려사항

## 8-1. 권장 아키텍처

```text
Web UI
  ↕
Local API Server
  ↕
Harness Core
  ├─ Scanner
  ├─ Parser
  ├─ Validator
  ├─ Patch Engine
  ├─ Snapshot/Rollback Engine
  ├─ Adapter: Hermes
  ├─ Adapter: Claude Code (future)
  └─ Adapter: Codex (future)
```

## 8-2. 기술 스택 후보

- UI: Next.js 또는 Vite React
- Local API: Node.js/Fastify 또는 Python/FastAPI
- File watch: chokidar 또는 watchfiles
- Patch: unified diff + structured patch
- Config parse: yaml, toml, markdown AST
- LLM bridge: Hermes tool call 또는 OpenAI-compatible API
- DB: SQLite for audit/snapshot metadata

## 8-3. Adapter Interface

각 에이전트 adapter는 다음 기능을 구현한다.

- detect(): 설치/프로필 탐지
- scan(): 하네스 항목 수집
- parse(item): 구조화
- validate(change): 변경 검증
- apply(change): 적용
- reload(): 런타임 반영 또는 재스캔
- exportPreset(): 공유 가능한 bundle 생성

## 8-4. 보안 고려사항

- 로컬호스트 바인딩 기본값: 127.0.0.1
- 외부 네트워크 접근 기본 비활성
- secret 마스킹
- write allowlist 경로 제한
- symlink traversal 방지
- destructive action confirmation
- audit log append-only 옵션

---

# 9. 실험 및 검증

## 9-1. MVP 검증 시나리오

1. Hermes 설치 환경에서 앱 실행
2. 전체 하네스 스캔 성공
3. memory 하나 추가
4. skill trigger 하나 수정
5. MCP server connection test 실행
6. AGENTS.md의 특정 preference section 요약 확인
7. 변경 rollback 수행
8. preset export/import dry-run

## 9-2. QA 체크리스트

- 잘못된 YAML을 가진 config에서 앱이 죽지 않는가?
- secret이 UI/LLM 로그에 노출되지 않는가?
- patch 적용 실패 시 원본 파일이 보존되는가?
- file watcher와 수동 재스캔 결과가 일치하는가?
- 동시에 두 변경이 발생했을 때 conflict를 감지하는가?
- rollback 후 validation이 통과하는가?

## 9-3. 사용자 테스트 질문

- “이 에이전트가 현재 무엇을 기억하는지 이해할 수 있었나?”
- “스킬이 언제 발동되는지 알 수 있었나?”
- “채팅으로 수정하는 과정이 파일 편집보다 안전하다고 느꼈나?”
- “변경 전후 diff가 충분히 이해 가능했나?”

---

# 10. 리스크 및 대응

## 리스크 1. 에이전트별 포맷 차이

- 영향: Cross-agent abstraction이 복잡해짐
- 대응: Hermes adapter만 MVP로 구현하고, Common Harness Model은 경험 기반으로 점진 확장

## 리스크 2. 자연어 수정의 불안정성

- 영향: 잘못된 config 변경 가능
- 대응: proposal/diff/validation/apply 4단계로 분리, 자동 적용 금지 기본값

## 리스크 3. Secret 노출

- 영향: 치명적 보안 사고
- 대응: secret redaction layer를 LLM 호출 전 강제 적용, snapshot에도 암호화/마스킹 정책 적용

## 리스크 4. OSS 설치 난이도

- 영향: 초기 adoption 저하
- 대응: single binary 또는 `npx agent-harness-studio` 형태 제공

## 리스크 5. 하네스 자체가 self-modifying system이 됨

- 영향: 사용자가 예상 못한 에이전트 행동 변화
- 대응: 변경 이력, 영향도 설명, rollback, risk level 표시

---

# 11. 일정 및 운영계획

## Phase 0. Design Spike (1주)

- Hermes harness inventory 정리
- Common Harness Model v0 정의
- UI wireframe 확정
- security policy 초안 작성

## Phase 1. Read-only Inspector MVP (2주)

- Hermes detect/scan 구현
- Memory/Skills/MCP/Root Context dashboard
- parse diagnostics
- local web UI

## Phase 2. Safe Edit MVP (2주)

- Chat Molder
- proposal/diff/validation/apply
- snapshot/rollback
- skill trigger 수정, memory 추가/삭제, MCP test

## Phase 3. Preset & OSS Launch (1주)

- export/import dry-run
- README, demo video, example presets
- GitHub release

## Phase 4. Multi-agent Expansion (후속)

- Claude Code/Cursor/Codex/OpenClaw/Gemini/Antigravity scanner 1차 완료
- Pi Coding Agent runner adapter 1차 완료
- OpenCode adapter는 아직 미구현 후보
- community marketplace

---

# 12. 참고자료

- Anthropic: Claude Code in large codebases — Harness matters as much as model
- OpenAI: Codex Subagents documentation
- Karpathy: LLM Wiki pattern
- GeekNews topic 29798: 자동화 실패와 human-in-the-loop 운영 교훈
- Hermes Agent local skills/memory/MCP architecture

---

# Appendix. 용어 정의

- Harness: 에이전트의 모델 외부 실행 환경. 프롬프트, 메모리, 스킬, 훅, MCP, 권한, 검증 루프 포함.
- Skill: 특정 작업에 대한 절차/지식/템플릿을 담은 재사용 가능한 능력 단위.
- MCP: Model Context Protocol. 외부 도구/데이터소스를 에이전트에 연결하는 표준.
- Root Context: AGENTS.md/CLAUDE.md 등 에이전트가 항상 참고하는 프로젝트/사용자 규칙.
- Chat Molder: 자연어로 하네스 변경안을 만들고 적용하는 대화형 인터페이스.
- Preset: 공유 가능한 하네스 구성 묶음.

---

# 변경 이력

- v0.1 / 2026.05.24 / 최초 작성
