const data = JSON.parse(document.getElementById('report-data').textContent);
const root = document.getElementById('report');
const sites = data.sites || [];
const siteNames = new Map(sites.map(site => [site.id, site.name]));
const esc = value => String(value ?? '').replace(/[&<>"']/g, char =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[char]);
const money = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: data.currency, minimumFractionDigits: 2, maximumFractionDigits: 2
});
const number = new Intl.NumberFormat('en-US');
const percent = new Intl.NumberFormat('zh-CN', {
  style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2
});
const finite = Number.isFinite;
const divide = (top, bottom) => finite(top) && finite(bottom) && bottom > 0 ? top / bottom : null;
const fields = {
  spend: ['广告花费', money, 0], sales: ['广告销售额', money, 1],
  orders: ['广告订单', number, 1], clicks: ['点击', number, 0],
  acos: ['ACOS', percent, -1], tacos: ['TACOS', percent, -1],
  cpc: ['CPC', money, -1], cvr: ['转化率', percent, 1], aov: ['广告客单价', money, 1],
};
const tableFields = ['spend', 'sales', 'clicks', 'orders', 'cpc', 'cvr', 'acos'];
const baseFields = ['spend', 'sales', 'clicks', 'orders'];

function metrics(row) {
  if (!row) return {};
  return {
    ...row, acos: divide(row.spend, row.sales), tacos: divide(row.tacosSpend ?? row.spend, row.totalSales),
    cpc: divide(row.spend, row.clicks), cvr: divide(row.orders, row.clicks), aov: divide(row.sales, row.orders)
  };
}

function sumPairs(pairs) {
  return [0, 1].map(period => {
    const rows = pairs.map(pair => pair?.[period]).filter(Boolean);
    if (!rows.length) return null;
    return Object.fromEntries(baseFields.map(key => [
      key, rows.every(row => finite(row[key])) ? rows.reduce((sum, row) => sum + row[key], 0) : null
    ]));
  });
}

const fmt = (key, value) => finite(value) ? fields[key][1].format(value) : '—';
const paired = (pair, key) => pair.map(row => fmt(key, metrics(row)[key])).join(' → ');
const direction = (key, delta) => {
  const change = fields[key][2] * Math.sign(delta);
  return change > 0 ? 'good' : change < 0 ? 'bad' : 'neutral';
};

function change(pair, key, percentagePoints = false) {
  const [prior, current] = pair.map(row => metrics(row)[key]);
  if (!finite(prior) || !finite(current) || (!percentagePoints && prior <= 0)) {
    return ['—', 'neutral'];
  }
  const delta = current - prior;
  if (Math.abs(delta) < 1e-10) return ['持平', 'neutral'];
  const size = percentagePoints ? (Math.abs(delta) * 100).toFixed(2) + ' 个百分点' : percent.format(Math.abs(delta) / prior);
  return [(delta > 0 ? '↑ ' : '↓ ') + size, direction(key, delta)];
}

function kpi(key) {
  const [delta, tone] = change(data.account, key);
  const current = metrics(data.account[1])[key];
  return '<article><small>' + fields[key][0] + '</small><strong>' + fmt(key, current) +
    '</strong><span class="kpi-change ' + tone + '">环比 ' + delta + '</span></article>';
}

function cells(pair, keys) {
  return keys.map(key => '<td>' + paired(pair, key) + '</td>').join('');
}

function table(rows, label, keys = tableFields) {
  if (!rows.length) return '<p class="scope-note">暂无对应数据。</p>';
  return '<div class="scroll" tabindex="0" role="region" aria-label="' + esc(label) +
    '"><table><thead><tr><th scope="col">' + esc(label) + '</th>' +
    keys.map(key => '<th scope="col">' + fields[key][0] + '</th>').join('') +
    '</tr></thead><tbody>' + rows.map(row => '<tr><th scope="row">' + esc(row.name) + '</th>' +
    cells(row.metrics, keys) + '</tr>').join('') + '</tbody></table></div>';
}

function summarize(rows, key) {
  const groups = new Map();
  for (const row of rows) {
    const label = key(row);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(row.metrics);
  }
  return [...groups].map(([name, pairs]) => ({name, metrics: sumPairs(pairs)}));
}

const lineRows = sites.flatMap(site => (site.stores || []).flatMap(store =>
  (store.lines || []).map(line => ({...line, site: site.id}))));
const lineTotals = summarize(lineRows, row => row.name);
const matrix = sites.flatMap(site => summarize(lineRows.filter(row => row.site === site.id), row => row.name)
  .map(line => ({...line, site: site.id})));

function explorer() {
  const options = list => list.map(([value, name]) =>
    '<option value="' + esc(value) + '">' + esc(name) + '</option>').join('');
  return '<section><h2>国家站点 × 产品线</h2><div class="explorer-filters">' +
    '<label>国家站点<select id="filter-site"><option value="">全部站点</option>' +
    options([...siteNames]) + '</select></label><label>产品线<select id="filter-line">' +
    '<option value="">全部产品线</option>' + options(lineTotals.map(line => [line.name, line.name])) +
    '</select></label><button type="button" id="filter-clear">清空筛选</button></div>' +
    '<p id="explorer-count" aria-live="polite"></p><div id="explorer-results"></div></section>';
}

function showFiltered() {
  const site = document.getElementById('filter-site').value;
  const line = document.getElementById('filter-line').value;
  const filtered = matrix.filter(row => (!site || row.site === site) && (!line || row.name === line));
  const rows = filtered.map(row => ({...row, name: siteNames.get(row.site) + ' · ' + row.name}));
  document.getElementById('explorer-count').textContent = filtered.length ? '共 ' + filtered.length + ' 条' : '当前筛选无数据';
  const result = document.getElementById('explorer-results');
  result.innerHTML = rows.length ? table(rows, '站点 · 产品线') : '';
  if (rows.length) {
    result.querySelector('table').insertAdjacentHTML('beforeend',
      '<tfoot><tr><th scope="row">总计</th>' + cells(sumPairs(rows.map(row => row.metrics)), tableFields) + '</tr></tfoot>');
  }
}

function lineCard(line) {
  const cards = ['spend', 'orders', 'cvr', 'acos'].map(key => {
    const [delta, tone] = change(line.metrics, key, key === 'cvr' || key === 'acos');
    const [prior, current] = line.metrics.map(row => metrics(row)[key]);
    const scale = Math.max(prior ?? 0, current ?? 0);
    const comparison = scale > 0 && finite(prior) && finite(current) ?
      '<div class="bars" aria-hidden="true"><i style="width:' + (100 * prior / scale) +
      '%"></i><i style="width:' + (100 * current / scale) + '%"></i></div>' : '';
    return '<span class="metric"><small>' + fields[key][0] + '</small><strong>' +
      fmt(key, current) + '</strong><span>上期 ' + fmt(key, prior) + ' · </span><span class="delta ' +
      tone + '">' + delta + '</span>' + comparison + '</span>';
  }).join('');
  const note = line.note ? '<p class="scope-note">' + esc(line.note) + '</p>' : '';
  return '<details><summary><b>' + esc(line.name) + '</b><span class="mini">' +
    cards + '</span></summary>' + table(line.types || [], '广告类型') + note + '</details>';
}

function focusPage() {
  const ranked = (data.parents || []).map(parent => {
    const [prior, current] = parent.metrics.map(metrics);
    const impact = finite(prior.acos) && finite(current.acos) && current.acos > prior.acos ?
      current.spend - current.sales * prior.acos : 0;
    return {...parent, impact};
  }).filter(parent => parent.impact > 1e-9).sort((a, b) => b.impact - a.impact)
    .slice(0, data.focusLimit ?? 6);
  const cards = ranked.map((parent, index) => {
    const measures = ['spend', 'sales', 'orders', 'cpc', 'cvr', 'aov', 'acos'].map(key => {
      const [delta, tone] = change(parent.metrics, key, key === 'cvr' || key === 'acos');
      return '<div class="focus-metric"><small>' + fields[key][0] + '</small><strong>' +
        paired(parent.metrics, key) + '</strong><span class="' + tone + '">' + delta + '</span></div>';
    }).join('');
    return '<details class="focus-card"><summary class="focus-summary"><span class="focus-rank">' +
      String(index + 1).padStart(2, '0') + '</span><span class="focus-identity"><strong>' +
      esc(parent.asin) + '</strong><small>' + esc([siteNames.get(parent.site), parent.store, parent.line].join(' · ')) +
      '</small></span><span class="focus-reason">' + esc(parent.headline || '广告效率下滑') +
      '</span><span class="focus-chevron" aria-hidden="true"></span></summary><div class="focus-detail">' +
      '<div class="focus-metrics">' + measures + '</div><p>按上期效率测算的花费差额 ' +
      money.format(parent.impact) + '</p><dl class="focus-notes"><div><dt>入选原因</dt><dd>' +
      esc(parent.reason) + '</dd></div><div><dt>后续要看</dt><dd>' + esc(parent.next) +
      '</dd></div></dl></div></details>';
  }).join('');
  return '<div id="focus" hidden><section class="focus-banner"><div><h2>本期优先关注的父 ASIN</h2>' +
    '<p>展开卡片查看两期数据和排查方向。</p></div><div class="focus-count"><strong>' +
    ranked.length + '</strong><span>个父 ASIN</span></div></section>' +
    (cards ? '<div class="focus-list">' + cards + '</div>' : '<section>本期暂无符合排序条件的父 ASIN。</section>') +
    '<section class="focus-method"><h3>筛选口径</h3><p>按站点、店铺和父 ASIN 汇总推广商品。对 ACOS 上升的可比父体，' +
    '以本期花费减去「本期广告销售额 × 上期 ACOS」排序。差额为相对上期效率的测算。</p>' +
    (data.focusNote ? '<p>' + esc(data.focusNote) + '</p>' : '') + '</section></div>';
}

const pages = [['overview', '大盘总览'], ...siteNames, ['focus', '重点关注']];
const title = data.client + '｜' + (data.title || '广告复盘');
document.title = title;
root.innerHTML = '<header><h1>' + esc(title) + '</h1><p>上期 ' + esc(data.prior) +
  '　·　本期 ' + esc(data.current) + '　·　币种 ' + esc(data.currency) + '</p></header>' +
  '<nav aria-label="报告页面">' + pages.map(([id, label]) => '<a href="#' +
  esc(id) + '">' + esc(label) + '</a>').join('') + '</nav>' +
  '<div id="overview"><section class="call"><h2>本期重点</h2><ul>' +
  (data.conclusions || []).map(item => '<li>' + esc(item) + '</li>').join('') + '</ul></section>' +
  '<section><h2>大盘结果</h2><div class="grid">' + ['spend', 'sales', 'acos', 'tacos', 'orders'].map(kpi).join('') +
  '</div></section><section><h2>大盘效率</h2><div class="grid">' + ['cpc', 'cvr', 'aov'].map(kpi).join('') +
  '</div></section><section><h2>国家站点数据变化</h2>' + table(sites, '国家站点') +
  '</section><section><h2>产品线数据变化</h2>' + table(lineTotals, '产品线') + '</section>' +
  explorer() + '</div>' + sites.map(site => '<div id="' + esc(site.id) + '" hidden><section><h2>' +
    esc(site.name) + '</h2>' + table(site.stores || [], '店铺') + '</section>' +
    (site.stores || []).map(store => '<section><h3>' + esc(store.name) + '</h3>' +
      ((store.lines || []).length ? '<div class="line-grid">' +
        store.lines.map(lineCard).join('') + '</div>' : '<p class="scope-note">暂无可展示的品线数据。</p>') +
      '</section>').join('') + '</div>').join('') + focusPage() + '<footer>' +
  (data.notes || []).map(note => '<p>' + esc(note) + '</p>').join('') + '</footer>';

function showPage() {
  const requested = location.hash.slice(1);
  const active = pages.some(([id]) => id === requested) ? requested : 'overview';
  for (const [id] of pages) {
    document.getElementById(id).hidden = id !== active;
    const link = document.querySelector('nav a[href="#' + id + '"]');
    if (id === active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}
for (const id of ['filter-site', 'filter-line']) {
  document.getElementById(id).addEventListener('change', showFiltered);
}
document.getElementById('filter-clear').addEventListener('click', () => {
  document.getElementById('filter-site').value = '';
  document.getElementById('filter-line').value = '';
  showFiltered();
});
addEventListener('hashchange', showPage);
showPage();
showFiltered();
