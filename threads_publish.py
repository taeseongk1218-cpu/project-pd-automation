#!/usr/bin/env python3
"""
스레드(Threads) 자동 발행 — Make.com을 대체하는 GitHub Actions 버전.

동작 원칙(사용자 지정):
  1. 하루 7번(08:00 / 10:30 / 13:00 / 15:00 / 17:20 / 19:40 / 22:00, KST 기준) 실행된다.
     실제 실행 시각은 cron이 트리거하지만, 이 스크립트가 시작하자마자 0~9분 무작위로
     대기(jitter)한 뒤 발행해서 매일 정확히 같은 분에 올라가지 않게 한다.
  2. pairs.json(=sync.py가 관리하는 티스토리/블로그스팟 매칭 결과)을 보고,
     "아직 스레드에 한 번도 소개 안 된 새 블로그 글"이 있으면 그 글을 최우선으로 홍보한다.
  3. 새 글이 없으면, 바로 전에 홍보하던 글의 '다른 관점' 문구를 이어서 올린다.
     단, 한 블로그 글당 관점이 다른 문구는 최대 3개까지만 쓴다.
  4. 3개를 다 썼는데 새 글도 없으면, 블로그 내용과 무관한 일반 건강 팁(tips.json)을 올린다.

관점 문구(angles)는 원래 블로그 글쓰기 스킬이 발행 시점에 함께 만들어서
pairs.json의 해당 글 레코드에 angles 배열로 채워주는 것을 전제로 설계했다.
아직 그 연동이 없는 동안에는, 이 스크립트가 제목을 기반으로 3가지 톤의
문구를 자동으로 만들어 대신 사용한다 (아래 AUTO_ANGLE_TEMPLATES) — 나중에 스킬이
angles를 채워주기 시작하면 자동으로 그쪽을 우선 사용한다.

필요한 GitHub Secrets: THREADS_ACCESS_TOKEN, THREADS_USER_ID
(둘 중 하나라도 없으면 조용히 아무 것도 하지 않고 끝난다.)
"""
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAIRS_PATH = os.path.join(BASE_DIR, "pairs.json")
TIPS_PATH = os.path.join(BASE_DIR, "tips.json")
STATE_PATH = os.path.join(BASE_DIR, "threads_state.json")

API_BASE = os.environ.get("THREADS_API_BASE", "https://graph.threads.net/v1.0")

JITTER_MAX_SEC = 9 * 60
PUBLISH_WAIT_SEC = 30

SUFFIX = "\n\n[500md87 건강블로그 새 글]"

AUTO_ANGLE_TEMPLATES = [
    lambda title: title,
    lambda title: f"오늘 다시 짚어보는 이야기 — {title}",
    lambda title: f"이거 놓치면 아쉬워요 — {title}",
]


def log(msg):
    print(msg, file=sys.stderr)


def fetch(url, data=None, method=None, timeout=30):
    req = urllib.request.Request(
        url, data=data, method=method, headers={"User-Agent": "health-crosspost-sync bot"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


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


def create_container(user_id, token, text):
    params = {"media_type": "TEXT", "text": text, "access_token": token}
    data = urllib.parse.urlencode(params).encode()
    body = fetch(f"{API_BASE}/{user_id}/threads", data=data, method="POST")
    result = json.loads(body)
    if "id" not in result:
        raise RuntimeError(f"스레드 컨테이너 생성 실패: {result}")
    return result["id"]


def publish_container(user_id, token, creation_id):
    params = {"creation_id": creation_id, "access_token": token}
    data = urllib.parse.urlencode(params).encode()
    body = fetch(f"{API_BASE}/{user_id}/threads_publish", data=data, method="POST")
    result = json.loads(body)
    if "id" not in result:
        raise RuntimeError(f"스레드 발행 실패: {result}")
    return result["id"]


def post_text(user_id, token, text):
    creation_id = create_container(user_id, token, text)
    time.sleep(PUBLISH_WAIT_SEC)
    return publish_container(user_id, token, creation_id)


def pick_url(rec):
    urls = [rec[p]["url"] for p in ("tistory", "blogspot") if p in rec]
    return random.choice(urls) if urls else None


def build_promo_text(rec, idx):
    title = rec.get("tistory", {}).get("title") or rec.get("blogspot", {}).get("title") or ""
    url = pick_url(rec)
    angles = rec.get("angles") or []
    if idx < len(angles) and angles[idx]:
        body = angles[idx]
    else:
        body = AUTO_ANGLE_TEMPLATES[min(idx, len(AUTO_ANGLE_TEMPLATES) - 1)](title)
    if url:
        return f"{body}\n\n{url}{SUFFIX}"
    return f"{body}{SUFFIX}"


def choose_action(pairs, state):
    candidates = [
        (sid, rec)
        for sid, rec in pairs.items()
        if "tistory" in rec
    ]

    # 1. 아직 Threads에 한 번도 소개하지 않은 새 글이 있으면 새 글 최우선
    new_candidates = [
        (sid, rec)
        for sid, rec in candidates
        if rec.get("threads_angles_posted", 0) == 0
    ]

    if new_candidates:
        sid, rec = max(
            new_candidates,
            key=lambda kv: kv[1].get("first_seen_at", "")
        )
        state["current_source_id"] = sid
        return "promo", sid, 0

    # 2. 새 글이 없으면 관점 3개를 아직 다 쓰지 않은 기존 글 중
    #    Threads 우선순위 점수가 가장 높은 글을 선택
    remaining = [
        (sid, rec)
        for sid, rec in candidates
        if 0 < rec.get("threads_angles_posted", 0) < 3
    ]

    if remaining:
        sid, rec = max(
            remaining,
            key=lambda kv: (
                float(kv[1].get("threads_priority", 0) or 0),
                kv[1].get("first_seen_at", "")
            )
        )

        posted = rec.get("threads_angles_posted", 0)
        state["current_source_id"] = sid
        return "promo", sid, posted

    # 3. 모든 글의 관점 3개를 다 사용한 경우에만 일반 건강 팁
    return "tip", None, None


def main():
    token = os.environ.get("THREADS_ACCESS_TOKEN")
    user_id = os.environ.get("THREADS_USER_ID")
    if not token or not user_id:
        log("THREADS_ACCESS_TOKEN / THREADS_USER_ID 시크릿이 아직 없습니다 - 스레드 발행은 건너뜁니다.")
        return

    jitter = random.randint(0, JITTER_MAX_SEC)
    log(f"{jitter}초 무작위 대기 후 발행합니다.")
    time.sleep(jitter)

    pairs = load_json(PAIRS_PATH, {})
    tips_data = load_json(TIPS_PATH, {"tips": []})
    tips = tips_data.get("tips", [])
    state = load_json(STATE_PATH, {"current_source_id": "", "tip_index": 0, "last_posted_at": ""})

    action, sid, idx = choose_action(pairs, state)

    if action == "promo":
        text = build_promo_text(pairs[sid], idx)
        log(f"홍보 글 발행: {sid} (관점 {idx + 1}/3)")
        media_id = post_text(user_id, token, text)
        pairs[sid]["threads_angles_posted"] = idx + 1
        pairs[sid]["threads_last_posted_at"] = now_iso()
        state["current_source_id"] = sid
        state["last_posted_at"] = now_iso()
        save_json(PAIRS_PATH, pairs)
        save_json(STATE_PATH, state)
        log(f"완료: {media_id}")
    else:
        if not tips:
            log("일반 팁 목록이 비어 있어 올릴 내용이 없습니다.")
            return
        tip_index = state.get("tip_index", 0) % len(tips)
        text = tips[tip_index]
        log(f"일반 팁 발행: #{tip_index + 1}")
        media_id = post_text(user_id, token, text)
        state["tip_index"] = (tip_index + 1) % len(tips)
        state["last_posted_at"] = now_iso()
        save_json(STATE_PATH, state)
        log(f"완료: {media_id}")


if __name__ == "__main__":
    main()
