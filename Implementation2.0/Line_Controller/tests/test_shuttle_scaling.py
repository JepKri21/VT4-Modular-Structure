"""Unit tests for live shuttle add/remove (cargo-safe retirement).

No pytest dependency — run directly:

    python tests/test_shuttle_scaling.py

Covers the controller-side pieces of the shuttle-scaling feature:
  - OccupancyManager.actor_busy / is_available per shuttle
  - ResourceManager actor-drain set helpers
  - aas_writer.remove_actor_from_skills filtering (cargo-safe AAS delete)
  - ConfigReloader.publish_capacity excluding draining actors
  - Scheduler._pick_shuttle skipping draining actors
"""

import json
import os
import sys

# The Line Controller modules expect the workspace root on sys.path; importing
# a light module (occupancy_manager) inserts it, mirroring how main.py runs.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import occupancy_manager  # noqa: E402  (also sets up the parent path)
from occupancy_manager import OccupancyManager  # noqa: E402
from resource_manager import ResourceManager  # noqa: E402
import aas_writer  # noqa: E402
import config_reload  # noqa: E402
from config_reload import ConfigReloader  # noqa: E402
import scheduler as scheduler_mod  # noqa: E402
from scheduler import Scheduler  # noqa: E402


def test_occupancy_actor_busy():
    om = OccupancyManager(controller=None)
    assert om.is_available("Transport_1", "Shuttle1")
    assert not om.actor_busy("Transport_1", "Shuttle1")

    # Reserved for an order -> busy.
    om.commit("order-1", [("Transport_1", "Shuttle1")])
    assert om.actor_busy("Transport_1", "Shuttle1")
    assert not om.is_available("Transport_1", "Shuttle1")

    # A different shuttle is still free.
    assert om.is_available("Transport_1", "Shuttle2")

    # Carrying cargo -> busy even if released later.
    om.set_cargo("Transport_1", "Shuttle2", "PCB-1")
    assert om.actor_busy("Transport_1", "Shuttle2")


def test_resource_manager_actor_drain_set():
    rm = ResourceManager("1883", "AAUSmartLab/ProductionLine1", "localhost", "8081", "")
    assert not rm.is_actor_draining("Transport_1", "Shuttle3")
    rm.mark_actor_draining("Transport_1", "Shuttle3")
    assert rm.is_actor_draining("Transport_1", "Shuttle3")
    # Other actors are unaffected.
    assert not rm.is_actor_draining("Transport_1", "Shuttle1")
    rm.discard_actor_drain("Transport_1", "Shuttle3")
    assert not rm.is_actor_draining("Transport_1", "Shuttle3")


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class _FakeRequests:
    """Stand-in for the `requests` module used inside aas_writer."""

    RequestException = Exception

    def __init__(self, skills_payload):
        self._skills = skills_payload
        self.put_body = None

    def get(self, url):
        return _FakeResp(200, self._skills)

    def put(self, url, headers=None, data=None):
        self.put_body = data
        return _FakeResp(204, None)


def _skills_with(actors):
    return {
        "submodelElements": [
            {
                "idShort": "Transport",
                "value": [
                    {"idShort": "SkillTriggers", "value": [{"value": "START"}]},
                    {
                        "idShort": "Actors",
                        "value": [{"value": a} for a in actors],
                    },
                ],
            }
        ]
    }


def test_remove_actor_from_skills_filters_and_puts():
    fake = _FakeRequests(_skills_with(["Shuttle1", "Shuttle2", "Shuttle3"]))
    orig = aas_writer.requests
    aas_writer.requests = fake
    try:
        ok = aas_writer.remove_actor_from_skills("http://x", "iri/Transport", "Shuttle3")
        assert ok is True
        assert fake.put_body is not None, "a PUT should have been issued"
        written = json.loads(fake.put_body.decode("utf-8"))
        actors_el = written["submodelElements"][0]["value"][1]
        values = [i["value"] for i in actors_el["value"]]
        assert values == ["Shuttle1", "Shuttle2"], values
    finally:
        aas_writer.requests = orig


def test_remove_actor_already_absent_no_put():
    fake = _FakeRequests(_skills_with(["Shuttle1", "Shuttle2"]))
    orig = aas_writer.requests
    aas_writer.requests = fake
    try:
        ok = aas_writer.remove_actor_from_skills("http://x", "iri/Transport", "Shuttle9")
        assert ok is True            # idempotent success
        assert fake.put_body is None  # nothing rewritten
    finally:
        aas_writer.requests = orig


class _FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload))


class _FakeController:
    def __init__(self):
        self.base_topic = "AAUSmartLab/ProductionLine1"
        self.client = _FakeClient()


class _FakeRM:
    def __init__(self, offering, draining):
        self._offering = offering
        self._draining = set(draining)

    def find_skill_offering(self, _name):
        return self._offering

    def is_actor_draining(self, topic, actor):
        return (topic, actor) in self._draining

    def has_handoff(self, _iri):
        return False


def test_publish_capacity_excludes_draining_actors():
    offering = [("iri-1", "Transport_1", ["Shuttle1", "Shuttle2", "Shuttle3"])]
    rm = _FakeRM(offering, draining={("Transport_1", "Shuttle3")})
    controller = _FakeController()

    reloader = object.__new__(ConfigReloader)  # bypass heavy __init__
    reloader._rm = rm
    reloader._controller = controller

    reloader.publish_capacity()

    assert controller.client.published, "capacity should be published"
    _topic, payload = controller.client.published[-1]
    msg = json.loads(payload)
    assert msg["max_concurrent"] == 2, msg


def test_pick_shuttle_skips_draining_actor():
    offering = [("iri-1", "Transport_1", ["Shuttle1", "Shuttle2"])]
    rm = _FakeRM(offering, draining={("Transport_1", "Shuttle1")})

    om = OccupancyManager(controller=None)  # everything available

    sched = object.__new__(Scheduler)
    sched.rm = rm
    sched.occupancy = om
    sched._shuttle_pick_cursor = 0
    # Bypass the capability/material support check (it would hit the AAS).
    sched._transport_supports = lambda *a, **k: True

    # Repeated picks must never return the draining Shuttle1.
    for _ in range(6):
        endpoint, _iri = Scheduler._pick_shuttle(sched, component_ref="PCB", material=None)
        assert endpoint.actor_name == "Shuttle2", endpoint.actor_name


class _VictimRM:
    """Minimal RM for _pick_retire_victim: a fixed actor list + drain set."""

    def __init__(self, actors, draining=()):
        self._actors = list(actors)
        self._draining = set(draining)

    def actors_for_skill(self, _iri, _skill):
        return list(self._actors)

    def is_actor_draining(self, topic, actor):
        return (topic, actor) in self._draining


def _victim_reloader(rm, occupancy):
    reloader = object.__new__(ConfigReloader)  # bypass heavy __init__
    reloader._rm = rm
    reloader._occupancy = occupancy
    return reloader


def test_pick_victim_keeps_requested_when_free():
    rm = _VictimRM(["Shuttle1", "Shuttle2", "Shuttle3"])
    om = OccupancyManager(controller=None)  # all free
    reloader = _victim_reloader(rm, om)
    victim = reloader._pick_retire_victim("iri", "Transport_1", "Shuttle3")
    assert victim == "Shuttle3", victim


def test_pick_victim_prefers_idle_when_requested_busy():
    rm = _VictimRM(["Shuttle1", "Shuttle2", "Shuttle3"])
    om = OccupancyManager(controller=None)
    # Requested Shuttle3 is carrying cargo (busy); Shuttle1/2 are idle.
    om.set_cargo("Transport_1", "Shuttle3", "PCB-1")
    reloader = _victim_reloader(rm, om)
    victim = reloader._pick_retire_victim("iri", "Transport_1", "Shuttle3")
    # Highest-numbered idle shuttle wins.
    assert victim == "Shuttle2", victim


def test_pick_victim_falls_back_to_requested_when_all_busy():
    rm = _VictimRM(["Shuttle1", "Shuttle2"])
    om = OccupancyManager(controller=None)
    om.commit("order-1", [("Transport_1", "Shuttle1"), ("Transport_1", "Shuttle2")])
    reloader = _victim_reloader(rm, om)
    victim = reloader._pick_retire_victim("iri", "Transport_1", "Shuttle2")
    assert victim == "Shuttle2", victim


def test_pick_victim_skips_already_draining_idle():
    rm = _VictimRM(["Shuttle1", "Shuttle2"], draining={("Transport_1", "Shuttle2")})
    om = OccupancyManager(controller=None)  # both idle, but Shuttle2 draining
    om.set_cargo("Transport_1", "Shuttle1", "PCB-1")  # requested busy
    reloader = _victim_reloader(rm, om)
    # Shuttle2 is idle but already draining → only Shuttle1 (busy) remains, so
    # fall back to the requested actor.
    victim = reloader._pick_retire_victim("iri", "Transport_1", "Shuttle1")
    assert victim == "Shuttle1", victim


def _run():
    tests = [
        test_occupancy_actor_busy,
        test_resource_manager_actor_drain_set,
        test_remove_actor_from_skills_filters_and_puts,
        test_remove_actor_already_absent_no_put,
        test_publish_capacity_excludes_draining_actors,
        test_pick_shuttle_skips_draining_actor,
        test_pick_victim_keeps_requested_when_free,
        test_pick_victim_prefers_idle_when_requested_busy,
        test_pick_victim_falls_back_to_requested_when_all_busy,
        test_pick_victim_skips_already_draining_idle,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001 - test harness reports and continues
            failed += 1
            print(f"FAIL  {t.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
