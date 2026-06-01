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
  searchBooks();
}

function resetSearch() {
  document.getElementById('resultArea').style.display = 'none';
  document.getElementById('bookPicker').style.display = 'none';
  document.getElementById('bookInput').value = '';
  document.getElementById('bookInput').focus();
}

function cancelPicker() {
  document.getElementById('bookPicker').style.display = 'none';
  document.getElementById('bookInput').focus();
}

function toggleFeedback() {
  const form = document.getElementById('feedbackForm');
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

document.getElementById('bookInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') searchBooks();
});

async function searchBooks() {
  const query = document.getElementById('bookInput').value.trim();
  if (!query) return;

  const btn = document.getElementById('searchBtn');
  const loading = document.getElementById('loadingState');
  const result = document.getElementById('resultArea');
  const error = document.getElementById('errorMsg');
  const picker = document.getElementById('bookPicker');

  btn.disabled = true;
  result.style.display = 'none';
  error.style.display = 'none';
  picker.style.display = 'none';
  loading.style.display = 'block';

  try {
    const res = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });

    const data = await res.json();
    loading.style.display = 'none';

   if (!data.books || data.books.length === 0) {
  summarizeBook(query, null);
  return;
}

if (data.books.length === 1) {
  showPicker(data.books, query);
  return;
}

// If user included author, go straight to summary with first result
if (query.toLowerCase().includes(' by ')) {
  showPicker(data.books, query);
  return;
}

    showPicker(data.books, query);

  } catch (err) {
    loading.style.display = 'none';
    error.textContent = "Something went wrong. Please try again.";
    error.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
}

function showPicker(books, query) {
  const picker = document.getElementById('bookPicker');
  const list = document.getElementById('pickerList');
  list.innerHTML = '';

  books.forEach(book => {
    const item = document.createElement('div');
    item.className = 'picker-item';
    item.onclick = () => {
      document.getElementById('bookPicker').style.display = 'none';
      document.getElementById('loadingState').style.display = 'block';
      summarizeBook(query, book);
    };

    const img = book.thumbnail
      ? `<img src="${book.thumbnail}" alt="${book.title}">`
      : `<div class="picker-item-no-img">${book.title.charAt(0)}</div>`;

    item.innerHTML = `
      ${img}
      <div class="picker-info">
        <div class="picker-title">${book.title}</div>
        <div class="picker-author">by ${book.author}</div>
        ${book.year ? `<div class="picker-year">${book.year}</div>` : ''}
      </div>
      <span style="color:var(--sage);font-size:1.2rem">→</span>
    `;
    list.appendChild(item);
  });

  picker.style.display = 'block';
}

async function summarizeBook(query, selectedBook) {
  const loading = document.getElementById('loadingState');
  const result = document.getElementById('resultArea');
  const error = document.getElementById('errorMsg');
  const btn = document.getElementById('searchBtn');

  btn.disabled = true;
  result.style.display = 'none';
  error.style.display = 'none';
  loading.style.display = 'block';

  try {
    const payload = { query };
    if (selectedBook) {
  payload.selected_title = selectedBook.title;
  payload.selected_author = selectedBook.author;
  payload.selected_description = selectedBook.description;
  payload.selected_categories = selectedBook.categories;
  payload.selected_ol_key = selectedBook.ol_key || "";
}

    const res = await fetch('/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
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
const ratingEl = document.getElementById('bookRating');
if (book.rating && book.rating.average) {
  const stars = Math.round(book.rating.average);
  const starStr = '★'.repeat(stars) + '☆'.repeat(5 - stars);
  ratingEl.textContent = `${starStr} ${book.rating.average}/5 (${book.rating.count.toLocaleString()} ratings)`;
  ratingEl.style.display = 'inline-flex';
} else {
  ratingEl.style.display = 'none';
}
  document.getElementById('resultArea').style.display = 'block';
  document.getElementById('resultArea').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function refineSummary() {
  const feedback = document.getElementById('feedbackInput').value.trim();
  const query = document.getElementById('bookInput').value.trim();

  if (!feedback) return;

  const btn = document.querySelector('.btn-refine');
  btn.textContent = 'Regenerating…';
  btn.disabled = true;

  try {
    const res = await fetch('/refine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, feedback })
    });

    const book = await res.json();

    if (book.error) {
      alert('Could not refine. Please try again.');
    } else {
      document.getElementById('feedbackForm').style.display = 'none';
      document.getElementById('feedbackInput').value = '';
      renderResult(book);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  } catch (err) {
    alert('Something went wrong. Please try again.');
  } finally {
    btn.textContent = 'Regenerate with correction →';
    btn.disabled = false;
  }
}