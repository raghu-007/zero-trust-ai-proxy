# Contributing

Keep the mock/live boundary explicit. Do not describe a simulated action as a real
GitHub commit, database query, security incident, or provider integration.

For a security change, include a negative regression case and a valid control
case. Tests should verify boundaries and behavior, not just duplicate helper
implementation.

## Run checks

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests/unit -v
python -m unittest discover -s tests/integration -v
python -m pip check
docker build --tag zero-trust-proxy:review .
git diff --check
```

The integration suite requires installed dependencies and must not silently skip
when they are absent.

CI uses read-only permissions and commit-pinned Actions. Gitleaks is downloaded
at a fixed version and its SHA-256 digest is checked before execution. When
updating it, verify the new official release and replace both version and digest.
Dependabot does not update that embedded scanner download automatically.

Do not add broad secret-scan exclusions or advisory ignores to hide a failed
check. Review a finding and document any narrowly justified exception.

Before committing, inspect staged changes for real credentials, logs, database
files, screenshots, and private account information. Use synthetic data in tests.
State which checks actually ran in a PR; distinguish pending integration,
container, and security checks from successful unit checks.

Dependency pins currently cover direct packages only. A fully resolved,
hash-locked dependency set should be generated and verified in an environment
that can install the required packages; do not fabricate a lockfile.
