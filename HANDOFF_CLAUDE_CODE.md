# Handoff: Memory Map 에이전트별 동적 아키텍처 다이어그램

## 프로젝트 위치
`/Users/letitbe/letitbe/agent-harness-studio`

## 현재 상황
Memory Map 탭(`App.jsx` L1691~1725)에 Hermes 전용 아키텍처 다이어그램이 **하드코딩**되어 있다. 다른 에이전트 워크스페이스(Claude Code, Codex, Gemini 등)를 선택해도 Hermes 다이어그램만 보인다.

## 해야 할 일
`App.jsx` L1691~1725의 하드코딩 다이어그램을 **`activeWorkspace` 기반 동적 렌더링**으로 교체하라.

### 에이전트별 메모리 구조 (이미 조사 완료)

**1. Hermes** (`~/.hermes`)
```
L0: System Prompt (memories/MEMORY.md + memories/USER.md) — every turn injected
L1: Pointer Index (memory_manifest.md) — PTR: tags resolve here
L2: Deep Storage — skills/, session_search (FTS5), Mem0 (vector localhost:8888), state/
L3: Cold Storage — reflections/ (monthly/yearly GC rollups via hierarchical-memory-gc)
```

**2. Claude Code** (`~/.claude`)
```
L0: System Prompt (CLAUDE.md) — injected every turn
L1: Project Context — project-level CLAUDE.md files
L2: Deep Storage — agent-memory/ (MemRosetta MCP), commands/, agents/
L3: No archive layer (session-scoped)
```

**3. Codex / oh-my-codex** (`~/.codex`)
```
L0: System Prompt (AGENTS.md) — injected every turn
L1: Agent Catalog — agents/*.toml (specialized sub-agents)
L2: Deep Storage — prompts/, skills/, ambient-suggestions/
L3: No archive layer
```

**4. Gemini CLI / Antigravity** (`~/.gemini`)
```
L0: System Prompt (GEMINI.md) — injected every turn
L1: Extensions — antigravity-ide/, antigravity-cli/
L2: Deep Storage — config/, history/
L3: No archive layer
```

**5. Cursor** (`~/.cursor`)
```
L0: IDE Context — skills-cursor/, projects/
L1: Extensions — plugins/, extensions/
L2: Tracking — ai-tracking/
L3: No archive layer
```

### 구현 가이드

1. `activeWorkspace` 값을 통해 현재 에이전트 감지:
   ```jsx
   const ws = workspaces.find(w => w.path === activeWorkspace);
   const agentId = ws?.id || 'hermes'; // 'hermes' | 'claude' | 'codex' | 'gemini' | 'cursor'
   ```

2. 에이전트별 아키텍처 맵을 상수/객체로 정의:
   ```jsx
   const ARCH_MAPS = {
     hermes: { name: 'Hermes', tiers: [...] },
     claude: { name: 'Claude Code', tiers: [...] },
     // ...
   };
   ```

3. 각 tier는 `{ label, color, lines: string[], arrow: string }` 구조.

4. 기존 하드코딩 JSX(L1691~1725)를 `ARCH_MAPS[agentId]` 순회 렌더링으로 교체.

5. 게이지 바(Memory Budget)도 에이전트별로 조건부 렌더링:
   - Hermes: MEMORY.md + USER.md (기존 로직)
   - Claude Code: CLAUDE.md 크기만
   - Codex: AGENTS.md 크기만
   - Gemini: GEMINI.md 크기만

### 관련 파일
- `src/ui/src/App.jsx` — 프론트엔드 (다이어그램: L1691~1725, 게이지: L1648~1690)
- `src/scanner/hermes_scanner.py` — 백엔드 스캐너 (이미 에이전트별 workspace 스캔 지원)
- `src/server/routers/scan.py` — 스캔 API (workspace 파라미터로 `/api/scan?workspace=...` 지원)

### 로컬 실행
```bash
cd /Users/letitbe/letitbe/agent-harness-studio
./run.sh
# Frontend: http://localhost:5173
# Backend:  http://localhost:8766
```
