from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_feature_access(db: AsyncSession, user_id: str, feature_key: str) -> bool:
    # 1) user overrides
    override = (
        await db.execute(
            text(
                """
                SELECT ufo.enabled
                FROM user_feature_overrides ufo
                JOIN features f ON f.id = ufo.feature_id
                WHERE ufo.user_id = :user_id AND f.feature_key = :feature_key
                LIMIT 1
                """
            ),
            {"user_id": user_id, "feature_key": feature_key},
        )
    ).scalar_one_or_none()
    if override is not None:
        return bool(override)

    # 2) plan features
    plan_access = (
        await db.execute(
            text(
                """
                SELECT pf.enabled
                FROM subscriptions s
                JOIN plans p ON p.id = s.plan_id
                JOIN plan_features pf ON pf.plan_id = p.id
                JOIN features f ON f.id = pf.feature_id
                WHERE s.user_id = :user_id
                  AND s.status = 'active'
                  AND f.feature_key = :feature_key
                ORDER BY s.start_date DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id, "feature_key": feature_key},
        )
    ).scalar_one_or_none()
    return bool(plan_access)


def require_feature_sync(entitlements: dict[str, Any], feature_key: str) -> None:
    if not entitlements.get(feature_key, False):
        raise HTTPException(status_code=403, detail=f"Feature '{feature_key}' not available for current subscription")
