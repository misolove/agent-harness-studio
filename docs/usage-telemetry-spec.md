# A안 — 사용 빈도 파싱 + 추천 엔진

> **핸드오프 대상**: Codex (또는 다음 세션의 Claude)
> **목표**: Agent Harness Studio를 "관찰 도구(Observability)" → "개입 도구(Intervention)"로 전환
> **선결 조건**: 본 문서 단독으로 작업 시작 가능. 별도 컨텍스트 불필요.

> **구현 상태(2026-05-27)**: A안 구현 및 검증 완료. 실제 구현 파일은 `src/server/usage_tracker.py`, `src/server/recommender.py`, `src/server/app.py`, `src/scanner/claude_scanner.py`, `src/ui/src/App.jsx`, `src/ui/src/App.css`이다. 이 문서는 원래 작업 지시서였고, 현재는 구현 의도와 검증 기준을 보존하는 사양/핸드오프 문서로 사용한다.

---

## 0. 30초 요약

지금 Studio는 "이 Skill은 14k 토큰이고 90일 된 거야"까지만 말한다.  
**A안 완성 후 결과**: "이 Skill은 14k 토큰인데 **지난 30일간 0번 호출**됐다 → 아카이브 추천 (신뢰도 92%)" 까지 말할 수 있다.

완료된 일은 3가지:
1. **각 에이전트 로그를 파싱**해서 Skill/Subagent invocation을 카운트
2. **추천 엔진**에서 "0번 호출 + 토큰 큼" 같은 휴리스틱으로 점수 매김
3. **🥗 Diet 모달에 "📊 Smart" 탭**을 추가해서 추천 리스트 + 일괄 아카이브 버튼

검증 결과: Claude workspace 기준 `/api/recommendations?workspace=/Users/letitbe/.claude&days=30`에서 263개 추천(`HIGH_VALUE:1`, `STALE_UNUSED:72`, `ARCHIVE:190`)을 반환했다.

---

## 1. 현재까지 구현된 것 (이미 완성, 손대지 말 것)

| 기능 | 위치 | 상태 |
|------|------|------|
| 8개 에이전트 스캐너 | `src/scanner/*_scanner.py` | ✅ |
| PAYLOAD 토큰 계산 + on_demand 분리 | `src/scanner/base_scanner.py` | ✅ |
| Chat Molder (LLM + Pi Agent) | `src/ui/src/App.jsx`, `src/server/app.py` | ✅ |
| 🥗 Diet 모달 (대용량/오래된 필터) | `App.jsx` 라인 ~2597 `showDietModal` | ✅ |
| `/api/actions/archive` | `app.py` 라인 끝부분 | ✅ |
| `/api/actions/copy` | `app.py` 라인 끝부분 | ✅ |
| Chat Molder 드래그 리사이즈 | `App.jsx` `handleResizeStart` | ✅ |

**Diet 모달이 현재 노출하는 두 가지 휴리스틱:**
- 토큰 ≥ 5000 (대용량)
- `modified_at` 기준 90일+ (오래됨)

→ 이 두 가지로는 부족. **"안 쓰임"** 신호가 빠져있음.

---

## 2. A안 구현 부분

### 2-1. Usage Tracker 모듈 (신규 파일)

**파일**: `src/server/usage_tracker.py`

```python
"""
Agent session log parser.
각 에이전트의 세션 로그에서 Skill/Subagent invocation을 카운트한다.

지원 에이전트:
- Claude Code: ~/.claude/projects/*/*.jsonl  (tool_use 이벤트 파싱)
- Codex: ~/.codex/history.jsonl  (세션 카운트만, tool 추적 없음)
- Cursor: ~/.cursor/projects/  (조사 필요 — 일단 미지원)

기타 에이전트 (gemini, hermes, antigravity, openclaw)는 로그 포맷 불명.
일단 Claude만 처리하고, 다른 에이전트는 향후 확장 포인트만 마련.
"""

from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import json
from typing import Dict, List, Any, Optional


def parse_claude_sessions(days: int = 30) -> Dict[str, Dict[str, Any]]:
    """
    ~/.claude/projects/-Users-letitbe/*.jsonl 파싱.
    
    Returns:
        {
          "skills": {
            "<skill_name>": {"count": int, "last_used": iso_timestamp, "sessions": int},
            ...
          },
          "agents": {
            "<subagent_type>": {"count": int, "last_used": iso_timestamp, "sessions": int},
            ...
          },
          "total_sessions": int,
          "cutoff_date": iso_timestamp,
        }
    
    Parsing rules:
    - 각 라인은 JSON. type=='assistant'인 라인만 본다.
    - message.content[].type == 'tool_use' 인 항목 추출
    - tool name == 'Skill' → input.skill 카운트 → "skills" 버킷
    - tool name == 'Agent' → input.subagent_type 카운트 → "agents" 버킷
    - timestamp는 라인 최상위 'timestamp' 필드 (ISO 8601)
    - sessions는 sessionId 또는 파일명 기준 unique count
    """
    cutoff = datetime.now() - timedelta(days=days)
    log_dir = Path.home() / ".claude" / "projects"
    
    skills = defaultdict(lambda: {"count": 0, "last_used": None, "sessions": set()})
    agents = defaultdict(lambda: {"count": 0, "last_used": None, "sessions": set()})
    total_sessions = set()
    
    for jsonl in log_dir.rglob("*.jsonl"):
        session_id = jsonl.stem
        total_sessions.add(session_id)
        try:
            with jsonl.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    if d.get("type") != "assistant":
                        continue
                    
                    ts_str = d.get("timestamp")
                    if not ts_str:
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        ts = ts.replace(tzinfo=None)  # naive 비교
                    except Exception:
                        continue
                    if ts < cutoff:
                        continue
                    
                    msg = d.get("message", {})
                    content = msg.get("content", []) if isinstance(msg, dict) else []
                    if not isinstance(content, list):
                        continue
                    
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        if c.get("type") != "tool_use":
                            continue
                        name = c.get("name")
                        inp = c.get("input", {}) or {}
                        
                        if name == "Skill":
                            skill_name = inp.get("skill")
                            if skill_name:
                                bucket = skills[skill_name]
                                bucket["count"] += 1
                                bucket["sessions"].add(session_id)
                                if not bucket["last_used"] or ts_str > bucket["last_used"]:
                                    bucket["last_used"] = ts_str
                        elif name == "Agent":
                            agent_name = inp.get("subagent_type")
                            if agent_name:
                                bucket = agents[agent_name]
                                bucket["count"] += 1
                                bucket["sessions"].add(session_id)
                                if not bucket["last_used"] or ts_str > bucket["last_used"]:
                                    bucket["last_used"] = ts_str
        except (OSError, PermissionError):
            continue
    
    # sessions set → count
    def _finalize(d):
        return {k: {**v, "sessions": len(v["sessions"])} for k, v in d.items()}
    
    return {
        "skills": _finalize(skills),
        "agents": _finalize(agents),
        "total_sessions": len(total_sessions),
        "cutoff_date": cutoff.isoformat(),
    }


def parse_codex_history(days: int = 30) -> Dict[str, Any]:
    """
    ~/.codex/history.jsonl 파싱 (단순 텍스트 프롬프트 라인).
    tool invocation은 추적 불가. 세션 카운트만 반환.
    
    Returns:
        {"prompt_count": int, "session_count": int, "last_used": iso_timestamp}
    """
    cutoff_epoch = (datetime.now() - timedelta(days=days)).timestamp()
    path = Path.home() / ".codex" / "history.jsonl"
    if not path.exists():
        return {"prompt_count": 0, "session_count": 0, "last_used": None}
    
    sessions = set()
    prompt_count = 0
    last_ts = None
    
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = d.get("ts")
            if not ts or ts < cutoff_epoch:
                continue
            sessions.add(d.get("session_id"))
            prompt_count += 1
            if not last_ts or ts > last_ts:
                last_ts = ts
    
    return {
        "prompt_count": prompt_count,
        "session_count": len(sessions),
        "last_used": datetime.fromtimestamp(last_ts).isoformat() if last_ts else None,
    }


def get_usage_summary(workspace: str, days: int = 30) -> Dict[str, Any]:
    """
    워크스페이스별 사용량 요약. dispatcher 역할.
    """
    ws = Path(workspace).expanduser().resolve()
    home = Path.home().resolve()
    
    if ws == (home / ".claude").resolve():
        return {"agent": "claude", **parse_claude_sessions(days)}
    if ws == (home / ".codex").resolve():
        return {"agent": "codex", **parse_codex_history(days)}
    # 다른 에이전트: 미지원, 빈 결과 반환
    return {"agent": ws.name, "skills": {}, "agents": {}, "total_sessions": 0,
            "cutoff_date": (datetime.now() - timedelta(days=days)).isoformat(),
            "unsupported": True}
```

### 2-2. Recommender 모듈 (신규 파일)

**파일**: `src/server/recommender.py` (신규)

```python
"""
스캔 결과 + 사용량 데이터를 결합해서 액션 추천을 생성한다.

추천 카테고리:
- ARCHIVE: 30일간 0번 호출 + 토큰 ≥ 1000
- STALE_UNUSED: 90일+ 미수정 AND 30일간 0번 호출
- HIGH_VALUE: 상위 10% 호출 빈도 (절대 아카이브 금지 표시용)
- HEAVY_UNUSED: 토큰 ≥ 5000 + 호출 빈도 하위 25%

각 추천은 confidence (0.0~1.0) + reason 텍스트를 포함.
"""

from typing import List, Dict, Any
from datetime import datetime


# Item name → invocation count 매핑을 위한 정규화 규칙:
# - Claude의 'Skill' tool_use는 input.skill = "moai-foundation-cc" 같은 문자열
# - 스캐너의 Skill item.name은 "SKILL.md"일 수도, 디렉토리명일 수도 있음
#   (스캐너마다 다름 — claude_scanner.py 확인 필요)
# 매칭은 다음 우선순위:
#   1. item.metadata.skill_id 가 있으면 그것
#   2. item.source_path 의 부모 디렉토리명
#   3. item.name 그대로


def _extract_skill_key(item: Dict[str, Any]) -> str:
    """스캔 item에서 usage 로그의 skill 이름과 매칭할 키 추출."""
    meta = item.get("metadata", {})
    if meta.get("skill_id"):
        return meta["skill_id"]
    sp = item.get("source_path", "")
    if sp:
        from pathlib import Path
        p = Path(sp)
        if p.name in ("SKILL.md", "AGENTS.md", "agent.md"):
            return p.parent.name
        return p.stem
    return item.get("name", "")


def _extract_agent_key(item: Dict[str, Any]) -> str:
    """Subagent item에서 usage 로그의 subagent_type과 매칭할 키 추출."""
    sp = item.get("source_path", "")
    if sp:
        from pathlib import Path
        # 파일명에서 .md 제거 (예: "expert-debug.md" → "expert-debug")
        return Path(sp).stem
    return item.get("name", "")


def build_recommendations(
    items: List[Dict[str, Any]],
    usage: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Args:
        items: scanner 결과 (각 item: type, name, source_path, token_estimate, metadata)
        usage: usage_tracker.get_usage_summary() 결과
    
    Returns:
        [{
          "item": {...},          # 원본 item
          "category": "ARCHIVE" | "STALE_UNUSED" | "HEAVY_UNUSED" | "HIGH_VALUE",
          "confidence": 0.0~1.0,
          "reason": "한국어 설명",
          "usage_count": int,
          "last_used": iso_timestamp | None,
          "potential_savings": int,  # 토큰 절감량
        }, ...]
    
    정렬: confidence 내림차순 → potential_savings 내림차순
    """
    skill_usage = usage.get("skills", {})
    agent_usage = usage.get("agents", {})
    now = datetime.now().timestamp()
    recs = []
    
    # HIGH_VALUE 식별: 호출 빈도 상위 10%
    all_counts = [v["count"] for v in {**skill_usage, **agent_usage}.values()]
    high_threshold = sorted(all_counts, reverse=True)[max(0, len(all_counts) // 10 - 1)] if all_counts else 0
    
    for item in items:
        item_type = item.get("type", "")
        tokens = item.get("token_estimate", 0) or 0
        meta = item.get("metadata", {})
        modified_at = meta.get("modified_at")
        days_old = int((now - modified_at) / 86400) if modified_at else None
        
        # Skill인지 Subagent인지 판단
        if item_type in ("Skill", "Skill Bundle"):
            key = _extract_skill_key(item)
            stats = skill_usage.get(key, {"count": 0, "last_used": None})
        elif item_type in ("Plugin",) or "agent" in (item.get("source_path") or "").lower():
            key = _extract_agent_key(item)
            stats = agent_usage.get(key, {"count": 0, "last_used": None})
        else:
            # Skill/Agent 아닌 항목은 사용량 추적 대상이 아님 — 스킵
            continue
        
        count = stats["count"]
        last_used = stats["last_used"]
        
        # ─── 카테고리 분류 ───
        category = None
        reason = ""
        confidence = 0.0
        
        if count >= high_threshold and high_threshold > 0:
            category = "HIGH_VALUE"
            reason = f"지난 30일간 {count}회 호출 (상위 10%) — 보존 권장"
            confidence = 0.95
        elif count == 0 and days_old and days_old >= 90:
            category = "STALE_UNUSED"
            reason = f"{days_old}일간 수정 없음 + 30일간 0회 호출"
            confidence = 0.92
        elif count == 0 and tokens >= 1000:
            category = "ARCHIVE"
            reason = f"지난 30일간 0회 호출됨 ({tokens:,} tokens 낭비)"
            confidence = 0.80
        elif tokens >= 5000 and count <= 2:
            category = "HEAVY_UNUSED"
            reason = f"대용량 ({tokens:,} tokens)인데 30일간 {count}회만 호출"
            confidence = 0.65
        
        if category:
            recs.append({
                "item": item,
                "category": category,
                "confidence": confidence,
                "reason": reason,
                "usage_count": count,
                "last_used": last_used,
                "potential_savings": tokens if category != "HIGH_VALUE" else 0,
            })
    
    # 정렬: confidence ↓, potential_savings ↓
    recs.sort(key=lambda r: (-r["confidence"], -r["potential_savings"]))
    return recs
```

### 2-3. API 엔드포인트 추가

**파일**: `src/server/app.py` — 기존 `/api/actions/archive` 다음 줄에 추가

```python
@app.get("/api/usage/stats")
def usage_stats(workspace: str = Query(...), days: int = Query(30)):
    """워크스페이스의 Skill/Subagent invocation 통계."""
    from .usage_tracker import get_usage_summary
    return get_usage_summary(workspace, days)


@app.get("/api/recommendations")
def recommendations(workspace: str = Query(...), days: int = Query(30)):
    """스캔 결과 + 사용량 기반 추천 리스트."""
    from .usage_tracker import get_usage_summary
    from .recommender import build_recommendations
    
    # 기존 scan endpoint와 동일하게 items 생성
    items = _run_full_scan(workspace)  # 기존 함수 재사용 — 정확한 함수명은 app.py에서 확인
    usage = get_usage_summary(workspace, days)
    recs = build_recommendations(items, usage)
    return {"recommendations": recs, "usage": usage}
```

⚠️ **확인 필요**: `_run_full_scan` 함수 이름이 정확한지 `app.py`의 `/api/scan` 엔드포인트를 grep해서 확인. 아마도 `run_scan_for_workspace(workspace)` 또는 비슷한 형태일 것.

### 2-4. UI 통합 (Diet 모달)

**파일**: `src/ui/src/App.jsx` — `showDietModal` 렌더링 블록 (라인 ~2597)

**현재 상태**: 3개 탭 — `all`, `large`, `stale`

**변경 사항**: 4번째 탭 `smart` 추가

```jsx
// 1. state 추가 (기존 dietTab 옆)
const [recommendations, setRecommendations] = useState([]);
const [recLoading, setRecLoading] = useState(false);

// 2. Diet 모달 열릴 때 추천 fetch
useEffect(() => {
  if (!showDietModal || dietTab !== 'smart') return;
  setRecLoading(true);
  fetch(`/api/recommendations?workspace=${encodeURIComponent(activeWorkspace)}&days=30`)
    .then(r => r.json())
    .then(d => setRecommendations(d.recommendations || []))
    .catch(() => setRecommendations([]))
    .finally(() => setRecLoading(false));
}, [showDietModal, dietTab, activeWorkspace]);

// 3. 탭 배열에 'smart' 추가 (기존 코드의 ~2628 라인 근처)
{[
  ['smart', '📊 Smart'],
  ['all', '전체 후보'],
  ['large', '대용량 (5K+)'],
  ['stale', `오래된 (${STALE_DAYS}일+)`]
].map(...)}

// 4. dietTab === 'smart'일 때 별도 렌더링
{dietTab === 'smart' ? (
  recLoading ? <div className="diet-empty">분석 중...</div>
  : recommendations.length === 0 ? <div className="diet-empty">추천 없음 ✓</div>
  : <table className="diet-table">
      <thead><tr>
        <th>이름</th><th>카테고리</th><th>호출수</th>
        <th>이유</th><th>신뢰도</th><th>액션</th>
      </tr></thead>
      <tbody>
        {recommendations.map((r, i) => (
          <tr key={i} className={`diet-row-${r.category.toLowerCase()}`}>
            <td>{r.item.name}</td>
            <td>
              <span className={`rec-badge rec-${r.category.toLowerCase()}`}>
                {r.category === 'HIGH_VALUE' ? '⭐ 보존' :
                 r.category === 'STALE_UNUSED' ? '🗑️ 정리' :
                 r.category === 'ARCHIVE' ? '🗄️ 아카이브' : '⚖️ 검토'}
              </span>
            </td>
            <td>{r.usage_count}</td>
            <td className="rec-reason">{r.reason}</td>
            <td>{(r.confidence * 100).toFixed(0)}%</td>
            <td>
              {r.category !== 'HIGH_VALUE' && (
                <button className="diet-btn-archive" 
                  onClick={() => setArchiveConfirm(r.item)}>
                  아카이브
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
) : (
  /* 기존 대용량/오래됨 테이블 */
)}
```

### 2-5. CSS (App.css 끝에 추가)

```css
.rec-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.rec-high_value { background: #064e3b; color: #6ee7b7; }
.rec-stale_unused { background: #7f1d1d; color: #fca5a5; }
.rec-archive { background: #78350f; color: #fcd34d; }
.rec-heavy_unused { background: #1e3a8a; color: #93c5fd; }
.rec-reason { color: #94a3b8; font-size: 12px; max-width: 280px; }
.diet-btn-archive {
  padding: 4px 10px;
  background: var(--accent-purple);
  border: none; border-radius: 4px;
  color: white; cursor: pointer; font-size: 12px;
}
.diet-btn-archive:hover { opacity: 0.85; }
.diet-row-high_value { opacity: 0.6; }  /* 보존 항목은 약간 흐리게 */
```

---

## 3. 데이터 소스 사전조사 결과

### 3-1. Claude Code 로그 — **파싱 가능 ✓**

**경로**: `~/.claude/projects/-Users-letitbe/*.jsonl`

**Skill invocation 예시:**
```json
{
  "type": "assistant",
  "timestamp": "2026-05-26T...",
  "sessionId": "...",
  "message": {
    "content": [
      {
        "type": "tool_use",
        "name": "Skill",
        "input": {
          "skill": "update-config",
          "args": "..."
        }
      }
    ]
  }
}
```

**Subagent invocation 예시:**
```json
{
  "type": "assistant",
  "message": {
    "content": [
      {
        "type": "tool_use",
        "name": "Agent",
        "input": {
          "subagent_type": "expert-debug",
          "description": "Diagnose openclaw latency",
          "prompt": "..."
        }
      }
    ]
  }
}
```

### 3-2. Codex 로그 — **부분 파싱 가능 △**

**경로**: `~/.codex/history.jsonl`

**포맷:** `{"session_id": "...", "ts": <epoch>, "text": "..."}`

→ user prompt 텍스트만 저장됨. **Tool/Skill invocation 추적 불가.**  
세션 활성도(prompt 수)만 카운트 가능.

### 3-3. 기타 에이전트 — **미조사**

| 에이전트 | 로그 위치 후보 | 액션 |
|---------|--------------|------|
| Cursor | `~/.cursor/projects/`, `~/.cursor/ai-tracking/` | A안에서는 미지원 |
| Gemini | `~/.gemini/`, `~/.gemini/antigravity/` | A안에서는 미지원 |
| Hermes | `~/.hermes/state/` (sqlite?) | A안에서는 미지원 |
| OpenClaw | `~/.openclaw/log/`, `~/.openclaw/*.sqlite` | A안에서는 미지원 |

→ **A안에서는 Claude만 완전 지원**. 나머지는 "데이터 없음, 토큰 기반 휴리스틱만 적용" 으로 graceful degrade.

---

## 4. 검증 방법

### 4-1. 백엔드 단위 테스트

```bash
cd /Users/letitbe/letitbe/agent-harness-studio
source .venv/bin/activate
python3 -c "
from src.server.usage_tracker import parse_claude_sessions
result = parse_claude_sessions(days=30)
print(f'Total sessions: {result[\"total_sessions\"]}')
print(f'Top 5 skills:')
for name, stats in sorted(result['skills'].items(), key=lambda x: -x[1]['count'])[:5]:
    print(f'  {name}: {stats[\"count\"]} calls')
print(f'Top 5 agents:')
for name, stats in sorted(result['agents'].items(), key=lambda x: -x[1]['count'])[:5]:
    print(f'  {name}: {stats[\"count\"]} calls')
"
```

**기대 결과 (~/.claude의 본인 데이터 기준):**
- Total sessions: ≥ 30
- Top skill: 'idea2planning', 'oh-my-claudecode' 계열 등이 보여야 함
- Top agent: 'expert-debug', 'general-purpose' 등

### 4-2. API 검증

```bash
# Usage stats
curl -s 'http://localhost:8766/api/usage/stats?workspace=/Users/letitbe/.claude&days=30' | python3 -m json.tool | head -30

# Recommendations
curl -s 'http://localhost:8766/api/recommendations?workspace=/Users/letitbe/.claude&days=30' \
  | python3 -m json.tool | head -50
```

### 4-3. UI 검증

1. 브라우저 → `localhost:5173`
2. 워크스페이스를 **Claude Code** 로 전환
3. 헤더 🥗 클릭 → Diet 모달
4. **📊 Smart 탭** 클릭
5. 리스트 표시 확인:
   - HIGH_VALUE 항목은 흐리게, "⭐ 보존" 배지
   - ARCHIVE/STALE_UNUSED 항목은 "🗄️ 아카이브" 버튼 활성
   - 신뢰도(%)와 이유 텍스트 표시
6. 아카이브 버튼 → 확인 다이얼로그 → 이동 → 스캔 새로고침

---

## 5. 알려진 함정 (gotchas)

### 5-1. Skill 이름 매칭 실패

`tool_use.input.skill` 값(예: `"oh-my-claudecode:explore"`)과 스캐너의 item.name 사이 형식 차이가 있을 수 있다.

**해결**: `claude_scanner.py`에서 Skill item을 만들 때 `metadata.skill_id`에 정규화된 이름(`"oh-my-claudecode:explore"`)을 명시적으로 박아넣어라. recommender의 `_extract_skill_key`가 이 필드를 최우선으로 사용한다.

→ **`claude_scanner.py` 수정 필요할 수 있음**. 먼저 다음을 확인:
```bash
curl -s 'http://localhost:8766/api/scan?workspace=/Users/letitbe/.claude' \
  | python3 -c "import sys, json; d=json.load(sys.stdin); 
    skills = [i for i in d['items'] if i['type']=='Skill'][:3]
    print(json.dumps(skills, indent=2))"
```
item의 name/source_path/metadata 형태를 보고 매칭 키 추출 방식 결정.

### 5-2. 시간대 처리

Claude jsonl의 timestamp는 UTC ISO 8601 (Z 접미사). Python `fromisoformat()`는 Python 3.11+에서 Z를 지원. **3.10 이하 호환을 위해 `Z` → `+00:00` 치환 필수**.

### 5-3. 거대한 jsonl 파일

세션이 길면 jsonl이 수십 MB. **반드시 line-by-line streaming**으로 읽어라. `json.loads(open().read())` 절대 금지.

### 5-4. 워크스페이스 ID vs path

`/api/scan?workspace=` 는 path를 받음 (예: `/Users/letitbe/.claude`). `usage_tracker.get_usage_summary(workspace)`도 path를 받음. **id (`"claude"`)와 path를 헷갈리지 말 것.**

→ frontend의 `activeWorkspace` 상태가 path를 들고 있는지 id를 들고 있는지 `App.jsx`에서 확인. 둘 다 케이스를 본 적 있음.

### 5-5. 빈 로그 / 권한 에러

```python
try:
    with jsonl.open(...) as f:
        ...
except (OSError, PermissionError):
    continue  # 로깅만 하고 스킵
```
**예외 무시 정책**: 한 jsonl 못 읽어도 전체 파싱 실패하면 안 됨.

---

## 6. 작업 순서 (완료 기록)

1. **사전조사**: `~/.claude/projects/` jsonl 구조 확인
2. **`usage_tracker.py`** 작성 + 단독 파싱 테스트
3. **`recommender.py`** 작성 + 추천 카테고리 테스트
4. **`app.py`에 2개 endpoint 추가** + curl 검증
5. **`claude_scanner.py` skill_id 메타데이터 및 nested agents 재귀 스캔 추가**
6. **`App.jsx` Smart 탭 UI 통합**
7. **`App.css` 배지/버튼 스타일 추가**
8. **`HANDOFF.md` 업데이트** — "A안 완료" 섹션 추가

---

## 7. 완료 기준 (Definition of Done)

- [x] Claude Code 워크스페이스에서 `/api/recommendations`가 비어있지 않은 응답을 반환
- [x] Smart 탭에 최소 5개 추천이 표시됨 (HIGH_VALUE, ARCHIVE, STALE_UNUSED 카테고리 혼합)
- [x] 아카이브 버튼 클릭 → 실제 파일 이동 → 스캔 새로고침 후 해당 항목 사라짐 (임시 파일 smoke test)
- [x] 다른 에이전트(Cursor, Gemini 등) 워크스페이스에서도 Smart 탭이 깨지지 않음 (unsupported + 빈 리스트)
- [x] 빌드 에러 0개: `cd src/ui && npm run build`
- [x] 기존 Diet 모달의 3개 탭(전체/대용량/오래됨) 정상 동작 유지

---

## 8. 참고 — 기존 코드의 관련 위치

| 항목 | 파일 | 라인 (대략) |
|------|------|-----------|
| Diet 모달 렌더링 시작 | `App.jsx` | 2597 |
| 탭 정의 (all/large/stale) | `App.jsx` | 2628 |
| Diet 모달 CSS | `App.css` | 끝부분 (`.diet-modal`, `.diet-tab` 등) |
| `/api/actions/archive` | `app.py` | 끝부분 (`if __name__` 직전) |
| `handleArchiveItem` 함수 | `App.jsx` | `handleEditClick` 위쪽 |
| `activeWorkspace` 상태 | `App.jsx` | useState 모음 영역 |
| Scanner items 구조 | `src/scanner/base_scanner.py` | `_finalize_items` |

---

**작성자**: Claude (Sonnet 4.5)  
**작성일**: 2026-05-27  
**핸드오프 사유**: Claude 사용 한도 임박 — Codex로 인계
