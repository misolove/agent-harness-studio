# Git 연동 안전 가이드

> 현황(2026-05-27): 초기 문서는 `~/.hermes` 중심으로 작성되었지만, 서버의 Git API는 `workspace` 또는 `path` 기준으로 허용된 agent workspace의 git 상태를 다룬다. Hermes 실데이터 수정에는 여전히 `~/.hermes` git init을 가장 권장하고, Claude/Codex 등 다른 workspace는 해당 디렉토리가 git repo일 때 동일한 이력/감사 패턴을 적용할 수 있다. Pi Agent Runner는 실행 전후 `GET /api/git/audit`으로 diff/risk를 캡처한다.

## 왜 Git인가?

| 방법 | 보호 범위 | 이력 | 선택 복원 |
|------|-----------|------|-----------|
| 샌드박스 (`HERMES_HOME=...sandbox`) | 실데이터 분리 | 없음 | 없음 |
| `HARNESS_READONLY=1` | 쓰기 차단 | 없음 | 없음 |
| 자동 백업 (`.bak.*`) | 마지막 1개 | 없음 | 없음 |
| **Git 연동 (권장)** | 전체 이력 | 무한 | 임의 커밋 |

Git을 사용하면 "방금 전 상태"뿐 아니라 **2주 전 특정 커밋 상태**로도 되돌릴 수 있습니다.

---

## 초기 설정

### 1단계: `~/.hermes` git 초기화

UI에서 헤더의 **"+ Git 연동"** 버튼 클릭. 또는:

```bash
cd ~/.hermes
git init
git add -A
git commit -m "initial: harness snapshot"
```

앱이 자동으로 `.gitignore`를 생성합니다:
```
*.bak.*    # 백업 사이드카 파일
.env       # 시크릿
*.log
```

### 2단계: (선택) 원격 백업

```bash
# GitHub private repo 연결 — 원격 백업
cd ~/.hermes
git remote add origin git@github.com:yourname/hermes-harness.git
git push -u origin main
```

> 스킬과 메모리에는 개인 정보가 포함될 수 있습니다. **반드시 private repo**를 사용하세요.

---

## 일상적인 사용 흐름

### 파일 편집 시

1. 에디터에서 파일 수정
2. 커밋 메시지 입력 (선택 — 비워두면 자동 생성)
3. **Save** → 저장 + 자동 커밋

```
커밋 메시지 예:
  harness-studio: edit my-skill    ← 자동 생성
  feat: add python code review     ← 직접 입력
```

### 이력 확인 및 복원

1. 에디터에서 **History** 버튼 클릭
2. 커밋 목록 확인 (해시 / 메시지 / 날짜)
3. 되돌리고 싶은 커밋의 **복원** 클릭
4. 복원 후 자동으로 새 커밋 생성 (이력 유지)

### Chat Molder Apply 시

Apply 버튼 클릭 → `/api/save` 호출 → 자동 커밋
커밋 메시지: `harness-studio: molder apply {skill-name}`

---

## API 요약

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/git/init` | POST | HERMES_HOME git 초기화 |
| `/api/git/log` | GET | 커밋 이력 조회 (`?path=...`로 파일 필터) |
| `/api/git/diff` | GET | 특정 커밋의 변경 내용 (`?commit_hash=...`) |
| `/api/git/rollback` | POST | 특정 커밋으로 파일 복원 |
| `/api/git/audit` | GET | workspace git status/stat 기반 risk audit |

---

## 안전 레이어 조합 권장

```
탐색만 할 때:
  HARNESS_READONLY=1  (읽기 전용)

개발/테스트:
  HERMES_HOME=~/.hermes/sandbox  (분리된 데이터)

실데이터 수정 (권장):
  HERMES_HOME=~/.hermes  (git init 완료된 상태)
  → 모든 변경이 커밋으로 기록됨
  → 언제든 임의 시점으로 복원 가능
```

---

## 문제 해결

### "Git 연동" 버튼이 안 보인다
- `HARNESS_READONLY=1`이면 버튼이 숨겨집니다. 읽기 전용 해제 후 시도.

### 커밋이 안 된다 (git user 설정 없음)
```bash
git config --global user.email "you@example.com"
git config --global user.name "Your Name"
```

### 복원 후 파일이 이상하다
```bash
cd ~/.hermes
git log --oneline -10      # 최근 10개 이력 확인
git diff HEAD~1 HEAD       # 마지막 변경 확인
git checkout HEAD~1 -- skills/my-skill/SKILL.md  # 수동 복원
```
