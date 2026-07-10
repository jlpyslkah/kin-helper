# -*- coding: utf-8 -*-
"""블로그 글 제목+주소 수집 스크립트 (티스토리 6곳 + 네이버 1곳)"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
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
        # 글 주소: 숫자 또는 /entry/... 형태만 (category/tag/guestbook 등 제외)
        if re.fullmatch(r"\d+", path) or path.startswith("entry/"):
            urls.append(u)
    return urls


def page_title(url):
    try:
        html = fetch_retry(url)
    except Exception:
        return None
    m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
    if not m:
        m = re.search(r'content="([^"]*)"\s+property="og:title"', html)
    if m:
        import html as h
        return h.unescape(m.group(1)).strip()
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m:
        import html as h
        return h.unescape(m.group(1)).strip()
    return None


def collect_tistory(blog):
    urls = tistory_post_urls(blog)
    print(f"[{blog}] 글 URL {len(urls)}개 발견", flush=True)
    posts = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(page_title, u): u for u in urls}
        done = 0
        for f in as_completed(futs):
            u = futs[f]
            t = f.result()
            done += 1
            if done % 50 == 0:
                print(f"[{blog}] {done}/{len(urls)} 처리", flush=True)
            if t:
                posts.append({"title": t, "url": u, "blog": blog.split(".")[0]})
    print(f"[{blog}] 완료: 제목 수집 {len(posts)}개", flush=True)
    return posts


def collect_naver(blog_id):
    posts = []
    page = 1
    while True:
        url = (f"https://blog.naver.com/PostTitleListAsync.naver?"
               f"blogId={blog_id}&currentPage={page}&countPerPage=30")
        try:
            raw = fetch_retry(url)
            data = json.loads(raw.replace("\\'", "'"))
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
                posts.append({
                    "title": title,
                    "url": f"https://blog.naver.com/{blog_id}/{log_no}",
                    "blog": "naver",
                })
        total = int(data.get("totalCount", 0) or 0)
        print(f"[naver] page {page} 수집 (누적 {len(posts)}/{total})", flush=True)
        if total and len(posts) >= total:
            break
        page += 1
        time.sleep(0.3)
    print(f"[naver] 완료: {len(posts)}개", flush=True)
    return posts


def main():
    all_posts = []
    all_posts.extend(collect_naver(NAVER_BLOG_ID))
    for b in TISTORY_BLOGS:
        try:
            all_posts.extend(collect_tistory(b))
        except Exception as e:
            print(f"[{b}] 실패: {e}", flush=True)
    # 중복 제거
    seen = set()
    uniq = []
    for p in all_posts:
        if p["url"] in seen:
            continue
        seen.add(p["url"])
        uniq.append(p)
    out = sys.argv[1] if len(sys.argv) > 1 else "posts.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(uniq, f, ensure_ascii=False, indent=1)
    print(f"총 {len(uniq)}개 저장 -> {out}", flush=True)


if __name__ == "__main__":
    main()
