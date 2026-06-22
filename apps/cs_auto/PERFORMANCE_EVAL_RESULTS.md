# CS Auto Actual Evaluation Results

## Sources

- [analysis 2026-06-16 17:08:39 accuracy_summary.csv](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260616_170839/analysis_agent/accuracy_summary.csv)
- [analysis 2026-06-16 17:08:39 confusion_matrix.md](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260616_170839/analysis_agent/confusion_matrix.md)
- [analysis 2026-06-16 17:08:39 report.json](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260616_170839/analysis_agent/report.json)
- [answer 2026-06-18 16:19:07 report.json](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260618_161907/answer_agent/report.json)
- [answer 2026-06-22 06:39:53 report.json](/C:/SKN25-FINAL-6Team/apps/tests/cs-auto_tests/eval/20260622_063953/answer_agent/report.json)

## `analysis_agent`

### Table 1. Axis accuracy

| Axis | Correct | Total | Accuracy |
|---|---:|---:|---:|
| `risk_level` | 132 | 143 | 92.31% |
| `category` | 126 | 143 | 88.11% |
| `routing_target` | 117 | 143 | 81.82% |
| `sentiment` | 111 | 143 | 77.62% |

### Interpretation

- The strongest axis is `risk_level`.
- The biggest operational story is `routing_target` at 81.82%.
- This means ticket understanding is relatively stable, but evidence-path selection is still the main bottleneck.

### Table 2. `routing_target` class metrics

| Class | Gold | Predicted | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| `fixed_answer` | 20 | 23 | 86.96% | 100.00% | 93.02% |
| `doc_only` | 57 | 57 | 84.21% | 84.21% | 84.21% |
| `DB_only` | 39 | 30 | 90.00% | 69.23% | 78.26% |
| `DB&DOC` | 27 | 33 | 66.67% | 81.48% | 73.33% |

### Interpretation

- `fixed_answer` recall is perfect, so conservative fallback handling is strong.
- `DB_only` precision is high, but recall is weak. True DB-only cases are being missed.
- `DB&DOC` has the lowest precision. Ambiguous cases are being over-routed into the hybrid class.

The clean summary is:

- safe on fallback
- under-captures `DB_only`
- over-predicts `DB&DOC`

### Table 3. Main routing confusions

| Gold | Predicted | Count | Meaning |
|---|---|---:|---|
| `DB_only` | `DB&DOC` | 6 | personal-state questions are over-promoted to hybrid |
| `doc_only` | `DB&DOC` | 5 | document-only questions are being mixed with state/policy logic |
| `DB&DOC` | `doc_only` | 3 | some true hybrid cases are being simplified too much |
| `fixed_answer` | other | 0 | fallback safety is stable |

### Why this is a good talking point

`analysis_agent` is not failing in a generic way. It has a specific bias:

- it avoids missing `fixed_answer`
- it tends to push uncertain cases into `DB&DOC`

That is a realistic production behavior. It is safer than random failure, but it creates extra cost and can blur the distinction between document-only and mixed-evidence responses.

## `answer_agent`

## Scope

These evaluation files do not measure full final-answer quality. They mainly measure:

- DB route decision accuracy
- SQL path execution success
- document retrieval hit rates

So the tables below should be read as retrieval-path performance, not as complete final-response correctness.

### Table 4. Best run vs latest run

| Metric | 2026-06-18 16:19:07 | 2026-06-22 06:39:53 | Interpretation |
|---|---:|---:|---|
| Tickets | 25 | 64 | latest eval is much larger |
| DB cases | 21 | 28 | broader DB coverage in latest run |
| Document cases | 13 | 36 | much wider document evaluation in latest run |
| DB router accuracy | 100.00% | 96.43% | still very strong |
| Document retrieval execution success | 13/13 = 100.00% | 36/36 = 100.00% | runtime stability is intact |
| Gold document hit | 13/13 = 100.00% | 22/36 = 61.11% | retrieval precision drops on larger set |
| Gold chunk hit | 13/13 = 100.00% | 20/36 = 55.56% | exact-grounding precision also drops |

### Interpretation

- The latest `answer_agent` is not failing to run.
- The weakness is retrieval precision, not orchestration stability.
- On a small set it achieved perfect document hit rates, but on a larger set the real bottleneck appears.

The best presentation line is:

- path selection is close to stable
- scaling bottleneck is document retrieval precision

### Table 5. Performance progression

| Run | DB router accuracy | Gold document hit | Gold chunk hit | Interpretation |
|---|---:|---:|---:|---|
| 2026-06-18 15:50:29 | 47.62% | 0/13 | 0/13 | early state, routing and retrieval both weak |
| 2026-06-18 15:56:59 | 100.00% | 0/13 | 0/13 | router fixed first, retrieval still failing |
| 2026-06-18 16:06:34 | 100.00% | 5/13 | 5/13 | retrieval starts improving |
| 2026-06-18 16:19:07 | 100.00% | 13/13 | 13/13 | perfect on the smaller evaluation set |
| 2026-06-22 06:39:53 | 96.43% | 22/36 | 20/36 | larger set exposes generalization limits |

### Interpretation

- Improvement over time is clear.
- The later drop is mostly a scale/generalization issue, not a simple regression.
- Small-set perfection did not fully generalize to the larger set.

## Recommended talking points

1. `analysis_agent` is broadly stable, but `routing_target` is the real bottleneck.
2. The strongest safety signal is `fixed_answer` recall at 100.00%.
3. The biggest classification weakness is `DB_only` recall at 69.23%.
4. `answer_agent` shows that routing/path control is nearly solved, but retrieval precision remains the scaling problem.
5. The most presentation-friendly narrative is not “the model got worse”, but “small-set success did not fully generalize under larger evaluation coverage”.
