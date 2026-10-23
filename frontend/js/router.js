// Pages are hidden, not removed, so every module keeps rendering into its elements.
const pages = [...document.querySelectorAll('[data-page]')];
const titles = new Map([...document.querySelectorAll('[data-nav]')].map(a => [a.dataset.nav, a.textContent.trim()]));
let onShow = () => {};
function focusHeading() {
  const heading = pages.find(page => !page.classList.contains('hidden'))?.querySelector('h1');
  if (heading) { heading.tabIndex = -1; heading.focus({preventScroll:true}); }
}
function show(event) {
  const name = location.hash.replace(/^#\/?/, '');
  const page = pages.find(p => p.dataset.page === name || p.id === name) ?? pages[0];
  for (const p of pages) p.classList.toggle('hidden', p !== page);
  for (const link of document.querySelectorAll('[data-nav]')) {
    if (link.dataset.nav === page.dataset.page) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
  document.title = `${titles.get(page.dataset.page) ?? 'Overview'} · Anodizing PLC Signal Test Console`;
  const activeLink = document.querySelector('[data-nav][aria-current=page]');
  if (matchMedia('(max-width:900px)').matches) activeLink?.scrollIntoView({block:'nearest',inline:'nearest'});
  window.scrollTo(0, 0);
  onShow(page.dataset.page);
  if (event?.type === 'hashchange') focusHeading();
}
export function go(name) { location.hash = `#/${name}`; }
export function initRouter(callback) {
  onShow = callback;
  document.getElementById('skip-link').addEventListener('click',event => { event.preventDefault(); focusHeading(); document.activeElement.scrollIntoView({block:'start'}); });
  const offset = new ResizeObserver(() => {
    const sticky = document.querySelector(matchMedia('(max-width:900px)').matches ? '.sidebar' : '.topbar');
    document.documentElement.style.scrollPaddingTop = `${Math.ceil(sticky.getBoundingClientRect().height)+12}px`;
  });
  offset.observe(document.querySelector('.topbar')); offset.observe(document.querySelector('.sidebar'));
  window.addEventListener('hashchange', show); show();
}
