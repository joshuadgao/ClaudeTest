# Daily news briefing

Every morning around 8 AM Eastern, a GitHub Action collects CNBC's business and markets headlines (RSS) and has Claude summarize them. Claude also uses web search to fill in market numbers and the day's calendar. The finished briefing is emailed to you from your Gmail account.

## Setup

1. **Create a Gmail app password.** Turn on 2-Step Verification for your Google account, then create one at https://myaccount.google.com/apppasswords.
2. **Get an Anthropic API key** at https://platform.claude.com/settings/keys. Each briefing costs a few cents.
3. **Add the repository secrets.** Go to Settings → Secrets and variables → Actions → New repository secret:
   - `ANTHROPIC_API_KEY`
   - `GMAIL_ADDRESS`: the Gmail address that sends the email
   - `GMAIL_APP_PASSWORD`: the 16-character app password, without spaces
   - `RECIPIENT_EMAIL` (optional): where the briefing goes. It defaults to `GMAIL_ADDRESS`.
4. **Send a test.** On the Actions tab, open **Daily news briefing** and click **Run workflow**.

The schedule only runs from the repository's default branch, so merge this into it first.

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=... GMAIL_ADDRESS=... GMAIL_APP_PASSWORD=...
DRY_RUN=1 python news_briefing.py   # print instead of emailing
```

To change the topics or format, edit `SYSTEM_PROMPT` and `FEEDS` in `news_briefing.py`.
