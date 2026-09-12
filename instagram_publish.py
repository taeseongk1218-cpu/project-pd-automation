#!/usr/bin/env python3
"""
sync.py가 만들어둔(그리고 이미 커밋되어 공개 URL로 접근 가능한) 인스타그램 카드 이미지를
실제로 인스타그램에 올린다. sync.py의 커밋/푸시가 끝난 "다음" 워크플로우 단계에서 실행해야
한다 - 인스타그램이 image_url을 내려받을 수 있으려면 그 이미지가 이미 GitHub에 반영되어 있어야
하기 때문이다.

IG_ACCESS_TOKEN / IG_USER_ID 시크릿이 아직 없으면 아무 것도 하지 않고 조용히 끝난다
(자격 증명을 나중에 등록해도 안전하게 이어서 쓸 수 있도록).

발행 규칙(사용자 지정):
  - 글 하나당 퀄리티 높은 게시물 1개만 올린다 (기존과 동일).
  - 같은 날 여러 글이 밀려서 올라올 경우를 대비해, 인스타그램 게시물 사이에는
    최소 4시간 간격을 둔다 - 간격이 안 됐으면 이번 실행에서는 건너뛰고 다음 정기 실행
    (15분 주기)에서 다시 확인한다.
  - 매번 몇 분씩 무작위로 늦춰 발행해서 매일 똑같은 분(分)에 올라가지 않게 한다.
"""
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAIRS_PATH = os.path.join(BASE_DIR, "pairs.json")
STATE_PATH = os.path.join(BASE_DIR, "instagram_state.json")

RAW_BASE = (
    "https://raw.githubusercontent.com/taeseongk1218-cpu/project-pd-automation/main/"
    "instagram_cards"
)

API_BASE = os.environ.get("IG_API_BASE", "https://graph.instagram.com/v21.0")

MIN_GAP_HOURS = 4
KST = timezone(timedelta(hours=9))
POST_START_HOUR = 8
POST_END_HOUR = 22
JITTER_MAX_SEC = 9 * 60


def log(msg):
    print(msg, file=sys.stderr)


def fetch(url, data=None, method=None, timeout=30):
    req = urllib.request.Request(
        url, data=data, method=method, headers={"User-Agent": "health-crosspost-sync bot"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_caption(title, chosen_url, source_id):
    return (
        f"📺 오늘 방송에서 눈여겨볼 이야기\n\n"
        f"{title}\n\n"
        f"방송에서 화제가 된 내용을 바탕으로 핵심만 다시 정리했습니다. "
        f"궁금했던 포인트를 확인해 보세요.\n\n"
        f"자세한 내용은 아래 글에서 확인할 수 있습니다.\n"
        f"{chosen_url}\n\n"
        f"PROJECT PD · {source_id}\n\n"
        f"#오늘의방송 #방송트렌드 #화제의정보 #프로젝트PD"
    )


def create_container(user_id, token, image_url, caption):
    params = {"image_url": image_url, "caption": caption, "access_token": token}
    data = urllib.parse.urlencode(params).encode()
    body = fetch(f"{API_BASE}/{user_id}/media", data=data, method="POST")
    result = json.loads(body)
    if "id" not in result:
        raise RuntimeError(f"media 컨테이너 생성 실패: {result}")
    return result["id"]


def wait_until_ready(creation_id, token, timeout_sec=60):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        url = f"{API_BASE}/{creation_id}?" + urllib.parse.urlencode(
            {"fields": "status_code", "access_token": token}
        )
        try:
            body = fetch(url, method="GET")
            data = json.loads(body)
            sc = data.get("status_code")
            if sc == "FINISHED":
                return
            if sc == "ERROR":
                raise RuntimeError(f"컨테이너 처리 에러: {data}")
        except Exception as e:
            log(f"상태 확인 실패(재시도): {e}")
        time.sleep(3)


def publish_container(user_id, token, creation_id):
    params = {"creation_id": creation_id, "access_token": token}
    data = urllib.parse.urlencode(params).encode()
    body = fetch(f"{API_BASE}/{user_id}/media_publish", data=data, method="POST")
    result = json.loads(body)
    if "id" not in result:
        raise RuntimeError(f"게시 실패: {result}")
    return result["id"]


def main():
    token = os.environ.get("IG_ACCESS_TOKEN")
    user_id = os.environ.get("IG_USER_ID")
    if not token or not user_id:
        log("IG_ACCESS_TOKEN / IG_USER_ID 시크릿이 아직 없습니다 - 인스타그램 발행 단계는 건너뜁니다.")
        return

    pairs = load_json(PAIRS_PATH, {})
    state = load_json(STATE_PATH, {"last_posted_at": ""})
    now = datetime.now(timezone.utc)
    kst_now = now.astimezone(KST)
    kst_minutes = kst_now.hour * 60 + kst_now.minute

    if not (POST_START_HOUR * 60 <= kst_minutes < POST_END_HOUR * 60):
        log("인스타그램 게시 가능 시간(한국시간 08:00~22:00)이 아니어서 이번 실행은 건너뜁니다.")
        return

    last_posted_at = state.get("last_posted_at")
    if last_posted_at:
        gap_hours = (now - parse_iso(last_posted_at)).total_seconds() / 3600
        if gap_hours < MIN_GAP_HOURS:
            log(f"마지막 인스타그램 게시로부터 {gap_hours:.1f}시간 경과 (최소 {MIN_GAP_HOURS}시간 필요) - 이번 실행은 건너뜁니다.")
            return

    due = None
    due_sid = None
    for sid, rec in sorted(
        pairs.items(),
        key=lambda kv: kv[1].get("first_seen_at", "")
    ):
        if rec.get("instagram_posted"):
            continue
        if not rec.get("instagram_image_committed"):
            continue
        due, due_sid = rec, sid
        break

    if not due:
        return

    title = due.get("tistory", {}).get("title") or due.get("blogspot", {}).get("title")
    urls = [due[p]["url"] for p in ("tistory", "blogspot") if p in due]
    if not title or not urls:
        return

    jitter = random.randint(0, JITTER_MAX_SEC)
    log(f"{jitter}초 무작위 대기 후 발행합니다 (매일 다른 시각처럼 보이게 하기 위함).")
    time.sleep(jitter)

    chosen_url = random.choice(urls)
    image_url = f"{RAW_BASE}/{due_sid}.png"
    caption = build_caption(title, chosen_url, due_sid)

    try:
        creation_id = create_container(user_id, token, image_url, caption)
        wait_until_ready(creation_id, token)
        media_id = publish_container(user_id, token, creation_id)
        due["instagram_posted"] = True
        due["instagram_posted_at"] = now_iso()
        due["instagram_media_id"] = media_id
        due["instagram_chosen_url"] = chosen_url
        state["last_posted_at"] = now_iso()
        save_json(PAIRS_PATH, pairs)
        save_json(STATE_PATH, state)
        log(f"{due_sid}: 인스타그램 게시 완료 ({media_id})")
    except Exception as e:
        log(f"{due_sid}: 인스타그램 게시 실패 - {e}")


if __name__ == "__main__":
    main()
