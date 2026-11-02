/*
 * 독후감·문학 공모전 모아보기
 * 순서: 데이터 읽기 → 검증 → 상태 계산 → 필터 → 정렬 → 화면 그리기
 * 공모전을 추가하거나 고칠 때는 이 파일이 아니라 data/contests.json 을 수정하세요.
 */
(function () {
  'use strict';

  var CATEGORIES = ['독후감', '문학작품'];
  var DEFAULT_CATEGORY = '독후감'; // category를 적지 않은 항목은 독후감 공모전으로 봄
  var TARGETS = ['초등', '중등', '고등', '일반'];
  var REGIONS = ['전국', '서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종',
    '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'];
  var BOOK_REQUIREMENTS = ['지정도서', '자유'];
  var STATUSES = ['접수중', '예정']; // '마감'은 토글로 따로 다룸
  var REQUIRED = ['id', 'title', 'organizer', 'target', 'region', 'startDate', 'endDate',
    'prize', 'url', 'source', 'updatedAt'];
  var URGENT_DAYS = 7;

  var state = {
    category: '',         // 빈 값이면 전체
    targets: [],          // 비어 있으면 전체
    region: '',           // 빈 값이면 전체
    statuses: STATUSES.slice(),
    showClosed: false
  };
  var contests = [];

  var el = {
    category: document.getElementById('category-tabs'),
    target: document.getElementById('filter-target'),
    region: document.getElementById('filter-region'),
    status: document.getElementById('filter-status'),
    closed: document.getElementById('filter-closed'),
    cards: document.getElementById('cards'),
    count: document.getElementById('result-count'),
    empty: document.getElementById('empty'),
    notice: document.getElementById('notice'),
    reset: document.getElementById('reset-btn'),
    emptyReset: document.getElementById('empty-reset-btn')
  };

  /* ---------- 날짜 (한국 시간 기준) ---------- */

  function todayKST() {
    // en-CA 형식은 YYYY-MM-DD
    return new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(new Date());
  }

  function isValidDate(s) {
    if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
    var p = s.split('-').map(Number);
    var d = new Date(Date.UTC(p[0], p[1] - 1, p[2]));
    return d.getUTCFullYear() === p[0] && d.getUTCMonth() === p[1] - 1 && d.getUTCDate() === p[2];
  }

  function toDayNumber(s) {
    var p = s.split('-').map(Number);
    return Date.UTC(p[0], p[1] - 1, p[2]) / 86400000;
  }

  function formatDate(s) {
    var p = s.split('-');
    return p[0] + '.' + p[1] + '.' + p[2];
  }

  /* ---------- 검증 ---------- */

  function validate(item, index, seenIds) {
    var errors = [];
    if (!item || typeof item !== 'object') return ['객체 형식이 아닙니다'];

    REQUIRED.forEach(function (key) {
      var v = item[key];
      if (v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0)) {
        errors.push('"' + key + '" 항목이 비어 있습니다');
      }
    });
    if (errors.length) return errors;

    if (seenIds[item.id]) errors.push('id "' + item.id + '"가 중복됩니다');
    if (!Array.isArray(item.target)) {
      errors.push('target은 ["초등", "중등"]처럼 배열이어야 합니다');
    } else {
      item.target.forEach(function (t) {
        if (TARGETS.indexOf(t) === -1) errors.push('target 값 "' + t + '"은(는) 허용되지 않습니다 (' + TARGETS.join(', ') + ')');
      });
    }
    if (REGIONS.indexOf(item.region) === -1) errors.push('region 값 "' + item.region + '"은(는) 허용되지 않습니다');
    var category = item.category || DEFAULT_CATEGORY;
    if (CATEGORIES.indexOf(category) === -1) {
      errors.push('category는 ' + CATEGORIES.join(' 또는 ') + '여야 합니다');
    } else if (category === '문학작품') {
      if (!Array.isArray(item.genres) || item.genres.length === 0) errors.push('genres는 ["시", "수필"]처럼 배열이어야 합니다');
    } else if (BOOK_REQUIREMENTS.indexOf(item.bookRequirement) === -1) {
      errors.push('bookRequirement는 "지정도서" 또는 "자유"여야 합니다');
    }
    ['startDate', 'endDate', 'updatedAt'].forEach(function (key) {
      if (!isValidDate(item[key])) errors.push(key + ' "' + item[key] + '"이(가) YYYY-MM-DD 형식이 아닙니다');
    });
    if (isValidDate(item.startDate) && isValidDate(item.endDate) && item.startDate > item.endDate) {
      errors.push('startDate가 endDate보다 늦습니다');
    }
    if (!/^https?:\/\//.test(String(item.url))) errors.push('url은 http:// 또는 https:// 로 시작해야 합니다');
    return errors;
  }

  /* ---------- 상태·D-day ---------- */

  function enrich(item, today) {
    var t = toDayNumber(today);
    var start = toDayNumber(item.startDate);
    var end = toDayNumber(item.endDate);
    var c = Object.assign({}, item);
    c.category = item.category || DEFAULT_CATEGORY;
    if (t < start) {
      c.status = '예정';
      c.dday = '' + (start - t) + '일 후 시작';
      c.badge = 'upcoming';
    } else if (t <= end) {
      var left = end - t;
      c.status = '접수중';
      c.dday = left === 0 ? 'D-DAY' : 'D-' + left;
      c.badge = left <= URGENT_DAYS ? 'urgent' : 'open';
    } else {
      c.status = '마감';
      c.dday = '마감';
      c.badge = 'closed';
    }
    c._start = start;
    c._end = end;
    return c;
  }

  var STATUS_ORDER = { '접수중': 0, '예정': 1, '마감': 2 };

  function compare(a, b) {
    var s = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
    if (s !== 0) return s;
    if (a.status === '접수중') return a._end - b._end;      // 마감 임박 순
    if (a.status === '예정') return a._start - b._start;    // 시작 빠른 순
    return b._end - a._end;                                  // 최근 마감 순
  }

  /* ---------- 필터 ---------- */

  function matches(c) {
    return matchesFilters(c) && (!state.category || c.category === state.category);
  }

  function matchesFilters(c) {
    if (c.status === '마감') {
      if (!state.showClosed) return false;
    } else if (state.statuses.indexOf(c.status) === -1) {
      return false;
    }
    if (state.targets.length && !c.target.some(function (t) { return state.targets.indexOf(t) !== -1; })) {
      return false;
    }
    if (state.region && state.region !== '전국') {
      // 특정 시·도를 고르면 그 지역 + 전국 공모전을 함께 보여 줌
      if (c.region !== state.region && c.region !== '전국') return false;
    } else if (state.region === '전국' && c.region !== '전국') {
      return false;
    }
    return true;
  }

  /* ---------- URL 쿼리 ↔ 상태 ---------- */

  function readQuery() {
    var q = new URLSearchParams(location.search);
    if (CATEGORIES.indexOf(q.get('category')) !== -1) state.category = q.get('category');
    if (q.get('target')) {
      state.targets = q.get('target').split(',').filter(function (t) { return TARGETS.indexOf(t) !== -1; });
    }
    if (q.get('region') && REGIONS.indexOf(q.get('region')) !== -1) state.region = q.get('region');
    if (q.has('status')) {
      state.statuses = q.get('status').split(',').filter(function (s) { return STATUSES.indexOf(s) !== -1; });
    }
    state.showClosed = q.get('closed') === '1';
  }

  function writeQuery() {
    var q = new URLSearchParams();
    if (state.category) q.set('category', state.category);
    if (state.targets.length) q.set('target', state.targets.join(','));
    if (state.region) q.set('region', state.region);
    if (state.statuses.length !== STATUSES.length) q.set('status', state.statuses.join(','));
    if (state.showClosed) q.set('closed', '1');
    var s = q.toString();
    history.replaceState(null, '', location.pathname + (s ? '?' + s : ''));
  }

  /* ---------- 화면 그리기 ---------- */

  function make(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined) n.textContent = text; // textContent만 사용 → HTML 삽입 방지
    return n;
  }

  function chip(label, pressed, onClick) {
    var b = make('button', 'chip', label);
    b.type = 'button';
    b.setAttribute('aria-pressed', String(pressed));
    b.addEventListener('click', onClick);
    return b;
  }

  function toggleIn(list, value) {
    var i = list.indexOf(value);
    if (i === -1) list.push(value); else list.splice(i, 1);
  }

  function renderCategoryTabs() {
    var visible = contests.filter(matchesFilters);
    el.category.textContent = '';
    [''].concat(CATEGORIES).forEach(function (category) {
      var count = visible.filter(function (c) { return !category || c.category === category; }).length;
      var tab = make('button', 'tab', (category || '전체') + ' ' + count);
      tab.type = 'button';
      tab.setAttribute('aria-pressed', String(state.category === category));
      tab.addEventListener('click', function () { state.category = category; update(); });
      el.category.appendChild(tab);
    });
  }

  function renderFilters() {
    renderCategoryTabs();

    el.target.textContent = '';
    el.target.appendChild(chip('전체', state.targets.length === 0, function () {
      state.targets = []; update();
    }));
    TARGETS.forEach(function (t) {
      el.target.appendChild(chip(t, state.targets.indexOf(t) !== -1, function () {
        toggleIn(state.targets, t); update();
      }));
    });

    el.status.textContent = '';
    STATUSES.forEach(function (s) {
      el.status.appendChild(chip(s, state.statuses.indexOf(s) !== -1, function () {
        toggleIn(state.statuses, s); update();
      }));
    });

    el.region.value = state.region;
    el.closed.checked = state.showClosed;
  }

  function renderCard(c) {
    var li = make('li', 'card' + (c.status === '마감' ? ' is-closed' : ''));

    var top = make('div', 'card-top');
    top.appendChild(make('span', 'badge ' + c.badge, c.dday));
    top.appendChild(make('span', 'region', c.category + ' · ' + c.region));
    li.appendChild(top);

    li.appendChild(make('h2', '', c.title));
    li.appendChild(make('p', 'organizer', c.organizer));

    var tags = make('ul', 'tags');
    tags.setAttribute('aria-label', '대상');
    c.target.forEach(function (t) { tags.appendChild(make('li', 'tag', t)); });
    li.appendChild(tags);

    var info = make('dl', 'info');
    [['접수', formatDate(c.startDate) + ' ~ ' + formatDate(c.endDate)],
     c.category === '문학작품' ? ['장르', c.genres.join(', ')] : ['도서', c.bookRequirement],
     ['시상', c.prize]].forEach(function (row) {
      info.appendChild(make('dt', '', row[0]));
      info.appendChild(make('dd', '', row[1]));
    });
    li.appendChild(info);

    var bottom = make('div', 'card-bottom');
    bottom.appendChild(make('span', 'updated', '출처 ' + c.source + ' · ' + formatDate(c.updatedAt) + ' 갱신'));
    var a = make('a', 'btn', '원문 보기');
    a.href = c.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', c.title + ' 원문 보기 (새 창)');
    bottom.appendChild(a);
    li.appendChild(bottom);

    return li;
  }

  function renderList() {
    var list = contests.filter(matches).sort(compare);
    el.cards.textContent = '';
    list.forEach(function (c) { el.cards.appendChild(renderCard(c)); });
    el.count.textContent = list.length + '개 공모전';
    el.empty.hidden = list.length !== 0;
  }

  function update() {
    renderFilters();
    renderList();
    writeQuery();
  }

  function resetFilters() {
    state.targets = [];
    state.region = '';
    state.statuses = STATUSES.slice();
    state.showClosed = false;
    update();
  }

  function showNotice(title, lines) {
    el.notice.textContent = '';
    el.notice.appendChild(make('strong', '', title));
    if (lines && lines.length) {
      var ul = make('ul');
      lines.forEach(function (l) { ul.appendChild(make('li', '', l)); });
      el.notice.appendChild(ul);
    }
    el.notice.hidden = false;
  }

  /* ---------- 시작 ---------- */

  function init() {
    var all = make('option', '', '전체 지역');
    all.value = '';
    el.region.appendChild(all);
    REGIONS.forEach(function (r) {
      var o = make('option', '', r === '전국' ? '전국 단위만' : r);
      o.value = r;
      el.region.appendChild(o);
    });

    el.region.addEventListener('change', function () { state.region = el.region.value; update(); });
    el.closed.addEventListener('change', function () { state.showClosed = el.closed.checked; update(); });
    el.reset.addEventListener('click', resetFilters);
    el.emptyReset.addEventListener('click', resetFilters);

    readQuery();
    renderFilters();
    el.count.textContent = '불러오는 중…';

    fetch('data/contests.json', { cache: 'no-cache' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.text();
      })
      .then(function (text) {
        var data;
        try {
          data = JSON.parse(text);
        } catch (e) {
          throw new Error('JSON 문법 오류: ' + e.message);
        }
        var items = Array.isArray(data && data.contests) ? data.contests : null;
        if (!items) throw new Error('최상위에 "contests" 배열이 없습니다');

        var today = todayKST();
        var seen = {};
        var problems = [];
        items.forEach(function (item, i) {
          var errs = validate(item, i, seen);
          var label = (item && item.id) ? 'id "' + item.id + '"' : (i + 1) + '번째 항목';
          if (errs.length) {
            problems.push(label + ': ' + errs.join(', '));
            console.warn('[contests.json] ' + label, errs);
            return;
          }
          seen[item.id] = true;
          contests.push(enrich(item, today));
        });

        if (problems.length) {
          showNotice(problems.length + '개 항목에 오류가 있어 화면에서 뺐습니다. data/contests.json을 확인해 주세요.', problems);
        }
        update();
      })
      .catch(function (err) {
        console.error(err);
        el.count.textContent = '';
        var hint = location.protocol === 'file:'
          ? ['파일을 더블클릭해서 열면 데이터를 읽을 수 없습니다. README의 "내 컴퓨터에서 미리 보기"를 참고하세요.']
          : [err.message];
        showNotice('데이터 파일을 읽을 수 없습니다.', hint);
      });
  }

  init();
})();
