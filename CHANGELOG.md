# Changelog

## 0.1.0

First offline release.

- Lint `blender.geometry_nodes.capture` v1 and, read-only, `nodebridge.graph` v1.
- Twenty-one rules with stable ids, severity, and confidence (`PROVEN`, `HIGH_CONFIDENCE`, `HEURISTIC`).
- Coverage counts for `PASS`, `FAIL`, `NOT_APPLICABLE`, and `NOT_EVALUATED`.
- Text, canonical JSON, SARIF 2.1.0, and a self-contained HTML summary.
- CLI: `lint`, `rules`, `list-rules`, `explain`, `validate-config`, `doctor`, `demo`.
- Exit codes 0–4 as documented in the README.
- Project config for budgets, nesting depth, limits, rule selection, and justified suppressions.
- Verified Blender 4.5.14 LTS fixture (`fixtures/blender/valid_scatter.json`, hash `62c1db4208e8`) plus broken and inefficient variants.
- Catalog checks apply only when the host version is exactly 4.5.14. Other versions stay structurally lintable and mark catalog rules `NOT_EVALUATED`.
- `gn-as-code`, `hda-as-code`, `pcg-as-code`, `shader-as-code`, and `nodebridge.semantic` are explicit unsupported formats.
