from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import re

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.5-flash-lite"

MAX_PICKER_RESULTS = 15

SKIP_KEYWORDS = ['cliffsnotes', 'sparknotes', 'gradesaver', 'study guide',
                 'criticism', 'annotated', 'interpretation', 'how to',
                 'companion', 'graphic novel', 'illustrated', ' notes',
                 'in america', 'neutronium', 'nineteenth-century',
                 "dostoyevsky's", "dostoevsky's"]


def get_ol_description(ol_key):
    """Fetch the full book description from Open Library."""
    try:
        url = f"https://openlibrary.org{ol_key}.json"
        response = requests.get(url, timeout=10)
        data = response.json()
        desc = data.get("description", "")
        if isinstance(desc, dict):
            return desc.get("value", "")
        return desc if isinstance(desc, str) else ""
    except Exception:
        return ""


def get_book_rating(ol_key):
    """Fetch the average reader rating from Open Library."""
    try:
        url = f"https://openlibrary.org{ol_key}/ratings.json"
        response = requests.get(url, timeout=10)
        data = response.json()
        summary = data.get("summary", {})
        average = summary.get("average", None)
        count = summary.get("count", 0)
        if average:
            return {"average": round(average, 1), "count": count}
    except Exception as e:
        print("Rating error:", e)
    return None


def search_open_library(query):
    """Search Open Library. Returns a list of books, or None if the search itself failed."""
    if " by " in query.lower():
        parts = query.lower().split(" by ", 1)
        title = parts[0].strip()
        author = parts[1].strip()
        url = (f"https://openlibrary.org/search.json?title={requests.utils.quote(title)}"
               f"&author={requests.utils.quote(author)}&limit=25"
               f"&fields=title,author_name,first_publish_year,subject,cover_i,key")
    else:
        url = (f"https://openlibrary.org/search.json?title={requests.utils.quote(query)}"
               f"&limit=50&fields=title,author_name,first_publish_year,subject,cover_i,key")

    data = None
    for attempt in range(2):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            break
        except Exception as e:
            print(f"Open Library attempt {attempt + 1} failed:", e)

    if data is None:
        return None

    books = []
    seen = set()
    query_title = query.lower().split(" by ")[0].strip()
    query_words = set(query_title.split())

    for doc in data.get("docs", []):
        result_title = doc.get("title", "")
        result_title_lower = result_title.lower()
        result_words = set(result_title_lower.split())
        author_str = ", ".join(doc.get("author_name", [])).lower()

        matching_words = query_words & result_words
        match_ratio = len(matching_words) / len(query_words) if query_words else 0
        reverse_ratio = len(matching_words) / len(result_words) if result_words else 0

        is_study_guide = (any(kw in result_title_lower for kw in SKIP_KEYWORDS) or
                          any(kw in author_str for kw in ['spark', 'cliffs', 'gradesaver']))

        exact_match = result_title_lower.strip() == query_title
        close_match = match_ratio >= 0.8 and reverse_ratio >= 0.5

        if not (exact_match or close_match) or is_study_guide:
            continue

        author_name = ", ".join(doc.get("author_name", ["Unknown"]))
        year = str(doc.get("first_publish_year", ""))
        key = f"{result_title_lower}|{author_name.lower()}"
        if key in seen:
            continue
        seen.add(key)

        books.append({
            "title": result_title,
            "author": author_name,
            "year": year,
            "description": "",
            "categories": ", ".join(doc.get("subject", [])[:3]),
            "thumbnail": f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg" if doc.get("cover_i") else "",
            "ol_key": doc.get("key", "")
        })

    books.sort(key=lambda x: int(x['year']) if x['year'].isdigit() else 9999)
    print(f"Open Library results for '{query}': {[(b['title'], b['author'], b['year']) for b in books]}")
    return books[:MAX_PICKER_RESULTS]


def get_book_info(query):
    """Fallback: look up the top match when no book was picked."""
    books = search_open_library(query) or []
    if books:
        first = books[0]
        return {
            "title": first["title"],
            "authors": first["author"],
            "description": get_ol_description(first["ol_key"]) if first["ol_key"] else "",
            "categories": first["categories"]
        }
    return None


def call_llm(prompt):
    """Send the prompt to Gemini and parse the JSON reply."""
    response = requests.post(
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7}
        },
        timeout=60
    )
    result = response.json()

    if "candidates" not in result:
        print("Gemini error:", response.status_code, result)
        raise Exception("The summary service is temporarily unavailable. Please try again later.")

    parts = result["candidates"][0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    text = re.sub(r'```[a-zA-Z]*', '', text).strip()
    start = text.find('{')
    end = text.rfind('}') + 1
    if start != -1 and end > start:
        text = text[start:end]
    text = text.replace('\r', '')
    text = re.sub(r'(?<!\\)\n', ' ', text)
    return json.loads(text)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Please enter a book title."}), 400
    books = search_open_library(query)
    if books is None:
        print(f"Search for '{query}' FAILED")
        return jsonify({"books": [], "failed": True})
    print(f"Search for '{query}' returned {len(books)} books")
    return jsonify({"books": books})


@app.route("/summarize", methods=["POST"])
def summarize():
    data = request.get_json()
    query = data.get("query", "").strip()
    selected_title = data.get("selected_title", "").strip()
    selected_author = data.get("selected_author", "").strip()
    selected_description = data.get("selected_description", "").strip()
    selected_categories = data.get("selected_categories", "").strip()
    selected_ol_key = data.get("selected_ol_key", "").strip()

    if not query:
        return jsonify({"error": "Please enter a book title."}), 400

    rating = get_book_rating(selected_ol_key) if selected_ol_key else None

    if selected_ol_key and not selected_description:
        selected_description = get_ol_description(selected_ol_key)

    if selected_title:
        context = (f"Here is the real information about this book:\nTitle: {selected_title}\n"
                   f"Author: {selected_author}\nGenre: {selected_categories}\n"
                   f"Description: {selected_description or 'No description available.'}\n\n"
                   f"Use this information to generate an accurate summary. "
                   f"Only summarize this exact book. If you are not confident about its plot "
                   f"and characters, say so honestly rather than guessing.")
    else:
        book_info = get_book_info(query)
        if book_info and book_info["description"]:
            context = (f"Here is the real information about this book:\nTitle: {book_info['title']}\n"
                       f"Author: {book_info['authors']}\nGenre: {book_info['categories']}\n"
                       f"Description: {book_info['description']}\n\n"
                       f"Use this information to generate an accurate summary.")
        else:
            context = (f"The user is looking for a summary of: {query}. Only summarize this exact book. "
                       f"If you are not 100% certain about this book's plot and characters, "
                       f"say so honestly rather than guessing.")

    prompt = f"""You are a literary assistant for a book summary app called Nutshells.

{context}

Return ONLY a valid JSON object. No markdown. No code fences. No backticks. Start with {{ and end with }}.

{{
  "title": "Full book title",
  "author": "Author name",
  "genre": "Genre in plain English",
  "characters": [
    {{ "name": "Name", "role": "Protagonist / Antagonist / Supporting", "description": "2-3 sentences about them." }}
  ],
  "plot": "3-4 paragraph summary separated by \\n\\n. Do NOT reveal the ending.",
  "openEnding": "2-3 sentences hinting at what lies ahead without spoiling the ending."
}}

Include 3-5 characters. Raw JSON only. No line breaks inside string values.

Writing rules:
- Write for a general audience, including teenagers, in a neutral and respectful tone.
- Do not use graphic, explicit or sensational language. For sensitive subjects such as sexual violence, abuse, suicide, racism or war, refer to them briefly and in general terms (for example "falsely accused of a serious crime against a white woman" or "faces violence"). Never describe the acts themselves.
- Never use slurs or offensive terms, even if they appear in the book.
- Describe racism and injustice factually, as themes of the story, without endorsing them.
- Stay spoiler-free."""

    try:
        book = call_llm(prompt)
        if rating:
            book["rating"] = rating
        return jsonify(book)
    except json.JSONDecodeError as e:
        print("JSON error:", e)
        return jsonify({"error": "Could not parse the book data. Please try again."}), 500
    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)