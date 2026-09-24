"""Call only the local demo proxy, reading a credential from a private file."""
import argparse
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--tool", choices=("github_commit", "query_db"), default="github_commit")
    args = parser.parse_args(argv)
    try:
        with open(args.key_file, "rb") as file:
            key = file.read(128).decode("ascii").strip()
        if not re.fullmatch(r"ztp_[A-Za-z0-9_-]{43}", key):
            raise ValueError("invalid key file")
    except (OSError, ValueError, UnicodeError):
        print("Cannot read a valid generated credential from the requested file.")
        return 2
    arguments = ({"repo": "demo/example", "message": "Example mock commit"}
                 if args.tool == "github_commit" else {"query": "SELECT * FROM demo_users"})
    body = json.dumps({"tool_name": args.tool, "args": arguments}).encode("utf-8")
    request = Request("http://127.0.0.1:8000/execute", data=body,
                      headers={"X-Agent-Key": key, "Content-Type": "application/json"}, method="POST")
    # Do not send a local credential through an environment proxy or a redirect.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            print(response.read(65536).decode("utf-8"))
        return 0
    except HTTPError as error:
        print(f"HTTP {error.code}: {error.read(65536).decode('utf-8', errors='replace')}")
        return 1
    except (URLError, OSError):
        print("Could not contact the local proxy on 127.0.0.1:8000.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
