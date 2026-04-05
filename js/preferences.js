/* === Preferences (localStorage) — Weird Tales === */
const Preferences = (function () {
  'use strict';

  const KEYS = {
    theme: 'wt-theme',
    fontSize: 'wt-font-size',
    lineHeight: 'wt-line-height',
  };

  const DEFAULTS = {
    theme: 'sepia',
    fontSize: 18,
    lineHeight: 1.72,
  };

  function get(key) {
    try {
      const val = localStorage.getItem(KEYS[key]);
      return val !== null ? JSON.parse(val) : DEFAULTS[key];
    } catch {
      return DEFAULTS[key];
    }
  }

  function set(key, value) {
    try {
      localStorage.setItem(KEYS[key], JSON.stringify(value));
    } catch {
      // localStorage full or disabled
    }
  }

  function setTheme(theme) {
    set('theme', theme);
    document.documentElement.setAttribute('data-theme', theme);
  }

  function setFontSize(size) {
    size = Math.max(14, Math.min(24, size));
    set('fontSize', size);
    document.documentElement.style.setProperty('--font-size', size + 'px');
  }

  function setLineHeight(lh) {
    lh = Math.max(1.4, Math.min(2.2, lh));
    set('lineHeight', lh);
    document.documentElement.style.setProperty('--line-height', lh);
  }

  function applyAll() {
    setTheme(get('theme'));
    setFontSize(get('fontSize'));
    setLineHeight(get('lineHeight'));
  }

  applyAll();

  return { get, set, setTheme, setFontSize, setLineHeight, applyAll };
})();
