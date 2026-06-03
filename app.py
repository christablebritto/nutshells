from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import re

app = Flask(__name__)

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

SKIP_KEYWORDS = ['cliffsnotes', 'sparknotes', 'gradesaver', 'study guide',
                 'criticism', 'annotated', 'interpretation', 'how to',
                 'companion', 'graphic novel', 'illustrated', ' notes',
                 'in america', 'neutronium', 'nineteenth-century',
                 "dostoyevsky's", "dostoevsky's"]


def get_ol_description(ol_key):
    try:
        url = f"https://openlibrary.org{ol_key}.json"
        response = requests.get(url, timeout=10)
        data = response.json()
        desc = data.get("description", "")
        if isinstance(desc, dict):
            return desc.get("value", "")
        return desc if isinstance(desc, str) else ""
    except:
        return ""


def get_book_rating(ol_key):
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
    try:
        if " by " in query.lower():
            parts = query.lower().split(" by ")
            title = parts[0].strip()
            author = parts[1].strip()
            url = f"https://openlibrary.org/search.json?title={requests.utils.quote(title)}&author={requests.utils.quote(author)}&limit=5&fields=title,author_name,first_publish_year,subject,cover_i,key,description"
        else:
            url = f"https://openlibrary.org/search.json?title={requests.utils.quote(query)}&limit=10&fields=title,author_name,first_publish_year,subject,cover_i,key,description"

        response = requests.get(url, timeout=10)
        data = response.json()

        books = []
        seen = set()
        query_title = query.lower().split(" by ")[0].strip()
        query_words = set(query_title.split())

        if "docs" in data:
            for doc in data["docs"]:
                result_title = doc.get("title", "")
                result_title_lower = result_title.lower()
                result_words = set(result_title_lower.split())
                author_str = ", ".join(doc.get("author_name", [])).lower()

                matching_words = query_words & result_words
                match_ratio = len(matching_words) / len(query_words) if query_words else 0
                reverse_ratio = len(matching_words) / len(result_words) if result_words else 0

                is_study_guide = any(kw in result_title_lower for kw in SKIP_KEYWORDS) or any(kw in author_str for kw in ['spark', 'cliffs', 'gradesaver'])

                exact_match = result_title_lower.strip() == query_title.strip()
                close_match = match_ratio >= 0.8 and reverse_ratio >= 0.5 and not is_study_guide

                if exact_match or close_match:
                    author_name = ", ".join(doc.get("author_name", ["Unknown"]))
                    year = str(doc.get("first_publish_year", ""))

                    description = ""
                    raw_desc = doc.get("description", "")
                    if isinstance(raw_desc, str) and raw_desc:
                        description = raw_desc
                    elif doc.get("key"):
                        description = get_ol_description(doc["key"])

                    key = f"{result_title_lower}|{author_name.lower()}"
                    if key not in seen:
                        seen.add(key)
                        books.append({
                            "title": result_title,
                            "author": author_name,
                            "year": year,
                            "description": description,
                            "categories": ", ".join(doc.get("subject", [])[:3]),
                            "thumbnail": f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-M.jpg" if doc.get("cover_i") else "",
                            "ol_key": doc.get("key", "")
                        })

        books.sort(key=lambda x: int(x['year']) if x['year'].isdigit() else 9999)
        print(f"Open Library results for '{query}': {[(b['title'], b['author'], b['year']) for b in books]}")
        return books
    except Exception as e:
        print("Open Library error:", e)
    return []


def get_book_info(query):
    try:
        books = search_open_library(query)
        if books:
            return {
                "title": books[0]["title"],
                "authors": books[0]["author"],
                "description": books[0]["description"],
                "categories": books[0]["categories"]
            }
    except Exception as e:
        print("Open Library error:", e)
    return None


def call_mistral(prompt):
    response = requests.post(
        url="https://api.mistral.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "mistral-large-latest",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7
        }
    )
    result = response.json()
    text = result["choices"][0]["message"]["content"].strip()
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
    print(f"Search for '{query}' returned {len(books)} books")
    if not books:
        return jsonify({"books": []})
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

    if selected_description:
        context = f"Here is the real information about this book:\nTitle: {selected_title}\nAuthor: {selected_author}\nGenre: {selected_categories}\nDescription: {selected_description}\n\nUse this information to generate an accurate summary."
    else:
        book_info = get_book_info(query)
        if book_info and book_info["description"]:
            context = f"Here is the real information about this book:\nTitle: {book_info['title']}\nAuthor: {book_info['authors']}\nGenre: {book_info['categories']}\nDescription: {book_info['description']}\n\nUse this information to generate an accurate summary."
        else:
            context = f"The user is looking for a summary of: {query}. Only summarize this exact book. If you are not 100% certain about this book's plot and characters, say so honestly rather than guessing."

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

Include 3-5 characters. Raw JSON only. No line breaks inside string values."""

    try:
        book = call_mistral(prompt)
        if rating:
            book["rating"] = rating
        return jsonify(book)
    except json.JSONDecodeError as e:
        print("JSON error:", e)
        return jsonify({"error": "Could not parse the book data. Please try again."}), 500
    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/refine", methods=["POST"])
def refine():
    data = request.get_json()
    query = data.get("query", "").strip()
    feedback = data.get("feedback", "").strip()

    if not query or not feedback:
        return jsonify({"error": "Missing information."}), 400

    book_info = get_book_info(feedback) or get_book_info(query)

    if book_info and book_info["description"]:
        context = f"Here is the real information about this book:\nTitle: {book_info['title']}\nAuthor: {book_info['authors']}\nGenre: {book_info['categories']}\nDescription: {book_info['description']}\n\nThe user also provided this correction: {feedback}\n\nUse this information to generate an accurate summary."
    else:
        context = f"The user searched for: \"{query}\"\nThe previous summary was wrong. User correction: \"{feedback}\"\nPlease generate an accurate summary based on the correction."

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

Include 3-5 characters. Raw JSON only. No line breaks inside string values."""

    try:
        book = call_mistral(prompt)
        return jsonify(book)
    except json.JSONDecodeError as e:
        print("JSON error:", e)
        return jsonify({"error": "Could not parse the book data. Please try again."}), 500
    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)