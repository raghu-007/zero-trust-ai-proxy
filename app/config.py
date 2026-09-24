"""Explicit local defaults. Environment variables are read when the app is created."""

from dataclasses import dataclass
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./zero_trust.db"
    cors_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1")
    rate_limit: int = 60
    rate_window: int = 60
    rate_clients: int = 1024
    body_timeout: int = 5
    enable_docs: bool = False

    def __post_init__(self):
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only SQLite is supported by this prototype")
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path or parsed.query
                    or parsed.fragment or "*" in origin):
                raise ValueError("CORS origins must be explicit http(s) origins without paths")
            if origin != f"{parsed.scheme}://{parsed.netloc}" or any(c.isspace() for c in origin):
                raise ValueError("CORS origins cannot contain whitespace or normalized prefixes")
            try:
                parsed.port
            except ValueError:
                raise ValueError("Invalid CORS origin port") from None
        if not self.allowed_hosts or any("*" in host or "/" in host or not host
                                         or any(c.isspace() for c in host) for host in self.allowed_hosts):
            raise ValueError("Allowed hosts must be explicit hostnames or IP literals")
        for value, maximum in ((self.rate_limit, 1000), (self.rate_window, 3600),
                               (self.rate_clients, 10000), (self.body_timeout, 60)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("Configuration value outside supported bounds")

    @classmethod
    def from_environment(cls):
        def csv(name, default):
            return tuple(part.strip() for part in os.getenv(name, default).split(",") if part.strip())
        docs = os.getenv("ZT_ENABLE_DOCS", "false").lower()
        if docs not in {"true", "false"}:
            raise ValueError("ZT_ENABLE_DOCS must be true or false")
        return cls(
            database_url=os.getenv("ZT_DATABASE_URL", cls.database_url),
            cors_origins=csv("ZT_CORS_ORIGINS", ""),
            allowed_hosts=csv("ZT_ALLOWED_HOSTS", "localhost,127.0.0.1"),
            rate_limit=int(os.getenv("ZT_RATE_LIMIT", "60")),
            rate_window=int(os.getenv("ZT_RATE_WINDOW", "60")),
            rate_clients=int(os.getenv("ZT_RATE_CLIENTS", "1024")),
            body_timeout=int(os.getenv("ZT_BODY_TIMEOUT", "5")),
            enable_docs=docs == "true",
        )
