<div align="center">

# 🔎 QueryPilot AI

**Ask your data. QueryPilot does the SQL.**

An agentic natural-language-to-SQL analyst. Ask a question in plain English —
QueryPilot inspects your schema, writes the SQL, runs it, and explains the result.

<img src="assets/ui-preview.png" alt="QueryPilot AI" width="100%">

</div>

---

## What it does

Most "text to SQL" demos hand the whole schema to a model and hope for the best.
QueryPilot works the way an analyst does — it gathers context first, then writes
the query:

```
Your question
     │
     ▼
load_skill('sql')     ← SQLite syntax rules + vetted query patterns
     │
     ▼
get_schema()          ← live table and column names, straight from the database
     │
     ▼
execute_sql(query)    ← read-only SELECT, executed against your data
     │
     ▼
Answer + results + full activity trace
```

Every step is a real tool call, and every one of them is visible in the UI. You
see the SQL that ran and the rows that came back — not just a confident-sounding
paragraph.

## Features

- **Plain-English questions** — no SQL knowledge needed to get an answer
- **Schema-grounded** — the agent reads the live schema before writing a query, so it never invents column names
- **Skill-based prompting** — a curated SQL reference (`skills/sql.md`) is loaded before each query, cutting syntax errors and hallucinated joins
- **Agent Activity trace** — a step-by-step checklist of what the agent actually did, expandable to the exact inputs and outputs of every tool call
- **Live progress** — stages stream into the UI as they happen (loading the reference, inspecting the schema, running the query)
- **Analyst-grade results** — sortable tables, metric cards for single-value answers, and a chart when the shape of the data warrants one
- **Bring your own database** — upload any SQLite file and start asking questions immediately
- **Read-only by design** — only `SELECT` and `WITH … SELECT` reach the database; writes are rejected before execution
- **Built-in dataset** — a seeded e-commerce database so the app is useful the moment it starts

## Tech stack

| Layer | Choice |
|---|---|
| Agent | [LangChain](https://python.langchain.com/) `create_agent` (ReAct loop) on [LangGraph](https://langchain-ai.github.io/langgraph/) |
| Model | `gemma-4-26b-a4b-it` via the Google Gemini API |
| UI | [Streamlit](https://streamlit.io/) — themed through `.streamlit/config.toml` plus a scoped stylesheet |
| Database | SQLite (bundled sample, or any file you upload) |

## Quickstart

**Requirements:** Python 3.12+ and a free [Google AI Studio](https://aistudio.google.com/app/apikey) API key.

### 1. Clone

```bash
git clone https://github.com/aj23101/QueryPilot-AI.git
cd QueryPilot-AI
```

### 2. Add your API key

```bash
cp .env.example .env          # Windows PowerShell: copy .env.example .env
```

Open `.env` and paste your key:

```env
GEMINI_API_KEY=your_key_here
```

### 3. Install

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync
```

Or with pip:

```bash
python -m venv .venv
.venv\Scripts\activate         # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Run

```bash
uv run streamlit run app.py
```

Or, with the virtual environment activated:

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501**. The sample database is created
automatically on first run.

## Usage

Click one of the starter prompts, or type your own question. To query your own
data, choose **Uploaded Database** in the sidebar and drop in any `.db`,
`.sqlite`, or `.sqlite3` file — the schema panel and the agent both switch over
to it right away.

Questions the bundled dataset answers well:

- *Who are the top 5 customers by total spend?*
- *Which product category generates the most revenue?*
- *What is the average order value by country?*
- *Which customers placed more than 2 orders?*

## The bundled dataset

| Table | Rows | Contents |
|---|---|---|
| `customers` | 20 | Name, email, city, country, signup date — 15 countries |
| `products` | 25 | Name, category, price, stock across 5 categories |
| `orders` | 40 | Linked to customers, with status and order date |
| `order_items` | 78 | Line items joining orders to products, with quantity and unit price |

Categories: Electronics, Clothing, Books, Home & Garden, Sports.
Order statuses: pending, processing, shipped, delivered, cancelled.

Recreate or inspect it any time:

```bash
python database.py
```

## Configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Google AI Studio key (`GOOGLE_API_KEY` also accepted) |
| `GEMINI_MODEL` | No | `gemma-4-26b-a4b-it` | Swap in another Gemini-API model |

If the key is missing, the app says so plainly on startup instead of throwing a
stack trace at you.

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
├── requirements.txt        # Dependencies for pip installs
├── pyproject.toml          # Dependencies for uv
└── README.md
```

## How the agent is wired

Three tools, defined in [`agent.py`](agent.py):

| Tool | Does |
|---|---|
| `load_skill` | Reads `skills/sql.md` — SQLite syntax rules, query patterns, safety rules |
| `get_schema` | Queries `sqlite_master` and `PRAGMA table_info` for the live structure |
| `execute_sql` | Runs a read-only query and returns a formatted table |

`execute_sql` rejects anything that isn't a `SELECT` or `WITH … SELECT`, so the
agent cannot write to, alter, or drop your data — and because SQLite's driver
executes a single statement per call, chained statements don't get through either.

Two entry points share the same result shape: `run_agent(question)` runs to
completion, and `run_agent_stream(question, on_stage=...)` reports each tool call
as it is issued, which is what drives the live progress display.

## Notes and limits

- Results shown in the table are produced by re-running the agent's own `SELECT` read-only, so the display stays in step with the query you can see.
- Charts appear only when the result is one label column plus one numeric column over a readable number of rows. No chart is forced onto data that doesn't suit one.
- The agent reasons over the schema, not the contents. Very large or heavily denormalised databases may need a more specific question.
- Answers come from a language model. Check the generated SQL before acting on anything that matters.

## License

MIT.
