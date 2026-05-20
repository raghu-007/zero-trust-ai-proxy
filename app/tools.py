import json

def mock_github_commit(args: dict) -> dict:
    """Mock implementation of a GitHub commit."""
    repo = args.get("repo", "unknown/repo")
    message = args.get("message", "Update files")
    return {
        "status": "success",
        "message": f"Successfully committed to {repo} with message: '{message}'",
        "commit_hash": "a1b2c3d4e5f6"
    }

def mock_query_db(args: dict) -> dict:
    """Mock implementation of a database query."""
    query = args.get("query", "")
    # Simulate returning some sensitive-looking data for PII testing
    return {
        "status": "success",
        "results": [
            {"id": 1, "name": "John Doe", "email": "john.doe@enterprise.com", "ssn": "123-45-6789"},
            {"id": 2, "name": "Jane Smith", "email": "jane.smith@enterprise.com", "ssn": "987-65-4321"}
        ]
    }

# Registry of available tools
TOOL_REGISTRY = {
    "github_commit": mock_github_commit,
    "query_db": mock_query_db
}

def execute_tool(tool_name: str, args: dict) -> str:
    """Executes a tool if it exists in the registry."""
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' not found.")
    
    func = TOOL_REGISTRY[tool_name]
    result_dict = func(args)
    return json.dumps(result_dict)
