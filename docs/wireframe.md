# [Wireframe] Agent Harness Studio

> Current implementation note (2026-05-27): Type A가 실제 UI의 기준이 되었다. 현재 화면은 workspace selector, 섹션 카드, 검색/정렬 가능한 목록, Logs tail read, Sessions/State DB/Checkpoints, Smart Diet, Diff Audit, Agent Runner, LLM/Pi Agent 전환형 Chat Molder를 포함한다. 아래 Type B/C는 탐색 아이디어로 유지한다.

## 화면 목적
- AI 에이전트의 하네스 전체 상태를 한눈에 파악(Inspection)
- 자연어 채팅을 통해 하네스를 실시간으로 수정(Molding)
- 변경 사항에 대한 시각적 피드백 및 검증 결과 확인(Validation)

---

## 공통 요구사항
- 상단: 에이전트 상태(Active/Warning/Error), 현재 선택된 workspace(Hermes/Claude/Cursor/Codex/Gemini 등)
- 중앙: 하네스 영역(Memory, Skills, Hooks, MCP, Context, Config, Logs, Sessions, State DB, Checkpoints, Agent Runner) 요약 카드
- 우측 또는 하단: Chat Molder (자연어 수정 인터페이스)
- 변경 제안 시: Diff 뷰 + Apply/Reject 버튼

---

# Type A — 현실적인 안 (Dashboard + Side Chat)

## 컨셉
현재 Hermes나 Claude Code 파워 유저들이 익숙한 **IDE 스타일의 대시보드**. 정보를 밀도 있게 전달하고, 채팅은 보조적인 조작 도구로 활용.

## 핵심 UX 방향
- 정보 탐색 우선 (6개 패널 고정 레이아웃)
- 수정은 채팅뿐만 아니라 각 카드 내 Quick Edit 버튼으로도 가능
- 에러/경고가 있는 영역을 즉시 빨간색으로 하이라이트

## Wireframe
```text
┌─────────────────────────────────────────────────────────────┐
│ [● Active] Agent Harness Studio (Hermes v2.4)     [Settings]│
├───────────────────────────────┬─────────────────────────────┤
│ 1. MEMORY [Edit]              │ CHAT MOLDER                 │
│ - User: 레리삐 (Asia/Seoul)    │                             │
│ - PTR: Invest, Voice          │ > 스킬 'security' 추가해줘  │
│ - Mem0: Connected (1.2k)      │                             │
├───────────────────────────────┤ ┌─────────────────────────┐ │
│ 2. SKILLS (24 active) [Add]   │ │ PROPOSAL: Add Skill     │ │
│ - research/idea2planning      │ │ target: skills/security │ │
│ - dev/systematic-debug        │ │ [ View Diff ]           │ │
│ - ! Error: legacy-v1 (parse)  │ │                         │ │
├───────────────────────────────┤ │ [ Apply ]  [ Reject ]   │ │
│ 3. MCP SERVERS [Test]         │ └─────────────────────────┘ │
│ - QMD (Local, 8 tools) [OK]   │                             │
│ - context7 (HTTP) [Warn: Slow]│                             │
├───────────────────────────────┤                             │
│ 4. ROOT CONTEXT [View]        │                             │
│ - AGENTS.md (14k chars)       │                             │
│ - Project: korea-event-radar  │                             │
├───────────────────────────────┤                             │
│ 5. HOOKS / 6. CONFIG [Detail] │ [Type your request here...] │
└───────────────────────────────┴─────────────────────────────┘
```

---

# Type B — 디자인 강조안 (Immersive Cards + Floating Chat)

## 컨셉
각 하네스 요소를 **대형 비주얼 카드**로 구성하여 현재 에이전트의 "뇌 상태"를 시각적으로 감상하는 구조.

## 핵심 UX 방향
- 비주얼 임팩트 중심 (카드마다 고유 아이콘/색상)
- 채팅은 필요할 때만 떠오르는 Floating Chat 형태
- 상태 변화 시 부드러운 애니메이션 효과

## Wireframe
```text
┌─────────────────────────────────────────────────────────────┐
│  [ HARNESS INSIGHT ]                                [Menu]  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ 🧠 MEMORY    │  │ ⚡ SKILLS    │  │ 🔌 MCP       │       │
│  │ 1.2k notes   │  │ 24 tools     │  │ 3 servers    │       │
│  │ [●●●●○]      │  │ [●●●●●]      │  │ [●●○○○]      │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ ⚓ CONTEXT   │  │ 🪝 HOOKS    │  │ ⚙️ CONFIG    │       │
│  │ AGENTS.md    │  │ 4 active     │  │ Qwen3/Hermes │       │
│  │ [●●●●○]      │  │ [●●●●○]      │  │ [●●●●●]      │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                             │
│                 ┌──────────────────────────┐                │
│                 │   🗨️ "하네스 수정하기..." │                │
│                 └──────────────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

---

# Type C — 실험적/미래형 안 (Context-Aware Molding Hub)

## 컨셉
화면 중앙에 에이전트의 **현재 컨텍스트(작업 중인 내용)**가 흐르고, 하네스는 그 주변에 상황에 맞게 노출/변화하는 구조.

## 핵심 UX 방향
- AI 중심 인터랙션 (상황에 따라 필요한 하네스 패널이 자동 팽창)
- "Molding Hub": 채팅창이 중앙에 위치하며, 채팅 내용에 따라 관련 하네스 파일이 라이브로 미리보기됨
- 시계열 뷰: 하네스가 시간이 지남에 따라 어떻게 변해왔는지 타임라인 표시

## Wireframe
```text
┌─────────────────────────────────────────────────────────────┐
│ [ Timeline: 2026.05.24 14:20 ]                              │
├─────────────────────────────────────────────────────────────┤
│        [ Active Context: Refactoring korea-event-radar ]    │
│                                                             │
│        ┌──────────────────────────────────────────┐         │
│  H     │                                          │    M    │
│  A     │          [  MOLDING HUB  ]               │    E    │
│  R     │                                          │    M    │
│  N     │  "이 프로젝트 규칙에 'PR 전 lint 필수'   │    O    │
│  E     │   라는 내용을 AGENTS.md에 추가해줘"      │    R    │
│  S     │                                          │    Y    │
│  S     └──────────────────────────────────────────┘         │
│                                                             │
│  ┌────────────────────┐      ┌──────────────────────────┐   │
│  │ AGENTS.md (Patch)  │      │ Proposed Change Analysis │   │
│  │ - lint: false      │  →   │ 이 변경은 'git-hook'     │   │
│  │ + lint: true       │      │ 스킬과 시너지가 납니다.  │   │
│  └────────────────────┘      └──────────────────────────┘   │
│                                                             │
│ [ Inspection ] [ Validation ] [ Snapshot ] [ Global Preset ]│
└─────────────────────────────────────────────────────────────┘
```
