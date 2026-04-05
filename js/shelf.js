/* === Magazine Shelf — Weird Tales === */
(function () {
  'use strict';

  let manifest = null;
  let activeDecade = 'all';
  let activeYear = null;

  const grid = document.getElementById('issue-grid');
  const countEl = document.getElementById('issue-count');
  const yearFilters = document.getElementById('year-filters');
  const subtitle = document.getElementById('shelf-subtitle');

  async function init() {
    const resp = await fetch('data/manifest.json');
    manifest = await resp.json();
    subtitle.textContent = `The Unique Magazine \u00b7 ${manifest.total_issues} Issues \u00b7 ${manifest.years[0]}\u2013${manifest.years[manifest.years.length - 1]}`;
    buildYearPills();
    render();
  }

  function buildYearPills() {
    manifest.years.forEach(year => {
      const btn = document.createElement('button');
      btn.className = 'filter-btn';
      btn.dataset.year = year;
      btn.textContent = year;
      btn.addEventListener('click', () => filterByYear(year));
      yearFilters.appendChild(btn);
    });
  }

  function filterByDecade(decade) {
    activeDecade = decade;
    activeYear = null;
    updateFilterUI();
    render();
  }

  function filterByYear(year) {
    if (activeYear === year) {
      activeYear = null;
    } else {
      activeYear = year;
      activeDecade = decadeOf(year);
    }
    updateFilterUI();
    render();
  }

  function decadeOf(year) {
    if (year < 1930) return '1920s';
    if (year < 1940) return '1930s';
    if (year < 1950) return '1940s';
    return '1950s';
  }

  function updateFilterUI() {
    document.querySelectorAll('#decade-filters .filter-btn').forEach(btn => {
      btn.classList.toggle('filter-btn--active', btn.dataset.filter === activeDecade);
    });
    document.querySelectorAll('#year-filters .filter-btn').forEach(btn => {
      btn.classList.toggle('filter-btn--active', btn.dataset.year == activeYear);
    });
  }

  function getFilteredIssues() {
    return manifest.issues.filter(issue => {
      if (activeYear && issue.year !== activeYear) return false;
      if (activeDecade !== 'all' && decadeOf(issue.year) !== activeDecade) return false;
      return true;
    });
  }

  function decadeClass(year) {
    if (year < 1930) return '';
    if (year < 1940) return ' issue-card--30s';
    if (year < 1950) return ' issue-card--40s';
    return ' issue-card--50s';
  }

  function render() {
    const issues = getFilteredIssues();
    countEl.textContent = `${issues.length} issue${issues.length !== 1 ? 's' : ''}`;

    grid.innerHTML = issues.map(issue => {
      const stories = issue.stories.slice(0, 3);
      const moreCount = issue.stories.length - 3;

      return `
        <a href="reader.html?issue=${issue.slug}" class="issue-card${decadeClass(issue.year)}">
          <div class="issue-card__masthead">Weird Tales</div>
          <div class="issue-card__number">Vol.${issue.volume} No.${issue.number} &middot; ${issue.date}</div>
          ${issue.cover_art ? `
            <div class="issue-card__cover-art">&ldquo;${escapeHtml(issue.cover_art.title)}&rdquo;</div>
            <div class="issue-card__cover-artist">by ${escapeHtml(issue.cover_art.artist)}</div>
          ` : ''}
          <hr class="issue-card__divider">
          <ul class="issue-card__stories">
            ${stories.map(s => `
              <li>&ldquo;${escapeHtml(s.title)}&rdquo; <span class="author">&mdash; ${escapeHtml(s.author)}</span></li>
            `).join('')}
            ${moreCount > 0 ? `<li style="color:var(--text-muted); font-style:italic">+ ${moreCount} more</li>` : ''}
          </ul>
          <div class="issue-card__footer">
            <span class="issue-card__price">${escapeHtml(issue.cover_price || '')}</span>
            <span class="issue-card__decade">${decadeOf(issue.year)}</span>
          </div>
        </a>
      `;
    }).join('');
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // Decade filter clicks
  document.querySelectorAll('#decade-filters .filter-btn').forEach(btn => {
    btn.addEventListener('click', () => filterByDecade(btn.dataset.filter));
  });

  // Settings panel
  const settingsToggle = document.getElementById('settings-toggle');
  const settingsPanel = document.getElementById('settings-panel');
  const settingsClose = document.getElementById('settings-close');
  const overlay = document.getElementById('overlay');

  function openSettings() {
    settingsPanel.classList.add('open');
    overlay.classList.add('visible');
  }

  function closeSettings() {
    settingsPanel.classList.remove('open');
    overlay.classList.remove('visible');
  }

  settingsToggle.addEventListener('click', openSettings);
  settingsClose.addEventListener('click', closeSettings);
  overlay.addEventListener('click', closeSettings);

  // Theme buttons
  document.querySelectorAll('[data-theme-choice]').forEach(btn => {
    btn.addEventListener('click', () => {
      const theme = btn.dataset.themeChoice;
      Preferences.setTheme(theme);
      document.querySelectorAll('[data-theme-choice]').forEach(b =>
        b.classList.toggle('btn--active', b.dataset.themeChoice === theme)
      );
    });
  });

  init();
})();
