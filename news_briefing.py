"""Build a morning business/markets briefing with Claude and email it via Gmail.

Required environment variables:
  ANTHROPIC_API_KEY    Anthropic API key
  GMAIL_ADDRESS        Gmail account the email is sent from
  GMAIL_APP_PASSWORD   Gmail app password for that account
Optional:
  RECIPIENT_EMAIL      where to send it (defaults to GMAIL_ADDRESS)
  DRY_RUN=1            print the briefing instead of emailing it
"""

import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import anthropic
import feedparser
import markdown

MODEL = "claude-opus-5-5"
EASTERN = ZoneInfo("America/New_York")

# CNBC's public RSS feeds.
FEEDS = {
    "Top News": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "Business": "https://www.cnbc.com/id/10001147/device/rss/rss.html",
    "Economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "Finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "Investing": "https://www.cnbc.com/id/15839069/device/rss/rss.html",
}
LOOKBACK = timedelta(hours=36)

SYSTEM_PROMPT = """You write a concise morning business and markets briefing that is emailed to one reader.

You are given recent CNBC headlines from RSS. Use them as the primary source for the top stories. Use the web search tool to fill in what RSS doesn't carry: the prior session's closing levels for the major indexes, futures, yields, oil, gold, bitcoin and the dollar, and today's scheduled economic data, Fed events and notable earnings.

Pick the stories that matter: market moves, Fed/rates/economic data, major earnings, big corporate news (M&A, layoffs, leadership changes) and macro or geopolitical events moving markets. Skip fluff, listicles and opinion pieces.

Only include facts you found in the provided headlines or your searches from the last 24-36 hours. Never invent numbers; if a figure isn't available, leave it out. On weekends and market holidays, say markets are closed and use the most recent close.

Reply with only the email body in Markdown, in this format:

# Morning Briefing — <weekday, month day, year>

**TL;DR:** 2-3 sentences on the biggest takeaways.

## Markets snapshot
- Bullets for the prior close of the S&P 500, Dow and Nasdaq (with % change), futures if available, and notable moves in the 10-year Treasury yield, oil, gold, bitcoin and the dollar.

## Top stories
5-8 bullets. Each: **bold headline** — 1-2 sentences on what happened and why it matters — [source](url).

## On the radar today
- Scheduled data releases, Fed events and notable earnings.

Keep it readable in under 3 minutes."""


def fetch_headlines(now: datetime) -> list[str]:
    seen = set()
    lines = []
    for section, url in FEEDS.items():
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            print(f"warning: could not read {section} feed: {feed.bozo_exception}", file=sys.stderr)
            continue
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link or link in seen:
                continue
            published = entry.get("published_parsed")
            if published:
                published_at = datetime(*published[:6], tzinfo=timezone.utc)
                if now - published_at > LOOKBACK:
                    continue
                stamp = published_at.astimezone(EASTERN).strftime("%a %b %d %I:%M %p ET")
            else:
                stamp = "time unknown"
            seen.add(link)
            summary = entry.get("summary", "").strip()
            lines.append(f"- [{section}] {entry.get('title', '').strip()} ({stamp})\n  {summary}\n  {link}")
    return lines


def write_briefing(headlines: list[str], now: datetime) -> str:
    client = anthropic.Anthropic()
    today = now.astimezone(EASTERN).strftime("%A, %B %d, %Y, %I:%M %p ET")
    user_prompt = (
        f"It is {today}.\n\n"
        + (
            "Recent CNBC headlines:\n\n" + "\n".join(headlines)
            if headlines
            else "The CNBC feeds returned nothing; rely on web search for today's top business and markets news."
        )
    )
    messages = [{"role": "user", "content": user_prompt}]

    # Web search runs server-side; a long search loop can pause and must be resumed.
    for _ in range(5):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}],
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()
        if response.stop_reason != "pause_turn":
            break
        messages = [{"role": "user", "content": user_prompt}, {"role": "assistant", "content": response.content}]

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined to write the briefing: {response.stop_details}")
    if response.stop_reason not in ("end_turn", "stop_sequence"):
        raise RuntimeError(f"Briefing did not finish (stop_reason={response.stop_reason})")

    # Text before the final searches is narration; the briefing starts at its heading.
    text = "".join(block.text for block in response.content if block.type == "text")
    start = text.find("# Morning Briefing")
    return (text[start:] if start != -1 else text).strip()


def send_email(body_md: str, now: datetime) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    recipient = os.environ.get("RECIPIENT_EMAIL") or sender
    msg = EmailMessage()
    msg["Subject"] = f"Morning Briefing — {now.astimezone(EASTERN).strftime('%a, %b %d')}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body_md)
    html = markdown.markdown(body_md)
    msg.add_alternative(
        f'<html><body style="font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; '
        f'font-size: 15px; line-height: 1.5; max-width: 680px;">{html}</body></html>',
        subtype="html",
    )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, os.environ["GMAIL_APP_PASSWORD"])
        smtp.send_message(msg)
    print(f"Sent briefing to {recipient}")


def main() -> None:
    now = datetime.now(timezone.utc)
    headlines = fetch_headlines(now)
    print(f"Collected {len(headlines)} CNBC headlines")
    briefing = write_briefing(headlines, now)
    if os.environ.get("DRY_RUN"):
        print(briefing)
    else:
        send_email(briefing, now)


if __name__ == "__main__":
    main()
