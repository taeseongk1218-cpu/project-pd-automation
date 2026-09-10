# project-pd-automation

`500md87.com`(티스토리, 건강블로그) 글과 `projectpdlab.blogspot.com`(블로그스팟) 글 중 같은
원본으로 만든 글끼리 짝을 맞추고, 기존 쓰레드(Threads) 자동 발행이 그 둘 중 링크를
무작위로 고를 수 있게 해주고, 글이 올라온 지 90분 뒤 인스타그램에 자동으로 카드 이미지를
게시하는 자동화입니다. GitHub Actions로 동작하며 비용이 들지 않습니다(공개 저장소는
Actions 실행 시간이 무제한).

> 이 저장소는 이 블로그·SNS 자동화만을 위한 전용 저장소입니다. 기존 건강블로그 쓰레드 자동
> 발행(Make.com 시나리오)은 전혀 건드리지 않습니다 — 이 저장소는 완전히 독립적으로 동작하고,
> 결과물(`latest.json`)만 다른 시스템이 읽어가는 구조입니다.

## 글 쓸 때 꼭 넣어야 하는 것 — SOURCE ID 주석

같은 내용으로 티스토리와 블로그스팟에 각각 글을 올릴 때, **두 글의 본문 어딘가에 똑같은
SOURCE ID 주석**을 하나씩 넣어주세요 (화면에는 보이지 않는 HTML 주석입니다):

```html
<!-- PD-SOURCE-ID:PD-20260910-001 -->
```

- `PD-YYYYMMDD-NNN` 형식: 발행일 + 그날의 일련번호(001, 002...)
- 티스토리 글에만 있고 블로그스팟 글이 아직 없어도 문제없습니다 — 기존처럼 티스토리
  링크만 쓰입니다. 나중에 블로그스팟에 짝 글을 올리면 자동으로 매칭됩니다.
- 이 주석이 없는 글은 이 자동화가 아예 신경 쓰지 않습니다(기존 동작에 영향 없음).

## 동작 방식 (15분마다 실행)

1. **`sync.py`** — 두 블로그 RSS에서 `PD-SOURCE-ID` 주석이 있는 글만 찾아
   `pairs.json`에 누적 기록하고, 가장 최근 글 정보를 `latest.json`으로 내보냅니다.
   - `latest.json` 예시:
     ```json
     {
       "source_id": "PD-20260910-001",
       "title": "글 제목",
       "tistory_url": "https://500md87.com/entry/...",
       "blogspot_url": "https://projectpdlab.blogspot.com/2026/09/....html",
       "updated_at": "2026-09-10T10:00:00Z"
     }
     ```
   - 짝 글이 아직 없으면 `blogspot_url`이 빈 문자열입니다.
   - 최초 발견 후 90분이 지난 글은 제목을 넣은 인스타그램 카드 이미지(1080x1080 PNG)를
     `instagram_cards/`에 만들어둡니다.
2. **커밋 & 푸시** — 방금 만든 이미지가 `raw.githubusercontent.com`으로 바로 접근 가능하게
   먼저 저장소에 반영합니다(인스타그램이 이미지를 내려받으려면 URL이 공개돼 있어야 하기
   때문에, 게시보다 먼저 커밋합니다).
3. **`instagram_publish.py`** — 이미지가 준비됐고 90분이 지났고 아직 인스타그램에 안 올린
   글을 골라, 인스타그램 Graph API로 카드 이미지 + 캡션(제목 + 티스토리/블로그스팟 링크 중
   무작위 하나 + 해시태그)을 게시합니다. `IG_ACCESS_TOKEN` / `IG_USER_ID` 시크릿이 아직
   등록되지 않았으면 조용히 건너뜁니다(에러 없이 정상 종료) — 나중에 시크릿만 등록하면
   바로 이어서 동작합니다.
4. **커밋 & 푸시** — 게시 결과(`instagram_posted` 등)를 다시 기록합니다.

## latest.json을 기존 쓰레드 자동화가 읽는 방법

건강블로그 쓰레드 자동 발행(Make.com "건강블로그 스레드 자동게시" 시나리오)의 "홍보" 분기에
이 저장소의 `latest.json`
(`https://raw.githubusercontent.com/taeseongk1218-cpu/project-pd-automation/main/latest.json`)
을 조회하는 단계가 들어 있어서, 그 글의 제목이 방금 RSS로 읽은 최신 글과 같고
`blogspot_url`이 있으면 티스토리/블로그스팟 링크 중 하나를 무작위로 고르도록 되어 있습니다.
`blogspot_url`이 없거나 이 조회가 실패하면 항상 기존처럼 티스토리 링크만 씁니다 — 즉
이 파일이 없거나 이상해도 기존 쓰레드 발행은 절대 멈추지 않습니다.

## 최초 설정 (한 번만)

### 1) 시크릿 등록 (인스타그램 자동 게시를 켜려면)

저장소의 **Settings → Secrets and variables → Actions → New repository secret**에서:

- `IG_ACCESS_TOKEN` — 인스타그램 비즈니스 계정(건강블로그 계정)의 콘텐츠 게시 권한이
  있는 액세스 토큰
- `IG_USER_ID` — 그 계정의 인스타그램 사용자 ID

두 시크릿을 등록하기 전까지는 매칭·카드 생성까지는 정상 동작하고, 인스타그램 게시만
자동으로 건너뜁니다.

## 수동 실행 (테스트)

**Actions** 탭 → **Health Blog Cross-Post Sync** 워크플로우 → **Run workflow** 버튼으로
언제든 즉시 한 번 실행해볼 수 있습니다.

## 다시 처리하고 싶을 때

`pairs.json`에서 해당 `PD-SOURCE-ID` 항목을 지우고 커밋하면, 다음 실행 때 처음부터 다시
매칭·인스타그램 게시 대상이 됩니다. 인스타그램만 다시 올리고 싶으면 그 항목의
`instagram_posted`를 `false`로 바꾸세요(`instagram_image_committed`는 `true`로 둬도 됨 -
이미지가 이미 있으면 다시 만들지 않고 그대로 재사용합니다).
# project-pd-automation
