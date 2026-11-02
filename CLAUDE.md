# 독후감·문학 공모전 모아보기

빌드 도구 없는 정적 사이트(GitHub Pages)와 Python 크롤러로 된 프로젝트입니다. 구조, 데이터 항목, 수집 규칙은 [README.md](README.md)를 봅니다.

## 작업 규칙
- 작업 전에 `git pull`을 합니다. 봇이 `data/contests.json`을 매일 `main`에 커밋하고, 사용자는 여러 PC에서 작업합니다.
- `main`에 푸시하면 사이트에 바로 배포됩니다. 커밋과 푸시는 사용자에게 확인받은 뒤 합니다.
- 사용자는 한국어를 씁니다. 코드 주석과 커밋 메시지도 한국어로 씁니다.

## 실행 (Windows, 저장소 루트)
```powershell
python -m venv .venv                                       # 새 PC에서 처음 한 번
.venv\Scripts\python.exe -m pip install -r crawler/requirements.txt

.venv\Scripts\python.exe crawler/crawl.py --dry-run        # 파일을 바꾸지 않고 수집 결과만 보기
.venv\Scripts\python.exe -m http.server 8000               # http://localhost:8000 미리 보기
```
- `.venv`는 `.gitignore`에 없습니다. 만들면 `.git/info/exclude`에 `.venv/`를 넣어 커밋되지 않게 합니다.
- 테스트 코드는 없습니다. 크롤러를 고치면 `--dry-run` 결과를 항목별로 읽어 확인합니다.
- `index.html`을 더블클릭해서 열면 데이터를 읽지 못합니다. 로컬 서버로 엽니다.

## 데이터를 다룰 때
- id가 `ck-`, `wv-`로 시작하면 크롤러 항목이고, 다음 수집 때 덮어쓰입니다. 고쳐서 유지하려면 id를 바꿔 직접 입력 항목으로 만듭니다.
- 직접 입력 항목은 크롤러가 고치거나 지우지 않습니다. 이 동작을 유지합니다.
- 항목 필드를 바꾸면 `crawler/crawl.py`의 `make_item`과 `js/app.js`의 `validate`를 함께 고칩니다. 검증에 실패한 항목은 화면에 나오지 않습니다.
- 문학 공모전의 대상은 본문 전체로 추정하지 않습니다. 본문의 "어린이·청소년"은 응모자가 아니라 작품의 독자인 경우가 많습니다.
