"""REFACTORING.md step 2 — HTTP-level dispatch tests for /import/upload and /import/api.

Guards that CSV header auto-detection and the JSON handler map still route to
the correct per-type importer after the split into app/api/importers/*.
"""

from sqlalchemy import select

from app.models.life import BodyMeasurement, InventoryItem
from app.models.task_location import TaskLocation
from app.models.user import User

CSV_MEASUREMENTS = "date,time_of_day,weight,chest\n2024-01-15,morning,98.5,112\n"
CSV_INVENTORY = (
    "category,name,quantity,is_shopping_list,status,priority\nclothing,Black stockings 40 den,3,true,need,2\n"
)
CSV_UNKNOWN = "foo,bar\n1,2\n"


class TestUploadCsv:
    """POST /import/upload — CSV auto-detect dispatches to the right importer."""

    async def test_measurements_auto_detected(self, auth_client, db_session, test_user: User) -> None:
        response = await auth_client.post(
            "/import/upload",
            files={"file": ("meas.csv", CSV_MEASUREMENTS, "text/csv")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["imported"] == 1
        assert body["skipped"] == 0

        rows = (
            (await db_session.execute(select(BodyMeasurement).where(BodyMeasurement.user_id == test_user.id)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].measured_date.isoformat() == "2024-01-15"
        assert rows[0].weight == 98.5

    async def test_inventory_auto_detected(self, auth_client, db_session, test_user: User) -> None:
        response = await auth_client.post(
            "/import/upload",
            files={"file": ("inv.csv", CSV_INVENTORY, "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1

        rows = (
            (await db_session.execute(select(InventoryItem).where(InventoryItem.user_id == test_user.id)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].name == "Black stockings 40 den"

    async def test_unknown_headers_400(self, auth_client) -> None:
        response = await auth_client.post(
            "/import/upload",
            files={"file": ("x.csv", CSV_UNKNOWN, "text/csv")},
        )
        assert response.status_code == 400


class TestApiPush:
    """POST /import/api — JSON handler map dispatches per import_type."""

    async def test_json_measurements(self, auth_client, db_session, test_user: User) -> None:
        payload = {
            "import_type": "measurements",
            "mode": "upsert",
            "data": [{"measured_date": "2024-01-15", "time_of_day": "evening", "weight": 99.0}],
        }
        response = await auth_client.post("/import/api", json=payload)
        assert response.status_code == 200
        assert response.json()["imported"] == 1

        rows = (
            (await db_session.execute(select(BodyMeasurement).where(BodyMeasurement.user_id == test_user.id)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].weight == 99.0

    async def test_json_locations(self, auth_client, db_session, test_user: User) -> None:
        payload = {
            "import_type": "locations",
            "data": [
                {
                    "slug": "my-office",
                    "title_ru": "Офис",
                    "location_type": "room",
                    "privacy_level": "private",
                }
            ],
        }
        response = await auth_client.post("/import/api", json=payload)
        assert response.status_code == 200
        assert response.json()["imported"] == 1

        rows = (
            (await db_session.execute(select(TaskLocation).where(TaskLocation.owner_id == test_user.id)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].slug == "my-office"

    async def test_unknown_type_400(self, auth_client) -> None:
        response = await auth_client.post("/import/api", json={"import_type": "nope", "data": []})
        assert response.status_code == 400
