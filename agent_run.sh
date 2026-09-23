#!/usr/bin/env bash
#
# Money Graph — one command, start to finish.
#
#   ./agent_run.sh                 install -> pipeline -> verify -> viewer + share link
#
# Choosing a model:
#   ./agent_run.sh                 uses .env — OpenAI key, or a self-hosted
#                                  OpenAI-compatible server via MONEYGRAPH_BASE_URL
#   ./agent_run.sh --offline       no model at all; every agent falls back to its
#                                  deterministic path, exports are identical
#   ./agent_run.sh --use-existing  skip the pipeline entirely and open the viewer
#                                  on the results already in the output folder
#
# Other options:
#   --recalibrate    re-run the calibrator agent instead of reusing its saved file
#   --no-app         stop after the exports are verified
#   --no-share       viewer on localhost only, no public link
#   --skip-install   assume dependencies are already present
#   --data DIR       read input from DIR instead of the configured folder
#   --port N         viewer port
#
# Exit codes: 0 all good · 1 pipeline failed · 2 exports missing or malformed
#             3 environment problem

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ----------------------------------------------------------------- options
OFFLINE=0; RECALIBRATE=0; RUN_APP=1; SHARE=1; SKIP_INSTALL=0; PORT=""
USE_EXISTING=0; DATA_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --offline)      OFFLINE=1 ;;
    --use-existing) USE_EXISTING=1 ;;
    --recalibrate)  RECALIBRATE=1 ;;
    --no-app)       RUN_APP=0 ;;
    --no-share)     SHARE=0 ;;
    --skip-install) SKIP_INSTALL=1 ;;
    --data)         DATA_DIR="${2:-}"; shift ;;
    --port)         PORT="${2:-}"; shift ;;
    -h|--help)      sed -n '2,/^[^#]/p' "$0" | grep '^#' | sed 's/^#\{1\} \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 3 ;;
  esac
  shift
done

# ------------------------------------------------------------------ pretty
if [[ -t 1 ]] && [[ "${TERM:-dumb}" != "dumb" ]]; then
  B=$'\033[1m'; DIM=$'\033[2m'; R=$'\033[0m'
  RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; BLU=$'\033[36m'
else
  B=""; DIM=""; R=""; RED=""; GRN=""; YLW=""; BLU=""
fi

STEP=0
step()  { STEP=$((STEP+1)); printf '\n%s[%d/%d]%s %s%s%s\n' "$BLU" "$STEP" "$TOTAL_STEPS" "$R" "$B" "$1" "$R"; }
ok()    { printf '  %s✓%s %s\n' "$GRN" "$R" "$1"; }
warn()  { printf '  %s!%s %s\n' "$YLW" "$R" "$1"; }
fail()  { printf '  %s✗%s %s\n' "$RED" "$R" "$1"; }
info()  { printf '  %s%s%s\n' "$DIM" "$1" "$R"; }
rule()  { printf '%s%s%s\n' "$DIM" "────────────────────────────────────────────────────────────────" "$R"; }

TOTAL_STEPS=5; [[ $RUN_APP -eq 1 ]] && TOTAL_STEPS=6
[[ $USE_EXISTING -eq 1 ]] && TOTAL_STEPS=$((TOTAL_STEPS - 1))

LOG_DIR=".run_logs"; mkdir -p "$LOG_DIR"
PIPELINE_LOG="$LOG_DIR/pipeline.log"
APP_LOG="$LOG_DIR/app.log"

cleanup() {
  local code=$?
  if [[ -n "${APP_PID:-}" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    printf '\n%sshutting the viewer down…%s\n' "$DIM" "$R"
    kill "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
  exit $code
}
trap cleanup INT TERM
trap 'fail "failed at line $LINENO"' ERR

printf '\n%s╭────────────────────────────────────────────────────────────╮%s\n' "$B" "$R"
printf '%s│  Money Graph — reconstructing structure from transfers     │%s\n' "$B" "$R"
printf '%s╰────────────────────────────────────────────────────────────╯%s\n' "$B" "$R"

# ================================================================ 1. python
step "Python environment"

# --- find an interpreter --------------------------------------------------
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done
if [[ -z "$PY" ]]; then
  fail "Python 3.10 or newer was not found on PATH"
  info "install it and re-run, e.g.:  brew install python@3.12"
  info "                              sudo apt install python3 python3-venv"
  exit 3
fi
ok "$("$PY" --version 2>&1) at $(command -v "$PY")"

# --- locate the interpreter inside a venv (posix and windows layouts) -----
venv_python() {
  if   [[ -x "$1/bin/python"        ]]; then echo "$1/bin/python"
  elif [[ -x "$1/Scripts/python.exe" ]]; then echo "$1/Scripts/python.exe"
  else echo ""; fi
}

# --- create the venv, or repair one that is broken ------------------------
# A .venv can exist and still be unusable: a half-finished creation, a venv
# built by a Python that has since been upgraded or uninstalled, a copied
# working tree. Test it rather than trusting that the directory is there.
VPY="$(venv_python .venv)"
VENV_OK=0
if [[ -n "$VPY" ]] && "$VPY" -c 'import sys' >/dev/null 2>&1; then
  VENV_OK=1
fi

if [[ $VENV_OK -eq 1 ]]; then
  ok "using existing .venv ($("$VPY" --version 2>&1))"
else
  if [[ -e .venv ]]; then
    warn ".venv exists but its interpreter does not run — rebuilding it"
    rm -rf .venv
  else
    info "no .venv yet — creating one"
  fi
  if ! "$PY" -m venv .venv >>"$LOG_DIR/venv.log" 2>&1; then
    fail "could not create a virtualenv — see $LOG_DIR/venv.log"
    tail -n 8 "$LOG_DIR/venv.log" 2>/dev/null || true
    info "on Debian/Ubuntu this usually means:  sudo apt install python3-venv"
    exit 3
  fi
  VPY="$(venv_python .venv)"
  if [[ -z "$VPY" ]]; then
    fail "the virtualenv was created but contains no interpreter"
    exit 3
  fi
  ok "created .venv ($("$VPY" --version 2>&1))"
fi

# Everything downstream — including the deliverables check and the viewer —
# expects the output folder to exist even on a first, failed run.
mkdir -p "$("$VPY" -c "import yaml" 2>/dev/null && \
            "$VPY" -c "import yaml;print(yaml.safe_load(open('config.yaml'))['paths']['outputs'])" \
            2>/dev/null || echo output_files)"

# ========================================================== 2. dependencies
step "Dependencies"

# The one check that matters: can the pipeline and the viewer be imported?
deps_present() {
  "$VPY" - <<'PY' >/dev/null 2>&1
import importlib
for mod in ("pandas", "pyarrow", "numpy", "networkx", "scipy",
            "yaml", "gradio", "pyvis"):
    importlib.import_module(mod)
PY
}

install_deps() {
  "$VPY" -m ensurepip --upgrade >>"$LOG_DIR/pip.log" 2>&1 || true
  "$VPY" -m pip install --quiet --upgrade pip >>"$LOG_DIR/pip.log" 2>&1 || true
  "$VPY" -m pip install --quiet -r requirements.txt >>"$LOG_DIR/pip.log" 2>&1
}

if deps_present; then
  ok "already satisfied"
elif [[ $SKIP_INSTALL -eq 1 ]]; then
  # --skip-install must not turn a missing dependency into a confusing crash
  # several steps later.
  fail "--skip-install was passed but the dependencies are not importable"
  info "re-run without --skip-install"
  exit 3
else
  info "installing from requirements.txt (the first run takes a minute)…"
  if ! install_deps || ! deps_present; then
    warn "first install attempt did not satisfy the imports — retrying"
    install_deps || true
  fi
  if deps_present; then
    ok "installed"
  else
    fail "dependencies could not be installed — see $LOG_DIR/pip.log"
    tail -n 15 "$LOG_DIR/pip.log" 2>/dev/null || true
    info "check network access, then re-run"
    exit 3
  fi
fi

# ================================================================= 3. model
step "Agent layer"

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    info "created .env from .env.example (no key set — that is fine)"
  else
    : > .env
    info "created an empty .env"
  fi
fi

HAVE_KEY=0
if [[ $OFFLINE -eq 1 ]]; then
  export MONEYGRAPH_NO_LLM=1
  warn "offline mode (--offline): no model calls, no cost"
  info "roles, clusters and ranks are identical; prose comes from templates"
else
  KEY="$(
    "$VPY" - <<'PY' 2>/dev/null || true
import os, pathlib
p = pathlib.Path(".env")
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
print(next((os.environ[n] for n in ("OPENAI_KEY", "OPENAI_API_KEY") if os.environ.get(n)), ""))
PY
  )"
  if [[ -n "$KEY" ]]; then
    HAVE_KEY=1
    # Ask the client itself, so the banner can never disagree with what runs.
    read -r MODEL ENDPOINT EFFORT <<<"$("$VPY" - <<'PY' 2>/dev/null || echo "? ? ?"
import sys, yaml
sys.path.insert(0, "src")
from moneygraph.agents.llm import LLMClient
from moneygraph.trace import RunTracer
cfg = yaml.safe_load(open("config.yaml"))
c = LLMClient(cfg, RunTracer({**cfg, "tracing": {"print_live": False}}))
print(c.model, c.base_url or "api.openai.com", c.reasoning_effort or "-")
PY
)"
    if [[ "$ENDPOINT" == "api.openai.com" ]]; then
      ok "key found — crew will run on ${B}${MODEL}${R} (reasoning: ${EFFORT})"
    else
      ok "self-hosted model: ${B}${MODEL}${R} at ${B}${ENDPOINT}${R}"
    fi
    # Asked through the tracer itself, so the check and the billing can never
    # disagree about whether a model is priced.
    PRICED="$("$VPY" - <<'PY' 2>/dev/null || echo "no"
import sys, yaml
sys.path.insert(0, "src")
from moneygraph.trace import RunTracer
cfg = yaml.safe_load(open("config.yaml"))
t = RunTracer(cfg)
found = t.rates_for(cfg["llm"]["model"], 0)
print(f"{found[0]['input']}/{found[0]['output']}" if found else "no")
PY
)"
    if [[ "$PRICED" == "no" ]]; then
      warn "no pricing set for $MODEL — tokens will be exact, spend will read 'unpriced'"
    else
      info "priced at \$${PRICED%/*} in / \$${PRICED#*/} out per 1M tokens"
    fi
  else
    export MONEYGRAPH_NO_LLM=1
    warn "no OPENAI_KEY in .env — running deterministically"
    info "the exports are identical either way; set the key in .env for the crew"
  fi
fi

# =============================================================== 4. pipeline
if [[ $USE_EXISTING -eq 1 ]]; then
  OUT_DIR="$("$VPY" -c "import yaml;print(yaml.safe_load(open('config.yaml'))['paths']['outputs'])")"
  if [[ ! -f "$OUT_DIR/nodes_roles.csv" ]]; then
    fail "--use-existing needs a previous run: no $OUT_DIR/nodes_roles.csv"
    info "run it once without the flag to produce them"
    exit 2
  fi
  WHEN="$(date -r "$OUT_DIR/nodes_roles.csv" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "unknown")"
  printf '\n%s[--]%s %sPipeline%s %s(skipped — reusing results from %s)%s\n' \
    "$BLU" "$R" "$B" "$R" "$DIM" "$WHEN" "$R"
  PIPE_RC=0
  ELAPSED=0
else
step "Pipeline"
rule
PIPE_ARGS=()
[[ $RECALIBRATE -eq 1 ]] && PIPE_ARGS+=(--recalibrate)
[[ -n "$DATA_DIR" ]] && PIPE_ARGS+=(--data "$DATA_DIR")

START_TS=$(date +%s)
set +e
"$VPY" run.py ${PIPE_ARGS[@]+"${PIPE_ARGS[@]}"} 2>&1 | tee "$PIPELINE_LOG"
PIPE_RC=${PIPESTATUS[0]}
set -e
ELAPSED=$(( $(date +%s) - START_TS ))
rule

if [[ $PIPE_RC -ne 0 ]]; then
  fail "pipeline exited with code $PIPE_RC after ${ELAPSED}s — full log: $PIPELINE_LOG"
  exit 1
fi
ok "pipeline finished in ${ELAPSED}s"
fi

# ================================================================ 5. verify
step "Deliverables"

OUT_DIR="$("$VPY" -c "import yaml;print(yaml.safe_load(open('config.yaml'))['paths']['outputs'])")"

set +e
"$VPY" - "$OUT_DIR" <<'PY'
import sys, json
from pathlib import Path
import pandas as pd

out = Path(sys.argv[1])
GRN, RED, YLW, DIM, R = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GRN = RED = YLW = DIM = R = ""

REQUIRED = {
    "nodes_roles.csv": ["gid", "role", "role_score", "cluster_id",
                        "priority_score", "evidence"],
    "clusters.csv": ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal",
                     "top_gids", "hypothesis"],
    "top_nodes.csv": ["rank", "gid", "role", "priority_score", "why"],
}

problems = []
print(f"  {'file':<26} {'rows':>7}  status")
print(f"  {DIM}{'-' * 58}{R}")

for name, cols in REQUIRED.items():
    p = out / name
    if not p.exists():
        problems.append(f"{name} was not written")
        print(f"  {name:<26} {'—':>7}  {RED}MISSING{R}")
        continue
    df = pd.read_csv(p)
    issues = []
    missing = [c for c in cols if c not in df.columns]
    if missing:
        issues.append(f"missing columns {missing}")
    elif list(df.columns)[:len(cols)] != cols:
        issues.append("required columns are not in the specified order")
    if df.empty:
        issues.append("no rows")
    if not missing and df[cols].isnull().any().any():
        bad = [c for c in cols if df[c].isnull().any()]
        issues.append(f"nulls in {bad}")
    if name == "top_nodes.csv" and len(df) < 20:
        issues.append(f"only {len(df)} rows, the brief requires at least 20")
    if name == "nodes_roles.csv" and not df["gid"].is_unique:
        issues.append("duplicate gids")

    if issues:
        problems.extend(f"{name}: {i}" for i in issues)
        print(f"  {name:<26} {len(df):>7}  {RED}{issues[0]}{R}")
    else:
        print(f"  {name:<26} {len(df):>7}  {GRN}ok{R}")

extras = ["node_features.parquet", "graph_edges.parquet", "profile_report.md",
          "data_requests.md", "review_notes.md", "agent_log.md",
          "dossiers.json", "run_trace.md", "run_trace.json"]
present = [e for e in extras if (out / e).exists()]
if present:
    print(f"\n  {DIM}also written: {', '.join(present)}{R}")

# ------------------------------------------------- what the roles look like
nr = out / "nodes_roles.csv"
if nr.exists():
    df = pd.read_csv(nr)
    counts = df["role"].value_counts()
    print(f"\n  roles assigned across {len(df):,} accounts:")
    width = max(counts.values) if len(counts) else 1
    for role, n in counts.items():
        bar = "█" * max(1, int(28 * n / width))
        print(f"    {role:<14} {n:>6}  {DIM}{bar}{R}")

tn = out / "top_nodes.csv"
if tn.exists():
    t = pd.read_csv(tn).head(3)
    print(f"\n  top of the review list:")
    for i, row in enumerate(t.to_dict("records"), 1):
        why = str(row.get("why", ""))
        why = why if len(why) <= 92 else why[:89] + "…"
        print(f"    {i}. gid {int(row['gid'])} ({row['role']}, "
              f"{float(row['priority_score']):.3f})")
        print(f"       {DIM}{why}{R}")

if problems:
    print(f"\n  {RED}{len(problems)} problem(s):{R}")
    for p_ in problems:
        print(f"    - {p_}")
    sys.exit(2)
sys.exit(0)
PY
VERIFY_RC=$?
set -e

if [[ $VERIFY_RC -ne 0 ]]; then
  fail "the required CSVs are missing or malformed"
  exit 2
fi
printf '\n'
ok "all three required CSVs are present and valid in ${B}${OUT_DIR}/${R}"

# --------------------------------------------------- time, tokens and spend
printf '\n'
"$VPY" - "$OUT_DIR" <<'PY' || true
import json, sys
from pathlib import Path

trace = Path(sys.argv[1]) / "run_trace.json"
B, DIM, YLW, R = "\033[1m", "\033[2m", "\033[33m", "\033[0m"
if not sys.stdout.isatty():
    B = DIM = YLW = R = ""
if not trace.exists():
    sys.exit(0)

d = json.loads(trace.read_text(encoding="utf-8"))
t = d.get("totals", {})
print(f"  {B}Run trace{R}")
print(f"    runtime        {d.get('total_runtime_s', 0):.2f}s "
      f"{DIM}of a {d.get('runtime_budget_s', 300):.0f}s budget "
      f"({'within' if d.get('within_budget') else 'OVER'}){R}")

stages = sorted(d.get("stages", []), key=lambda s: -s.get("duration_s", 0))[:4]
if stages:
    print(f"    slowest        " + ", ".join(
        f"{s['name']} {s['duration_s']:.1f}s" for s in stages))

n = t.get("n_calls", 0)
if n == 0:
    print(f"    model calls    0 {DIM}(deterministic run){R}")
    print(f"    cost           $0.00")
else:
    print(f"    model calls    {n}" + (f" {YLW}({t['n_failed']} failed){R}"
                                       if t.get("n_failed") else ""))
    print(f"    tokens         {t.get('total_tokens', 0):,} "
          f"{DIM}({t.get('input_tokens', 0):,} in / {t.get('output_tokens', 0):,} out"
          + (f", {t['reasoning_tokens']:,} reasoning" if t.get("reasoning_tokens") else "")
          + f"){R}")
    cost = t.get("cost_usd")
    if cost is None:
        print(f"    cost           {YLW}unpriced{R} "
              f"{DIM}— set llm.pricing in config.yaml{R}")
    else:
        print(f"    cost           ${cost:.4f}"
              + (f" {YLW}({t['n_unpriced_calls']} call(s) unpriced){R}"
                 if t.get("n_unpriced_calls") else ""))
    agents = d.get("by_agent", {})
    if agents:
        print(f"    by agent       " + ", ".join(
            f"{a} x{r['n_calls']}" for a, r in sorted(agents.items())))

if d.get("budget_stopped"):
    print(f"    {YLW}budget         {d['budget_stopped']} — "
          f"the run completed deterministically from there{R}")
for w in (d.get("warnings") or [])[:5]:
    print(f"    {YLW}warning        {w}{R}")
PY

if [[ $RUN_APP -eq 0 ]]; then
  printf '\n%s✓ done.%s Open the viewer any time with: %s./agent_run.sh --use-existing%s\n\n' \
    "$GRN" "$R" "$B" "$R"
  exit 0
fi

# ================================================================== 6. app
step "Viewer"

APP_ARGS=()
[[ $SHARE -eq 1 ]] && APP_ARGS+=(--share) || APP_ARGS+=(--no-share)
[[ -n "$PORT" ]] && APP_ARGS+=(--port "$PORT")

info "starting Gradio…"
[[ $SHARE -eq 1 ]] && info "requesting a public share link (first run downloads a small helper)"

: > "$APP_LOG"
# PYTHONUNBUFFERED: with stdout redirected to a file Python block-buffers, so
# Gradio's "Running on local URL" line would not reach the log until it exits —
# which is exactly when we need to read the URLs out of it.
PYTHONUNBUFFERED=1 "$VPY" app/app.py ${APP_ARGS[@]+"${APP_ARGS[@]}"} >>"$APP_LOG" 2>&1 &
APP_PID=$!

LOCAL_URL=""; SHARE_URL=""
for _ in $(seq 1 90); do
  kill -0 "$APP_PID" 2>/dev/null || break
  [[ -z "$LOCAL_URL" ]] && LOCAL_URL="$(grep -oE 'http://(127\.0\.0\.1|localhost|0\.0\.0\.0):[0-9]+' "$APP_LOG" | head -n1 || true)"
  [[ -z "$SHARE_URL" ]] && SHARE_URL="$(grep -oE 'https://[a-z0-9-]+\.gradio\.live' "$APP_LOG" | head -n1 || true)"
  if [[ -n "$LOCAL_URL" ]] && { [[ -n "$SHARE_URL" ]] || [[ $SHARE -eq 0 ]]; }; then break; fi
  sleep 1
done

if ! kill -0 "$APP_PID" 2>/dev/null; then
  fail "the viewer exited on startup — log: $APP_LOG"
  tail -n 20 "$APP_LOG" || true
  exit 1
fi

# Gradio should have printed it; if the line was swallowed, fall back to the
# port we asked for rather than showing nothing.
if [[ -z "$LOCAL_URL" ]]; then
  FALLBACK_PORT="${PORT:-$("$VPY" -c "import yaml;print(yaml.safe_load(open('config.yaml'))['viewer']['port'])" 2>/dev/null || echo 7860)}"
  LOCAL_URL="http://127.0.0.1:${FALLBACK_PORT}"
fi

printf '\n'
rule
printf '%s  Money Graph is up%s\n\n' "$B" "$R"
[[ -n "$LOCAL_URL" ]]  && printf '    local    %s%s%s\n' "$B" "$LOCAL_URL" "$R"
if [[ $SHARE -eq 1 ]]; then
  if [[ -n "$SHARE_URL" ]]; then
    printf '    share    %s%s%s  %s(public, expires in 1 week)%s\n' "$B" "$SHARE_URL" "$R" "$DIM" "$R"
  else
    printf '    share    %snot ready yet — watch %s%s\n' "$YLW" "$APP_LOG" "$R"
  fi
fi
printf '\n    %sTabs:%s Start here · Who to review first · Account detail · Groups ·\n' "$DIM" "$R"
printf '          Ask · How it decided · Your data · Cost & timing · Downloads\n'
printf '\n    %sDemo path:%s open %sAccount detail%s, paste a gid, and the page shows its role,\n' "$DIM" "$R" "$B" "$R"
printf '               the exact rule that produced it, and a map of the money around it.\n' 
printf '\n    %sCtrl+C to stop.%s\n' "$DIM" "$R"
rule

wait "$APP_PID"
