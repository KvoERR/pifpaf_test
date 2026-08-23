// ===== Утилиты =====
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function formatNumber(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace('.0', '') + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'K';
  return String(n);
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' });
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Ошибка запроса');
  return data;
}

// ===== Состояние =====
let currentUser = null;

// ===== Логин =====
function showLogin() {
  $('#login-modal').classList.remove('hidden');
  $('#login-error').classList.add('hidden');
}
function closeLogin() {
  $('#login-modal').classList.add('hidden');
}
window.showLogin = showLogin;
window.closeLogin = closeLogin;

$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = $('#login-username').value.trim();
  const password = $('#login-password').value;
  try {
    const user = await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    });
    currentUser = user;
    closeLogin();
    enterDashboard();
  } catch (err) {
    $('#login-error').textContent = err.message;
    $('#login-error').classList.remove('hidden');
  }
});

async function logout() {
  await api('/api/logout', { method: 'POST' });
  currentUser = null;
  showLanding();
}
window.logout = logout;

// ===== Переключение экранов =====
function showLanding() {
  $('#landing').classList.remove('hidden');
  $('#dashboard').classList.add('hidden');
}
function enterDashboard() {
  $('#landing').classList.add('hidden');
  $('#dashboard').classList.remove('hidden');
  loadDashboard();
}

// ===== Импорт аккаунта по ссылке (без авторизации) =====
async function doImport(url) {
  const loading = $('#import-loading');
  const error = $('#import-error');
  const result = $('#import-result');
  loading.classList.remove('hidden');
  error.classList.add('hidden');
  result.classList.add('hidden');
  try {
    const data = await api('/api/account/import', {
      method: 'POST',
      body: JSON.stringify({ url })
    });
    renderImported(data.account, data.live);
  } catch (err) {
    error.textContent = err.message;
    error.classList.remove('hidden');
  } finally {
    loading.classList.add('hidden');
  }
}

function renderImported(acc, live) {
  const box = $('#import-result');
  const reels = acc.reels || [];
  const totalViews = reels.reduce((s, r) => s + (r.views || 0), 0);
  const totalLikes = reels.reduce((s, r) => s + (r.likes || 0), 0);
  const totalComments = reels.reduce((s, r) => s + (r.comments || 0), 0);
  const best = [...reels].sort((a, b) => (b.views || 0) - (a.views || 0))[0];

  const cards = reels.map(r => `
    <div class="reel-card">
      <div class="reel-thumb">
        <img src="${r.thumbnail}" alt="рилс" loading="lazy">
        <span class="reel-views">👁️ ${formatNumber(r.views)}</span>
      </div>
      <div class="reel-body">
        <div class="reel-caption">${r.caption || ''}</div>
        <div class="reel-meta">
          <span>❤️ ${formatNumber(r.likes)}</span>
          <span>💬 ${formatNumber(r.comments)}</span>
        </div>
        <div class="reel-date">${formatDate(r.posted_at)}</div>
      </div>
    </div>
  `).join('');

  const liveBadge = live
    ? '<span class="badge" style="background:rgba(34,197,94,0.15);color:#22c55e">⚡ Реальные данные Apify</span>'
    : '<span class="badge">🧪 Демо-данные (токен Apify не задан)</span>';

  box.className = 'import-result';
  box.innerHTML = `
    <div class="account-top">
      <img class="account-avatar" src="${acc.avatar}" alt="${acc.name}" onerror="this.style.visibility='hidden'">
      <div>
        <div class="account-name">${acc.name} <span class="account-ig">@${acc.handle}</span></div>
        <div class="account-bio">${acc.bio || ''}</div>
        <div class="account-link"><a href="${acc.url}" target="_blank" rel="noopener">Открыть профиль →</a></div>
      </div>
      <div class="account-badges">${liveBadge}</div>
    </div>

    <div class="stats-grid">
      <div class="stat-card"><div class="stat-icon">🎬</div><div class="stat-value">${reels.length}</div><div class="stat-label">Рилсов</div></div>
      <div class="stat-card"><div class="stat-icon">👁️</div><div class="stat-value">${formatNumber(totalViews)}</div><div class="stat-label">Всего просмотров</div></div>
      <div class="stat-card"><div class="stat-icon">❤️</div><div class="stat-value">${formatNumber(totalLikes)}</div><div class="stat-label">Лайков</div></div>
      <div class="stat-card"><div class="stat-icon">📈</div><div class="stat-value">${best ? formatNumber(best.views) : '—'}</div><div class="stat-label">Лучший рилс</div></div>
    </div>

    ${best ? `
      <div class="best-card">
        <h3>🏆 Лучший рилс</h3>
        <div class="best-reel">
          <img src="${best.thumbnail}" alt="">
          <div class="best-reel-info">
            <div class="best-views">${formatNumber(best.views)} просмотров</div>
            <div class="best-caption">${best.caption || ''}</div>
          </div>
        </div>
      </div>` : ''}

    <h3 class="reels-title">🎬 Рилсы аккаунта</h3>
    <div class="reels-grid">${cards || '<p style="color:var(--ink-500)">Рилсы не найдены</p>'}</div>
  `;
}

function demoImport() {
  $('#import-url').value = 'https://www.instagram.com/anna/';
  doImport($('#import-url').value.trim());
}
window.demoImport = demoImport;

$('#import-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const url = $('#import-url').value.trim();
  if (!url) return;
  doImport(url);
});

// ===== Дашборд =====
async function loadDashboard() {
  try {
    const me = await api('/api/me');
    currentUser = me;
    $('#dash-avatar').src = me.avatar;
    $('#dash-name').textContent = me.name;
    $('#dash-instagram').textContent = me.instagram;
    $('#dash-greeting').textContent = `Привет, ${me.name.split(' ')[0]}! Вот твоя аналитика.`;

    await loadOverview();
    await loadMyReels();
    await loadDashFeed();
  } catch (err) {
    // Не авторизован
    showLanding();
  }
}

// ===== Навигация по дашборду =====
$$('.side-link').forEach(link => {
  link.addEventListener('click', () => {
    $$('.side-link').forEach(l => l.classList.remove('active'));
    link.classList.add('active');
    const view = link.dataset.view;
    $$('.view').forEach(v => v.classList.add('hidden'));
    $('#view-' + view).classList.remove('hidden');
    $('#dash-title').textContent = {
      overview: 'Обзор',
      reels: 'Мои рилсы',
      feed: 'Лента'
    }[view];
  });
});

// ===== Обзор =====
async function loadOverview() {
  const data = await api('/api/my/analytics');
  const { totals, best, timeline } = data;

  $('#stat-views').textContent = formatNumber(totals.total_views);
  $('#stat-reels').textContent = totals.reel_count;
  $('#stat-likes').textContent = formatNumber(totals.total_likes);
  $('#stat-avg').textContent = formatNumber(Math.round(totals.avg_views));

  // Лучший рилс
  const bestEl = $('#best-reel');
  if (best) {
    bestEl.innerHTML = `
      <img src="${best.thumbnail}" alt="лучший рилс">
      <div class="best-reel-info">
        <div class="best-views">👁️ ${formatNumber(best.views)}</div>
        <div class="best-caption">${best.caption || 'Без описания'}</div>
        <div class="best-caption" style="opacity:0.8;font-size:12px">${formatDate(best.posted_at)}</div>
      </div>
    `;
  } else {
    bestEl.innerHTML = '<p style="opacity:0.9">Пока нет рилсов</p>';
  }

  drawChart(timeline);
}

// ===== График =====
function drawChart(timeline) {
  const canvas = $('#views-chart');
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 800;
  const height = 220;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.scale(dpr, dpr);

  ctx.clearRect(0, 0, width, height);

  const labels = timeline.map(t => {
    const d = new Date(t.day + 'T00:00:00');
    return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
  });
  const values = timeline.map(t => t.views);

  if (values.length === 0) {
    ctx.fillStyle = '#64748b';
    ctx.font = '14px Inter';
    ctx.textAlign = 'center';
    ctx.fillText('Нет данных для графика', width / 2, height / 2);
    return;
  }

  const pad = { top: 20, right: 20, bottom: 30, left: 50 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const max = Math.max(...values) * 1.1;

  // Сетка
  ctx.strokeStyle = '#e2e8f0';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#94a3b8';
  ctx.font = '11px Inter';
  ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (chartH / 4) * i;
    const val = max - (max / 4) * i;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    ctx.fillText(formatNumber(Math.round(val)), pad.left - 8, y + 4);
  }

  // Линия
  const stepX = values.length > 1 ? chartW / (values.length - 1) : 0;
  ctx.beginPath();
  values.forEach((v, i) => {
    const x = pad.left + stepX * i;
    const y = pad.top + chartH - (v / max) * chartH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#3479ff';
  ctx.lineWidth = 3;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.stroke();

  // Заливка под линией
  const grad = ctx.createLinearGradient(0, pad.top, 0, height - pad.bottom);
  grad.addColorStop(0, 'rgba(52,121,255,0.25)');
  grad.addColorStop(1, 'rgba(52,121,255,0)');
  ctx.lineTo(pad.left + stepX * (values.length - 1), pad.top + chartH);
  ctx.lineTo(pad.left, pad.top + chartH);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Точки
  values.forEach((v, i) => {
    const x = pad.left + stepX * i;
    const y = pad.top + chartH - (v / max) * chartH;
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#3479ff';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  // Подписи оси X
  ctx.fillStyle = '#94a3b8';
  ctx.textAlign = 'center';
  labels.forEach((label, i) => {
    const x = pad.left + stepX * i;
    ctx.fillText(label, x, height - 8);
  });
}

// ===== Мои рилсы =====
async function loadMyReels() {
  const reels = await api('/api/my/reels');
  const grid = $('#my-reels');
  grid.innerHTML = '';

  if (reels.length === 0) {
    grid.innerHTML = '<p style="color:var(--ink-500)">Пока нет рилсов. Добавь первый!</p>';
    return;
  }

  reels.forEach(reel => {
    const card = document.createElement('div');
    card.className = 'reel-card';
    card.innerHTML = `
      <div class="reel-thumb">
        <img src="${reel.thumbnail}" alt="рилс" loading="lazy">
        <span class="reel-views">👁️ ${formatNumber(reel.views)}</span>
      </div>
      <div class="reel-body">
        <div class="reel-caption">${reel.caption || ''}</div>
        <div class="reel-meta">
          <span>❤️ ${formatNumber(reel.likes)}</span>
          <span>💬 ${formatNumber(reel.comments)}</span>
        </div>
        <div class="reel-date">${formatDate(reel.posted_at)}</div>
      </div>
    `;
    grid.appendChild(card);
  });
}

// ===== Лента в дашборде =====
async function loadDashFeed() {
  const users = await api('/api/users');
  const grid = $('#dash-feed');
  grid.innerHTML = '';

  for (const user of users) {
    const reels = await api(`/api/users/${user.id}/reels`);
    reels.slice(0, 2).forEach(reel => {
      const card = document.createElement('div');
      card.className = 'feed-card';
      card.innerHTML = `
        <div class="feed-thumb">
          <img src="${reel.thumbnail}" alt="рилс" loading="lazy">
          <span class="feed-views">👁️ ${formatNumber(reel.views)}</span>
        </div>
        <div class="feed-body">
          <div class="feed-author">
            <img src="${user.avatar}" alt="${user.name}">
            <div>
              <div class="feed-author-name">${user.name}</div>
              <div class="feed-author-ig">${user.instagram}</div>
            </div>
          </div>
          <div class="feed-caption">${reel.caption || ''}</div>
          <div class="feed-meta">
            <span>❤️ ${formatNumber(reel.likes)}</span>
            <span>💬 ${formatNumber(reel.comments)}</span>
          </div>
          <div class="feed-date">${formatDate(reel.posted_at)}</div>
        </div>
      `;
      grid.appendChild(card);
    });
  }
}

// ===== Добавление рилса =====
function openAddReel() {
  $('#add-modal').classList.remove('hidden');
  $('#add-error').classList.add('hidden');
  $('#add-submit').disabled = false;
  $('#add-loading').classList.add('hidden');
  $('#add-submit').classList.remove('hidden');
}
function closeAddReel() {
  $('#add-modal').classList.add('hidden');
}
window.openAddReel = openAddReel;
window.closeAddReel = closeAddReel;

$('#add-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const url = $('#add-url').value.trim();
  const caption = $('#add-caption').value.trim();
  const submit = $('#add-submit');
  const loading = $('#add-loading');
  submit.disabled = true;
  loading.classList.remove('hidden');
  submit.classList.add('hidden');
  try {
    await api('/api/my/reels', {
      method: 'POST',
      body: JSON.stringify({ url, caption })
    });
    closeAddReel();
    $('#add-url').value = '';
    $('#add-caption').value = '';
    await loadOverview();
    await loadMyReels();
    await loadDashFeed();
  } catch (err) {
    $('#add-error').textContent = err.message;
    $('#add-error').classList.remove('hidden');
    submit.disabled = false;
    loading.classList.add('hidden');
    submit.classList.remove('hidden');
  }
});

// ===== Инициализация =====
async function init() {
  try {
    await api('/api/me');
    enterDashboard();
  } catch {
    showLanding();
  }
}

init();