"""Mock connectors: no network calls, SQL execution, or real commits."""


def mock_github_commit(args):
    # Do not echo untrusted free text into the response.
    return {"status": "mock_success", "repo": args["repo"], "commit_hash": "demo-commit"}


def mock_query_db(args):
    return {"status": "mock_success", "results": [
        {"id": 1, "name": "Example User", "email": "user@example.test", "ssn": "123-45-6789"},
    ]}


TOOL_REGISTRY = {"github_commit": mock_github_commit, "query_db": mock_query_db}


def execute_tool(tool_name, args):
    return TOOL_REGISTRY[tool_name](args)
