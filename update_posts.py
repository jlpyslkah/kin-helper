# -*- coding: utf-8 -*-
"""블로그 글 수집 → posts.js 생성 (GitHub Actions에서 매일 실행)"""
import datetime
import html
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

TISTORY_BLOGS = [
    "doitgothere.tistory.com",
    "dailymoment1.tistory.com",
    "careerselect.tistory.com",
    "aginggracefully.tistory.com",
    "smart-spender.tistory.com",
    "plansaver.tistory.com",
]
NAVER_BLOG_ID = "jlpyslkah"


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_retry(url, tries=3):
    for i in range(tries):
        try:
            return fetch(url)
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1 + i)


def tistory_post_urls(blog):
    xml = fetch_retry(f"https://{blog}/sitemap.xml")
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    urls = []
    for u in locs:
        path = urllib.parse.urlparse(u).path.strip("/")
        if re.fullmatch(r"\d+", path) or path.startswith("entry/"):
            urls.append(u)
    return urls


def page_title(url):
    try:
        page = fetch_retry(url)
    except Exception:
        return None
    m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', page)
    if not m:
        m = re.search(r'content="([^"]*)"\s+property="og:title"', page)
    if not m:
        m = re.search(r"<title>(.*?)</title>", page, re.S)
    return html.unescape(m.group(1)).strip() if m else None


def collect_tistory(blog):
    urls = tistory_post_urls(blog)
    posts = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(page_title, u): u for u in urls}
        for f in as_completed(futs):
            t = f.result()
            if t:
                posts.append({"title": t, "url": futs[f], "blog": blog.split(".")[0]})
    print(f"[{blog}] {len(posts)}개", flush=True)
    return posts


def collect_naver(blog_id):
    posts = []
    page = 1
    while True:
        url = (f"https://blog.naver.com/PostTitleListAsync.naver?"
               f"blogId={blog_id}&currentPage={page}&countPerPage=30")
        try:
            data = json.loads(fetch_retry(url).replace("\\'", "'"))
        except Exception as e:
            print(f"[naver] page {page} 오류: {e}", flush=True)
            break
        plist = data.get("postList") or []
        if not plist:
            break
        for p in plist:
            title = urllib.parse.unquote_plus(p.get("title", ""))
            log_no = p.get("logNo", "")
            if title and log_no:
                posts.append({"title": title, "url": f"https://blog.naver.com/{blog_id}/{log_no}", "blog": "naver"})
        total = int(data.get("totalCount", 0) or 0)
        if total and len(posts) >= total:
            break
        page += 1
        time.sleep(0.3)
    print(f"[naver] {len(posts)}개", flush=True)
    return posts


def clean_title(t):
    for _ in range(3):
        t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def main():
    all_posts = collect_naver(NAVER_BLOG_ID)
    for b in TISTORY_BLOGS:
        try:
            all_posts.extend(collect_tistory(b))
        except Exception as e:
            print(f"[{b}] 실패: {e}", flush=True)

    seen = set()
    compact = []
    for p in all_posts:
        t = clean_title(p["title"])
        if len(t) < 4 or p["url"] in seen:
            continue
        seen.add(p["url"])
        compact.append({"t": t, "u": p["url"], "b": p["blog"]})

    # 수집이 크게 실패한 경우(절반 이하) 기존 파일 유지
    if len(compact) < 1300:
        raise SystemExit(f"수집 결과가 너무 적음({len(compact)}개) — posts.js 갱신 중단")

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    with open("posts.js", "w", encoding="utf-8") as f:
        f.write(f"// 내 블로그 글 목록 (자동 수집: {now} KST)\n")
        f.write(f'window.POSTS_UPDATED = "{now}";\n')
        f.write("window.POSTS = ")
        json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print(f"총 {len(compact)}개 -> posts.js ({now})", flush=True)


if __name__ == "__main__":
    main()
