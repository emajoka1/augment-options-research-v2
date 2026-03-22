from enum import Enum


class AgentMode(str, Enum):
    RESEARCH_AGENT = "RESEARCH_AGENT"
    PRODUCTION_AGENT = "PRODUCTION_AGENT"


class PermissionError(RuntimeError):
    pass


class Guardrails:
    """Simple mode-level write guardrails.

    RESEARCH_AGENT: can write in kb/, experiments/, proposals/
    PRODUCTION_AGENT: read-only from approved rules/playbooks; no self-modification.
    """

    def __init__(self, mode: AgentMode):
        self.mode = mode

    def assert_write_allowed(self, relative_path: str) -> None:
        if self.mode == AgentMode.RESEARCH_AGENT:
            allowed_prefixes = ("kb/", "experiments/", "proposals/")
            if relative_path.startswith(allowed_prefixes):
                return
            raise PermissionError(f"Research mode cannot write outside {allowed_prefixes}: {relative_path}")

        # Production restrictions
        raise PermissionError(
            "PRODUCTION_AGENT is read-only for governance artifacts and cannot self-modify."
        )

    def assert_read_allowed(self, relative_path: str) -> None:
        if self.mode == AgentMode.RESEARCH_AGENT:
            return
        # PRODUCTION_AGENT may only read approved rules/playbooks and logs
        allowed_prefixes = (
            "kb/decisions/approved/",
            "kb/rules/",
            "kb/playbooks/",
            "kb/trade_logs/",
        )
        if not relative_path.startswith(allowed_prefixes):
            raise PermissionError(f"PRODUCTION_AGENT read denied: {relative_path}")
