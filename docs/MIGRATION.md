# Moving from the original demo to the hardened prototype

This update changes credential and tool-argument contracts. Back up an existing
SQLite database privately before upgrading. Stop the old process first.

## Credentials

The old publicly documented mock key and other legacy key formats are rejected.
There is no fallback that accepts plaintext or old-format credentials.

For an existing DevOps-Bot row, rotate into a new file:

```bash
python init_db.py --agent-name DevOps-Bot --rotate --key-file .secrets/devops-bot-v2.key
```

For a new database, omit `--rotate`. Rotation immediately invalidates the old
digest, reactivates the selected agent, and preserves its tool policies. Update
the agent's private credential source before resuming it. Do not place the key in
source code, request examples, screenshots, or shell arguments.

An existing key file is never overwritten. An existing agent is never silently
reseeded. A failed database transaction attempts to remove only the newly created
key file. An abrupt process crash between file creation and database commit can
leave an unusable orphan file; verify provisioning before distributing it.

## Database

The agents and policies tables retain their existing columns. Startup creates the
new metadata-only `audit_events_v2` table; it does not rewrite old audit records.

**Existing `audit_logs` rows may contain raw arguments, results, or exception
details.** New privacy behavior does not retroactively redact them. Review their
retention, backups, and access controls privately. This update does not erase
historical evidence automatically.

Schema creation is suitable for this local prototype, not a general production
migration system. Use a reviewed migration process before adding real deployments.

## Request changes

- `github_commit` requires `repo` in owner/name form and `message`.
- `query_db` accepts only the fixed fixture query
  `SELECT * FROM demo_users`; it never evaluates SQL.
- Extra arguments and unknown request fields are rejected.
- Responses use `mock_success` to distinguish fixtures from real side effects.
- API docs and CORS are disabled by default; enable explicit settings if needed.
- Error responses no longer contain agent names, supplied tool strings, or
  connector exception text.

The Docker setup now uses a named data volume. It does not automatically import
the earlier host-mounted database. Keep the old database backed up until you
have deliberately provisioned or migrated the intended data.

## Verification before merging or deploying

Run unit and integration tests, dependency checks, the container build, and the
credential scan. Inspect the current [validation status](VALIDATION.md).
An unexecuted CI job does not validate code. Successful unit tests alone do not
establish HTTP, ORM, packaging, or deployment compatibility.
