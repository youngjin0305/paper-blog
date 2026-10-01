(() => {
  const form = document.querySelector('form.search');
  if (!form) return;

  const input = form.elements.q;
  const cards = [...document.querySelectorAll('.post-card[data-post-id]')];
  const index = window.paperSearchIndex || {};
  const count = document.getElementById('post-count');
  const empty = document.getElementById('search-empty');
  let timer;

  const normalize = value => value.normalize('NFKC').toLowerCase();
  const apply = () => {
    const query = input.value.trim();
    const terms = normalize(query).split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const card of cards) {
      const text = index[card.dataset.postId] || '';
      card.hidden = !terms.every(term => text.includes(term));
      if (!card.hidden) shown++;
    }
    count.textContent = shown;
    if (empty) empty.hidden = shown !== 0;

    const page = new URL(window.location.href);
    if (query) page.searchParams.set('q', query);
    else page.searchParams.delete('q');
    window.history.replaceState(null, '', page);
    for (const link of document.querySelectorAll('.filter-row a')) {
      const target = new URL(link.href);
      if (query) target.searchParams.set('q', query);
      else target.searchParams.delete('q');
      link.href = target.href;
    }
  };

  input.value = new URL(window.location.href).searchParams.get('q') || '';
  form.addEventListener('submit', event => {
    event.preventDefault();
    clearTimeout(timer);
    apply();
  });
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(apply, 120);
  });
  apply();
})();
