# Agent Harness Studio

AI 에이전트의 하네스(메모리·스킬·훅·MCP·루트 컨텍스트)를 웹 대시보드에서 시각화하고 자연어로 수정하는 오픈소스 컨트롤 타워.

## 핵심 철학: Harness over Model
모델 자체의 성능보다 에이전트의 작업 환경(Harness) 설계를 고도화하는 것이 실질적인 에이전트 생산성을 결정합니다.

## 주요 기능
- **Harness Inspector**: 분산된 설정 파일과 메모리를 한눈에 시각화
- **Chat Molder**: 자연어 대화로 하네스 구성요소 즉시 수정 및 반영
- **Live Validation**: 변경 사항에 대한 실시간 diff 및 영향도 분석
- **Harness Preset**: 검증된 하네스 설정을 팀/커뮤니티와 공유

## 문서 (Docs)
- [1-pager](docs/1pager.md): 프로젝트 기획 배경 및 목표
- [PRD](docs/prd.md): 상세 제품 요구사항 정의서
- [Wireframe](docs/wireframe.md): 3가지 UI/UX 컨셉 제안

## 시작하기 (Development)
현재 Hermes 에이전트를 위한 스캐너 엔진 프로토타이핑 단계입니다.

```bash
# src/scanner/ 프로토타입 실행 (예정)
python src/scanner/hermes_scanner.py
```
