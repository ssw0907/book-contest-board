"""
독후감 공모전 크롤러

공모전 정보 사이트에서 '독후감' 공모전을 찾아 data/contests.json 에 자동으로 반영합니다.

실행:  python crawler/crawl.py
옵션:  --dry-run   파일은 고치지 않고 찾은 결과만 화면에 출력

동작 규칙
- 크롤러가 넣은 항목은 id가 'ck-'(공모전코리아) 또는 'wv-'(위비티)로 시작합니다.
- 사람이 직접 넣은 항목(그 밖의 id)은 절대 건드리지 않습니다.
- 사람이 넣은 항목과 제목이 같은 공모전은 크롤링 결과에서 뺍니다(사람이 넣은 정보 우선).
- 실제 공모전을 하나라도 찾으면 예시 데이터(source가 "예시 데이터")는 지웁니다.
- 마감된 지 KEEP_CLOSED_DAYS일이 지난 크롤링 항목은 지웁니다.
- 어떤 사이트가 접속에 실패하면, 그 사이트에서 예전에 가져온 항목은 그대로 둡니다.
"""

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "contests.json"

USER_AGENT = "Mozilla/5.0 (compatible; book-contest-board/1.0; +https://github.com/)"
REQUEST_DELAY = 1.5      # 요청 사이 대기 시간(초) — 사이트에 부담을 주지 않기 위해
MAX_PAGES = 3            # 사이트별로 읽을 검색 결과 페이지 수
KEEP_CLOSED_DAYS = 30    # 마감 후 며칠까지 남겨 둘지
MAX_POST_AGE_DAYS = 400  # 이보다 오래전에 올라온 글은 읽지 않음

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).date()

# 제목에 이 단어 중 하나가 있어야 독후감 공모전으로 봅니다.
TITLE_KEYWORDS = re.compile(r"독후감|독서\s*감상|독후\s*감상|서평|독서왕|독후\s*활동")

TARGETS = ["초등", "중등", "고등", "일반"]

SIDO = {
    "서울": ["서울"], "부산": ["부산"], "대구": ["대구"], "인천": ["인천"],
    "광주": ["광주광역시", "광주시교육청", "광주시립"], "대전": ["대전"], "울산": ["울산"],
    "세종": ["세종"], "경기": ["경기"], "강원": ["강원"], "충북": ["충북", "충청북도"],
    "충남": ["충남", "충청남도"], "전북": ["전북", "전라북도"], "전남": ["전남", "전라남도"],
    "경북": ["경북", "경상북도"], "경남": ["경남", "경상남도"], "제주": ["제주"],
}

# 시·군·구 이름 → 시·도 (제목·주최에 시도 이름이 없을 때 추정용)
CITY_TO_SIDO = {
    "경기": "수원 성남 고양 용인 부천 안산 안양 남양주 화성 평택 의정부 시흥 파주 김포 광명 광주시 군포 하남 오산 "
            "이천 안성 의왕 양주 구리 포천 동두천 과천 여주 양평 가평 연천",
    "강원": "춘천 원주 강릉 동해 태백 속초 삼척 홍천 횡성 영월 평창 정선 철원 화천 양구 인제 고성군 양양",
    "충북": "청주 충주 제천 보은 옥천 영동 증평 진천 괴산 음성 단양",
    "충남": "천안 공주 보령 아산 서산 논산 계룡 당진 금산 부여 서천 청양 홍성 예산 태안",
    "전북": "전주 군산 익산 정읍 남원 김제 완주 진안 무주 장수 임실 순창 고창 부안",
    "전남": "목포 여수 순천 나주 광양 담양 곡성 구례 고흥 보성 화순 장흥 강진 해남 영암 무안 함평 영광 장성 완도 진도 신안",
    "경북": "포항 경주 김천 안동 구미 영주 영천 상주 문경 경산 의성 청송 영양 영덕 청도 고령 성주 칠곡 예천 봉화 울진 울릉",
    "경남": "창원 진주 통영 사천 김해 밀양 거제 양산 의령 함안 창녕 남해 하동 산청 함양 거창 합천",
    "인천": "남동구 부평 계양 연수구 미추홀 강화 옹진",
    "서울": "강남구 강동구 강북구 강서구 관악 광진 구로 금천 노원 도봉 동대문 동작 마포 서대문 서초 성동 성북 송파 양천 "
            "영등포 용산 은평 종로 중랑",
    "부산": "해운대 수영구 사하구 사상구 금정구 기장 연제구 부산진",
}


# ---------------------------------------------------------------- 공통 도우미

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def get_soup(url):
    time.sleep(REQUEST_DELAY)
    res = session.get(url, timeout=20)
    res.raise_for_status()
    return BeautifulSoup(res.content, "html.parser")


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def norm_title(title):
    """중복 판단용: 연도·괄호·공백·기호를 지운 제목"""
    t = re.sub(r"20\d\d(년|학년도)?", "", title)
    t = re.sub(r"제\s*\d+\s*회", "", t)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t)


def is_same_contest(a, b):
    """(정리된 제목, 마감일) 두 개가 같은 공모전인지. 사이트마다 제목을 조금씩 다르게 적기 때문에 비슷하면 같다고 봅니다."""
    ratio = SequenceMatcher(None, a[0], b[0]).ratio()
    if a[1] and a[1] == b[1]:
        return ratio >= 0.5
    return ratio >= 0.9


def parse_period(text):
    """'2026.10.14 ~ 2026.11.22' 또는 '2026-10-14 ~ 2026-11-22' → (시작, 마감)"""
    found = re.findall(r"(20\d\d)[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", text or "")
    if len(found) < 2:
        return None, None
    try:
        start = date(int(found[0][0]), int(found[0][1]), int(found[0][2]))
        end = date(int(found[1][0]), int(found[1][1]), int(found[1][2]))
    except ValueError:
        return None, None
    return start.isoformat(), end.isoformat()


def _ordered(found):
    return [t for t in TARGETS if t in found]


def guess_targets(target_text, body):
    """
    대상 추정 순서
    1) 본문의 '부문'(초등부·청소년부·일반부 등)이 가장 정확하므로 먼저 봅니다.
    2) 없으면 대상 칸과 본문에 나온 학교급 단어를 봅니다.
    3) 그래도 없고 '누구나/전 국민'이라고만 적혀 있으면 전체로 봅니다.
    """
    body = body or ""
    found = set()
    if re.search(r"초등\s*(학생)?\s*부|초등\s*(저|고)학년\s*부?|어린이\s*부|아동\s*부", body):
        found.add("초등")
    if re.search(r"중\s*[·ㆍ.,/]?\s*고등?\s*(학생)?\s*(부|/)|청소년\s*부", body):
        found.update(["중등", "고등"])
    if re.search(r"(?<!고)중등\s*부|중학생?\s*부", body):
        found.add("중등")
    if re.search(r"(?<!중[·ㆍ])고등\s*(학생)?\s*부|고교\s*부", body):
        found.add("고등")
    if re.search(r"일반\s*부|성인\s*부|대학(생)?\s*부", body):
        found.add("일반")
    if found:
        return _ordered(found)

    text = f"{target_text or ''} {body}"
    if re.search(r"초등|어린이", text):
        found.add("초등")
    if re.search(r"중학|중등", text):
        found.add("중등")
    if re.search(r"고등|고교", text):
        found.add("고등")
    if "청소년" in text and not found & {"중등", "고등"}:
        found.update(["중등", "고등"])
    if re.search(r"일반인|대학생|성인", text):
        found.add("일반")
    if found:
        return _ordered(found)

    if re.search(r"누구나|제한\s*없|전\s*국민", text):
        return list(TARGETS)
    return []


def guess_region(title, organizer, body):
    """신청 가능한 지역을 추정합니다. '전국' 공모라고 적혀 있으면 전국."""
    if "전국" in title or re.search(r"전국\s*(의\s*)?(초등|중|고|청소년|학생|누구나|어린이|국민)", body or ""):
        return "전국"
    head = f"{title} {organizer}"
    for sido, words in SIDO.items():
        if any(w in head for w in words):
            return sido
    for sido, cities in CITY_TO_SIDO.items():
        if any(c in head for c in cities.split()):
            return sido
    return "전국"


def guess_book(body):
    text = body or ""
    if re.search(r"자유\s*도서|도서\s*(선정\s*)?자유|도서\s*제한\s*없", text):
        return "자유"
    if re.search(r"지정\s*도서|대상\s*도서|선정\s*도서|추천\s*도서|권장\s*도서|올해의\s*책|한\s*권의\s*책|도서\s*목록|중\s*1\s*권|\d+\s*권\s*\S*\s*(가운데|중에서)", text):
        return "지정도서"
    return "자유"


def make_item(id_, title, organizer, targets, region, start, end, book, prize, url, source):
    return {
        "id": id_,
        "title": title,
        "organizer": organizer or "정보 없음",
        "target": targets,
        "region": region,
        "startDate": start,
        "endDate": end,
        "bookRequirement": book,
        "prize": prize or "원문 참고",
        "url": url,
        "source": source,
        "updatedAt": TODAY.isoformat(),
    }


# ---------------------------------------------------------------- 공모전코리아

def crawl_contestkorea():
    base = "https://www.contestkorea.com/sub/"
    word = quote("독후감")
    items = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{base}list.php?int_gbn=1&Txt_bcode=&Txt_key=all&Txt_word={word}&page={page}"
        soup = get_soup(url)
        rows = soup.select(".list_style_2 > ul > li")
        if not rows:
            break
        too_old = False
        for li in rows:
            a = li.select_one(".title a")
            title_el = li.select_one(".title .txt")
            if not a or not title_el:
                continue
            title = clean(title_el.get_text())
            m = re.search(r"str_no=(\d+)", a.get("href", ""))
            if not m or not TITLE_KEYWORDS.search(title):
                continue
            str_no = m.group(1)
            try:
                posted = datetime.strptime(str_no[:8], "%Y%m%d").date()
                if (TODAY - posted).days > MAX_POST_AGE_DAYS:
                    too_old = True
                    continue
            except ValueError:
                pass
            try:
                item = contestkorea_detail(urljoin(base, a["href"]), str_no, title)
            except Exception as e:  # 한 건 실패는 건너뜀
                print(f"  [공모전코리아] {title} 상세 읽기 실패: {e}")
                continue
            if item:
                items.append(item)
        if too_old:
            break
    return items


def contestkorea_detail(url, str_no, title):
    soup = get_soup(url)
    fields = {}
    for tr in soup.select(".txt_area table tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            fields[clean(th.get_text())] = td
    period = fields.get("접수기간")
    start, end = parse_period(period.get_text() if period else "")
    if not start:
        print(f"  [공모전코리아] {title}: 접수기간을 찾지 못해 건너뜀")
        return None

    def text_of(key):
        return clean(fields[key].get_text(" ")) if key in fields else ""

    organizer = text_of("주최 . 주관")
    target_text = text_of("참가대상")
    prize = re.sub(r"^기타\s*:\s*", "", text_of("시상내역"))
    meta = soup.find("meta", attrs={"name": "description"})
    body = meta.get("content", "") if meta else ""

    official = None
    home = fields.get("홈페이지")
    if home:
        link = home.select_one("[val2]")
        if link and link.get("val2", "").startswith("http"):
            official = link["val2"]

    targets = guess_targets(target_text, body)
    if not targets:
        print(f"  [공모전코리아] {title}: 대상을 알 수 없어 건너뜀")
        return None
    return make_item(
        f"ck-{str_no}", title, organizer, targets,
        guess_region(title, organizer, body), start, end, guess_book(body), prize,
        official or url, "공모전코리아",
    )


# ---------------------------------------------------------------- 위비티

def crawl_wevity():
    base = "https://www.wevity.com/index.php"
    word = quote("독후감")
    items = []
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        soup = get_soup(f"{base}?c=find&s=1&sp=name&sw={word}&gp={page}")
        found_any = False
        for a in soup.select("ul.list li .tit a"):
            m = re.search(r"ix=(\d+)", a.get("href", ""))
            title = clean(a.find(string=True, recursive=False) or a.get_text())
            if not m:
                continue
            found_any = True
            ix = m.group(1)
            if ix in seen or not TITLE_KEYWORDS.search(title):
                continue
            seen.add(ix)
            try:
                item = wevity_detail(f"{base}?c=find&s=1&gbn=view&ix={ix}", ix, title)
            except Exception as e:
                print(f"  [위비티] {title} 상세 읽기 실패: {e}")
                continue
            if item:
                items.append(item)
        if not found_any:
            break
    return items


def wevity_detail(url, ix, title):
    soup = get_soup(url)
    fields = {}
    for li in soup.select("ul.cd-info-list > li"):
        label = li.select_one(".tit")
        if not label:
            continue
        key = clean(label.get_text())
        label.extract()
        fields[key] = li
    period = fields.get("접수기간")
    start, end = parse_period(period.get_text() if period else "")
    if not start:
        print(f"  [위비티] {title}: 접수기간을 찾지 못해 건너뜀")
        return None

    def text_of(key):
        return clean(fields[key].get_text(" ")) if key in fields else ""

    organizer = text_of("주최/주관")
    body_el = soup.select_one("#viewContents")
    body = clean(body_el.get_text(" ")) if body_el else ""
    prize = " / ".join(p for p in [
        f"1등 {text_of('1등 상금')}" if text_of("1등 상금") else "",
        f"총 상금 {text_of('총 상금')}" if text_of("총 상금") else "",
    ] if p)

    official = None
    home = fields.get("홈페이지")
    if home:
        link = home.find("a", href=True)
        if link and link["href"].startswith("http"):
            official = link["href"]

    # 위비티의 '응모대상'은 '어린이'처럼 뭉뚱그려 적힌 경우가 많아 본문도 함께 봅니다.
    targets = guess_targets(text_of("응모대상"), body[:600])
    if not targets:
        print(f"  [위비티] {title}: 대상을 알 수 없어 건너뜀")
        return None
    return make_item(
        f"wv-{ix}", title, organizer, targets,
        guess_region(title, organizer, body[:600]), start, end, guess_book(body), prize,
        official or url, "위비티",
    )


# ---------------------------------------------------------------- 합치기

SOURCES = [
    ("ck-", "공모전코리아", crawl_contestkorea),
    ("wv-", "위비티", crawl_wevity),
]


def is_crawled(item):
    return any(item.get("id", "").startswith(prefix) for prefix, _, _ in SOURCES)


def main():
    parser = argparse.ArgumentParser(description="독후감 공모전 크롤러")
    parser.add_argument("--dry-run", action="store_true", help="파일을 고치지 않고 결과만 출력")
    args = parser.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    existing = data.get("contests", [])
    manual = [c for c in existing if not is_crawled(c)]
    old_crawled = [c for c in existing if is_crawled(c)]

    crawled = []
    failed_prefixes = []
    for prefix, name, func in SOURCES:
        print(f"[{name}] 읽는 중…")
        try:
            got = func()
            print(f"[{name}] 독후감 공모전 {len(got)}건")
            crawled.extend(got)
        except Exception as e:
            print(f"[{name}] 실패 — 예전 항목을 유지합니다: {e}")
            failed_prefixes.append(prefix)
            crawled.extend(c for c in old_crawled if c["id"].startswith(prefix))

    # 실제 데이터가 생기면 예시 데이터는 뺌
    if crawled:
        manual = [c for c in manual if c.get("source") != "예시 데이터"]

    # 중복 제거: 사람이 넣은 항목 > 공모전코리아 > 위비티 순서로 우선
    taken = [(norm_title(c["title"]), c.get("endDate")) for c in manual]
    merged = []
    for c in crawled:
        key = (norm_title(c["title"]), c["endDate"])
        if any(is_same_contest(key, t) for t in taken):
            continue
        taken.append(key)
        merged.append(c)

    # 오래전에 마감됐거나 날짜가 뒤바뀐 항목 제거
    cutoff = (TODAY - timedelta(days=KEEP_CLOSED_DAYS)).isoformat()
    merged = [c for c in merged if c["endDate"] >= cutoff and c["startDate"] <= c["endDate"]]

    # 내용이 그대로면 예전 updatedAt 유지 (매일 불필요한 변경이 생기지 않게)
    old_by_id = {c["id"]: c for c in old_crawled}
    for c in merged:
        old = old_by_id.get(c["id"])
        if old and {k: v for k, v in old.items() if k != "updatedAt"} == \
                {k: v for k, v in c.items() if k != "updatedAt"}:
            c["updatedAt"] = old.get("updatedAt", c["updatedAt"])

    result = manual + merged
    print(f"\n결과: 직접 입력 {len(manual)}건 + 크롤링 {len(merged)}건 = {len(result)}건")
    for c in merged:
        print(f"  {c['endDate']} 마감 | {c['region']:>2} | {','.join(c['target'])} | {c['bookRequirement']} | {c['title']}")

    if args.dry_run:
        print("\n(--dry-run: 파일은 고치지 않았습니다)")
        return 0

    data["contests"] = result
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{DATA_FILE.relative_to(ROOT)} 저장 완료")
    return 1 if len(failed_prefixes) == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
