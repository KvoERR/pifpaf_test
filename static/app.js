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

// ===== Импорт аккаунта по ссылке =====
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

$('#import-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const url = $('#import-url').value.trim();
  if (!url) return;
  doImport(url);
});