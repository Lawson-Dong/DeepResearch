import json
import re
from config import MODEL, client

def call_llm(system, user_msg, temperature=0.7):
    """Call DeepSeek API"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg}
        ],
        temperature=temperature,
        max_tokens=8000,
    )
    return resp.choices[0].message.content


def extract_json(text):
    """Extract JSON from model output, tolerating markdown fences and extra text."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Model did not output JSON: " + text[:300])

    return json.loads(text[start:end + 1])