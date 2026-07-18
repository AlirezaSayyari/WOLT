import pytest

from app.application.observability_service import ObservabilityService


@pytest.mark.parametrize("value", ["=CMD()", "+SUM(A1)", "-1+2", "@IMPORTDATA()"])
def test_csv_export_neutralizes_spreadsheet_formulas(value: str) -> None:
    assert ObservabilityService._csv_cell(value) == f"'{value}"


def test_csv_export_leaves_normal_operational_values_unchanged() -> None:
    assert ObservabilityService._csv_cell("Integration VLAN") == "Integration VLAN"
