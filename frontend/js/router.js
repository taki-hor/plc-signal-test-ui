// Pages are hidden, not removed, so every module keeps rendering into its elements.
const pages = [...document.querySelectorAll('[data-page]')];
const titles = new Map([...document.querySelectorAll('[data-nav]')].map(a => [a.dataset.nav, a.textContent.trim()]));
let onShow = () => {};
function show() {
  const name = location.hash.replace(/^#\/?/, '');
  const page = pages.find(p => p.dataset.page === name || p.id === name) ?? pages[0];
  for (const p of pages) p.classList.toggle('hidden', p !== page);
  for (const link of document.querySelectorAll('[data-nav]')) {
    if (link.dataset.nav === page.dataset.page) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
  document.title = `${titles.get(page.dataset.page) ?? 'Overview'} · Anodizing PLC Signal Test Console`;
  window.scrollTo(0, 0);
  onShow(page.dataset.page);
}
export function go(name) { location.hash = `#/${name}`; }
export function initRouter(callback) { onShow = callback; window.addEventListener('hashchange', show); show(); }
