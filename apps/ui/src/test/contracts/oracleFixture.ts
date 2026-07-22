import oracleFixture from "@/test/fixtures/oracleMockScenarios.json";

export type OracleFixture = typeof oracleFixture;
export type OracleScenarioId = keyof OracleFixture["scenarios"];
export type OracleScenario = OracleFixture["scenarios"][OracleScenarioId];

export const ORACLE_CONTRACT_VERSION = oracleFixture.oracle_contract_version;

export function oracleScenarioIds(): OracleScenarioId[] {
  return Object.keys(oracleFixture.scenarios).sort() as OracleScenarioId[];
}

export function oracleScenario(id: OracleScenarioId): OracleScenario {
  return oracleFixture.scenarios[id];
}

export function allOracleScenarios(): Array<[OracleScenarioId, OracleScenario]> {
  return oracleScenarioIds().map((id) => [id, oracleScenario(id)]);
}
