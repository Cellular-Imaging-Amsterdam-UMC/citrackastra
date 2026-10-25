(() => {
  const key = 'citrackastra-theme';
  let theme = 'dark';
  try {
    const stored = localStorage.getItem(key);
    if (stored === 'bright' || stored === 'dark') theme = stored;
  } catch (_) { /* A private browser can refuse persistent storage. */ }
  document.documentElement.dataset.theme = theme;
  const bind = () => {
    const button = document.querySelector('[data-theme-toggle]');
    if (!button) return;
    const update = () => {
      button.setAttribute('aria-pressed', String(theme === 'dark'));
      button.setAttribute('aria-label', `Theme: ${theme === 'dark' ? 'Dark' : 'Bright'}. Switch to ${theme === 'dark' ? 'Bright' : 'Dark'}`);
    };
    button.addEventListener('click', () => {
      theme = theme === 'dark' ? 'bright' : 'dark';
      document.documentElement.dataset.theme = theme;
      try { localStorage.setItem(key, theme); } catch (_) { /* Theme still works for this page. */ }
      update();
    });
    update();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once: true });
  else bind();
})();
