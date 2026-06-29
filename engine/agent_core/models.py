"""Stable domain enums shared by the runtime, API, and tests."""

from enum import Enum, IntEnum


class CapabilityLevel(IntEnum):
    READ_ONLY = 0
    REVERSIBLE_WRITE = 1
    CONTROLLED_RESOURCE = 2
    EXTERNAL_EFFECT = 3
    SYSTEM_FORBIDDEN = 4


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    RETRYING = "retrying"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MemoryKind(str, Enum):
    USER = "user"
    ACCOUNT = "account"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"

