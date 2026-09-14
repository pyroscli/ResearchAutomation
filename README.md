# Research Intelligence Bot

Telegram research assistant. The bot handles chat, tasks, storage, and delivery. **Cursor Cloud Agents** do the search, reading, ranking, and summaries. The deployed application does not call OpenAI, Anthropic, Gemini, OpenRouter, or Ollama.

## What the MVP does

- `/start`, `/help`, `/search <query>`, `/history`
- Natural-language queries (`Research the latest approaches to LLM inference.`)
- Papers, technical blogs, and YouTube
- Structured JSON from a Cloud Agent → validated → formatted for Telegram
- Postgres: users, sessions, tasks, deduped sources, results

Not in this slice: personal library, follow-up pronouns, GitHub, patents, deep/comparison/learning modes.

## Architecture

Intelligence stays in Cursor Cloud Agents. The Telegram app is orchestration, storage, and delivery. It does not call an LLM API.

```
                         Research Intelligence Layer

   Telegram user
        |
        v
  
    Telegram bot        /start  /help  /search  NL query
    ack + delivery   
 
           |
           v
          
    Task orchestrator --------->  Postgres         
    rate limits                   users, tasks,    
    state machine                 sources, results 
         
           |
           |  launch Cloud Agent (no LLM API in the bot)
           v
  
                 Cursor Cloud Agent                       
                                                       
      Query --> Understand --> Search --> Candidates     
                   |                                     
                   +-- papers -- arXiv / Semantic Scholar / Crossref
                   +-- blogs  -- technical articles
                   +-- videos -- YouTube + transcript
                                                         
      Dedupe --> Rank --> Read --> Analyze --> JSON      

                              |
                              v
                 artifacts/research-result.json
                              |
                              v
  
    Validator        ---> Telegram formatter
 
                                       
                                       v
                                 Telegram user
```

### Research Paper Pipeline

```
                    Query
                      |
                      v
               Search / Retrieval
          /           |           \
     arXiv     Semantic Scholar   Crossref
          \           |           /
                      v
                  Deduplicate
                      |
         
          |           |           |
          v           v           v
     Rank paper  Fetch PDF/   Extract
                 abstract     content
          |           |           |
          
                      |
                      v
              Cloud Agent analyze
                      |
                      v
                   Summary
```

### YouTube Research Workflow

```
  YouTube Search --> Find relevant videos --> Get transcript
                                                  |
                                                  v
                                           Chunk transcript
                                                  |
                                                  v
                                        Cloud Agent summary
                                                  |
                                                  v
                                          Generate timestamps
```

Both pipelines write the same JSON report. Telegram formatting happens after validation, not inside the agent.

### Layers

| Layer | Owns | Must not own |
|---|---|---|
| Telegram interface | `/start`, `/help`, NL query, ack, formatted report | Search, ranking, summarization |
| Task orchestrator | Create task, launch/resume agent, timeouts, rate limits | Reading papers or inventing summaries |
| Postgres | Users, sessions, tasks, deduped sources, results | Intelligence |
| Cloud Research Agent | Query expansion, multi-source search, read, analyze, rank, JSON report | Telegram markup, user IDs, DB writes |
| Validator + formatter | Schema check, chunked Telegram messages, original links | Re-running research or changing claims |

### Task state machine

```
QUEUED --> SEARCHING --> ANALYZING --> SUMMARIZING --> COMPLETED
   |           |             |              |
   +-----------+-------------+--------------+-----> FAILED
```

Telegram gets an immediate “Research started…” message. `FAILED` covers launch errors, run errors, timeouts, and invalid JSON.

### Data model

```
User 1──* ResearchSession 1──* ResearchTask 1──* ResearchResult *──1 Source
```

- **User** — `telegram_user_id`
- **ResearchSession** — `cursor_agent_id`, status
- **ResearchTask** — query, status, `cursor_run_id`
- **Source** — type, unique `canonical_key` (DOI → arXiv id → YouTube id → URL), reliability
- **ResearchResult** — relevance score, verified, summary JSON

Playbook files in `playbook/` are the agent contract. The JSON schema is `playbook/schema/research-result.schema.json`. The agent never emits Telegram HTML — one JSON document per run, then the formatter talks to Telegram.

## Setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Create a Cursor API key at [Cursor Dashboard → Integrations](https://cursor.com/dashboard/integrations). Use a user key or an unrestricted service-account key. Repository-scoped keys cannot create no-repo cloud agents.
3. Copy environment variables:

```bash
cp .env.example .env
```

4. Run the bot in the background (no `python -m researchbot` needed):

```bash
docker compose up -d --build
```

Docker keeps Postgres and the bot running, and restarts them if they crash. Telegram still works from your phone. Stop the old `python -m researchbot` process first if it is still running — Telegram only allows one poller.

Logs:

```bash
docker compose logs -f bot
```

Stop:

```bash
docker compose down
```

This stays up only while this machine is on. If the laptop sleeps or shuts down, the bot goes offline. For always-on (phone only, laptop off), deploy the same Docker image to a VPS, Railway, Render, or Fly.io with `TELEGRAM_BOT_TOKEN`, `CURSOR_API_KEY`, and a Postgres database.

### Local development

```bash
docker compose up -d db
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m researchbot
```

## Agent workspace

By default the orchestrator launches a **no-repo** Cloud Agent and inlines `playbook/` into the prompt. The agent must write `artifacts/research-result.json`.

If this repository is on GitHub, set `PLAYBOOK_REPO_URL` so the agent clones it and reads `playbook/` from disk. The agent is instructed not to edit the bot.

No-repo cloud agents must be enabled on your Cursor account or team.

## Tests

```bash
pytest
```

These cover report validation and Telegram formatting only. They do not call Telegram or Cursor.
