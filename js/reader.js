/* === Issue Reader — Weird Tales === */
(function () {
  'use strict';

  const params = new URLSearchParams(window.location.search);
  const issueSlug = params.get('issue');
  if (!issueSlug) {
    window.location.href = 'index.html';
    return;
  }

  let manifest = null;
  let issueData = null;
  let sections = [];
  let currentSection = 0;
  let sectionParam = null;

  const content = document.getElementById('reader-content');
  const navTitle = document.getElementById('nav-title');
  const progressBar = document.getElementById('progress-bar');
  const tocList = document.getElementById('toc-list');
  const tocInfo = document.getElementById('toc-issue-info');

  async function init() {
    sectionParam = parseInt(window.location.hash.replace('#section-', ''), 10) || null;

    const manifestResp = await fetch('data/manifest.json');
    manifest = await manifestResp.json();
    issueData = manifest.issues.find(i => i.slug === issueSlug);

    if (!issueData) {
      content.innerHTML = '<p style="text-align:center;padding:4rem 0">Issue not found.</p>';
      return;
    }

    const textResp = await fetch(`issues/${issueData.filename}`);
    if (!textResp.ok) {
      content.innerHTML = '<p style="text-align:center;padding:4rem 0">Could not load issue text.</p>';
      return;
    }

    const text = await textResp.text();
    sections = parseIssueText(text);
    currentSection = sectionParam != null ? Math.min(sectionParam, sections.length - 1) : 0;

    document.title = `${issueData.date} — Weird Tales`;
    navTitle.textContent = `Weird Tales \u00b7 ${issueData.date}`;

    buildTOC();
    renderSection(currentSection);
    setupProgressBar();
    setupSettings();
    setupPanels();

    window.addEventListener('hashchange', () => {
      const idx = parseInt(window.location.hash.replace('#section-', ''), 10);
      if (!isNaN(idx) && idx >= 0 && idx < sections.length) {
        navigateToSection(idx);
      }
    });
  }

  /**
   * Parse the raw .txt into sections.
   * Format: === dividers separate sections, just like tales-reader.
   */
  function parseIssueText(text) {
    const lines = text.split('\n');
    const dividerIndices = [];

    for (let i = 0; i < lines.length; i++) {
      if (/^={10,}\s*$/.test(lines[i].trim())) {
        dividerIndices.push(i);
      }
    }

    const result = [];

    // Skip first 3 dividers (header, cover art, toc blocks) — same as tales-reader
    let i = 3;
    while (i < dividerIndices.length) {
      const startDiv = dividerIndices[i];

      if (i + 1 < dividerIndices.length && dividerIndices[i + 1] - startDiv < 15) {
        // Title-block pair: divider, title lines, divider, content
        const titleStart = startDiv + 1;
        const titleEnd = dividerIndices[i + 1];
        const contentStart = titleEnd + 1;
        const contentEnd = (i + 2 < dividerIndices.length) ? dividerIndices[i + 2] : lines.length;

        const titleLines = lines.slice(titleStart, titleEnd).map(l => l.trim()).filter(Boolean);
        const contentLines = lines.slice(contentStart, contentEnd);

        const parsed = parseTitleBlock(titleLines);
        result.push({
          type: parsed.type,
          title: parsed.title,
          author: parsed.author,
          lines: contentLines,
        });

        i += 2;
      } else {
        // Single divider section
        const contentStart = startDiv + 1;
        const contentEnd = (i + 1 < dividerIndices.length) ? dividerIndices[i + 1] : lines.length;
        const contentLines = lines.slice(contentStart, contentEnd);
        const firstLines = contentLines.filter(l => l.trim()).slice(0, 3);

        result.push({
          type: 'feature',
          title: firstLines[0] || 'Section',
          author: '',
          lines: contentLines,
        });

        i += 1;
      }
    }

    return result;
  }

  function parseTitleBlock(titleLines) {
    let title = '';
    let author = '';
    let type = 'story';

    for (const line of titleLines) {
      if (/^by\s+/i.test(line)) {
        author = line.replace(/^by\s+/i, '').trim();
      } else if (!author) {
        title += (title ? ' ' : '') + line;
      }
    }

    if (!title) title = titleLines.join(' ');

    const titleUpper = title.toUpperCase();
    if (titleUpper.includes('EDITOR') || titleUpper.includes('THE EYRIE')) {
      type = 'editorial';
    } else if (titleUpper.includes('WEIRD STORY REPRINT') || titleUpper.includes('REPRINT')) {
      type = 'reprint';
    } else if (titleUpper.includes('LETTER') || titleUpper.includes('READERS')) {
      type = 'letters';
    } else if (titleUpper.includes('BOOK REVIEW') || titleUpper.includes('READING LAMP')) {
      type = 'reviews';
    } else if (titleUpper.includes('POEM') || titleUpper.includes('VERSE')) {
      type = 'poem';
    }

    return { type, title: toTitleCase(title), author };
  }

  function toTitleCase(str) {
    if (str === str.toUpperCase() && str.length > 3) {
      return str.toLowerCase().replace(/(?:^|\s|[-"(])\w/g, c => c.toUpperCase());
    }
    return str;
  }

  function buildTOC() {
    tocInfo.innerHTML = `
      <strong>Weird Tales</strong><br>
      Vol.${escapeHtml(issueData.volume)} No.${escapeHtml(String(issueData.number))} &middot; ${escapeHtml(issueData.date)}<br>
      ${escapeHtml(issueData.editor || '')}
    `;

    let lastType = null;
    tocList.innerHTML = sections.map((sec, idx) => {
      let label = '';
      if (sec.type === 'story' && lastType !== 'story') {
        label = '<li class="toc-drawer__section-label">Stories</li>';
      } else if (sec.type !== 'story' && sec.type !== lastType && lastType === 'story') {
        label = '<li class="toc-drawer__section-label">Features</li>';
      }
      lastType = sec.type;

      return `${label}
        <li class="toc-drawer__item">
          <a href="#section-${idx}" class="toc-drawer__link${idx === currentSection ? ' toc-drawer__link--active' : ''}" data-section="${idx}">
            ${escapeHtml(sec.title)}
            ${sec.author ? `<span class="toc-drawer__link-author">${escapeHtml(sec.author)}</span>` : ''}
          </a>
        </li>`;
    }).join('');

    tocList.querySelectorAll('.toc-drawer__link').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const idx = parseInt(link.dataset.section, 10);
        navigateToSection(idx);
        closeTOC();
      });
    });
  }

  function renderSection(idx) {
    const sec = sections[idx];
    if (!sec) return;

    currentSection = idx;
    window.history.replaceState(null, '', `?issue=${issueSlug}#section-${idx}`);
    updateTOCActive(idx);

    const isStory = sec.type === 'story' || sec.type === 'reprint';
    const html = formatContent(sec.lines, isStory);

    const prevSec = idx > 0 ? sections[idx - 1] : null;
    const nextSec = idx < sections.length - 1 ? sections[idx + 1] : null;

    const issueIdx = manifest.issues.findIndex(i => i.slug === issueSlug);
    const prevIssue = issueIdx > 0 ? manifest.issues[issueIdx - 1] : null;
    const nextIssue = issueIdx < manifest.issues.length - 1 ? manifest.issues[issueIdx + 1] : null;

    content.innerHTML = `
      <div class="section-header">
        <h1 class="section-header__title">${escapeHtml(sec.title)}</h1>
        ${sec.author ? `<p class="section-header__author">by ${escapeHtml(sec.author)}</p>` : ''}
      </div>

      <div class="story-text${isStory ? ' story-text--drop-cap' : ''}">
        ${html}
      </div>

      <nav class="section-nav">
        ${prevSec ? `
          <a href="#section-${idx - 1}" class="section-nav__link" data-section="${idx - 1}">
            <span class="section-nav__direction">&larr; Previous</span>
            <span class="section-nav__title">${escapeHtml(prevSec.title)}</span>
          </a>
        ` : '<span></span>'}
        ${nextSec ? `
          <a href="#section-${idx + 1}" class="section-nav__link section-nav__link--next" data-section="${idx + 1}">
            <span class="section-nav__direction">Next &rarr;</span>
            <span class="section-nav__title">${escapeHtml(nextSec.title)}</span>
          </a>
        ` : '<span></span>'}
      </nav>

      <nav class="issue-nav">
        ${prevIssue ? `<a href="reader.html?issue=${prevIssue.slug}" class="issue-nav__link">&larr; ${escapeHtml(prevIssue.date)}</a>` : '<span></span>'}
        ${nextIssue ? `<a href="reader.html?issue=${nextIssue.slug}" class="issue-nav__link">${escapeHtml(nextIssue.date)} &rarr;</a>` : '<span></span>'}
      </nav>
    `;

    content.querySelectorAll('.section-nav__link').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        navigateToSection(parseInt(link.dataset.section, 10));
      });
    });

    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  function formatContent(lines, isStory) {
    const paragraphs = [];
    let currentPara = [];

    for (const line of lines) {
      const trimmed = line.trim();

      if (trimmed === '') {
        if (currentPara.length > 0) {
          paragraphs.push(currentPara.join(' '));
          currentPara = [];
        }
        continue;
      }

      // Roman numeral or chapter markers (centered)
      if (/^\s{5,}[IVXLC]+\.?\s*$/.test(line) || /^\s{5,}(PART|CHAPTER)\s+/i.test(line)) {
        if (currentPara.length > 0) {
          paragraphs.push(currentPara.join(' '));
          currentPara = [];
        }
        paragraphs.push(`<div class="sub-section">${escapeHtml(trimmed)}</div>`);
        continue;
      }

      // [THE END] / [END]
      if (/^\[THE END\]$|^\[END\]$/i.test(trimmed)) {
        if (currentPara.length > 0) {
          paragraphs.push(currentPara.join(' '));
          currentPara = [];
        }
        paragraphs.push('<div class="the-end">[The End]</div>');
        continue;
      }

      // Section break (* * * or ----)
      if (/^[-*\s]{3,}$/.test(trimmed) && trimmed.length < 20) {
        if (currentPara.length > 0) {
          paragraphs.push(currentPara.join(' '));
          currentPara = [];
        }
        paragraphs.push('<div class="section-divider"></div>');
        continue;
      }

      currentPara.push(trimmed);
    }

    if (currentPara.length > 0) {
      paragraphs.push(currentPara.join(' '));
    }

    return paragraphs.map(p => {
      if (p.startsWith('<')) return p;
      let html = escapeHtml(p);
      html = html.replace(/_(.*?)_/g, '<em>$1</em>');
      return `<p>${html}</p>`;
    }).join('\n');
  }

  function navigateToSection(idx) {
    if (idx >= 0 && idx < sections.length) {
      renderSection(idx);
    }
  }

  function updateTOCActive(idx) {
    tocList.querySelectorAll('.toc-drawer__link').forEach(link => {
      link.classList.toggle('toc-drawer__link--active',
        parseInt(link.dataset.section, 10) === idx);
    });
  }

  function setupProgressBar() {
    window.addEventListener('scroll', () => {
      const scrollTop = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const pct = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
      progressBar.style.width = Math.min(100, pct) + '%';
    }, { passive: true });
  }

  function setupPanels() {
    const tocToggle = document.getElementById('toc-toggle');
    const tocDrawer = document.getElementById('toc-drawer');
    const tocClose = document.getElementById('toc-close');
    const settingsToggle = document.getElementById('settings-toggle');
    const settingsPanel = document.getElementById('settings-panel');
    const settingsClose = document.getElementById('settings-close');
    const overlay = document.getElementById('overlay');

    function closeAll() {
      tocDrawer.classList.remove('open');
      settingsPanel.classList.remove('open');
      overlay.classList.remove('visible');
    }

    tocToggle.addEventListener('click', () => {
      closeAll();
      tocDrawer.classList.add('open');
      overlay.classList.add('visible');
    });

    settingsToggle.addEventListener('click', () => {
      closeAll();
      settingsPanel.classList.add('open');
      overlay.classList.add('visible');
    });

    tocClose.addEventListener('click', closeAll);
    settingsClose.addEventListener('click', closeAll);
    overlay.addEventListener('click', closeAll);

    window.closeTOC = closeAll;
  }

  function closeTOC() {
    if (window.closeTOC) window.closeTOC();
  }

  function setupSettings() {
    const fontSlider = document.getElementById('font-size-slider');
    const fontValue = document.getElementById('font-size-value');
    const lhSlider = document.getElementById('line-height-slider');
    const lhValue = document.getElementById('line-height-value');

    fontSlider.value = Preferences.get('fontSize');
    fontValue.textContent = Preferences.get('fontSize') + 'px';
    lhSlider.value = Preferences.get('lineHeight');
    lhValue.textContent = Preferences.get('lineHeight').toFixed(1);

    fontSlider.addEventListener('input', () => {
      const size = parseInt(fontSlider.value, 10);
      Preferences.setFontSize(size);
      fontValue.textContent = size + 'px';
    });

    lhSlider.addEventListener('input', () => {
      const lh = parseFloat(lhSlider.value);
      Preferences.setLineHeight(lh);
      lhValue.textContent = lh.toFixed(1);
    });

    const currentTheme = Preferences.get('theme');
    document.querySelectorAll('[data-theme-choice]').forEach(btn => {
      btn.classList.toggle('btn--active', btn.dataset.themeChoice === currentTheme);
      btn.addEventListener('click', () => {
        Preferences.setTheme(btn.dataset.themeChoice);
        document.querySelectorAll('[data-theme-choice]').forEach(b =>
          b.classList.toggle('btn--active', b === btn)
        );
      });
    });
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  window.ReaderNav = {
    nextSection() { navigateToSection(currentSection + 1); },
    prevSection() { navigateToSection(currentSection - 1); },
    get currentSection() { return currentSection; },
    get totalSections() { return sections.length; },
  };

  init();
})();
