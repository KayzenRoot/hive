# Claude for Open Source application evidence

This document is a reviewer-facing evidence map for HIVE's application to the
Claude for Open Source Program. It is intentionally conservative: it records
verifiable facts and does not substitute aspirational adoption for measured
ecosystem usage.

Verified against the official Anthropic program terms on 2026-09-18.

## Project identity

HIVE is a public, local-first developer-tooling platform for large
LLM-assisted software projects. It combines project-scoped context and memory,
hybrid retrieval, token-budget controls, governed execution, evidence-producing
review gates, and a local Control Center. The repository is maintained by
KayzenRoot and its stable v1.0.0 release is publicly available.

License: Apache-2.0 (OSI approved).

## Eligibility evidence

| Requirement | HIVE evidence |
|---|---|
| Public open-source project | Public GitHub repository `KayzenRoot/hive` |
| OSI-approved license | Root `LICENSE` is Apache-2.0 and GitHub identifies the repository as Apache-2.0 |
| Recent public OSS activity | Public commits, pull requests, reviews and the v1.0.0 release are present in September 2026 |
| Maintainer role | KayzenRoot owns and maintains the repository and has merge/admin control |
| Working software | v1.0.0 release, Docker Compose quick start, CI, integration evidence and automated tests are public |
| Security/contribution paths | `SECURITY.md`, `CONTRIBUTING.md`, `SUPPORT.md`, issue/PR templates and CodeQL are present |

The applicant must separately satisfy personal requirements that cannot be
proved by repository contents, including age, residency/export eligibility,
GitHub-account age/good standing, and Anthropic-affiliation restrictions.

## Track assessment

HIVE does not currently claim any Maintainer Track numeric threshold. In
particular, this document does not claim 500 dependent repositories, 100
dependent packages, 200,000 monthly registry downloads, 100 merged PRs into
third-party repositories, 20 external merged-PR contributors, or an OpenSSF
criticality score of 0.4.

The intended application route is the discretionary **Ecosystem Impact Track**.
The argument is based on HIVE's function as developer infrastructure, its
maintainer's substantive role, and the public technical evidence in this
repository. HIVE is newly open-sourced, so downstream adoption should not be
invented or implied where it has not yet been measured.

## Application statement

The following statement is deliberately below the program's 500-word limit:

> I maintain HIVE, an Apache-2.0 local-first developer-tooling platform for
> large software projects built with LLM assistance. HIVE addresses a recurring
> infrastructure problem in AI-assisted development: models lose project
> context, repeatedly ingest the same material, and can make changes without a
> durable chain from requirements and architecture to tests, review evidence,
> and release state.
>
> HIVE provides project-scoped durable memory and content-addressed intake,
> Git-aware repository indexing, lexical/semantic/hybrid retrieval,
> checkpoint-first context assembly, progressive disclosure, adaptive token
> budgets, context fingerprints, delta context, provider/prompt-cache adapters,
> governed execution, and deterministic review evidence. It is designed to be
> provider-independent and local-first, with PostgreSQL/pgvector as canonical
> durable storage and Redis only as a noncanonical cache.
>
> The public v1.0.0 repository includes Docker-based installation,
> security/support/contribution policies, CI, CodeQL, deterministic validation,
> integration checks, and extensive automated tests. The project is maintained
> directly by me and is now distributed under the OSI-approved Apache License
> 2.0 so other developers can inspect, use, modify, and contribute to it.
>
> HIVE is newly open-sourced and I am not claiming adoption metrics that do not
> yet exist. I am applying through the Ecosystem Impact Track because its
> function is foundational developer tooling: reducing context loss and token
> waste while making AI-assisted software work more reproducible, auditable,
> and safer to maintain. Claude Max would be used directly for HIVE
> maintenance: implementation and refactoring, test generation, security and
> architecture review, documentation, issue/PR triage, and improving the
> provider-independent context and evaluation infrastructure.

## Planned subscription use

Use Claude Max for substantive HIVE maintenance: architecture and code review,
implementation/refactoring, regression-test design, security review,
documentation, issue/PR triage, and evaluation of context-retrieval and
token-efficiency behavior. Do not describe the benefit as API credits: the
program benefit is a personal six-month Claude Max 20x subscription.

## Reviewer navigation

Start with `README.md`, then inspect `docs/INSTALLATION.md`,
`docs/CONTEXT-MANAGER.md`, `SECURITY.md`, `CONTRIBUTING.md`, the
`benchmarks/` directory, and the GitHub Actions history. Canonical scope,
architecture, decisions and checkpoints are under `docs/project-brain/`.

## Submission safeguards

- Apply once with the maintainer's real GitHub account.
- Do not purchase, exchange, automate or otherwise inflate engagement metrics.
- Do not claim downstream dependents or usage that cannot be verified.
- Use an email address the applicant can access for an activation link.
- If approved, activate within the period stated in the then-current official
  terms and keep the subscription for the approved individual's use only.
