"""
Streamlit UI for QueryPilot AI — "Ask your data. QueryPilot does the SQL."

Run: streamlit run app.py

This module is presentation only. All agent behaviour lives in agent.py and all
schema/seed logic lives in database.py; nothing here changes either.
"""

import html
import re
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from database import DB_PATH, init_db

APP_DIR = Path(__file__).parent

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="QueryPilot AI",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Importing the agent builds the LLM client, which fails fast if the API key is
# missing. Surface that as a readable message instead of a Streamlit traceback.
try:
    from agent import run_agent, run_agent_stream, set_db_path
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

# Ensure the bundled DB exists on every startup
init_db()


# ── Styling ────────────────────────────────────────────────────────────────────

def load_css() -> str:
    """Read the stylesheet fresh each rerun so edits hot-reload with the app."""
    path = APP_DIR / "assets" / "styles.css"
    return path.read_text(encoding="utf-8") if path.exists() else ""


st.markdown(f"<style>{load_css()}</style>", unsafe_allow_html=True)


# ── Constants ──────────────────────────────────────────────────────────────────

SAMPLE_QUESTIONS = [
    "Who are the top 5 customers by total spend?",
    "Which product category generates the most revenue?",
    "What is the average order value by country?",
    "Which customers placed more than 2 orders?",
    "Which products have the highest sales?",
    "Show me monthly revenue trends",
]

WORKFLOW = [
    "Your question",
    "Schema understanding",
    "SQL generation",
    "Query execution",
    "Data insight",
]

# Order the activity trace follows, with the label shown once a step completes.
STEP_ORDER = ["load_skill", "get_schema", "execute_sql"]
STEP_DONE_LABEL = {
    "load_skill": "SQL skill loaded",
    "get_schema": "Database schema inspected",
    "execute_sql": "SQL generated and executed",
}


# ── Data helpers ───────────────────────────────────────────────────────────────

def get_active_db_path() -> Path:
    """Return the currently active database path from session state."""
    return st.session_state.get("active_db_path", DB_PATH)


@st.cache_data(show_spinner=False)
def get_schema_map(db_path: str, mtime: float) -> dict[str, list[tuple]]:
    """Return {table_name: [column_info, ...]}. `mtime` busts the cache."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        schema = {}
        for table in tables:
            cursor.execute(f'PRAGMA table_info("{table}")')
            schema[table] = cursor.fetchall()
        conn.close()
        return schema
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def get_table_counts(db_path: str, mtime: float) -> dict[str, int]:
    """Row count per table, for the sidebar statistics grid."""
    counts: dict[str, int] = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        for (table,) in cursor.fetchall():
            try:
                counts[table] = cursor.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
            except sqlite3.Error:
                continue
        conn.close()
    except Exception:
        pass
    return counts


def db_signature(path) -> float:
    """Modification time of the active DB, used as a cache key."""
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return 0.0


def fetch_dataframe(sql: str, db_path) -> pd.DataFrame | None:
    """
    Re-run the agent's SELECT read-only to get structured rows for the results
    table and charts. The agent's own text output stays the source of truth;
    this is display sugar, so any failure just falls back to that text.
    """
    if not sql:
        return None
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned.upper().startswith(("SELECT", "WITH")):
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            return pd.read_sql_query(cleaned, conn)
        finally:
            conn.close()
    except Exception:
        return None


def last_sql(steps: list) -> str:
    """The most recent SQL the agent actually executed."""
    for step in reversed(steps):
        if step.get("tool") == "execute_sql":
            args = step.get("input") or {}
            if isinstance(args, dict) and args.get("query"):
                return str(args["query"]).strip()
    return ""


def friendly_error(exc: Exception) -> str:
    """Map raw exceptions onto something a user can act on."""
    text = str(exc)
    low = text.lower()
    if "api key" in low or "api_key" in low or "permission_denied" in low or "401" in low:
        return (
            "QueryPilot could not authenticate with the model provider. "
            "Check that `GEMINI_API_KEY` in your `.env` file is a valid "
            "Google AI Studio key, then reload the page."
        )
    if "quota" in low or "rate limit" in low or "429" in low or "resource_exhausted" in low:
        return (
            "The model provider is rate-limiting requests right now. "
            "Wait a moment and ask again."
        )
    if "deadline" in low or "timeout" in low or "timed out" in low:
        return "The request took too long to complete. Try asking again, or narrow the question."
    if "connect" in low or "network" in low or "dns" in low:
        return "QueryPilot could not reach the model provider. Check your internet connection and try again."
    # Anything unexpected: one trimmed line, never a traceback.
    first_line = text.strip().splitlines()[0] if text.strip() else "Unknown error"
    return f"QueryPilot could not complete that request. {first_line[:220]}"


# ── Render helpers ─────────────────────────────────────────────────────────────

def esc(value) -> str:
    return html.escape(str(value))


# Streamlit's markdown treats `$` as a LaTeX delimiter, so an answer containing
# two currency amounts renders everything between them as italic maths. Escape
# only `$` that introduces a number, leaving genuine LaTeX untouched.
_CURRENCY_DOLLAR = re.compile(r"\$(?=\s?[\d.,])")


def md_safe(text: str) -> str:
    """Make agent prose safe for st.markdown without mangling currency."""
    return _CURRENCY_DOLLAR.sub(lambda _: "\\$", text or "")


def fmt_int(n: int) -> str:
    return f"{n:,}"


def render_agent_activity(steps: list, expanded: bool = False) -> None:
    """
    Collapsible trace of what the agent actually did. Shows only real tool
    calls, their inputs and their outputs — no model reasoning.
    """
    if not steps:
        return

    called = [s.get("tool") for s in steps]
    done = [t for t in STEP_ORDER if t in called]

    with st.expander(f"Agent Activity · {len(steps)} steps", expanded=expanded):
        # Checklist summary
        for tool_name in STEP_ORDER:
            if tool_name in done:
                st.markdown(
                    f'<div class="qp-act-step"><span class="qp-act-check">&#10003;</span>'
                    f"{esc(STEP_DONE_LABEL[tool_name])}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="qp-act-step qp-act-pending"><span>&#8212;</span>'
                    f"{esc(STEP_DONE_LABEL[tool_name])} (not used)</div>",
                    unsafe_allow_html=True,
                )

        st.divider()

        # Per-call detail
        for i, step in enumerate(steps, 1):
            tool_name = step.get("tool", "tool")
            tool_input = step.get("input") or {}
            tool_output = step.get("output") or ""

            if tool_name == "execute_sql":
                title = f"{i}. execute_sql"
            elif tool_name == "get_schema":
                title = f"{i}. get_schema"
            elif tool_name == "load_skill":
                skill = tool_input.get("skill_name", "") if isinstance(tool_input, dict) else ""
                title = f"{i}. load_skill · {skill}" if skill else f"{i}. load_skill"
            else:
                title = f"{i}. {tool_name}"

            st.markdown(f'<div class="qp-block-label">{esc(title)}</div>',
                        unsafe_allow_html=True)

            if tool_name == "execute_sql":
                query = tool_input.get("query", "") if isinstance(tool_input, dict) else ""
                st.code(query or str(tool_input), language="sql")
            elif isinstance(tool_input, dict) and tool_input:
                st.code(str(tool_input), language="python")

            preview = tool_output[:900] + (" …" if len(tool_output) > 900 else "")
            st.text(preview or "(no output)")


def render_metrics(df: pd.DataFrame) -> None:
    """
    Metric cards for results that are genuinely a small set of headline numbers,
    i.e. a single row of aggregates. Not forced onto ordinary tables.
    """
    numeric = df.select_dtypes(include="number")
    if len(df) != 1 or numeric.empty or len(numeric.columns) > 4:
        return

    cols = st.columns(len(numeric.columns))
    for col_box, name in zip(cols, numeric.columns):
        value = numeric.iloc[0][name]
        if pd.isna(value):
            shown = "—"
        elif float(value).is_integer():
            shown = fmt_int(int(value))
        else:
            shown = f"{float(value):,.2f}"
        label = str(name).replace("_", " ").strip().title()
        with col_box:
            st.metric(label=label, value=shown, border=True)


def maybe_chart(df: pd.DataFrame) -> None:
    """
    Draw a bar chart only when the shape clearly suits one: a single label
    column plus exactly one numeric column, over a readable number of rows.
    """
    numeric_cols = list(df.select_dtypes(include="number").columns)
    label_cols = [c for c in df.columns if c not in numeric_cols]

    if len(numeric_cols) != 1 or len(label_cols) != 1 or not (2 <= len(df) <= 25):
        return

    label_col, value_col = label_cols[0], numeric_cols[0]

    # A label column of near-unique free text (e.g. emails) charts badly.
    if df[label_col].nunique() != len(df):
        return

    with st.expander("Chart", expanded=False):
        st.bar_chart(
            df.set_index(label_col)[value_col],
            horizontal=True,
            use_container_width=True,
        )


def render_results(df: pd.DataFrame | None, fallback_text: str) -> None:
    """Results as a real table when we can rebuild them, else the agent's text."""
    if df is None:
        if fallback_text:
            st.markdown('<div class="qp-block-label">Results</div>',
                        unsafe_allow_html=True)
            st.text(fallback_text[:2000])
        return

    if df.empty:
        st.markdown(
            '<div class="qp-empty-note">That query ran successfully but matched '
            "no rows. Try widening the filters or asking a broader question.</div>",
            unsafe_allow_html=True,
        )
        return

    render_metrics(df)

    # A single scalar already shown as a metric card needs no table under it.
    if len(df) == 1 and len(df.columns) == 1 and not df.select_dtypes(include="number").empty:
        return

    st.markdown('<div class="qp-block-label">Results</div>', unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.markdown(
        f'<div class="qp-rowcount">{fmt_int(len(df))} '
        f'{"row" if len(df) == 1 else "rows"} · {len(df.columns)} columns</div>',
        unsafe_allow_html=True,
    )
    maybe_chart(df)


def render_sql(sql: str) -> None:
    """Generated SQL in a highlighted block (Streamlit adds its own copy button)."""
    if not sql:
        return
    st.markdown('<div class="qp-block-label">Generated SQL</div>',
                unsafe_allow_html=True)
    st.code(sql, language="sql")


def render_answer(entry: dict) -> None:
    """Render one assistant turn: answer, SQL, results, activity trace."""
    if entry.get("error"):
        st.markdown(
            '<div class="qp-error">'
            '<div class="qp-error-title">Something went wrong</div>'
            f'<div class="qp-error-body">{esc(entry["error"])}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        if entry.get("steps"):
            render_agent_activity(entry["steps"])
        return

    if entry.get("content"):
        st.markdown(md_safe(entry["content"]))

    sql = entry.get("sql", "")
    render_sql(sql)

    df = None
    if sql:
        df = fetch_dataframe(sql, entry.get("db_path", DB_PATH))
    render_results(df, entry.get("result_text", ""))

    render_agent_activity(entry.get("steps", []))


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div class="qp-side-brand">'
        '<div class="qp-logo">&#128270;</div>'
        '<div class="qp-side-brand-name">QueryPilot AI</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Database selector ──
    st.markdown('<div class="qp-side-head">Database</div>', unsafe_allow_html=True)
    db_mode = st.radio(
        "Choose a database",
        options=["Bundled E-Commerce Database", "Uploaded Database"],
        index=0,
        label_visibility="collapsed",
    )

    if db_mode == "Uploaded Database":
        uploaded_file = st.file_uploader(
            "Upload Database",
            type=["db", "sqlite", "sqlite3"],
            help="Any SQLite file. QueryPilot inspects its schema automatically.",
        )
        if uploaded_file is not None:
            # Save to a temp file that persists for this session
            if "uploaded_db_path" not in st.session_state or \
               st.session_state.get("uploaded_db_name") != uploaded_file.name:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".db", delete=False, dir=APP_DIR / "data"
                )
                tmp.write(uploaded_file.getbuffer())
                tmp.close()
                st.session_state["uploaded_db_path"] = tmp.name
                st.session_state["uploaded_db_name"] = uploaded_file.name
                st.session_state["messages"] = []  # clear chat for new DB

            active_path = Path(st.session_state["uploaded_db_path"])
            st.session_state["active_db_path"] = active_path
            set_db_path(active_path)
        else:
            # No file uploaded yet — fall back to bundled
            st.session_state["active_db_path"] = DB_PATH
            set_db_path(DB_PATH)
    else:
        st.session_state["active_db_path"] = DB_PATH
        set_db_path(DB_PATH)

    active_db = get_active_db_path()
    is_bundled = active_db == DB_PATH
    db_label = (
        "Bundled E-Commerce"
        if is_bundled
        else st.session_state.get("uploaded_db_name", "Uploaded database")
    )

    st.markdown(
        '<div class="qp-db-active">'
        '<span class="qp-dot"></span>'
        f'<span class="qp-db-active-name">{esc(db_label)}</span>'
        "</div>",
        unsafe_allow_html=True,
    )

    if db_mode == "Uploaded Database" and is_bundled:
        st.caption("No file uploaded yet — showing the bundled dataset.")

    # ── Compact statistics ──
    sig = db_signature(active_db)
    counts = get_table_counts(str(active_db), sig)
    schema_map = get_schema_map(str(active_db), sig)

    if counts:
        cards = []
        # For the bundled set, show the three tables a reader cares about rather
        # than the first three alphabetically (which buries `products`).
        if is_bundled:
            preferred = [t for t in ("customers", "products", "orders") if t in counts]
            shown = [(t, counts[t]) for t in preferred]
        else:
            shown = list(counts.items())[:3]

        for table, n in shown:
            cards.append(
                '<div class="qp-stat">'
                f'<div class="qp-stat-value">{fmt_int(n)}</div>'
                f'<div class="qp-stat-label">{esc(table.replace("_", " ").title())}</div>'
                "</div>"
            )
        # Fourth card: categories for the bundled set, table count otherwise.
        if is_bundled:
            try:
                conn = sqlite3.connect(active_db)
                cat_n = conn.execute(
                    "SELECT COUNT(DISTINCT category) FROM products"
                ).fetchone()[0]
                conn.close()
                cards.append(
                    '<div class="qp-stat">'
                    f'<div class="qp-stat-value">{fmt_int(cat_n)}</div>'
                    '<div class="qp-stat-label">Categories</div>'
                    "</div>"
                )
            except sqlite3.Error:
                pass
        else:
            cards.append(
                '<div class="qp-stat">'
                f'<div class="qp-stat-value">{fmt_int(len(counts))}</div>'
                '<div class="qp-stat-label">Tables</div>'
                "</div>"
            )
        st.markdown(f'<div class="qp-stats">{"".join(cards)}</div>',
                    unsafe_allow_html=True)

    # ── Schema viewer ──
    st.markdown('<div class="qp-side-head">Schema</div>', unsafe_allow_html=True)
    if schema_map:
        for table_name, columns in schema_map.items():
            with st.expander(f"{table_name} · {len(columns)}"):
                rows = []
                for col in columns:
                    is_pk = bool(col[5])
                    name_cls = "qp-col-name qp-col-pk" if is_pk else "qp-col-name"
                    key_mark = " &#128273;" if is_pk else ""
                    rows.append(
                        '<div class="qp-col">'
                        f'<span class="{name_cls}">{esc(col[1])}{key_mark}</span>'
                        f'<span class="qp-col-type">{esc(col[2])}</span>'
                        "</div>"
                    )
                st.markdown("".join(rows), unsafe_allow_html=True)
    else:
        st.caption("No tables found in this database.")

    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        st.session_state["messages"] = []
        st.rerun()


# ── Header ─────────────────────────────────────────────────────────────────────

active_db = get_active_db_path()
is_bundled = active_db == DB_PATH
header_db = (
    "ecommerce.db" if is_bundled
    else st.session_state.get("uploaded_db_name", "uploaded.db")
)

st.markdown(
    '<div class="qp-header">'
    '  <div class="qp-brand">'
    '    <div class="qp-logo">&#128270;</div>'
    "    <div>"
    '      <div class="qp-brand-name">QueryPilot AI</div>'
    '      <div class="qp-brand-sub">AI-Powered Data Analyst</div>'
    "    </div>"
    "  </div>"
    '  <div class="qp-header-right">'
    '    <span class="qp-pill qp-pill--live"><span class="qp-dot"></span>Connected</span>'
    f'    <span class="qp-pill"><code>{esc(header_db)}</code></span>'
    "  </div>"
    "</div>",
    unsafe_allow_html=True,
)

# Init chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Resolve the pending question up front. st.chat_input always pins to the bottom
# of the viewport regardless of where it is called, so reading it here lets the
# hero disappear on the same run that answers the first question.
question: str | None = st.chat_input("Ask QueryPilot about your data...")
if "pending_q" in st.session_state:
    question = st.session_state.pop("pending_q")

# ── Hero / empty state ─────────────────────────────────────────────────────────

if not st.session_state["messages"] and not question:
    flow = f'<span class="qp-flow-arrow">&#8594;</span>'.join(
        f'<span class="qp-flow-step">{esc(s)}</span>' for s in WORKFLOW
    )
    st.markdown(
        '<div class="qp-hero">'
        '  <div class="qp-hero-mark">&#128270;</div>'
        '  <h1 class="qp-hero-brand">QueryPilot AI</h1>'
        '  <div class="qp-hero-tagline">Ask your data anything.</div>'
        '  <p class="qp-hero-sub">Ask questions in plain English. QueryPilot '
        "inspects your database, writes the SQL, executes it, and explains the "
        "result.</p>"
        f'  <div class="qp-flow">{flow}</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="qp-section-label">Start with an example</div>',
                unsafe_allow_html=True)

    left, right = st.columns(2, gap="small")
    for i, q in enumerate(SAMPLE_QUESTIONS):
        target = left if i % 2 == 0 else right
        with target:
            if st.button(q, key=f"qp-example-{i}", use_container_width=True):
                st.session_state["pending_q"] = q
                st.rerun()

# ── Chat history ───────────────────────────────────────────────────────────────

for msg in st.session_state["messages"]:
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(md_safe(msg["content"]))
    else:
        with st.chat_message("assistant", avatar="🔎"):
            render_answer(msg)

# ── Run the pending question ───────────────────────────────────────────────────

if question:
    # Ensure agent is pointed at the active DB before running
    set_db_path(get_active_db_path())

    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user", avatar="👤"):
        st.markdown(md_safe(question))

    with st.chat_message("assistant", avatar="🔎"):
        progress = st.empty()
        completed: list[str] = []

        def show_progress(current: str = "Understanding your question") -> None:
            done_rows = "".join(
                f'<div class="qp-act-step"><span class="qp-act-check">&#10003;</span>'
                f"{esc(label)}</div>"
                for label in completed
            )
            progress.markdown(
                f'<div class="qp-running"><span class="qp-spin"></span>'
                f"QueryPilot is analyzing your data…</div>{done_rows}"
                f'<div class="qp-act-step qp-act-pending">'
                f"<span>&#8250;</span>{esc(current)}</div>",
                unsafe_allow_html=True,
            )

        def on_stage(_tool: str, label: str) -> None:
            show_progress(label)
            completed.append(label)

        show_progress()

        entry: dict = {"role": "assistant", "db_path": get_active_db_path()}
        try:
            result = run_agent_stream(question, on_stage=on_stage)
            entry["content"] = result.get("answer") or "No answer generated."
            entry["steps"] = result.get("steps", [])
        except Exception as exc:  # noqa: BLE001 — surfaced as a friendly message
            entry["error"] = friendly_error(exc)
            entry["steps"] = []

        progress.empty()

        steps = entry.get("steps", [])
        entry["sql"] = last_sql(steps)
        entry["result_text"] = next(
            (s.get("output", "") for s in reversed(steps)
             if s.get("tool") == "execute_sql"),
            "",
        )

        render_answer(entry)

    st.session_state["messages"].append(entry)

st.markdown(
    '<div class="qp-input-hint">QueryPilot runs read-only SELECT queries. '
    "Always verify results before acting on them.</div>",
    unsafe_allow_html=True,
)
