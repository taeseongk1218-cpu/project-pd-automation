#!/usr/bin/env python3
"""
sync.py가 만들어둔(그리고 이미 커밋되어 공개 URL로 접근 가능한) 인스타그램 카드 이미지를
실제로 인스타그램에 올린다. sync.py의 커밋/푸시가 끝난 "다음" 워크플로우 단계에서 실행해야
한다 - 인스타그램이 image_url을 내려받으려면 그 이미지가 이미 GitHub에 반영되어 있어야
하기 때문이다.

IG_ACCESS_TOKEN / IG_USER_ID 시크릿이 아직 없으면 아무 것도 하지 않고 조용히 끝난다
(자격 증명을 나중에 등록해도 안전하게 이어서 쓸 수 있도록).
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

# 이 저장소(project-pd-automation)의 raw 파일 경로. 저장소/브랜치/경로를 바꾸면 여기도 맞춰 바꿔야 한다.
RAW_BASE = (
    "https://raw.githubusercontent.com/taeseongk1218-cpu/project-pd-automation/main/"
    "instagram_cards"
)

# Instagram Login 기반 Graph API 기본값(instagram_business_basic 등 신규 권한 체계).
# 만약 페이스북 페이지 연결형(구) 토큰을 쓴다면 IG_API_BASE 시크릿으로
# https://graph.facebook.com/v21.0 를 넣어서 덮어쓸 수 있다.
API_BASE = os.environ.get("IG_API_BASE", "https://graph.instagram.com/v21.0")

INSTAGRAM_DELAY_MIN = 90


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


def load_pairs():
    with open(PAIRS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pairs(pairs):
    with open(PAIRS_PATH, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_caption(title, chosen_url):
    return (
        f"{title}\n\n"
        f"{chosen_url}\n\n"
        f"[500md87 건강블로그 새 글]\n\n"
        f"#건강정보 #건강블로그 #오늘의건강"
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

    pairs = load_pairs()
    now = datetime.now(timezone.utc)
    changed = False

    for sid, rec in pairs.items():
        if rec.get("instagram_posted"):
            continue
        if not rec.get("instagram_image_committed"):
            continue
        age_min = (now - parse_iso(rec["first_seen_at"])).total_seconds() / 60
        if age_min < INSTAGRAM_DELAY_MIN:
            continue

        title = rec.get("tistory", {}).get("title") or rec.get("blogspot", {}).get("title")
        urls = [rec[p]["url"] for p in ("tistory", "blogspot") if p in rec]
        if not title or not urls:
            continue
        chosen_url = random.choice(urls)
        image_url = f"{RAW_BASE}/{sid}.png"
        caption = build_caption(title, chosen_url)

        try:
            creation_id = create_container(user_id, token, image_url, caption)
            wait_until_ready(creation_id, token)
            media_id = publish_container(user_id, token, creation_id)
            rec["instagram_posted"] = True
            rec["instagram_posted_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            rec["instagram_media_id"] = media_id
            rec["instagram_chosen_url"] = chosen_url
            changed = True
            log(f"{sid}: 인스타그램 게시 완료 ({media_id})")
        except Exception as e:
            log(f"{sid}: 인스타그램 게시 실패 - {e}")

    if changed:
        save_pairs(pairs)


if __name__ == "__main__":
    main()
