# CLAUDE.md

Follow `guideline.md` (the working brief) and `docs/case_brief.docx` (the
organizers' case brief). Where they disagree on a fact, the organizers win.

The architecture rule that overrides convenience, every time:

> **Agents run the investigation. The rule engine is the adjudicator.**
>
> Agents choose what to examine, how deep to go, and what the thresholds should
> be. `roles.py` decides what the role *is*, by comparing a metric to a
> threshold, and emits a `RuleTrace`. The brief disqualifies "a role without an
> explainable rule", so an agent that assigns a role, a score, a cluster or a
> rank is a failed submission, not a feature.

Every agent must declare both:

- `validate()` — its output is checked before use, and rejection is normal.
- `fallback()` — a deterministic result, because the brief forbids requiring a
  paid service to reproduce the outcome.

The calibrator additionally **simulates** its proposed thresholds against the
real distribution before they are accepted, and persists the result to
`config.calibrated.yaml` so runs stay reproducible.

Other non-negotiables:

- `data/` and `starter/` are read-only organizer inputs. Never modify them.
- No hardcoded gids in `src/` or `app/`. Thresholds live in config, and a test
  greps for 5+ digit literals that are not config values.
- Every generated string is a hypothesis for verification, never a statement
  about a person. The blacklist is in `config.yaml` and is enforced in each
  agent's validator *and* again before export.
- `./agent_run.sh` is the entry point; `python run.py` is the pipeline alone.
  Both must work in under 5 minutes with no API key and no network.
- The model is configurable: OpenAI, any OpenAI-compatible `base_url`, or
  none. The tool loop always speaks Chat Completions, because that is what
  self-hosted servers implement.
- Never print a spend figure the tracer could not price. Unpriced means
  unpriced.
- `agent_log.md` is a deliverable. If an agent did something, it is in there.
