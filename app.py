from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import re

app = Flask(__name__)

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/summarize", methods=["POST"])
def summarize():
    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Please enter a book title."}), 400

    prompt = f"""You are a literary assistant for a book summary app called Nutshells. The user wants a summary of: "{query}"

Return ONLY a valid JSON object. No markdown. No code fences. No backticks. Start with {{ and end with }}.

{{
  "title": "Full book title",
  "author": "Author name",
  "genre": "Genre",
  "characters": [
    {{ "name": "Name", "role": "Protagonist / Antagonist / Supporting", "description": "2-3 sentences about them." }}
  ],
  "plot": "3-4 paragraph summary separated by \\n\\n. Do NOT reveal the ending.",
  "openEnding": "2-3 sentences hinting at what lies ahead without spoiling the ending."
}}

Include 3-5 characters. Raw JSON only. No line breaks inside string values."""

    try:
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

        # Clean up markdown fences
        text = re.sub(r'```[a-zA-Z]*', '', text).strip()

        # Extract JSON object
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end > start:
            text = text[start:end]

        # Fix control characters
        text = text.replace('\r', '')
        text = re.sub(r'(?<!\\)\n', ' ', text)

        book = json.loads(text)
        return jsonify(book)

    except json.JSONDecodeError as e:
        print("JSON error:", e)
        return jsonify({"error": "Could not parse the book data. Please try again."}), 500
    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)