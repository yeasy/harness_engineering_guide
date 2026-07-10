"""Authentication values for MCP transports."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BearerTokenAuth:
    """Bearer token that keeps its secret value out of representations."""

    token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.token.strip():
            raise ValueError("Bearer token must not be empty")

    def as_headers(self) -> dict[str, str]:
        """Return the HTTP authorization header consumed by the SDK transport."""
        return {"Authorization": f"Bearer {self.token}"}
