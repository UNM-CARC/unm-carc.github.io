/* Shared selection logic is exported for the build's date-boundary tests. */
(function (root) {
  function chooseNotices(notices, now) {
    const current = notices.filter(n => n.status === 'active' ||
      (n.status === 'scheduled' && Date.parse(n.start) <= now && now < Date.parse(n.end)));
    const upcoming = notices.filter(n => n.status === 'scheduled' && Date.parse(n.start) > now)
      .sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
    return current.concat(upcoming.slice(0, 1));
  }
  if (typeof module !== 'undefined') module.exports = { chooseNotices };
  if (!root.document) return;
  const ticker = document.querySelector('.gg-ticker');
  if (!ticker) return;
  const data = JSON.parse(document.getElementById('gg-ticker-data').textContent);
  const track = ticker.querySelector('.gg-ticker-track');
  const motion = root.matchMedia('(prefers-reduced-motion: reduce)');
  let lastSelection = '';
  function render(force) {
    const notices = chooseNotices(data.notices, Date.now());
    const selection = JSON.stringify(notices);
    if (!force && selection === lastSelection) return;
    // Don't replace a link while someone is interacting with the ticker.
    if (!force && ticker.contains(document.activeElement)) return;
    lastSelection = selection;
    const group = document.createElement('div');
    group.className = 'gg-ticker-group';
    notices.map(n => ({ ...n, maintenance: true })).concat(data.news).forEach(item => {
      const link = document.createElement('a');
      link.href = item.url;
      link.className = 'gg-ticker-item' + (item.maintenance ? ' gg-ticker-maintenance' : '');
      const kind = document.createElement('span');
      kind.className = 'gg-ticker-kind';
      kind.textContent = item.maintenance ? 'MAINTENANCE' : 'NEWS';
      const star = document.createElement('span');
      star.className = 'gg-ticker-star';
      star.setAttribute('aria-hidden', 'true');
      star.textContent = '✦';
      link.append(kind, document.createTextNode(' ' + item.title), star);
      group.append(link);
    });
    track.replaceChildren(group);
    ticker.classList.toggle('is-moving', !motion.matches);
    if (!motion.matches) {
      const copy = group.cloneNode(true);
      copy.setAttribute('aria-hidden', 'true');
      copy.querySelectorAll('a').forEach(a => a.tabIndex = -1);
      track.append(copy);
      track.style.setProperty('--ticker-duration', Math.max(30, group.offsetWidth / 35) + 's');
    }
  }
  motion.addEventListener('change', () => render(true));
  root.addEventListener('resize', () => {
    const group = track.firstElementChild;
    if (group) track.style.setProperty('--ticker-duration', Math.max(30, group.offsetWidth / 35) + 's');
  });
  render(true);
  root.setInterval(() => render(false), 60000);
})(typeof window !== 'undefined' ? window : globalThis);
