"""Provision/rotate credentials into a new private file, never standard output."""
import argparse
import os
from pathlib import Path
import re
from sqlalchemy import select
from app.config import Settings
from app.core import hash_api_key, new_api_key
from app.database import Store
from app.models import Agent, Policy


def provision(store, name, key_file, rotate=False):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("Agent name must be 1-64 ASCII letters, digits, underscores, or hyphens")
    store.initialize()
    path = Path(key_file)
    created = False
    try:
        with store.sessions.begin() as session:
            agent = session.scalar(select(Agent).where(Agent.name == name))
            if agent is not None and not rotate:
                raise ValueError("Agent already exists; use --rotate with a new key-file path")
            if agent is None and rotate:
                raise ValueError("Cannot rotate an agent that does not exist")
            raw_key = new_api_key()
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(descriptor, "w", encoding="ascii") as file:
                file.write(raw_key + "\n")
            if agent is None:
                agent = Agent(name=name, api_key=hash_api_key(raw_key), is_active=True)
                session.add(agent)
                session.flush()
                session.add_all([
                    Policy(agent_id=agent.id, tool_name="github_commit", is_allowed=True),
                    Policy(agent_id=agent.id, tool_name="query_db", is_allowed=False),
                ])
            else:
                agent.api_key = hash_api_key(raw_key)
                agent.is_active = True
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-name", default="DevOps-Bot")
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--rotate", action="store_true")
    args = parser.parse_args(argv)
    store = None
    try:
        store = Store(Settings.from_environment().database_url)
        provision(store, args.agent_name, args.key_file, args.rotate)
    except ValueError as exc:
        print(str(exc))
        return 2
    except Exception:
        print("Provisioning failed; check database access and use a new writable key-file path.")
        return 1
    finally:
        if store is not None:
            store.close()
    print("Credential written to the requested file. Store it privately; do not commit or paste it.")
    print("New agents may use only mock github_commit. Rotation preserves existing policies.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
