# 지식인(Kin) 홍보 후보 검색 자동화 — 설치 방법

깃허브 쓰기 권한 문제로 자동 커밋이 안 돼서, 파일로 대신 드립니다. 아래 순서로 직접 저장소에 올려주세요.

## 1. 파일을 저장소에 올리기

`taeseongk1218-cpu/project-pd-automation` 저장소 루트에 이 폴더의 파일들을 그대로 복사해 넣고 커밋하세요:

- `kin_search.py`
- `kin_candidates.json`
- `kin_state.json`
- `.github/workflows/kin-search.yml`

## 2. 시크릿 등록

저장소 **Settings → Secrets and variables → Actions → New repository secret**에서:

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

네이버 오픈 API(https://developers.naver.com/apps)에서 애플리케이션을 등록하면 무료로 발급받을 수 있어요. "검색" API 사용 권한만 있으면 됩니다.

## 3. 동작 확인

**Actions** 탭 → **Kin Promotion Candidate Search** 워크플로우 → **Run workflow**로 수동 실행해보세요.

## 꼭 알아두실 것

- 이 스크립트는 **지식인에 직접 게시하지 않습니다.** 새 글이 올라오면 관련 질문 3개(순수 2 + 홍보 1)를 찾아 `kin_candidates.json`에 초안만 쌓아둡니다.
- 초안 문구(`draft`)는 뼈대일 뿐이에요 — 실제 게시 전에 반드시 사람이 직접(원하면 클로드와 채팅으로) 질문 내용에 맞게 다듬어야 합니다. 이 스크립트는 AI를 호출하지 않아서 비용은 안 들지만, 그만큼 답변 품질도 낮아요.
- 30분마다 자동 실행되며, 이미 처리한 글은 `kin_state.json`에 기록돼서 중복 처리하지 않습니다.
