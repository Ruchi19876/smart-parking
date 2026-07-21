/**
 * dashboard.js — SmartPark Live Dashboard JavaScript
 * =====================================================
 * This file contains shared utility functions available on all pages.
 * Page-specific logic (poll loops, chart init) lives in each template's
 * extra_scripts block so it only runs on the right page.
 *
 * Key responsibilities:
 *   - Auto-dismiss flash messages after 4 seconds
 *   - Global toast notification helper
 *   - CSRF-safe fetch helper (adds Content-Type header)
 */

// Auto-dismiss flash messages after 4 seconds
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    document.querySelectorAll('.flash').forEach(el => {
      el.style.transition = 'opacity 0.5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    });
  }, 4000);

  // Close flash on button click
  document.querySelectorAll('.flash-close').forEach(btn => {
    btn.addEventListener('click', () => btn.parentElement.remove());
  });
});

/**
 * Global toast notification helper.
 * Used by page-specific scripts to show status messages.
 * @param {string} msg   - Message to display
 * @param {string} type  - 'success' | 'error' | 'info'
 */
function showToast(msg, type = 'info') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className = `toast toast-${type} toast-show`;
  setTimeout(() => toast.classList.remove('toast-show'), 3500);
}

/**
 * Safe JSON fetch wrapper.
 * Adds Content-Type header and returns parsed JSON.
 * On network error, shows a toast and returns null.
 */
async function apiFetch(url, method = 'GET', body = null) {
  try {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' }
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    return await res.json();
  } catch (err) {
    console.error('[SmartPark] API error:', err);
    showToast('Network error — check console.', 'error');
    return null;
  }
}

/**
 * Theme switcher.
 * Only touches CSS background variables (see [data-theme] rules in
 * style.css) — no layout, component, or logic changes.
 */
const THEME_STORAGE_KEY = 'smartpark-theme';

function applyTheme(theme) {
  if (theme && theme !== 'dark-navy') {
    document.documentElement.setAttribute('data-theme', theme);
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  document.querySelectorAll('.theme-option').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.themeValue === (theme || 'dark-navy'));
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const switcher = document.getElementById('themeSwitcher');
  if (!switcher) return; // not on this page (e.g. login screen)

  const btn = document.getElementById('themeSwitcherBtn');
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || 'dark-navy';
  applyTheme(savedTheme);

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = switcher.classList.toggle('open');
    btn.setAttribute('aria-expanded', isOpen);
  });

  document.querySelectorAll('.theme-option').forEach(option => {
    option.addEventListener('click', () => {
      const theme = option.dataset.themeValue;
      applyTheme(theme);
      localStorage.setItem(THEME_STORAGE_KEY, theme);
      switcher.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
    });
  });

  // Close panel when clicking outside it
  document.addEventListener('click', (e) => {
    if (!switcher.contains(e.target)) {
      switcher.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
    }
  });
});
