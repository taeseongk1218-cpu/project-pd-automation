#!/usr/bin/env python3
"""
네이버 지식인(Kin) 홍보 후보 검색 자동화 - 초안 생성만, 자동 게시 없음

이 스크립트는 다음을 한다:
  1. 매 실행마다 티스토리(500md87.com) · 블로그스팟(projectpdlab.blogspot.com) ·
     네이버 블로그(blog.naver.com/neptune83) 세 곳의 RSS를 읽어서 새 게시물을 찾는다.
  2. 새 게시물 제목을 검색어로 삼아 네이버 검색 오픈 API(지식인 검색)로 관련 질문을 찾는다.
  3. 검색된 질문 중 상위 3개를 골라, 순수 답변 2개(링크 없음) + 홍보 답변 1개(링크 포함)로
     역할을 나눈다.
  4. 결과를 지식인 홍보 초안(kin_candidates.json)에 쌓는다 - 절대 지식인 사이트에 직접
     게시하지 않는다. 네이버 지식인은 공식 게시 API가 없고, Project PD 정책상 지식인 답변은
     항상 사람이 직접 로그인해서 검토 후 올리기로 되어 있기 때문이다.

주의: 이 스크립트가 만드는 초안 문구는 틀(뼈대)일 뿐이다.
실제로 지식인에 게시되면 안 될 수준이므로, 반드시 사람이 직접 확인하고 다듬은 후에
게시하세요 - 이 초안은 최종 답변 수준의 글이 아니다.

필요한 GitHub Secrets: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET (네이버 오픈 API 검색용 - 검색용
계정은 무료다). 없으면 아무 것도 하지 않고 종료한다.
"""
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

TISTORY_RSS = "https://500md87.com/rss"
BLOGSPOT_RSS = "https://projectpdlab.blogspot.com/feeds/posts/default?alt=rss"
NAVER_RSS = "https://rss.blog.naver.com/neptune83.xml"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATES_PATH = os.path.join(BASE_DIR, "kin_candidates.json")
STATE_PATH = os.path.join(BASE_DIR, "kin_state.json")

KIN_API = "https://openapi.naver.com/v1/search/kin.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

MAX_QUESTIONS_PER_POST = 3
MAX_NEW_POSTS_PER_RUN = 5  # 한 번에 너무 많이 처리하지 않도록 - 검색 API 호출량 제한


def log(msg):
    print(msg, file=sys.stderr)


def fetch(url, timeout=20, headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall("./channel/item"):
        title = html.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        if title and link:
            items.append({"title": title, "link": link})
    return items


def strip_title_noise(title):
    # 검색에 방해되는 괄호·특수문자·이모지 등을 제거한다
    title = re.sub(r"[\[\(].*?[\]\)]", " ", title)
    title = re.sub(r"[^\w\s가-힣]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


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


def collect_new_posts(state):
    processed = set(state.get("processed_links", []))
    new_posts = []
    for blog_label, url in (("tistory", TISTORY_RSS), ("blogspot", BLOGSPOT_RSS), ("naver", NAVER_RSS)):
        try:
            items = parse_feed(fetch(url))
        except Exception as e:
            log(f"{blog_label} RSS 가져오기 실패 (이번 실행은 건너뜀): {e}")
            continue
        for item in items:
            if item["link"] in processed:
                continue
            new_posts.append({"blog": blog_label, "title": item["title"], "link": item["link"]})
    return new_posts


def search_kin(query, client_id, client_secret, display=10):
    params = urllib.parse.urlencode({"query": query, "display": display, "sort": "sim"})
    body = fetch(
        f"{KIN_API}?{params}",
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
    )
    data = json.loads(body)
    results = []
    for item in data.get("items", []):
        title = re.sub(r"</?b>", "", html.unescape(item.get("title", "")))
        link = item.get("link", "")
        if title and link:
            results.append({"title": title, "link": link})
    return results


def build_draft(role, post_title, post_url, question_title):
    note = "[클로드나 사람이 직접 다듬어서 실제 질문·상황에 맞는지 확인한 뒤에 게시하세요 - 이 초안은 뼈대일 뿐입니다]"
    if role == "promo":
        return (
            f"(홍보용 · 링크 포함) '{question_title}' 질문에, 관련 정리해둔 "
            f"'{post_title}' 글에서 도움 될 만한 내용을 찾을 수 있어요.\n{post_url}\n\n{note}"
        )
    return (
        f"(순수용 · 링크 없음) '{question_title}' 질문에 순수 답변만 - "
        f"질문자 상황에 맞게 구체적으로 풀어서 쓸 것.\n\n{note}"
    )


def main():
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        log("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 시크릿이 아직 없습니다 - 지식인 검색은 건너뜁니다.")
        return

    state = load_json(STATE_PATH, {"processed_links": []})
    candidates = load_json(CANDIDATES_PATH, [])

    new_posts = collect_new_posts(state)[:MAX_NEW_POSTS_PER_RUN]
    if not new_posts:
        log("새 게시물 없음.")
        return

    for post in new_posts:
        query = strip_title_noise(post["title"])[:40]
        try:
            results = search_kin(query, client_id, client_secret)
        except Exception as e:
            log(f"지식인 검색 실패 ({post['link']}): {e}")
            continue

        top = results[:MAX_QUESTIONS_PER_POST]
        if not top:
            log(f"관련 지식인 질문 없음: {post['title']}")
            state["processed_links"].append(post["link"])
            continue

        questions = []
        for idx, q in enumerate(top):
            role = "promo" if idx == len(top) - 1 else "pure"
            questions.append({
                "question_title": q["title"],
                "question_link": q["link"],
                "role": "홍보(링크 포함)" if role == "promo" else "순수답변(링크 없음)",
                "draft": build_draft(role, post["title"], post["link"], q["title"]),
            })

        candidates.append({
            "source_blog": post["blog"],
            "post_title": post["title"],
            "post_url": post["link"],
            "generated_at": now_iso(),
            "questions": questions,
            "posted_manually": False,
        })
        state["processed_links"].append(post["link"])
        log(f"{post['blog']} / {post['title']}: 지식인 후보 {len(questions)}개 생성")

    save_json(CANDIDATES_PATH, candidates)
    save_json(STATE_PATH, state)


if __name__ == "__main__":
    main()
