# CLAUDE.md

Follow `guideline.md`. It is the working brief for this repository: mission,
hard constraints, repo layout, role rules, thresholds policy, phase plan and
definition of done.

Non-negotiables repeated here so they are never missed:

- `data/` and `starter/` are **read-only** organizer inputs. Never modify them.
- No hardcoded gids anywhere in `src/` or `app/`. Thresholds live in `config.yaml`.
- Every generated string is phrased as a hypothesis for verification, never as
  a statement of guilt.
- `python run.py` must run the whole pipeline end to end, deterministically.
