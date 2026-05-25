#!/usr/bin/env python3
"""
Daily IELTS study material generator.
Fetches BBC 6 Minute English and generates 4-skill IELTS materials via Claude API.
"""

import os, json, datetime, sys, re
import feedparser, requests, anthropic
from bs4 import BeautifulSoup

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "ieltsdaily", "daily")
BBC_RSS    = "https://podcasts.files.bbci.co.uk/p02pc9pj.rss"
HEADERS    = {"User-Agent": "Mozilla/5.0 (compatible; IELTSBot/1.0)"}


def fetch_episode() -> dict:
    feed = feedparser.parse(BBC_RSS)
    if not feed.entries:
        raise RuntimeError("BBC RSS feed returned no entries")

    e = feed.entries[0]
    title = e.get("title", "BBC 6 Minute English")
    link  = e.get("link", "https://www.bbc.co.uk/learningenglish")
    raw   = e.get("summary", "") or e.get("description", "")
    summary = BeautifulSoup(raw, "html.parser").get_text(" ").strip()

    transcript = ""
    try:
        r = requests.get(link, headers=HEADERS, timeout=20)
        if r.ok:
            soup = BeautifulSoup(r.text, "lxml")
            for sel in [
                {"class_": re.compile(r"transcript|script", re.I)},
                {"class_": "widget-bbcle-contentreading-script"},
                {"id": re.compile(r"transcript|content", re.I)},
            ]:
                blocks = soup.find_all("div", **sel)
                if blocks:
                    transcript = " ".join(b.get_text(" ") for b in blocks)
                    break
            if not transcript:
                main = soup.find("main") or soup.find("article")
                if main:
                    transcript = main.get_text(" ")
            transcript = re.sub(r"\s+", " ", transcript).strip()[:3000]
    except Exception as ex:
        print(f"Warning: transcript fetch failed: {ex}")

    return {
        "title": title,
        "url":   link,
        "content": transcript if len(transcript) > 200 else summary,
    }


PROMPT = """You are an expert IELTS teacher (Band 9 level). Based on this BBC 6 Minute English episode, create comprehensive daily IELTS study materials.

Episode title: {title}
Content: {content}

Return a single valid JSON object with EXACTLY this schema. No markdown, no code fences.

{{
  "listening": {{
    "title": "episode title string",
    "url": "episode URL string",
    "source": "BBC 6 Minute English",
    "topic": "one-sentence topic summary in English",
    "topic_zh": "中文話題說明",
    "transcript_excerpt": "200-word natural sounding script passage on the topic",
    "vocabulary": [
      {{"word": "string", "type": "noun|verb|adjective|adverb|phrase", "definition": "clear IELTS-level definition", "definition_zh": "中文解釋", "example": "natural example sentence"}}
    ],
    "questions": [
      {{"q": "comprehension question", "options": ["A: ...", "B: ...", "C: ...", "D: ..."], "answer": "A|B|C|D", "explanation": "why correct"}}
    ]
  }},
  "reading": {{
    "title": "article title",
    "passage": "300-word academic English passage on the topic",
    "questions": [
      {{"type": "TFNG", "statement": "statement text", "answer": "True|False|Not Given", "explanation": "explanation"}},
      {{"type": "TFNG", "statement": "statement text", "answer": "True|False|Not Given", "explanation": "explanation"}},
      {{"type": "TFNG", "statement": "statement text", "answer": "True|False|Not Given", "explanation": "explanation"}},
      {{"type": "MCQ",  "q": "question text", "options": ["A: ...", "B: ...", "C: ...", "D: ..."], "answer": "A|B|C|D", "explanation": "explanation"}}
    ]
  }},
  "speaking": {{
    "topic": "Part 2 topic in English",
    "topic_zh": "中文話題",
    "part2": {{
      "cue_card": "Full cue card text with bullet points using \\n for line breaks",
      "band_tips": ["tip 1", "tip 2", "tip 3"]
    }},
    "part3": [
      {{"q": "discussion question", "q_zh": "中文翻譯", "key_points": ["point 1", "point 2", "point 3"]}},
      {{"q": "discussion question", "q_zh": "中文翻譯", "key_points": ["point 1", "point 2", "point 3"]}},
      {{"q": "discussion question", "q_zh": "中文翻譯", "key_points": ["point 1", "point 2", "point 3"]}},
      {{"q": "discussion question", "q_zh": "中文翻譯", "key_points": ["point 1", "point 2", "point 3"]}}
    ]
  }},
  "writing": {{
    "task2_question": "Full Task 2 essay question",
    "task2_question_zh": "中文翻譯",
    "essay_type": "opinion|discussion|problem-solution|two-part",
    "useful_phrases": [
      {{"phrase": "academic phrase", "when_to_use": "usage context in English", "when_to_use_zh": "中文使用時機", "example": "example in a sentence"}}
    ],
    "outline": {{
      "intro": "suggested introduction strategy",
      "body1": "first body paragraph main idea",
      "body2": "second body paragraph main idea",
      "conclusion": "conclusion approach"
    }}
  }}
}}

Requirements: vocabulary = 5 items, listening questions = 3, reading questions = 4 (3 TFNG + 1 MCQ), part3 = 4 questions, useful_phrases = 5 items. All at IELTS Band 7-9 level."""


def generate(episode: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": PROMPT.format(
            title=episode["title"],
            content=episode["content"][:2500],
        )}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    data["listening"]["url"]   = episode["url"]
    data["listening"]["title"] = episode["title"]
    return data


def save(data: dict, date: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = {"date": date, "generated_at": datetime.datetime.utcnow().isoformat() + "Z", **data}
    path = os.path.join(OUTPUT_DIR, f"{date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved {path}")
    return path


def notify(date: str):
    topic = os.environ.get("NTFY_TOPIC", "")
    if not topic:
        return
    try:
        r = requests.post(
            f"https://ntfy.sh/{topic}",
            data="四科學習素材已就緒，今日雅思練習開始！".encode(),
            headers={
                "Title":    "📚 每日雅思學習",
                "Priority": "default",
                "Tags":     "books,mortar_board",
                "Click":    f"https://148car.github.io/ieltsdaily/?date={date}",
            },
            timeout=15,
        )
        print(f"✓ Notification sent ({r.status_code})")
    except Exception as ex:
        print(f"Warning: notification failed: {ex}")


def main():
    today = datetime.date.today().isoformat()
    out_path = os.path.join(OUTPUT_DIR, f"{today}.json")

    if os.path.exists(out_path) and "--force" not in sys.argv:
        print(f"Already generated for {today}. Use --force to regenerate.")
        return

    print(f"▶ Generating IELTS content for {today}...")
    episode = fetch_episode()
    print(f"  Episode: {episode['title']} ({len(episode['content'])} chars)")

    data = generate(episode)
    print("✓ Claude generation complete")

    save(data, today)
    notify(today)
    print("✓ Done!")


if __name__ == "__main__":
    main()
