#!/usr/bin/env python3
"""
500md87.com(티스토리) <-> projectpdlab.blogspot.com(블로그스팟) 글 매칭 + 인스타그램 카드 준비.

흐름:
  1. 두 블로그의 RSS를 각각 읽어서, 본문 안에 숨겨진
     `<!-- PD-SOURCE-ID:PD-YYYYMMDD-NNN -->` 주석이 있는 글만 골라낸다.
     (이 주석은 글 작성 시 직접 넣는 것으로, 같은 원본 소스로 만든 티스토리 글과
     블로그스팟 글에 같은 SOURCE ID를 넣어두면 이 스크립트가 서로 짝을 맞춘다.)
  2. `pairs.json`에 SOURCE ID별로 티스토리/블로그스팟 URL·제목·최초 발견 시각을 누적 기록한다.
  3. 가장 최근에 발견된(=first_seen_at이 가장 늦은) 글 정보를 `latest.json`으로 따로 내보낸다.
     기존 쓰레드(Threads) 자동 발행 시나리오(Make.com)가 이 파일을 읽어서, 티스토리 링크와
     블로그스팟 링크 중 하나를 무작위로 골라 쓴다. (블로그스팟 글이 아직 없으면
     blogspot_url이 빈 문자열이라 기존처럼 티스토리 링크만 쓰인다 - 안전한 기본값)
  4. 최초 발견 후 90분이 지났고 아직 인스타그램에 올리지 않은 글은, 제목을 넣은 카드
     이미지를 만들어 커밋한다(실제 인스타그램 게시는 이 스크립트가 아니라
     instagram_publish.py가, 이미지가 저장소에 반영된 다음 실행 단계에서 처리한다 -
     인스타그램이 이미지를 내려받을 수 있으려면 그 URL이 이미 공개되어 있어야 하기 때문).

이 스크립트는 기존 쓰레드 자동화(Make.com 시나리오, gov-thread-autopost)를 전혀 건드리지
않는다 - 이 저장소 안에서만 동작하고 새 파일만 만든다.
"""
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from card import make_title_card

TISTORY_RSS = "https://500md87.com/rss"
BLOGSPOT_RSS = "https://projectpdlab.blogspot.com/feeds/posts/default?alt=rss"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAIRS_PATH = os.path.join(BASE_DIR, "pairs.json")
LATEST_PATH = os.path.join(BASE_DIR, "latest.json")
CARDS_DIR = os.path.join(BASE_DIR, "instagram_cards")

SOURCE_ID_RE = re.compile(r"PD-SOURCE-ID:\s*(PD-\d{8}-\d{3})")
THREADS_PRIORITY_RE = re.compile(r"PD-THREADS-PRIORITY:\s*(\d{1,3})")


def log(msg):
    print(msg, file=sys.stderr)


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item"):
        title = html.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        desc = html.unescape(item.findtext("description") or "")
        if not desc:
            content_encoded = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            desc = html.unescape(content_encoded or "")
        items.append({"title": title, "link": link, "desc": desc})
    return items


def extract_source_id(desc):
    m = SOURCE_ID_RE.search(desc)
    return m.group(1) if m else None


def extract_threads_priority(desc):
    m = THREADS_PRIORITY_RE.search(desc)
    if not m:
        return 0
    return max(0, min(100, int(m.group(1))))

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def collect_matches(pairs, now):
    for label, url in (("tistory", TISTORY_RSS), ("blogspot", BLOGSPOT_RSS)):
        try:
            items = parse_feed(fetch(url))
        except Exception as e:
            log(f"{label} RSS 가져오기 실패 (이번 실행은 건너뜀): {e}")
            continue

        for item in items:
            sid = extract_source_id(item["desc"])
            if not sid:
                continue
            rec = pairs.setdefault(sid, {})
            priority = extract_threads_priority(item["desc"])

            if priority > 0:
                rec["threads_priority"] = priority
            else:
                rec.setdefault("threads_priority", 0)
            if label not in rec:
                rec[label] = {"url": item["link"], "title": item["title"], "found_at": now}
                log(f"{sid}: {label} 글 매칭 등록 - {item['title']}")
            found_ats = [rec[p]["found_at"] for p in ("tistory", "blogspot") if p in rec]
            rec["first_seen_at"] = min(found_ats)
            rec.setdefault("instagram_posted", False)
            rec.setdefault("instagram_image_committed", False)


def write_latest(pairs, now):
    candidates = [(sid, rec) for sid, rec in pairs.items() if "tistory" in rec]
    if not candidates:
        log("아직 PD-SOURCE-ID가 붙은 글이 없습니다 (정상 - 앞으로 새 글부터 적용됩니다).")
        return
    sid, latest = max(candidates, key=lambda kv: kv[1]["first_seen_at"])
    latest_out = {
        "source_id": sid,
        "title": latest["tistory"]["title"],
        "tistory_url": latest["tistory"]["url"],
        "blogspot_url": latest.get("blogspot", {}).get("url", ""),
        "updated_at": now,
    }
    save_json(LATEST_PATH, latest_out)
    log(f"latest.json 갱신: {latest_out['title']} (블로그스팟 짝: {'있음' if latest_out['blogspot_url'] else '아직 없음'})")


def generate_due_cards(pairs, now):
    os.makedirs(CARDS_DIR, exist_ok=True)
    now_dt = parse_iso(now)
    for sid, rec in pairs.items():
        if rec.get("instagram_posted") or rec.get("instagram_image_committed"):
            continue
        age_min = (now_dt - parse_iso(rec["first_seen_at"])).total_seconds() / 60
        
            
        title = rec.get("tistory", {}).get("title") or rec.get("blogspot", {}).get("title")
        if not title:
            continue
        img_path = os.path.join(CARDS_DIR, f"{sid}.png")
        try:
            make_title_card(title, img_path)
            rec["instagram_image_committed"] = True
            log(f"{sid}: 인스타그램 카드 이미지 생성 완료 ({age_min:.0f}분 경과)")
        except Exception as e:
            log(f"{sid}: 카드 이미지 생성 실패 - {e}")


def main():
    now = now_iso()
    pairs = load_json(PAIRS_PATH, {})

    collect_matches(pairs, now)
    save_json(PAIRS_PATH, pairs)

    write_latest(pairs, now)

    generate_due_cards(pairs, now)
    save_json(PAIRS_PATH, pairs)


if __name__ == "__main__":
    main()
