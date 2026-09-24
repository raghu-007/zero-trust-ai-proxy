# Security policy

This repository is a local security-control prototype using mock connectors.
It is not a hosted service or a production certification.

## Report a problem

Use GitHub's private vulnerability reporting option in the Security tab if it is
available. Otherwise open a minimal issue requesting a private contact route,
without credentials, exploit details, or personal data. Ordinary non-sensitive
defects can be reported with a synthetic reproduction.

Do not post a live credential to demonstrate an exposure. Revoke or rotate an
exposed key and review its use; deleting a later source line does not invalidate
a key or remove earlier commits.

## Data handling

Generated key files belong in private storage. The local `.secrets/` directory
and database patterns are ignored, but ignore rules do not protect already-tracked
files or replace filesystem permissions.

New audit rows exclude raw arguments, results, credentials, and exception strings.
Old audit rows may still contain sensitive data; see [migration guidance](docs/MIGRATION.md).
The database is not encrypted by this application.

Treat response redaction as a limited mitigation. It can miss data and produce
false positives. Do not connect real internal systems or external AI providers
without reviewing the [trust boundaries and remaining work](docs/ARCHITECTURE.md).

## Verification

Run both test suites and all CI jobs. Credential and dependency scans can identify
specific problems; clean output does not prove the absence of vulnerabilities.
See [the validation record](docs/VALIDATION.md) for checks that have and have not run.
