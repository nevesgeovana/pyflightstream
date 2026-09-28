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
