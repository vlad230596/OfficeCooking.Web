from app.migration.transform import child_uuid, stable_uuid


def test_uuid_v5_derivation_is_stable_and_uses_source_position() -> None:
    assert stable_uuid("users:0") == stable_uuid("users:0")
    assert stable_uuid("users:0") != stable_uuid("users:1")
    assert child_uuid("Templates/example.json", "ingredients", 3) == child_uuid(
        "Templates/example.json", "ingredients", 3
    )
    assert child_uuid("Templates/example.json", "ingredients", 3) != child_uuid(
        "Templates/example.json", "ingredients", 4
    )
