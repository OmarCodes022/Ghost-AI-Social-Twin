from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Command:
    type: str  # pause | resume | status | override
    contact_phone: Optional[str] = None
    args: dict = field(default_factory=dict)


class NotificationChannel(ABC):
    """Abstract notification and control interface.

    Implementations: Telegram, Discord, Slack, SMS, etc.
    Swap by changing which subclass is instantiated in handler.py.
    """

    @abstractmethod
    def send_alert(self, text: str) -> None:
        """Send a plain text alert to Omar."""

    @abstractmethod
    def send_escalation(
        self,
        contact_name: str,
        contact_phone: str,
        message: str,
        reason: str,
    ) -> None:
        """Notify Omar of a message Ghost can't handle."""

    @abstractmethod
    def parse_command(self, webhook_event: dict) -> Optional[Command]:
        """Parse an incoming platform webhook into a Command, or None if not a command."""

    @abstractmethod
    def ack(self, webhook_event: dict) -> dict:
        """Return the HTTP response the platform expects after receiving a webhook."""
