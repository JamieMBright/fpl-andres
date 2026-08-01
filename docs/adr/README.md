# Architecture decision records

Decisions the code already encodes, written down after the fact because the
reasoning was not obvious from the code alone and each of them looks like an
oversight to a fresh reader.

| ADR                                                    | Decision                                               |
| ------------------------------------------------------ | ------------------------------------------------------ |
| [0001](0001-forced-rls-with-no-policies.md)            | Forced row level security with no policies             |
| [0002](0002-immutable-published-artifacts.md)          | Published artifacts are immutable                      |
| [0003](0003-structural-leakage-guards.md)              | Leakage is prevented structurally, not by discipline   |
| [0004](0004-recency-decayed-deployment.md)             | Deployment is classified from recency-decayed evidence |
| [0005](0005-no-partitioning-for-the-history-corpus.md) | The history corpus is not partitioned                  |

Each record states the alternatives that were rejected, because "why not the
obvious thing" is the question a reader actually has.
