"""Mock diagnostic fixture provider."""

from __future__ import annotations

from zigbeelens.mock.fixtures import (
    BUILDERS,
    ScenarioData,
    build_report_preview,
    device_detail_from_summary,
    get_scenario,
    list_scenarios,
)


class MockProvider:
    def __init__(self, scenario_id: str) -> None:
        self.scenario_id = scenario_id
        self._data: ScenarioData | None = None

    @property
    def data(self) -> ScenarioData:
        if self._data is None:
            self._data = get_scenario(self.scenario_id)
        return self._data

    @staticmethod
    def list_scenarios() -> list[dict[str, str]]:
        return list_scenarios()

    @staticmethod
    def is_valid_scenario(scenario_id: str) -> bool:
        return scenario_id in BUILDERS

    def dashboard(self):
        return self.data.dashboard

    def networks(self):
        return self.data.networks

    def network(self, network_id: str):
        for net in self.data.networks:
            if net.id == network_id:
                return net
        return None

    def devices(self, network_id: str | None = None):
        if network_id:
            return [d for d in self.data.devices if d.network_id == network_id]
        return list(self.data.devices)

    def device(self, network_id: str, ieee_address: str):
        for d in self.data.devices:
            if d.network_id == network_id and d.ieee_address == ieee_address:
                return device_detail_from_summary(d, self.data)
        return None

    def routers(self):
        from zigbeelens.mock.fixtures import conclusion
        from zigbeelens.schemas import IncidentScope, RouterRisk, Severity

        router_devices = [d for d in self.data.devices if d.device_type.value == "Router"]
        risks = self.data.router_risks or self.data.dashboard.router_risks
        risk_map = {(r.network_id, r.ieee_address): r for r in risks}
        items: list[RouterRisk] = []
        for d in router_devices:
            key = (d.network_id, d.ieee_address)
            if key in risk_map:
                items.append(risk_map[key])
            else:
                items.append(
                    RouterRisk(
                        network_id=d.network_id,
                        ieee_address=d.ieee_address,
                        friendly_name=d.friendly_name,
                        availability=d.availability,
                        linkquality=d.linkquality,
                        last_seen=d.last_seen,
                        possibly_dependent_devices=None,
                        correlated_affected_devices=0,
                        risk=conclusion(
                            "router_ok",
                            Severity.healthy,
                            IncidentScope.router_candidate,
                            d.health.confidence,
                            f"{d.friendly_name} shows no elevated router risk.",
                        ),
                    )
                )
        return items

    def incidents(self):
        return self.data.incidents

    def incident(self, incident_id: str):
        for inc in self.data.incidents:
            if inc.id == incident_id:
                return inc
        return None

    def timeline(self, network_id: str | None = None):
        events = self.data.timeline or self.data.dashboard.recent_timeline
        if network_id:
            events = [e for e in events if e.network_id == network_id]
        return sorted(events, key=lambda e: e.timestamp, reverse=True)

    def report_preview(self):
        return build_report_preview(self.data)
