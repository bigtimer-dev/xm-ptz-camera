"""Live test against a real camera: XM_HOST=<camera ip> XM_PASSWORD=<password> pytest -s"""
import os

import pytest
import pytest_socket
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xm_ptz.const import DOMAIN

HOST = os.environ.get("XM_HOST")
pytestmark = pytest.mark.skipif(not HOST, reason="set XM_HOST to run against a real camera")


@pytest.fixture
def allow_camera():
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts(["127.0.0.1", HOST])


async def test_live(hass, hass_client_no_auth, allow_camera):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": HOST, "port": 34567, "username": os.environ.get("XM_USER", "admin"),
              "password": os.environ.get("XM_PASSWORD", "")},
        options={"sync_time": os.environ.get("XM_SYNC_TIME") == "1"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state.value == "loaded"
    serial = entry.runtime_data.coordinator.serial
    registry = er.async_get(hass)

    def eid(domain: str, key: str) -> str:
        return registry.async_get_entity_id(domain, DOMAIN, f"{serial}_{key}")

    states = sorted(hass.states.async_all(), key=lambda s: s.entity_id)
    for s in states:
        print(f"{s.entity_id:55} {s.state}")
    assert not [s.entity_id for s in states if s.state == "unavailable" and not s.entity_id.endswith("sub_stream")]

    # Read-modify-write round trip with the current value (no change on the camera).
    sens = hass.states.get(eid("number", "motion_sensitivity"))
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": sens.entity_id, "value": float(sens.state)}, blocking=True)
    assert hass.states.get(sens.entity_id).state == sens.state

    # Raw config read through the camera entity service.
    cam = eid("camera", "camera_0")
    resp = await hass.services.async_call(DOMAIN, "get_config", {"entity_id": cam, "name": "Detect.DetectTrack"},
                                          blocking=True, return_response=True)
    assert "Enable" in resp[cam]["value"]

    # Snapshot through the camera entity.
    client = await hass_client_no_auth()
    token = hass.states.get(cam).attributes["access_token"]
    r = await client.get(f"/api/camera_proxy/{cam}?token={token}")
    body = await r.read()
    assert r.status == 200 and body[:2] == b"\xff\xd8"
    print("snapshot bytes:", len(body), "clock offset:", hass.states.get(eid("sensor", "clock_offset")).state)

    assert await hass.config_entries.async_unload(entry.entry_id)
