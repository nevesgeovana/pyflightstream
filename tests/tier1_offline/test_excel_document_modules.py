# GEOVERSE_HEADER
# file_version: "2.0.0"
# file_role: macro-free-workbook-document-identity
# last_modified_at: "2026-09-27T21:40:49.642Z"
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementation-agent}
# dependencies: [pyflightstream.workspace.excel]
# authority: geoverse-goddess-control-plane
# status: active
# confidentiality: public
# change_summary: "Verify the approved macro-free package and worksheet identity."
# revision_source: git
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pyflightstream.workspace.excel import create_workbook


def test_workbook_package_is_macro_free_with_required_sheets(tmp_path):
    # GOAL033:excel:checks:optional_workbook
    path = create_workbook(tmp_path / "documents.xlsx", workspace=tmp_path)
    with ZipFile(path) as package:
        content_types = package.read("[Content_Types].xml")
        assert b"macroEnabled" not in content_types and b"vbaProject" not in content_types
        workbook = ET.fromstring(package.read("xl/workbook.xml"))
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        sheets = workbook.findall(namespace + "sheets/" + namespace + "sheet")
        assert [sheet.attrib["name"] for sheet in sheets] == [
            "Controls",
            "Runs",
            "Dictionary",
            "Preview",
            "_Baseline",
        ]
        assert sheets[-1].attrib["state"] == "veryHidden"
