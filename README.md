<div align="center">

# 🔎 QueryPilot AI

### Ask your data. QueryPilot does the SQL.

An agentic natural-language-to-SQL analyst. Ask a question in plain English —
QueryPilot inspects your schema, writes the SQL, runs it, and explains the answer.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white">
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-1.45%2B-FF4B4B?logo=streamlit&logoColor=white">
  <img alt="LangChain" src="https://img.shields.io/badge/LangChain-1.0%2B-1C3C3C?logo=langchain&logoColor=white">
  <img alt="Gemini API" src="https://img.shields.io/badge/Google%20Gemini%20API-4285F4?logo=google&logoColor=white">
</p>

<img src="assets/ui-preview.png" alt="QueryPilot AI interface" width="100%">

</div>

---

## Table of contents

- [Overview](#overview)
- [Why it is built this way](#why-it-is-built-this-way)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Usage](#usage)
- [The bundled dataset](#the-bundled-dataset)
- [Project structure](#project-structure)
- [How it works](#how-it-works)
- [Design system](#design-system)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [License](#license)

---

## Overview

QueryPilot AI turns questions into answers without asking you to write SQL.

Type *"Who are the top 5 customers by total spend?"* and the agent loads a SQL
reference, reads the live database schema, composes a query, executes it, and
explains what came back — showing you the SQL and the rows at every step.

It ships with a seeded e-commerce database so it is useful the moment it starts,
and it accepts any SQLite file you upload.

## Why it is built this way

Most text-to-SQL demos paste the whole schema into one prompt and hope the model
gets it right. That breaks quietly: the model invents a column, the query fails
or — worse — returns plausible but wrong numbers, and you have no way to tell.

QueryPilot works the way an analyst does. It gathers context **before** it writes
anything:

1. **Load the rules.** A curated SQL reference (`skills/sql.md`) covering SQLite
   syntax, vetted join patterns, and safety rules.
2. **Read the actual schema.** Live table and column names from the database
   itself, so column names are never guessed.
3. **Then write the query** — and run it read-only.

Each step is a real tool call, and the UI shows all of them. You always see the
SQL that ran and the rows it returned, not just a confident paragraph.

## Features

| | |
|---|---|
| **Plain-English questions** | No SQL knowledge required to get an answer |
| **Schema-grounded** | Reads the live schema before every query, so column names are never invented |
| **Skill-based prompting** | A curated SQL reference is loaded first, cutting syntax errors and bad joins |
| **Agent Activity trace** | Step-by-step checklist of what the agent did, expandable to every tool call's input and output |
| **Live progress** | Stages stream into the UI as they happen — not a fake spinner |
| **Generated SQL** | Shown in a syntax-highlighted block with a copy button |
| **Analyst-grade results** | Sortable tables, metric cards for single values, a chart when the data suits one |
| **Bring your own database** | Upload any SQLite file and query it immediately |
| **Read-only by design** | Only `SELECT` and `WITH … SELECT` reach the database |
| **Graceful failures** | Clear, actionable messages — never a raw traceback |

## Architecture

```
                      ┌──────────────────────────┐
   Your question ───► │   LangChain ReAct agent  │
                      │  (gemma-4-26b-a4b-it)    │
                      └────────────┬─────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
   ┌─────────────┐        ┌────────────────┐       ┌────────────────┐
   │ load_skill  │        │   get_schema   │       │  execute_sql   │
   │ skills/     │        │ sqlite_master  │       │ read-only      │
   │   sql.md    │        │ PRAGMA info    │       │ SELECT / WITH  │
   └─────────────┘        └────────────────┘       └───────┬────────┘
                                                           │
                                                           ▼
                                                    ┌──────────────┐
                                                    │   SQLite DB  │
                                                    └──────┬───────┘
                                                           │
                      ┌────────────────────────────────────┘
                      ▼
          Answer  +  Generated SQL  +  Results table  +  Activity trace
```

The agent decides which tools to call and in what order; the system prompt steers
it through skill → schema → query on every question.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Agent | [LangChain](https://python.langchain.com/) `create_agent` on [LangGraph](https://langchain-ai.github.io/langgraph/) | ReAct loop with tool calling and streamable state |
| Model | `gemma-4-26b-a4b-it` via the Google Gemini API | Open-weights, supports tool calling, free tier |
| UI | [Streamlit](https://streamlit.io/) | Chat UI and data rendering without a separate frontend |
| Database | SQLite | Zero-setup, file-based, trivially swappable |
| Packaging | [uv](https://docs.astral.sh/uv/) | Fast, lockfile-based installs |

## Getting started

### Prerequisites

- **Python 3.12 or newer**
- **A Google AI Studio API key** — [get one free](https://aistudio.google.com/app/apikey)
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip

### 1. Clone the repository

```bash
git clone https://github.com/aj23101/QueryPilot-AI.git
cd QueryPilot-AI
```

### 2. Add your API key

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
copy .env.example .env
```

Open `.env` and paste your key:

```env
GEMINI_API_KEY=your_key_here
```

### 3. Install dependencies

**With uv** (recommended):

```bash
uv sync
```

**With pip:**

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run the app

```bash
uv run streamlit run app.py
```

Or, with the virtual environment activated:

```bash
streamlit run app.py
```

QueryPilot opens at **http://localhost:8501**. The sample database is created
automatically on first run — no extra setup.

## Configuration

All configuration lives in `.env`:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | **Yes** | — | Google AI Studio API key |
| `GOOGLE_API_KEY` | No | — | Accepted as a fallback if `GEMINI_API_KEY` is unset |
| `GEMINI_MODEL` | No | `gemma-4-26b-a4b-it` | Swap in any tool-calling model on the Gemini API |

If the key is missing or still the placeholder, the app says so clearly on
startup instead of throwing a stack trace.

## Usage

### Asking questions

Click one of the six starter prompts on the welcome screen, or type your own in
the input at the bottom. The built-in prompts are:

- *Who are the top 5 customers by total spend?*
- *Which product category generates the most revenue?*
- *What is the average order value by country?*
- *Which customers placed more than 2 orders?*
- *Which products have the highest sales?*
- *Show me monthly revenue trends*

Anything else the schema supports works too, for example *"List all products with
less than 100 units in stock"* or *"How many orders are in each status?"*

### Reading the answer

Each response has up to four parts:

1. **Answer** — the agent's plain-English summary
2. **Generated SQL** — the exact query that ran, syntax-highlighted
3. **Results** — a sortable table, plus metric cards for single-value answers and a chart where the shape fits
4. **Agent Activity** — a collapsible trace: which tools ran, with what inputs, and what each returned

### Using your own database

Select **Uploaded Database** in the sidebar and drop in any `.db`, `.sqlite`, or
`.sqlite3` file. The schema panel, the statistics, and the agent all switch to it
immediately — no restart, no configuration. The chat clears so answers from the
previous database don't mix with the new one.

## The bundled dataset

A small e-commerce store, seeded on first run.

| Table | Rows | Columns |
|---|---|---|
| `customers` | 20 | `id`, `name`, `email`, `city`, `country`, `signup_date` |
| `products` | 25 | `id`, `name`, `category`, `price`, `stock` |
| `orders` | 40 | `id`, `customer_id`, `order_date`, `status` |
| `order_items` | 78 | `id`, `order_id`, `product_id`, `quantity`, `unit_price` |

**Relationships:** `orders.customer_id → customers.id`,
`order_items.order_id → orders.id`, `order_items.product_id → products.id`

**Spread:** 15 countries · 5 categories (Electronics, Clothing, Books,
Home & Garden, Sports) · 5 order statuses (pending, processing, shipped,
delivered, cancelled)

Revenue for a line item is `quantity * unit_price`. Recreate or inspect the
database at any time:

```bash
python database.py
```

## Project structure

```text
QueryPilot-AI/
├── app.py                  # Streamlit UI, chat flow, result rendering
├── agent.py                # Agent, tool definitions, streaming run loop
├── database.py             # SQLite schema and sample-data seeder
├── skills/
│   └── sql.md              # SQL reference the agent loads before querying
├── assets/
│   ├── styles.css          # Component styles for the QueryPilot UI
│   └── ui-preview.png      # Screenshot used in this README
├── .streamlit/
│   └── config.toml         # Dark theme tokens (colors, typography, radii)
├── data/
│   └── ecommerce.db        # Generated on first run (gitignored)
├── .env.example            # API key template
├── requirements.txt        # Dependencies for pip
├── pyproject.toml          # Dependencies for uv
├── uv.lock                 # Pinned dependency versions
└── README.md
```

`app.py` is presentation only. All agent behaviour lives in `agent.py`, and all
schema and seed logic in `database.py`.

## How it works

### The three tools

Defined in [`agent.py`](agent.py):

| Tool | Signature | Does |
|---|---|---|
| `load_skill` | `(skill_name: str) -> str` | Reads `skills/<name>.md` — SQLite syntax rules, query patterns, safety rules |
| `get_schema` | `() -> str` | Queries `sqlite_master` and `PRAGMA table_info` for the live structure |
| `execute_sql` | `(query: str) -> str` | Runs a read-only query, returns a formatted table (first 100 rows) |

### Safety

`execute_sql` rejects anything that is not a `SELECT` or `WITH … SELECT` before
it reaches the database. The agent cannot insert, update, delete, or drop. And
because SQLite's driver executes exactly one statement per call, chained
statements do not get through either.

The schema reader skips SQLite's internal `sqlite_%` tables, so uploaded
databases show only your own tables.

### Two entry points

Both return the same shape — `{"answer": str, "steps": [...]}`:

```python
run_agent(question)                          # runs to completion
run_agent_stream(question, on_stage=...)     # reports each tool call as it happens
```

`run_agent_stream` is what drives the live progress display. It fires a callback
as each tool call is issued, reporting only real tool activity — never model
reasoning.

## Design system

A dark, low-contrast palette built for long sessions. Colors are set through
Streamlit's official theming system in `.streamlit/config.toml`, so native
widgets stay consistent, with `assets/styles.css` handling custom components.

| Token | Value | Use |
|---|---|---|
| Page | `#08090B` | Main background |
| Sunken | `#0D0F12` | Sidebar, input, code blocks |
| Surface | `#111318` | Cards and panels |
| Border | `#242832` | Dividers and outlines |
| Text | `#F5F7FA` / `#9299A6` / `#646B78` | Primary / secondary / muted |
| Accent | `#7C6CFF` | Single accent — focus, links, highlights |
| Success | `#35C98B` | Connected status indicator |

The layout is responsive from wide desktop down to phone width.

## Development

**Regenerate the sample database**

```bash
python database.py
```

**Edit the styling** — `assets/styles.css` is read fresh on every rerun, so
changes hot-reload with the app. `.streamlit/config.toml` changes need a restart.

**Change the model** — set `GEMINI_MODEL` in `.env` to any tool-calling model on
the Gemini API. Tool calling is required; models without it cannot drive the agent.

**Extend the agent's SQL knowledge** — add patterns to `skills/sql.md`. The agent
loads it before every query, so new guidance takes effect immediately with no
code change.

**Add a skill** — drop another `.md` file into `skills/`. `load_skill` will find
it by filename and list it among the available skills.

## Troubleshooting

**`error: uv trampoline failed to canonicalize script path`**

The virtual environment was created at a different path — usually because the
project folder was renamed or moved after `uv sync`. uv bakes an absolute path
into each launcher, and those do not move with the folder. Rebuild them:

```bash
uv sync --reinstall
```

If that reports `Access is denied`, close any running Streamlit process first.

**`GEMINI_API_KEY is not set`**

`.env` is missing, or still holds the placeholder from `.env.example`. Add a real
key from [Google AI Studio](https://aistudio.google.com/app/apikey) and reload.

**PowerShell: "running scripts is disabled on this system"**

Activation is blocked by execution policy. Allow it for the current window only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Or skip activation entirely with `uv run streamlit run app.py`.

**The agent says it cannot find a column**

Ask it to list the schema first, or open the Schema panel in the sidebar to check
the real column names. On an uploaded database, confirm the file actually
contains the tables you expect.

## Limitations

- Answers come from a language model. **Check the generated SQL before acting on anything that matters.**
- The agent reasons over the schema, not the data. Very large or heavily denormalised databases may need a more specific question.
- Results in the table are produced by re-running the agent's own `SELECT` read-only, so the display stays in step with the query shown.
- `execute_sql` returns the first 100 rows to the agent; the results table shows the full result set.
- Charts appear only for one label column plus one numeric column over a readable number of rows — no chart is forced onto data that does not suit one.
- SQLite only. Other engines would need a new schema reader and executor.

## License

Intended for release under the MIT License. No `LICENSE` file has been added to
the repository yet — add one before publishing if that is the intent.

---

<div align="center">

**QueryPilot AI** · Ask your data. QueryPilot does the SQL.

</div>
