"""HTTP-layer tests for the FastAPI surface over the rules engine (SETUP-02).

These verify wiring, response schemas, and error mapping — not the rules math,
which is already covered by the engine test suites. Rolls are random here, so we
assert on invariants (ranges, structure) rather than exact totals.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_roll_valid(client: TestClient) -> None:
    resp = client.post("/dice/roll", json={"notation": "2d6+3"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["dice"]) == 2
    assert all(1 <= d <= 6 for d in body["dice"])
    assert body["modifier"] == 3
    assert 5 <= body["total"] <= 15
    assert body["notation"] == "2d6+3"
    assert body["dropped"] == []


def test_roll_invalid_notation_is_400(client: TestClient) -> None:
    resp = client.post("/dice/roll", json={"notation": "nonsense"})
    assert resp.status_code == 400
    assert "invalid dice notation" in resp.json()["detail"]


def test_roll_missing_field_is_422(client: TestClient) -> None:
    resp = client.post("/dice/roll", json={})
    assert resp.status_code == 422


def test_d20_straight(client: TestClient) -> None:
    resp = client.post("/dice/d20", json={"modifier": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["dice"]) == 1
    assert 1 <= body["dice"][0] <= 20
    assert body["total"] == body["dice"][0] + 5
    assert body["dropped"] == []


def test_d20_advantage_drops_a_die(client: TestClient) -> None:
    resp = client.post("/dice/d20", json={"advantage": True})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["dropped"]) == 1
    assert body["dice"][0] >= body["dropped"][0]


def test_ability_check_with_dc(client: TestClient) -> None:
    resp = client.post("/checks/ability", json={"bonus": 3, "dc": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["is_success"], bool)
    assert body["dc"] == 10
    assert body["total"] == body["roll"]["total"]


def test_ability_check_without_dc_has_null_success(client: TestClient) -> None:
    resp = client.post("/checks/ability", json={"bonus": 0})
    assert resp.status_code == 200
    assert resp.json()["is_success"] is None


def test_skill_check_expertise(client: TestClient) -> None:
    resp = client.post(
        "/checks/skill",
        json={"ability_score": 16, "expertise": True, "level": 5, "dc": 12},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["is_success"], bool)


def test_skill_check_bad_ability_score_is_400(client: TestClient) -> None:
    resp = client.post("/checks/skill", json={"ability_score": 0})
    assert resp.status_code == 400


def test_saving_throw(client: TestClient) -> None:
    resp = client.post(
        "/checks/save",
        json={"ability_score": 14, "proficient": True, "level": 3, "dc": 13},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["is_success"], bool)


def test_attack_roll(client: TestClient) -> None:
    resp = client.post("/combat/attack", json={"bonus": 5, "ac": 15})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ac"] == 15
    assert isinstance(body["is_hit"], bool)
    assert isinstance(body["is_critical"], bool)
    assert isinstance(body["is_fumble"], bool)
    assert len(body["roll"]["dice"]) == 1


def test_damage_roll(client: TestClient) -> None:
    resp = client.post("/combat/damage", json={"notation": "1d8+2"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["dice"]) == 1
    assert 3 <= body["total"] <= 10


def test_damage_critical_doubles_dice(client: TestClient) -> None:
    resp = client.post("/combat/damage", json={"notation": "2d6", "critical": True})
    assert resp.status_code == 200
    assert len(resp.json()["dice"]) == 4


def test_damage_invalid_notation_is_400(client: TestClient) -> None:
    resp = client.post("/combat/damage", json={"notation": "bogus"})
    assert resp.status_code == 400
