const SPINE_COLORS = [
  '#2d5a3d','#3d7a52','#5a8a6a','#2d6b4a','#4a7a5a',
  '#3d5a2d','#6b8a3d','#2d4a3d','#5a6b2d','#3d6b5a'
];

function getSpineColor(title) {
  let hash = 0;
  for (let c of title) hash = (hash * 31 + c.charCodeAt(0)) & 0xffffffff;
  return SPINE_COLORS[Math.abs(hash) % SPINE_COLORS.length];
}

function fillAndSearch(val) {
  document.getElementById('bookInput').value = val;
  summarizeBook();
}

function resetSearch() {
  document.getElementById('resultArea').style.display = 'none';
  document.getElementById('bookInput').value = '';
  document.getElementById('bookInput').focus();
}

document.getElementById('bookInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') summarizeBook();
});

async function summarizeBook() {
  const query = document.getElementById('bookInput').value.trim();
  if (!query) return;

  const btn = document.getElementById('searchBtn');
  const loading = document.getElementById('loadingState');
  const result = document.getElementById('resultArea');
  const error = document.getElementById('errorMsg');

  btn.disabled = true;
  result.style.display = 'none';
  error.style.display = 'none';
  loading.style.display = 'block';

  try {
    const res = await fetch('/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });

    const book = await res.json();

    if (book.error) {
      error.textContent = book.error;
      error.style.display = 'block';
    } else {
      renderResult(book);
    }
  } catch (err) {
    error.textContent = "Something went wrong. Please try again.";
    error.style.display = 'block';
  } finally {
    loading.style.display = 'none';
    btn.disabled = false;
  }
}

function renderResult(book) {
  document.getElementById('bookTitle').textContent = book.title;
  document.getElementById('bookAuthor').textContent = `by ${book.author}`;
  document.getElementById('bookGenre').textContent = book.genre;

  const spine = document.getElementById('bookSpine');
  spine.style.background = getSpineColor(book.title);
  spine.textContent = book.title.charAt(0).toUpperCase();

  const grid = document.getElementById('charactersGrid');
  grid.innerHTML = '';
  for (const char of book.characters) {
    const card = document.createElement('div');
    card.className = 'char-card';
    card.innerHTML = `
      <div class="char-name">${char.name}</div>
      <div class="char-role">${char.role}</div>
      <div class="char-desc">${char.description}</div>
    `;
    grid.appendChild(card);
  }

  const plotEl = document.getElementById('plotText');
  plotEl.innerHTML = book.plot.split('\n').filter(p => p.trim()).map(p => `<p>${p}</p>`).join('');

  document.getElementById('openEndingText').textContent = book.openEnding;

  document.getElementById('resultArea').style.display = 'block';
  document.getElementById('resultArea').scrollIntoView({ behavior: 'smooth', block: 'start' });
}