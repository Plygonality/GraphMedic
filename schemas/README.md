# Schemas

`sarif-schema-2.1.0.json` is the OASIS SARIF Version 2.1.0 JSON Schema (errata 01), vendored so tests can validate reports without a network fetch.

- Schema id: `https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json`
- Draft: JSON Schema draft-04 (`additionalProperties: false` at the log root)
- GraphMedic does not relicense this file. The GraphMedic code is MIT; this schema stays under its OASIS terms.
- Lint writes SARIF that is intended to satisfy the schema. Extra diagnostic fields go in `properties` and `partialFingerprints`. The `$schema` property is a declaration. Offline lint does not download it.

Validate locally with `jsonschema.Draft4Validator` after `pip install -e ".[dev]"`. The CLI test suite already does this.
