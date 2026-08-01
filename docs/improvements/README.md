# Improvement work orders

Full briefs for every item in the [improvement audit](../../IMPROVEMENTS.md).
The audit is the index — one line per candidate fix. These files carry the
detail: verified file and line references, the problem, the implementation
steps, the constraints that must not be broken, the tests to write first, the
acceptance criteria and the validation command.

Each brief is written to be handed to a single agent on its own. An agent should
not need to re-derive context from the audit table or from the rest of the
repository before starting.

| File                                                                                                 | Items   | Category                           |
| ---------------------------------------------------------------------------------------------------- | ------- | ---------------------------------- |
| [01-correctness-and-modelling.md](01-correctness-and-modelling.md)                                   | 1–18    | Correctness and modelling          |
| [02-numerical-and-statistical-rigour.md](02-numerical-and-statistical-rigour.md)                     | 19–32   | Numerical and statistical rigour   |
| [03-python-performance-and-scalability.md](03-python-performance-and-scalability.md)                 | 33–40   | Python performance and scalability |
| [04-ingestion-adapters-and-network-robustness.md](04-ingestion-adapters-and-network-robustness.md)   | 41–57   | Ingestion, adapters and network    |
| [05-persistence-idempotency-and-data-integrity.md](05-persistence-idempotency-and-data-integrity.md) | 58–69   | Persistence and data integrity     |
| [06-security-and-secret-handling.md](06-security-and-secret-handling.md)                             | 70–82   | Security and secret handling       |
| [07-api-and-serverless-functions.md](07-api-and-serverless-functions.md)                             | 83–96   | API and serverless functions       |
| [08-database-schema-and-migrations.md](08-database-schema-and-migrations.md)                         | 97–108  | Database schema and migrations     |
| [09-frontend-architecture-and-performance.md](09-frontend-architecture-and-performance.md)           | 109–125 | Frontend architecture and perf     |
| [10-frontend-accessibility-ux-and-seo.md](10-frontend-accessibility-ux-and-seo.md)                   | 126–137 | Frontend accessibility, UX and SEO |
| [11-contracts-typing-and-api-surface.md](11-contracts-typing-and-api-surface.md)                     | 138–148 | Contracts, typing and API surface  |
| [12-testing-and-reproducibility.md](12-testing-and-reproducibility.md)                               | 149–167 | Testing and reproducibility        |
| [13-ci-cd-tooling-and-developer-experience.md](13-ci-cd-tooling-and-developer-experience.md)         | 168–184 | CI/CD, tooling and DX              |
| [14-documentation-and-governance.md](14-documentation-and-governance.md)                             | 185–204 | Documentation and governance       |

## How to use a brief

1. Read the brief and open the files it names. If a reference has drifted, fix
   the brief in the same change.
2. Write the failing focused test first, then the minimal code, then refactor.
3. Never default a missing controlling FPL rule or sourced parameter — fail its
   source contract visibly. Nothing here overrides
   [`docs/LIMITATIONS.md`](../LIMITATIONS.md).
4. Run the focused validation named in the brief immediately after each
   substantive edit, and `pnpm check` before committing a milestone.
