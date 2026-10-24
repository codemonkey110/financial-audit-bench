# Current project architecture

This document describes the architecture implemented by the repository today.
It complements the [cloud deployment architecture](cloud-architecture.md), which
is a proposed target rather than a description of running infrastructure.

## Benchmark execution and grading

```mermaid
flowchart LR
    User[Researcher] -->|fab run / regrade| CLI[Local CLI]
    Env[Local .env and exported settings] -.-> CLI

    CLI -->|Resolve pinned revision or --tasks-dir| Dataset[Task dataset]
    Dataset -->|tasks, review_tasks, inputs| CLI
    CLI -->|Select tasks, copy assets, hash sources| Prepared[artifacts/harbor]
    CLI -->|Write config and run metadata| Experiments[experiments/run-id]
    Prepared --> Harbor[Harbor CLI subprocess]
    Experiments -->|Job configuration| Harbor

    Harbor -->|Concurrent trials| Docker[Docker task environments]
    Docker -->|Prompt, task files, workspace| Agent[AuditAgent]
    Agent -->|Model requests| Models[LLM provider APIs]
    Agent -->|bash tool calls| Docker
    Agent -->|Trajectory and logs| Jobs[(Local jobs/job-name)]
    Docker -->|Workbooks and trial results| Jobs
    Harbor -->|Job result| Jobs

    Jobs -->|Optional --grade| Grader[Host-side grading]
    Prepared -->|Task tests and rubric| Grader
    Grader -->|Recalculate workbooks| LO[LibreOffice]
    Grader -->|Optional semantic checks| Judge[Judge model API]
    Grader -->|Reports, scores, updated results| Jobs
    Jobs -->|fab regrade copies source job| Regrade[New local regrade job]
    Regrade --> Grader
    User -->|Inspect saved results| Jobs
```

The `fab` command runs on the user's machine. It downloads the default
revision-pinned dataset from Hugging Face or accepts a local dataset directory,
selects tasks, prepares a Harbor dataset under `artifacts/harbor`, and writes
run configuration and metadata under `experiments/`. It then invokes Harbor as
a subprocess. Harbor runs trials in Docker task environments; the benchmark's
`AuditAgent` requests model completions and executes the model's bash tool calls
through the Harbor environment. Job results, trial artifacts, and agent
trajectories are saved under the local `jobs/` directory.

Grading is optional and runs after the Harbor job completes. It is performed by
the local Python process, not inside the task containers. The grader prepares
a temporary shared workbook-recalculation cache, uses LibreOffice, evaluates
rubrics, and may call a judge model for declared semantic checks. Reports,
scores, and updated Harbor results are written into the job directory.
`fab regrade` copies a saved job to a new local job directory and grades it
against the selected task catalog and current rubrics.

## Synthetic binder generation

```mermaid
flowchart LR
    User[Researcher] -->|fab generate-synthetic-binder| CLI[Local CLI]
    CLI --> Config[Business type, seed, output directory]
    Priors[Shipped DP priors and authored rules] --> Pipeline[Staged generation pipeline]
    Config --> Pipeline
    Pipeline --> Profile[Engagement profile and financial world]
    Profile --> Plan[Audit plan]
    Plan --> Project[Project binder documents]
    Project --> Validate[PBC validation]
    Validate -->|Binder files and generation manifest| Output[(Local output directory)]
```

Binder generation is a separate local CLI workflow. It uses shipped priors and
authored rules, executes staged generation and validation, and writes a binder
package plus a generation manifest to the requested output directory. It does
not require model API calls.

## Deployment boundary

The repository currently provides a CLI and local file-based run state. Dataset
assets may come from Hugging Face; model and optional judge requests go to
provider APIs. There is no implemented run API, coordinator service, queue,
job metadata database, or shared cloud object store. See the
[cloud architecture](cloud-architecture.md) for a provider-neutral proposal
that moves execution and grading into independently managed workers.
