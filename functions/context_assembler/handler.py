import logging
import os

from db import (
    fetch_contact,
    fetch_contact_state,
    fetch_conversation_history,
    fetch_few_shots,
    fetch_ghost_state,
    fetch_life_events,
    fetch_per_person_rules,
)
from models import Tier1Context

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def lambda_handler(event, context):
    """
    Invoked synchronously by Ghost Lambda before every Bedrock call.

    Input:  { "contact_phone": str, "perception": dict }
    Output: Tier1Context as JSON-serialisable dict
    """
    contact_phone = event["contact_phone"]
    perception = event.get("perception", {})

    log.info("assembling tier 1 context for %s", contact_phone)

    contact = fetch_contact(contact_phone)

    language = (
        perception.get("classification", {}).get("language")
        or contact.language_primary
    )

    ctx = Tier1Context(
        ghost_state=fetch_ghost_state(),
        contact=contact,
        contact_state=fetch_contact_state(contact_phone),
        per_person_rules=fetch_per_person_rules(contact_phone),
        conversation_history=fetch_conversation_history(contact_phone),
        life_events=fetch_life_events(contact_phone),
        few_shots=fetch_few_shots(language, contact.relationship_tier),
        perception=perception,
    )

    log.info(
        "context assembled: %d messages, %d few_shots",
        len(ctx.conversation_history),
        len(ctx.few_shots),
    )

    return ctx.model_dump()
