"""DingTalk directory sync (PRD §9.1).

Periodically pulls the org's user list and mirrors it into the
``users`` table. Runs as a background task scheduled in
``core.main.lifespan``; the function here does the actual sync
work so it can be called manually from the admin API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.im_adapters.dingtalk.adapter import DingTalkAdapter

logger = logging.getLogger(__name__)


async def fetch_dingtalk_directory(adapter: DingTalkAdapter) -> List[Dict[str, Any]]:
    """Return the list of users from DingTalk. Empty if credentials missing."""

    if not adapter.app_key:
        return []
    # TODO: real implementation uses the DingTalk OpenAPI
    # /topapi/v2/user/list endpoint with pagination + auth.
    # See PRD v5.1 §8 for the request shape.
    return []


async def sync_directory(adapter: DingTalkAdapter) -> Dict[str, int]:
    """Sync the DingTalk directory into the platform's users table.

    Returns a small summary {added, updated, removed, errors}.
    """

    users = await fetch_dingtalk_directory(adapter)
    if not users:
        return {"added": 0, "updated": 0, "removed": 0, "errors": 0}
    # TODO: reconcile with core.database.models.User rows.
    return {"added": 0, "updated": 0, "removed": 0, "errors": 0}
