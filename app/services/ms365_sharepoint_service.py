"""
Microsoft 365 SharePoint Service

Upload files, create folders, and manage documents in SharePoint.
Uses application-level permissions.
"""

import httpx
import logging

from app.services.ms365_base import MS365BaseService
from app.config import settings

logger = logging.getLogger(__name__)


class MS365SharePointService(MS365BaseService):
    """Service for SharePoint document storage."""

    @classmethod
    def is_configured(cls) -> bool:
        return bool(
            super().is_configured()
            and settings.MS365_SHAREPOINT_SITE_ID
            and settings.MS365_SHAREPOINT_DRIVE_ID
        )

    @classmethod
    def _drive_path(cls) -> str:
        return f"/sites/{settings.MS365_SHAREPOINT_SITE_ID}/drives/{settings.MS365_SHAREPOINT_DRIVE_ID}"

    @classmethod
    async def create_folder(cls, folder_path: str) -> dict | None:
        """Create a folder in SharePoint. folder_path like 'Customers/Smith_abc123'."""
        if not cls.is_configured():
            return None

        try:
            parts = folder_path.strip("/").split("/")
            current_path = ""
            result = None
            for part in parts:
                parent = f"{cls._drive_path()}/root:/{current_path}" if current_path else f"{cls._drive_path()}/root"
                try:
                    result = await cls.graph_post(
                        f"{parent}/children",
                        {
                            "name": part,
                            "folder": {},
                            "@microsoft.graph.conflictBehavior": "fail",
                        },
                    )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 409:
                        # Folder already exists
                        result = await cls.graph_get(f"{cls._drive_path()}/root:/{current_path}/{part}")
                    else:
                        raise
                current_path = f"{current_path}/{part}" if current_path else part

            logger.info("SharePoint folder ready: %s", folder_path)
            return result

        except Exception as e:
            logger.error("Failed to create SharePoint folder: %s", e)
            return None

    @classmethod
    async def upload_file(
        cls,
        folder_path: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict | None:
        """Upload a file to SharePoint. Returns item metadata."""
        if not cls.is_configured():
            return None

        try:
            token = await cls.get_app_token()
            upload_url = (
                f"{cls.GRAPH_BASE}{cls._drive_path()}/root:/{folder_path}/{filename}:/content"
            )

            async with httpx.AsyncClient() as client:
                resp = await client.put(
                    upload_url,
                    content=content,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": content_type,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                result = resp.json()

            logger.info("Uploaded to SharePoint: %s/%s", folder_path, filename)
            return result

        except Exception as e:
            logger.error("SharePoint upload failed: %s", e)
            return None

    @classmethod
    async def get_file_link(cls, item_id: str) -> str | None:
        """Get a shareable link for a SharePoint item."""
        if not cls.is_configured():
            return None

        try:
            result = await cls.graph_post(
                f"{cls._drive_path()}/items/{item_id}/createLink",
                {"type": "view", "scope": "organization"},
            )
            return result.get("link", {}).get("webUrl")

        except Exception as e:
            logger.error("Failed to get SharePoint link: %s", e)
            return None

    @classmethod
    async def list_folder_contents(cls, folder_path: str) -> list[dict]:
        """List files in a SharePoint folder."""
        if not cls.is_configured():
            return []

        try:
            result = await cls.graph_get(
                f"{cls._drive_path()}/root:/{folder_path}:/children"
                f"?$select=id,name,size,lastModifiedDateTime,webUrl&$top=100",
            )
            return result.get("value", [])

        except Exception as e:
            logger.error("Failed to list SharePoint folder: %s", e)
            return []

    @classmethod
    def build_customer_folder(cls, customer_name: str, customer_id: str) -> str:
        safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in customer_name).strip()
        short_id = str(customer_id)[:8]
        return f"Customers/{safe_name}_{short_id}"
