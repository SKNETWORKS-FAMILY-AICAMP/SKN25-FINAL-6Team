# Analysis Agent Confusion Matrix

## category
| gold ↓ / pred → | account | bug | gacha | general | payment | policy | refund |
|---|---|---|---|---|---|---|---|
| account | 20 | 0 | 0 | 0 | 0 | 2 | 0 |
| bug | 0 | 38 | 0 | 1 | 0 | 0 | 0 |
| gacha | 0 | 0 | 9 | 0 | 0 | 0 | 1 |
| general | 0 | 3 | 0 | 29 | 0 | 0 | 0 |
| payment | 0 | 3 | 0 | 1 | 9 | 0 | 4 |
| policy | 0 | 0 | 0 | 1 | 0 | 10 | 0 |
| refund | 0 | 1 | 0 | 0 | 0 | 0 | 11 |

## risk_level
| gold ↓ / pred → | HIGH | LOW | MID |
|---|---|---|---|
| HIGH | 23 | 3 | 3 |
| LOW | 3 | 81 | 0 |
| MID | 0 | 2 | 28 |

## sentiment
| gold ↓ / pred → | negative | neutral | positive |
|---|---|---|---|
| negative | 43 | 11 | 1 |
| neutral | 9 | 62 | 11 |
| positive | 0 | 0 | 6 |

## routing_target
| gold ↓ / pred → | DB&DOC | DB_only | doc_only | fixed_answer |
|---|---|---|---|---|
| DB&DOC | 21 | 1 | 5 | 0 |
| DB_only | 22 | 14 | 3 | 0 |
| doc_only | 24 | 2 | 29 | 2 |
| fixed_answer | 2 | 0 | 1 | 17 |
