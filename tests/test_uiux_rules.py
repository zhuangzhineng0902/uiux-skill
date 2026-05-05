from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "uiux_rules.py"


def load_module():
    spec = importlib.util.spec_from_file_location("uiux_rules", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


uiux = load_module()


def ast_dependencies_available() -> bool:
    command = [
        "node",
        "-e",
        "for (const p of ['@vue/compiler-sfc','@vue/compiler-dom','@babel/parser']) "
        "{ require.resolve(p, {paths: [process.cwd(), process.cwd() + '/example']}); }",
    ]
    try:
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def component_rule(rule_id: str, component: str, property_name: str, default_value: str = "", subject: str = ""):
    return uiux.Rule(
        {
            "rule_id": rule_id,
            "layer": "component",
            "component": component,
            "state": "default",
            "property_name": property_name,
            "default_value": default_value,
            "subject": subject,
            "condition_if": f"If component = {component}",
            "preferred_pattern": "test preferred",
            "anti_pattern": "test anti",
        }
    )


def foundation_rule(rule_id: str, property_name: str, default_value: str = "", subject: str = ""):
    return uiux.Rule(
        {
            "rule_id": rule_id,
            "layer": "foundation",
            "component": "",
            "state": "default",
            "property_name": property_name,
            "default_value": default_value,
            "subject": subject,
            "condition_if": f"If foundation property = {property_name}",
            "preferred_pattern": "test preferred",
            "anti_pattern": "test anti",
        }
    )


class CssParserTests(unittest.TestCase):
    def test_extracts_only_vue_style_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Sample.vue"
            path.write_text(
                """
<script setup>
const styleObject = { color: '#fff', margin: '13px' }
</script>
<template><x-card :style="{ color: '#333' }" /></template>
<style scoped>
.card { margin: 16px 24px; color: #333; }
</style>
""",
                encoding="utf-8",
            )

            declarations = uiux.extract_declarations(path)
            pairs = {(item.prop, item.value) for item in declarations}

        self.assertIn(("color", "#333"), pairs)
        self.assertIn(("margin-left", "24px"), pairs)
        self.assertNotIn(("margin", "13px"), pairs)
        self.assertTrue(all(item.origin in {"tinycss2", "fallback-css"} for item in declarations))

    def test_fallback_parser_handles_media_blocks_without_fake_at_rule_declaration(self):
        original = uiux.tinycss2
        uiux.tinycss2 = None
        try:
            declarations = uiux.parse_css_declarations(
                Path("x.css"),
                """
.card { margin: 16px 24px; color: #333; }
@media (max-width: 600px) { .card { padding: 8px; } }
""",
                1,
                "x.css",
            )
        finally:
            uiux.tinycss2 = original

        pairs = [(item.prop, item.value) for item in declarations]
        self.assertIn(("padding-left", "8px"), pairs)
        self.assertNotIn((".card { padding", "8px"), pairs)

    def test_css_value_matches_rem_and_px_equivalence(self):
        self.assertTrue(uiux.css_value_matches("1rem", ["16px"]))
        self.assertTrue(uiux.css_value_matches("2rem", ["32px"]))
        self.assertFalse(uiux.css_value_matches("0.4rem", ["4px", "8px"]))


class ComponentRecognitionTests(unittest.TestCase):
    def test_loads_alias_csv_and_infers_internal_component_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp)
            (rules_dir / "component-aliases.csv").write_text(
                "tag,component,library,notes\ncorp-money-input,input,internal,test\n",
                encoding="utf-8",
            )

            aliases = uiux.load_component_aliases(rules_dir)

        self.assertEqual(aliases["corp-money-input"], "input")
        self.assertEqual(uiux.resolve_component_name("x-data-grid", aliases), "table")
        self.assertEqual(uiux.resolve_component_name("pro-date-picker", aliases), "datepicker")

    def test_extracts_vue_component_usages_and_skips_child_tags(self):
        aliases = {
            **uiux.DEFAULT_COMPONENT_ALIASES,
            "corp-select": "select",
            "corp-form": "form",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Sample.vue"
            path.write_text(
                """
<template>
  <corp-form label-width="120px">
    <el-form-item label="名称">
      <corp-select v-model="value" clearable />
      <el-option label="A" value="a" />
    </el-form-item>
  </corp-form>
</template>
""",
                encoding="utf-8",
            )

            usages = uiux.extract_component_usages(path, aliases)

        tags = [usage.tag for usage in usages]
        self.assertEqual(tags, ["corp-form", "corp-select"])
        self.assertEqual(usages[0].component, "form")
        self.assertEqual(usages[1].attrs["clearable"], True)

    def test_template_scanner_reports_high_confidence_component_prop_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "Page.vue").write_text(
                """
<template>
  <x-form label-width="120px">
    <x-input />
    <x-input size="small" />
    <x-select />
    <x-date-picker clearable />
    <x-collapse />
  </x-form>
</template>
<style>
.page { margin: 0; }
</style>
""",
                encoding="utf-8",
            )

            rules = {
                "foundation": [],
                "global": [],
                "component": [
                    component_rule("CMP-009", "input", "size", "default", "input size"),
                    component_rule("CMP-011", "select", "component-config", "", "配置可清除"),
                    component_rule("CMP-015", "datepicker", "component-config", "", "配置可清除"),
                    component_rule("CMP-023", "form", "label-position", "top", "form label position"),
                    component_rule("CMP-046", "collapse", "icon", "left", "collapse icon"),
                ],
            }
            aliases = {
                "x-form": "form",
                "x-input": "input",
                "x-select": "select",
                "x-date-picker": "datepicker",
                "x-collapse": "collapse",
            }

            violations = uiux.scan_project(project, rules, aliases)

        by_rule = {item["rule_id"]: item for item in violations}
        self.assertIn("CMP-009", by_rule)
        self.assertEqual(by_rule["CMP-009"]["actual"], "small")
        self.assertIn("CMP-011", by_rule)
        self.assertNotIn("CMP-015", by_rule)
        self.assertIn("CMP-023", by_rule)
        self.assertIn("CMP-046", by_rule)
        self.assertFalse(
            any(item["rule_id"] == "CMP-009" and "未找到 size" in item["actual"] for item in violations),
            "missing size should not be reported because global defaults may supply default size",
        )

    @unittest.skipUnless(ast_dependencies_available(), "AST dependencies are not installed")
    def test_vue_ast_scanner_ignores_unknown_dynamic_bound_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "Page.vue").write_text(
                """
<script setup>
const computedSize = getSize()
</script>
<template>
  <x-input :size="computedSize" />
  <x-select :clearable="isClearable" />
</template>
""",
                encoding="utf-8",
            )

            rules = {
                "foundation": [],
                "global": [],
                "component": [
                    component_rule("CMP-009", "input", "size", "default", "input size"),
                    component_rule("CMP-011", "select", "component-config", "", "配置可清除"),
                ],
            }
            aliases = {"x-input": "input", "x-select": "select"}

            violations = uiux.scan_project(project, rules, aliases)

        self.assertFalse(violations, "unknown dynamic bindings should not produce high-confidence violations")

    @unittest.skipUnless(ast_dependencies_available(), "AST dependencies are not installed")
    def test_tsx_ast_scanner_recognizes_internal_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "Page.tsx").write_text(
                """
export function Page() {
  return <section><XInput size="small" /><XSelect /></section>
}
""",
                encoding="utf-8",
            )

            rules = {
                "foundation": [],
                "global": [],
                "component": [
                    component_rule("CMP-009", "input", "size", "default", "input size"),
                    component_rule("CMP-011", "select", "component-config", "", "配置可清除"),
                ],
            }
            aliases = {"x-input": "input", "x-select": "select"}

            violations = uiux.scan_project(project, rules, aliases)

        by_rule = {item["rule_id"]: item for item in violations}
        self.assertEqual(by_rule["CMP-009"]["actual"], "small")
        self.assertIn("CMP-011", by_rule)


class ScanOutputTests(unittest.TestCase):
    @unittest.skipUnless(ast_dependencies_available(), "AST dependencies are not installed")
    def test_scan_reports_tailwind_arbitrary_class_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "Page.vue").write_text(
                """
<template>
  <section class="p-[18px] text-[#333] text-[13px] rounded-[3px] shadow-[0_1px_2px_rgba(0,0,0,0.2)]" />
</template>
""",
                encoding="utf-8",
            )
            rules = {
                "foundation": [
                    foundation_rule("FDN-003", "color", "", "Tailwind arbitrary color"),
                    foundation_rule("FDN-006", "spacing", "4px|8px", "Tailwind spacing"),
                    foundation_rule("FDN-005", "typography-token", "12px|14px", "Tailwind typography"),
                    foundation_rule("FDN-013", "border-radius", "2px|4px|8px", "radius"),
                    foundation_rule("FDN-012", "box-shadow", "", "shadow"),
                ],
                "global": [],
                "component": [],
            }

            report = uiux.scan_project_detailed(project, rules, {})

        by_rule = {item["rule_id"]: item for item in report["violations"]}
        self.assertEqual(by_rule["FDN-003"]["actual"], "class `text-[#333]`")
        self.assertEqual(by_rule["FDN-006"]["actual"], "class `p-[18px]`")
        self.assertEqual(by_rule["FDN-005"]["actual"], "class `text-[13px]`")
        self.assertEqual(by_rule["FDN-013"]["actual"], "class `rounded-[3px]`")
        self.assertEqual(by_rule["FDN-012"]["actual"], "class `shadow-[0_1px_2px_rgba(0,0,0,0.2)]`")
        self.assertGreaterEqual(report["diagnostics"]["class_usages"], 1)

    @unittest.skipUnless(ast_dependencies_available(), "AST dependencies are not installed")
    def test_scan_diagnostics_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "Page.vue").write_text("<template><div class=\"p-[18px]\" /></template>", encoding="utf-8")
            rules = {
                "foundation": [foundation_rule("FDN-006", "spacing", "4px|8px", "Tailwind spacing")],
                "global": [],
                "component": [],
            }

            report = uiux.scan_project_detailed(project, rules, {})
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                uiux.print_violations_markdown(report["violations"], project, report["diagnostics"])

        self.assertTrue(report["diagnostics"]["ast"]["ast_enabled"])
        self.assertIn("## AST 诊断", buffer.getvalue())
        self.assertIn("静态 class 用法", buffer.getvalue())

    def test_scan_results_are_enriched_and_sorted_by_severity(self):
        violations = uiux.enrich_violations(
            [
                {
                    "rule_id": "FDN-006",
                    "layer": "foundation",
                    "component": "",
                    "state": "default",
                    "property_name": "spacing",
                    "expected": "4px|8px",
                    "actual": "3px",
                    "path": "/tmp/a.vue",
                    "line": 20,
                    "reason": "spacing 应符合 FDN-006",
                    "condition_if": "",
                    "preferred_pattern": "使用标准间距令牌",
                    "anti_pattern": "不要硬编码间距",
                },
                {
                    "rule_id": "CMP-011",
                    "layer": "component",
                    "component": "select",
                    "state": "default",
                    "property_name": "component-config",
                    "expected": "",
                    "actual": "未找到 clearable",
                    "path": "/tmp/a.vue",
                    "line": 10,
                    "reason": "选择器缺少 clearable 配置",
                    "condition_if": "",
                    "preferred_pattern": "启用 clearable",
                    "anti_pattern": "不要忽略清除能力",
                },
            ]
        )

        sorted_violations = uiux.sort_violations(violations)

        self.assertEqual(sorted_violations[0]["rule_id"], "CMP-011")
        self.assertEqual(sorted_violations[0]["severity"], "high")
        self.assertEqual(sorted_violations[1]["severity"], "low")
        self.assertEqual(sorted_violations[0]["suggestion"], "启用 clearable")

    def test_markdown_output_groups_same_rule_and_file(self):
        violations = uiux.enrich_violations(
            [
                {
                    "rule_id": "CMP-009",
                    "layer": "component",
                    "component": "input",
                    "state": "default",
                    "property_name": "size",
                    "expected": "default",
                    "actual": "small",
                    "path": "/tmp/Page.vue",
                    "line": 3,
                    "reason": "组件 size 配置不符合规范",
                    "condition_if": "",
                    "preferred_pattern": "将 size 设置为 default",
                    "anti_pattern": "不要使用 small",
                },
                {
                    "rule_id": "CMP-009",
                    "layer": "component",
                    "component": "input",
                    "state": "default",
                    "property_name": "size",
                    "expected": "default",
                    "actual": "large",
                    "path": "/tmp/Page.vue",
                    "line": 8,
                    "reason": "组件 size 配置不符合规范",
                    "condition_if": "",
                    "preferred_pattern": "将 size 设置为 default",
                    "anti_pattern": "不要使用 small",
                },
            ]
        )
        buffer = io.StringIO()

        with contextlib.redirect_stdout(buffer):
            uiux.print_violations_markdown(uiux.sort_violations(violations), Path("/tmp/project"))

        output = buffer.getvalue()
        self.assertIn("合并展示：1 组", output)
        self.assertIn("行号：3, 8", output)
        self.assertIn("优化建议：将 size 设置为 default", output)
        self.assertEqual(output.count("- CMP-009"), 1)


if __name__ == "__main__":
    unittest.main()
