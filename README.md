# FinancialAuditBench

A benchmark for evaluating AI agents on financial statement audit tasks. Agents
receive synthetic engagement binders and workpaper templates, perform the
specified audit procedures, and submit completed workpapers for rubric-based
evaluation.

The paper benchmark contains **45 tasks** across six engagement binders, with
45 matching review tasks.

## Setup

Requires Python 3.12 or 3.13, [uv](https://docs.astral.sh/uv/), and Docker for agent
execution. Grading runs locally and requires LibreOffice (`soffice` on `PATH`).
Run from the repository root:

```bash
uv sync
cp .env.example .env
```

Add your provider API keys to `.env`.

Tasks are downloaded automatically from
[Hugging Face](https://huggingface.co/datasets/modusaudit/FinancialAuditBench)
when running the benchmark.

## Run

```bash
uv run fab run --model gpt-6-astra --reasoning-effort medium --grade
```

Results are saved in `jobs/`. Omit `--grade` to skip grading; add `--review`
to run review tasks.

Pass the model name directly, including its provider prefix when needed
(e.g. `openrouter/google/gemini-3.8-flash`). Reasoning effort defaults to `medium`;
use `--num-workers` to set the number of concurrent tasks.

### OpenRouter

Set `FAB_OPENROUTER_STREAM=1` in `.env` for OpenRouter models. Long silent reasoning
can otherwise hit OpenRouter's upstream idle timeout, which returns an empty reply.
Optional settings:

- `FAB_OPENROUTER_PROVIDER`: JSON provider preferences for agent calls (the judge is not pinned), e.g.
  `{"only": ["google-vertex/us"]}`.
- `FAB_JUDGE_MODEL`: route the judge through another provider, e.g.
  `openrouter/openai/gpt-5.6-luna`. The judge model stays the same; the published
  results used OpenAI's Responses API directly.

`.env` does not override variables already exported in your shell.

Grading starts after each model job finishes. Recalculation uses shared batches
of up to 32 workbooks, followed by parallel grading controlled by `--num-workers`.

## Generate synthetic binders

```bash
uv run fab generate-synthetic-binder manufacturing generated_binders/demo --seed 42
```

## Documentation

- [Tasks and grading](docs/benchmark-tasks.md)
- [Published agent trajectories](https://huggingface.co/datasets/modusaudit/FinancialAuditBench-Trajectories)
- [Synthetic binder generation](src/financial_audit_bench/synthetic_binders/README.md)
- [Differential privacy](docs/dp-release/README.md)

## License

Copyright © 2026 Modus Audit Inc. [MIT License](LICENSE).
