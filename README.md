# Football AI Pro — Render build

Files:
- `app.py`
- `requirements.txt`
- `render.yaml`

## Render
Create a Blueprint/Web Service from this repo. `render.yaml` supplies the build/start commands.

Required for automatic NFL/NCAAF odds board:
- `ODDS_API_KEY`

Optional Telegram alerts:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Do not commit API keys/tokens into GitHub.

Notes:
- Auto Board uses consensus sportsbook odds from The Odds API when configured.
- Sharp tickets/handle and 2H play-by-play remain manual unless a separate data provider is connected.
- AI Score is a heuristic model score, not a guaranteed win probability.
