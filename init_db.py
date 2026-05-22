from app.database import SessionLocal, engine
from app import models
from app.security import hash_api_key

def init_db():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    try:
        # Check if agent already exists
        if db.query(models.Agent).filter_by(name="DevOps-Bot").first():
            print("Database already initialized.")
            return

        # Create Mock Agent — API key is hashed before storage
        raw_key = "sk-mock-key-123"
        agent = models.Agent(name="DevOps-Bot", api_key=hash_api_key(raw_key))
        db.add(agent)
        db.commit()
        db.refresh(agent)
        
        # Create Policy: Allowed to use github_commit
        policy_allow = models.Policy(agent_id=agent.id, tool_name="github_commit", is_allowed=True)
        
        # Create Policy: NOT allowed to use query_db (Explicit deny)
        policy_deny = models.Policy(agent_id=agent.id, tool_name="query_db", is_allowed=False)
        
        db.add(policy_allow)
        db.add(policy_deny)
        db.commit()
        
        print("Database initialized with mock Agent 'DevOps-Bot'")
        print(f"API Key (send this in X-Agent-Key header): {raw_key}")
        print("  NOTE: Key is stored as a SHA-256 hash, NOT in plain text.")
        print("Allowed Tool: github_commit")
        print("Denied Tool: query_db")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
