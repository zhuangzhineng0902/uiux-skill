#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import tinycss2
except ImportError:  # pragma: no cover - optional dependency, fallback parser is used.
    tinycss2 = None


RULE_FILES = {
    "foundation": "foundation-rules.csv",
    "component": "component-rules.csv",
    "global": "global-layout-rules.csv",
}

COMPONENT_ALIASES_FILE = "component-aliases.csv"
AST_COMPONENT_EXTRACTOR = Path(__file__).with_name("extract_ast_components.js")
DYNAMIC_ATTR_PREFIX = "__dynamic__:"

SCAN_EXTENSIONS = {
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".pcss",
    ".html",
    ".vue",
    ".svelte",
    ".jsx",
    ".tsx",
    ".js",
    ".ts",
}

IGNORED_DIRS = {
    ".git",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    "vendor",
}

STATE_MARKERS = {
    "hover": (":hover", "hover", "is-hover"),
    "focus": (":focus", ":focus-visible", "focus", "focused", "is-focus"),
    "active": (":active", ".active", "is-active", "aria-selected", "selected"),
    "disabled": (":disabled", "[disabled]", "disabled", "aria-disabled"),
    "open": (".open", "is-open", "[open]", "aria-expanded"),
    "error": (".error", "is-error", ":invalid", "invalid", "aria-invalid"),
    "loading": ("loading", "is-loading", "spinner"),
    "selected": (".selected", "is-selected", "aria-current", "selected"),
}

SPACING_PROPS = {
    "gap",
    "row-gap",
    "column-gap",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
}

POSITION_PROPS = {
    "top",
    "right",
    "bottom",
    "left",
}

BORDER_PROPS = {
    "border-width",
    "border-style",
    "border-color",
    "border-top-width",
    "border-right-width",
    "border-bottom-width",
    "border-left-width",
    "border-top-color",
    "border-right-color",
    "border-bottom-color",
    "border-left-color",
}

FOUNDATION_TOKEN_PROP_ALIASES = {
    "color": {"color"},
    "background-color": {"background-color"},
    "primary-color": {"color", "background-color", "border-color"},
    "font-size": {"font-size"},
    "line-height": {"line-height"},
    "font-weight": {"font-weight"},
    "font-family": {"font-family"},
    "font-variant-numeric": {"font-variant-numeric"},
    "spacing": SPACING_PROPS,
    "space": SPACING_PROPS,
    "gap": {"gap", "row-gap", "column-gap"},
    "padding": {"padding-top", "padding-right", "padding-bottom", "padding-left"},
    "margin": {"margin-top", "margin-right", "margin-bottom", "margin-left"},
    "radius": {"border-radius"},
    "border-radius": {"border-radius"},
    "shadow": {"box-shadow"},
    "box-shadow": {"box-shadow"},
    "opacity": {"opacity"},
    "border": BORDER_PROPS,
    "border-width": {
        "border-width",
        "border-top-width",
        "border-right-width",
        "border-bottom-width",
        "border-left-width",
    },
    "border-style": {"border-style"},
    "border-color": {
        "border-color",
        "border-top-color",
        "border-right-color",
        "border-bottom-color",
        "border-left-color",
    },
}

GLOBAL_LAYOUT_PROPS = {
    "width",
    "max-width",
    "min-width",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "gap",
    "row-gap",
    "column-gap",
    "grid-template-columns",
    "top",
    "right",
    "bottom",
    "left",
    "z-index",
}

SHORTHAND_EXPANSIONS = {
    "padding": ("padding-top", "padding-right", "padding-bottom", "padding-left"),
    "margin": ("margin-top", "margin-right", "margin-bottom", "margin-left"),
}

DEFAULT_COMPONENT_ALIASES = {
    "el-button": "button",
    "el-link": "link",
    "el-table": "table",
    "el-table-column": "table",
    "el-form": "form",
    "el-input": "input",
    "el-input-number": "input",
    "el-select": "select",
    "el-date-picker": "datepicker",
    "el-dropdown": "dropdown",
    "el-collapse": "collapse",
}

INTERNAL_COMPONENT_PREFIXES = ("base", "biz", "corp", "ep", "pro", "u", "x")
COMPONENT_NAME_HINTS = {
    "button": ("button", "btn"),
    "link": ("link",),
    "table": ("table", "grid"),
    "form": ("form",),
    "input": ("input", "textarea"),
    "select": ("select", "picker-select"),
    "datepicker": ("date-picker", "datepicker", "date", "time-picker"),
    "dropdown": ("dropdown", "menu"),
    "collapse": ("collapse", "accordion"),
}

IGNORED_TEMPLATE_TAGS = {
    "el-collapse-item",
    "el-dropdown-item",
    "el-form-item",
    "el-option",
    "option",
}


@dataclass(frozen=True)
class Rule:
    row: dict[str, str]

    @property
    def rule_id(self) -> str:
        return self.row.get("rule_id", "")

    @property
    def layer(self) -> str:
        return self.row.get("layer", "")

    @property
    def component(self) -> str:
        return self.row.get("component", "").strip().lower()

    @property
    def state(self) -> str:
        return self.row.get("state", "").strip().lower() or "default"

    @property
    def property_name(self) -> str:
        return self.row.get("property_name", "").strip().lower()

    @property
    def default_value(self) -> str:
        return self.row.get("default_value", "").strip()

    @property
    def subject(self) -> str:
        return self.row.get("subject", "").strip()


@dataclass(frozen=True)
class Declaration:
    path: Path
    line: int
    prop: str
    value: str
    context: str
    source_prop: str = ""
    origin: str = "css"


@dataclass(frozen=True)
class ComponentUsage:
    path: Path
    line: int
    tag: str
    component: str
    attrs: dict[str, str | bool]
    context: str


def resolve_rules_dir(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()

    candidates = [
        Path.cwd() / "data",
        Path(__file__).resolve().parents[3] / "data",
        Path(__file__).resolve().parents[2] / "data",
    ]
    for candidate in candidates:
        if all((candidate / filename).exists() for filename in RULE_FILES.values()):
            return candidate.resolve()
    raise SystemExit("找不到规则 CSV 文件。请显式传入 --rules-dir。")


def load_rules(rules_dir: Path) -> dict[str, list[Rule]]:
    result: dict[str, list[Rule]] = {}
    for bucket, filename in RULE_FILES.items():
        path = rules_dir / filename
        if not path.exists():
            raise SystemExit(f"缺少规则文件：{path}")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            result[bucket] = [Rule(row) for row in csv.DictReader(handle)]
    return result


def load_component_aliases(rules_dir: Path) -> dict[str, str]:
    aliases = dict(DEFAULT_COMPONENT_ALIASES)
    path = rules_dir / COMPONENT_ALIASES_FILE
    if not path.exists():
        return aliases
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            tag = normalize_component_tag(row.get("tag", ""))
            component = row.get("component", "").strip().lower()
            if tag and component:
                aliases[tag] = component
    return aliases


def parse_components(raw_values: Iterable[str]) -> list[str]:
    components: list[str] = []
    for raw in raw_values:
        for item in re.split(r"[,，\s]+", raw):
            normalized = item.strip().lower()
            if normalized and normalized not in components:
                components.append(normalized)
    return components


def select_rules(rules: dict[str, list[Rule]], components: list[str]) -> list[Rule]:
    selected = list(rules["foundation"]) + list(rules["global"])
    if components:
        component_set = set(components)
        selected.extend(
            rule
            for rule in rules["component"]
            if rule.component in component_set or rule.subject.lower() in component_set
        )
    return selected


def format_rule(rule: Rule) -> dict[str, str]:
    fields = [
        "rule_id",
        "layer",
        "page_type",
        "subject",
        "component",
        "state",
        "property_name",
        "condition_if",
        "then_clause",
        "else_clause",
        "default_value",
        "preferred_pattern",
        "anti_pattern",
        "evidence",
        "source_ref",
    ]
    return {field: rule.row.get(field, "") for field in fields}


def print_rules_markdown(rules: list[Rule]) -> None:
    buckets = [
        ("基础规范规则", [rule for rule in rules if rule.layer == "foundation"]),
        ("全局布局规则", [rule for rule in rules if rule.layer == "global"]),
        ("组件规范规则", [rule for rule in rules if rule.layer == "component"]),
    ]
    for title, bucket_rules in buckets:
        print(f"## {title}")
        if not bucket_rules:
            print("\n未选择任何规则。\n")
            continue
        for rule in bucket_rules:
            values = format_rule(rule)
            print(
                f"- {values['rule_id']} "
                f"[{values['component'] or values['subject']} / {values['state']} / {values['property_name']}]\n"
                f"  - 条件：{values['condition_if']}\n"
                f"  - 要求：{values['then_clause']}\n"
                f"  - 默认值：{values['default_value']}\n"
                f"  - 推荐做法：{values['preferred_pattern']}\n"
                f"  - 禁止/避免：{values['anti_pattern']}\n"
            )


def iter_frontend_files(project: Path) -> Iterable[Path]:
    for path in project.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix.lower() not in SCAN_EXTENSIONS:
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        yield path


def extract_component_usages(path: Path, aliases: dict[str, str]) -> list[ComponentUsage]:
    usages = extract_component_usages_from_files([path], aliases)
    if usages:
        return usages
    return extract_component_usages_fallback(path, aliases)


def extract_component_usages_from_files(paths: Iterable[Path], aliases: dict[str, str]) -> list[ComponentUsage]:
    candidates = [
        path
        for path in paths
        if path.suffix.lower() in {".vue", ".svelte", ".html", ".jsx", ".tsx", ".js", ".ts"}
    ]
    if not candidates:
        return []
    usages = extract_component_usages_ast(candidates, aliases)
    if usages is not None:
        return usages
    fallback_usages: list[ComponentUsage] = []
    for path in candidates:
        fallback_usages.extend(extract_component_usages_fallback(path, aliases))
    return fallback_usages


def extract_component_usages_ast(paths: list[Path], aliases: dict[str, str]) -> list[ComponentUsage] | None:
    if not AST_COMPONENT_EXTRACTOR.exists():
        return None
    payload = {"files": [str(path) for path in paths]}
    try:
        completed = subprocess.run(
            ["node", str(AST_COMPONENT_EXTRACTOR)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=str(Path(__file__).resolve().parents[1]),
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        items = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return component_usages_from_ast_items(items, aliases)


def component_usages_from_ast_items(items: list[object], aliases: dict[str, str]) -> list[ComponentUsage]:
    usages: list[ComponentUsage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_tag = str(item.get("tag", "")).strip()
        tag = normalize_component_tag(raw_tag)
        component = resolve_component_name(tag, aliases)
        if not component:
            continue
        raw_attrs = item.get("attrs", {})
        attrs = normalize_ast_attrs(raw_attrs if isinstance(raw_attrs, dict) else {})
        usages.append(
            ComponentUsage(
                Path(str(item.get("path", ""))),
                int(item.get("line") or 1),
                raw_tag,
                component,
                attrs,
                re.sub(r"\s+", " ", str(item.get("context", ""))).strip(),
            )
        )
    return usages


def normalize_ast_attrs(raw_attrs: dict[object, object]) -> dict[str, str | bool]:
    attrs: dict[str, str | bool] = {}
    for raw_name, raw_value in raw_attrs.items():
        name = normalize_attr_name(str(raw_name))
        if not name:
            continue
        if raw_value is True:
            attrs[name] = True
        elif raw_value is False:
            attrs[name] = "false"
        elif raw_value is None:
            attrs[name] = True
        else:
            attrs[name] = str(raw_value).strip()
    return attrs


def extract_component_usages_fallback(path: Path, aliases: dict[str, str]) -> list[ComponentUsage]:
    if path.suffix.lower() not in {".vue", ".svelte", ".html"}:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    template_sources = extract_template_sources(path, text)
    usages: list[ComponentUsage] = []
    for source in template_sources:
        usages.extend(parse_template_components(path, source["template"], source["line"], aliases))
    return usages


def extract_template_sources(path: Path, text: str) -> list[dict[str, object]]:
    suffix = path.suffix.lower()
    if suffix in {".vue", ".svelte"}:
        sources: list[dict[str, object]] = []
        for match in re.finditer(r"<template\b[^>]*>(?P<template>.*?)</template>", text, flags=re.IGNORECASE | re.DOTALL):
            template = match.group("template")
            if template.strip():
                sources.append(
                    {
                        "template": template,
                        "line": text[: match.start("template")].count("\n") + 1,
                    }
                )
        return sources
    return [{"template": text, "line": 1}]


def parse_template_components(path: Path, template: str, start_line: int, aliases: dict[str, str]) -> list[ComponentUsage]:
    usages: list[ComponentUsage] = []
    tag_pattern = re.compile(r"<(?P<tag>[A-Za-z][\w.:-]*)(?P<attrs>(?:\s+[^<>]*?)?)(?:/?)>", flags=re.DOTALL)
    for match in tag_pattern.finditer(template):
        raw_tag = match.group("tag")
        if raw_tag.startswith(("/", "!", "?")):
            continue
        tag = normalize_component_tag(raw_tag)
        component = resolve_component_name(tag, aliases)
        if not component:
            continue
        attrs = parse_template_attrs(match.group("attrs") or "")
        line = start_line + template[: match.start()].count("\n")
        context = f"<{raw_tag}{match.group('attrs') or ''}>"
        usages.append(ComponentUsage(path, line, raw_tag, component, attrs, re.sub(r"\s+", " ", context).strip()))
    return usages


def normalize_component_tag(value: str) -> str:
    value = value.strip()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    return value.replace("_", "-").lower()


def resolve_component_name(tag: str, aliases: dict[str, str]) -> str:
    if tag in IGNORED_TEMPLATE_TAGS:
        return ""
    if tag in aliases:
        return aliases[tag]
    parts = [part for part in re.split(r"[-:.]", tag) if part]
    if not parts:
        return ""
    for component, hints in COMPONENT_NAME_HINTS.items():
        if tag == component or tag.endswith(f"-{component}") or any(hint in tag for hint in hints):
            if len(parts) > 1 or parts[0] in INTERNAL_COMPONENT_PREFIXES:
                return component
    return ""


def parse_template_attrs(raw: str) -> dict[str, str | bool]:
    attrs: dict[str, str | bool] = {}
    attr_pattern = re.compile(
        r"(?P<name>[:@#]?[A-Za-z_][\w:.-]*)(?:\s*=\s*(?P<quote>['\"])(?P<quoted>.*?)\2|\s*=\s*(?P<bare>[^\s\"'=<>`]+))?",
        flags=re.DOTALL,
    )
    for match in attr_pattern.finditer(raw):
        name = normalize_attr_name(match.group("name"))
        if not name:
            continue
        value = match.group("quoted") if match.group("quoted") is not None else match.group("bare")
        attrs[name] = True if value is None else value.strip()
    return attrs


def normalize_attr_name(name: str) -> str:
    name = name.strip()
    if name.startswith("@") or name.startswith("#"):
        return ""
    if name.startswith(":"):
        name = name[1:]
    if name.startswith("v-bind:"):
        name = name[len("v-bind:") :]
    if "." in name:
        name = name.split(".", 1)[0]
    return to_kebab_case(name)


def extract_declarations(path: Path) -> list[Declaration]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    declarations: list[Declaration] = []
    for source in extract_style_sources(path, text):
        declarations.extend(parse_css_declarations(path, source["css"], source["line"], source["context"]))
    return declarations


def extract_style_sources(path: Path, text: str) -> list[dict[str, object]]:
    suffix = path.suffix.lower()
    if suffix in {".vue", ".svelte", ".html"}:
        sources: list[dict[str, object]] = []
        for match in re.finditer(r"<style\b(?P<attrs>[^>]*)>(?P<css>.*?)</style>", text, flags=re.IGNORECASE | re.DOTALL):
            css = match.group("css")
            if not css.strip():
                continue
            line = text[: match.start("css")].count("\n") + 1
            attrs = re.sub(r"\s+", " ", match.group("attrs").strip())
            sources.append({"css": css, "line": line, "context": f"<style {attrs}>".strip()})
        return sources
    return [{"css": text, "line": 1, "context": path.name}]


def parse_css_declarations(path: Path, css: str, start_line: int, source_context: str) -> list[Declaration]:
    if tinycss2 is not None:
        try:
            rules = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
            return parse_tinycss_rules(path, rules, start_line, [source_context])
        except Exception:
            pass
    return parse_css_declarations_fallback(path, css, start_line, source_context)


def parse_tinycss_rules(path: Path, rules: list[object], start_line: int, context_stack: list[str]) -> list[Declaration]:
    declarations: list[Declaration] = []
    for rule in rules:
        rule_type = getattr(rule, "type", "")
        if rule_type == "qualified-rule":
            selector = tinycss2.serialize(rule.prelude).strip()
            context = " ".join(part for part in [*context_stack, selector] if part)
            for declaration in tinycss2.parse_declaration_list(rule.content, skip_comments=True, skip_whitespace=True):
                if getattr(declaration, "type", "") != "declaration":
                    continue
                prop = to_kebab_case(declaration.name)
                value = clean_value(tinycss2.serialize(declaration.value))
                if prop and value:
                    line = start_line + max(getattr(declaration, "source_line", 1) - 1, 0)
                    declarations.extend(expand_declaration(path, line, prop, value, context, origin="tinycss2"))
        elif rule_type == "at-rule" and getattr(rule, "content", None):
            at_context = f"@{rule.lower_at_keyword} {tinycss2.serialize(rule.prelude).strip()}".strip()
            nested = tinycss2.parse_rule_list(rule.content, skip_comments=True, skip_whitespace=True)
            declarations.extend(parse_tinycss_rules(path, nested, start_line, [*context_stack, at_context]))
    return declarations


def parse_css_declarations_fallback(path: Path, css: str, start_line: int, source_context: str) -> list[Declaration]:
    declarations: list[Declaration] = []
    for selector, body, line in iter_css_blocks(css, start_line):
        context = f"{source_context} {selector}".strip()
        declarations.extend(parse_declaration_block(path, body, line, context))
    return declarations


def iter_css_blocks(css: str, start_line: int) -> Iterable[tuple[str, str, int]]:
    stack: list[tuple[str, int]] = []
    token_start = 0
    index = 0
    while index < len(css):
        char = css[index]
        if char in {"'", '"'}:
            index = skip_css_string(css, index)
            continue
        if css.startswith("/*", index):
            index = css.find("*/", index + 2)
            if index == -1:
                break
            index += 2
            continue
        if char == "{":
            selector = css[token_start:index].strip()
            stack.append((selector, index + 1))
            token_start = index + 1
        elif char == "}" and stack:
            selector, body_start = stack.pop()
            body = css[body_start:index]
            line = start_line + css[:body_start].count("\n")
            if selector and ":" in body and not selector.lstrip().startswith("@"):
                yield selector, body, line
            token_start = index + 1
        index += 1


def skip_css_string(css: str, index: int) -> int:
    quote = css[index]
    index += 1
    while index < len(css):
        if css[index] == "\\":
            index += 2
            continue
        if css[index] == quote:
            return index + 1
        index += 1
    return index


def parse_declaration_block(path: Path, body: str, start_line: int, context: str) -> list[Declaration]:
    declarations: list[Declaration] = []
    chunk_start = 0
    depth = 0
    index = 0
    while index <= len(body):
        char = body[index] if index < len(body) else ";"
        if char in {"'", '"'}:
            index = skip_css_string(body, index)
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == ";" and depth == 0:
            chunk = body[chunk_start:index].strip()
            if ":" in chunk:
                prop, value = chunk.split(":", 1)
                prop = to_kebab_case(prop)
                value = clean_value(value)
                line = start_line + body[:chunk_start].count("\n")
                if prop and value:
                    declarations.extend(expand_declaration(path, line, prop, value, context, origin="fallback-css"))
            chunk_start = index + 1
        index += 1
    return declarations


def expand_declaration(path: Path, line: int, prop: str, value: str, context: str, origin: str = "css") -> list[Declaration]:
    if prop in SHORTHAND_EXPANSIONS:
        values = split_box_values(value)
        expanded = dict(zip(SHORTHAND_EXPANSIONS[prop], values, strict=True))
        return [
            Declaration(path, line, expanded_prop, expanded_value, context, source_prop=prop, origin=origin)
            for expanded_prop, expanded_value in expanded.items()
        ]
    if prop == "border":
        return expand_border(path, line, value, context, origin=origin)
    return [Declaration(path, line, prop, value, context, source_prop=prop, origin=origin)]


def split_box_values(value: str) -> tuple[str, str, str, str]:
    parts = [part for part in re.split(r"\s+", clean_value(value)) if part]
    if len(parts) == 1:
        top = right = bottom = left = parts[0]
    elif len(parts) == 2:
        top = bottom = parts[0]
        right = left = parts[1]
    elif len(parts) == 3:
        top = parts[0]
        right = left = parts[1]
        bottom = parts[2]
    else:
        top, right, bottom, left = parts[:4]
    return top, right, bottom, left


def expand_border(path: Path, line: int, value: str, context: str, origin: str = "css") -> list[Declaration]:
    width = ""
    style = ""
    color = ""
    for part in re.split(r"\s+", clean_value(value)):
        if re.match(r"^\d+(\.\d+)?(px|rem|em)$", part):
            width = part
        elif part in {"none", "solid", "dashed", "dotted", "double"}:
            style = part
        elif looks_like_css_color(part):
            color = part
    declarations = []
    if width:
        declarations.append(Declaration(path, line, "border-width", width, context, source_prop="border", origin=origin))
    if style:
        declarations.append(Declaration(path, line, "border-style", style, context, source_prop="border", origin=origin))
    if color:
        declarations.append(Declaration(path, line, "border-color", color, context, source_prop="border", origin=origin))
    return declarations or [Declaration(path, line, "border", value, context, source_prop="border", origin=origin)]


def clean_value(value: str) -> str:
    value = value.strip().strip("'\"")
    value = re.sub(r"\s*!important$", "", value, flags=re.IGNORECASE)
    return value.strip()


def to_kebab_case(value: str) -> str:
    value = value.strip()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    return value.replace("_", "-").lower()


def normalize_css_value(value: str) -> str:
    value = clean_value(value).lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*,\s*", ",", value)
    return value


def expected_values(rule: Rule) -> list[str]:
    raw_values = [rule.default_value]
    if rule.property_name in {"spacing", "font-size", "typography-token", "border-radius", "box-shadow", "color", "background-color"}:
        raw_values.extend(
            [
                rule.row.get("then_clause", ""),
                rule.row.get("preferred_pattern", ""),
            ]
        )

    result: list[str] = []
    for raw in raw_values:
        if not raw:
            continue
        parts = [part.strip() for part in re.split(r"[、|/，]", raw) if part.strip()]
        candidates = parts if any(looks_like_css_value(part) for part in parts) else [raw]
        for candidate in candidates:
            if looks_like_css_value(candidate) and candidate not in result:
                result.append(candidate)
        for value in extract_css_literals(raw):
            if value not in result:
                result.append(value)
    return result


def extract_css_literals(value: str) -> list[str]:
    literals: list[str] = []
    patterns = [
        r"#[0-9a-fA-F]{3,8}\b",
        r"rgba?\([^)]*\)",
        r"hsla?\([^)]*\)",
        r"\b\d+(\.\d+)?(px|rem|em|%|vh|vw|s|ms)\b",
        r"\b0\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, value):
            literal = match.group(0)
            if literal not in literals:
                literals.append(literal)
    return literals


def looks_like_css_value(value: str) -> bool:
    value = value.strip()
    return bool(
        looks_like_css_color(value)
        or re.search(r"\b\d+(\.\d+)?(px|rem|em|%|vh|vw|s|ms)\b", value)
        or value in {"0", "none", "auto", "transparent", "inherit", "initial", "unset", "100%"}
    )


def looks_like_css_color(value: str) -> bool:
    return bool(re.search(r"^(#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\()", value.strip()))


def rule_css_properties(rule: Rule) -> set[str]:
    if rule.layer == "foundation":
        subject = rule.subject.lower()
        if rule.property_name == "color":
            if "边框" in subject:
                return {"border-color", "border-top-color", "border-right-color", "border-bottom-color", "border-left-color"}
            if "分割线" in subject:
                return {"border-color", "background-color"}
            if "背景" in subject:
                return {"background-color"}
            if "文本" in subject:
                return {"color"}
        return set(FOUNDATION_TOKEN_PROP_ALIASES.get(rule.property_name, {rule.property_name}))
    return {rule.property_name}


def context_matches_component(rule: Rule, context: str) -> bool:
    if rule.layer != "component":
        return True
    if not rule.component:
        return True
    lowered = context.lower()
    component = re.escape(rule.component)
    return bool(re.search(rf"(\.{component}\b|\b{component}\b|-{component}\b|{component}-)", lowered))


def context_matches_state(rule: Rule, context: str) -> bool:
    if rule.layer != "component":
        return True
    if rule.state in {"", "default"}:
        lowered = context.lower()
        return not any(
            marker in lowered
            for state, markers in STATE_MARKERS.items()
            for marker in markers
        )
    lowered = context.lower()
    return any(marker in lowered for marker in STATE_MARKERS.get(rule.state, (rule.state,)))


def scan_project(project: Path, rules: dict[str, list[Rule]], component_aliases: dict[str, str] | None = None) -> list[dict[str, object]]:
    declarations: list[Declaration] = []
    aliases = component_aliases or DEFAULT_COMPONENT_ALIASES
    frontend_files = list(iter_frontend_files(project))
    for path in frontend_files:
        declarations.extend(extract_declarations(path))
    usages = extract_component_usages_from_files(frontend_files, aliases)

    comparable_rules = [
        rule
        for bucket in ("foundation", "global", "component")
        for rule in rules[bucket]
        if is_comparable_rule(rule)
    ]

    violations: list[dict[str, object]] = []
    for declaration in declarations:
        for rule in comparable_rules:
            if declaration.prop not in rule_css_properties(rule):
                continue
            if not context_matches_component(rule, declaration.context):
                continue
            if not context_matches_state(rule, declaration.context):
                continue
            expected = [normalize_css_value(value) for value in expected_values(rule)]
            actual = normalize_css_value(declaration.value)
            if css_value_matches(actual, expected):
                continue
            if rule.layer == "foundation" and not foundation_context_matches(rule, declaration):
                continue
            if rule.layer == "global" and not global_context_matches(rule, declaration.context):
                continue
            if is_low_confidence_css_comparison(rule, declaration):
                continue
            violations.append(
                {
                    "rule_id": rule.rule_id,
                    "layer": rule.layer,
                    "component": rule.component,
                    "state": rule.state,
                    "property_name": rule.property_name,
                    "expected": rule.default_value,
                    "actual": declaration.value,
                    "path": str(declaration.path),
                    "line": declaration.line,
                    "reason": f"{rule.property_name} 应符合 {rule.rule_id}",
                    "condition_if": rule.row.get("condition_if", ""),
                    "preferred_pattern": rule.row.get("preferred_pattern", ""),
                    "anti_pattern": rule.row.get("anti_pattern", ""),
                }
            )

    violations.extend(scan_component_usages(usages, rules["component"]))
    violations.extend(find_missing_component_states(declarations, rules["component"]))
    return dedupe_violations(violations)


def is_comparable_rule(rule: Rule) -> bool:
    if not rule.property_name or not expected_values(rule):
        return False
    if rule.layer == "global" and rule.property_name not in GLOBAL_LAYOUT_PROPS:
        return False
    if rule.layer == "foundation" and not rule_css_properties(rule):
        return False
    return True


def is_low_confidence_css_comparison(rule: Rule, declaration: Declaration) -> bool:
    actual = normalize_css_value(declaration.value)
    if rule.property_name == "spacing":
        if actual in {"0", "0px", "0rem", "0em", "auto"}:
            return True
        if "calc(" in actual or actual.startswith("-"):
            return True
        if declaration.prop in POSITION_PROPS:
            return True
        if is_reset_context(declaration.context):
            return True
    if rule.layer == "foundation" and rule.property_name in {"spacing", "font-size", "typography-token"}:
        if is_reset_context(declaration.context):
            return True
    return False


def css_value_matches(actual: str, expected: list[str]) -> bool:
    if actual in expected:
        return True
    actual_px = css_length_to_px(actual)
    if actual_px is None:
        return False
    return any(expected_px is not None and abs(actual_px - expected_px) < 0.01 for expected_px in map(css_length_to_px, expected))


def css_length_to_px(value: str) -> float | None:
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px|rem)", normalize_css_value(value))
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    return number if unit == "px" else number * 16


def is_reset_context(context: str) -> bool:
    lowered = context.lower()
    reset_selectors = ("*", "::before", "::after", "body", "html", "#app")
    reset_markers = ("reset", "normalize", "base.css", "main.css")
    return any(selector in lowered for selector in reset_selectors) and any(marker in lowered for marker in reset_markers)


def global_context_matches(rule: Rule, context: str) -> bool:
    subject = rule.subject.lower()
    condition = rule.row.get("condition_if", "").lower()
    if "屏幕宽度" in condition and "@media" not in context.lower():
        return False
    if "屏幕宽度" not in condition and "@media" in context.lower():
        return False
    if not subject or subject in {"explicit-if-then-else"}:
        return True
    normalized_subject = re.sub(r"\s+", "-", subject)
    lowered = context.lower()
    return subject in lowered or normalized_subject in lowered


def foundation_context_matches(rule: Rule, declaration: Declaration) -> bool:
    subject = rule.subject.lower()
    if not subject:
        return False
    context = declaration.context
    lowered = context.lower()
    aliases = {
        "标题文本": ("title", "heading", "h1", "h2", "h3"),
        "一级文本": ("primary-text", "body", "content"),
        "二级文本": ("secondary-text", "muted", "caption", "subtext"),
        "禁用文本": ("disabled", "is-disabled", "[disabled]"),
        "一级边框": ("primary-border",),
        "分割线": ("divider", "separator"),
        "布局背景": ("layout-background", "page-shell", "layout"),
        "主字体": ("body", "root", "html"),
        "regular": ("regular", "body"),
        "medium": ("medium", "emphasis"),
        "英文加粗": ("semibold", "bold"),
        "间距": ("spacing", "space", "gap", "padding", "margin"),
        "圆角": ("radius", "rounded", "border-radius"),
        "阴影": ("shadow", "elevation", "box-shadow"),
        "透明度": ("opacity", "alpha"),
        "边框": ("border", "stroke"),
    }
    if subject in lowered or re.sub(r"\s+", "-", subject) in lowered:
        return True
    if "边框" in subject and declaration.prop not in BORDER_PROPS:
        return False
    if "圆角" in subject and declaration.prop != "border-radius":
        return False
    if "阴影" in subject and declaration.prop != "box-shadow":
        return False
    if "透明度" in subject and declaration.prop != "opacity":
        return False
    if any(any(alias in lowered for alias in values) for key, values in aliases.items() if key in subject):
        return True
    return is_foundation_token_set_rule(rule)


def is_foundation_token_set_rule(rule: Rule) -> bool:
    if rule.property_name not in FOUNDATION_TOKEN_PROP_ALIASES:
        return False
    if not expected_values(rule):
        return False
    subject_and_condition = f"{rule.subject} {rule.row.get('condition_if', '')}".lower()
    token_markers = (
        "token",
        "令牌",
        "基础",
        "色板",
        "字阶",
        "间距",
        "圆角",
        "阴影",
        "透明度",
        "边框",
    )
    return any(marker in subject_and_condition for marker in token_markers)


def scan_component_usages(usages: list[ComponentUsage], component_rules: list[Rule]) -> list[dict[str, object]]:
    rules_by_component: dict[str, list[Rule]] = {}
    for rule in component_rules:
        if rule.component:
            rules_by_component.setdefault(rule.component, []).append(rule)

    violations: list[dict[str, object]] = []
    for usage in usages:
        for rule in rules_by_component.get(usage.component, []):
            violation = evaluate_component_rule(usage, rule)
            if violation:
                violations.append(violation)
    return violations


def evaluate_component_rule(usage: ComponentUsage, rule: Rule) -> dict[str, object] | None:
    prop = rule.property_name
    if prop == "size":
        return require_prop_value(usage, rule, "size", rule.default_value or "default", report_missing=False)
    if prop == "label-position":
        if not is_primary_component_tag(usage):
            return None
        return require_prop_value(usage, rule, "label-position", rule.default_value or "top")
    if prop == "fixed-position":
        if has_action_column_marker(usage):
            return require_prop_value(usage, rule, "fixed", "right")
        return None
    if prop == "component-config":
        return evaluate_component_config_rule(usage, rule)
    if prop == "white-space" and usage.tag.lower().endswith("table-column"):
        if has_any_prop(usage, {"show-overflow-tooltip", "tooltip"}):
            return None
        return component_violation(usage, rule, "缺少防止表头换行的 tooltip/nowrap 配置", "未找到 show-overflow-tooltip")
    if prop == "icon" and usage.component == "collapse":
        if not is_primary_component_tag(usage):
            return None
        return require_prop_value(usage, rule, "expand-icon-position", rule.default_value or "left")
    return None


def evaluate_component_config_rule(usage: ComponentUsage, rule: Rule) -> dict[str, object] | None:
    subject = rule.subject.lower()
    if usage.component == "select":
        if any(marker in subject for marker in ("清除", "clearable", "可清")) and not has_truthy_prop(usage, "clearable"):
            return component_violation(usage, rule, "选择器缺少 clearable 配置", "未找到 clearable")
        if any(marker in subject for marker in ("搜索", "searchable", "filterable")) and not has_any_prop(usage, {"filterable", "remote", "searchable"}):
            return component_violation(usage, rule, "选择器缺少可搜索配置", "未找到 filterable/searchable")
        if any(marker in subject for marker in ("折叠", "collapsed")) and is_multiple_select(usage) and not has_truthy_prop(usage, "collapse-tags"):
            return component_violation(usage, rule, "多选选择器缺少标签折叠配置", "未找到 collapse-tags")
    if usage.component == "datepicker":
        if any(marker in subject for marker in ("清除", "clearable", "可清")) and not has_truthy_prop(usage, "clearable"):
            return component_violation(usage, rule, "日期选择器缺少 clearable 配置", "未找到 clearable")
    return None


def require_prop_value(usage: ComponentUsage, rule: Rule, prop_name: str, expected: str, report_missing: bool = True) -> dict[str, object] | None:
    actual = attr_value(usage, prop_name)
    if actual is None:
        if not report_missing:
            return None
        return component_violation(usage, rule, f"组件缺少 {prop_name} 配置", f"未找到 {prop_name}")
    if is_dynamic_attr_value(actual):
        return None
    if normalize_template_value(actual) != normalize_template_value(expected):
        return component_violation(usage, rule, f"组件 {prop_name} 配置不符合规范", str(actual))
    return None


def component_violation(usage: ComponentUsage, rule: Rule, reason: str, actual: str) -> dict[str, object]:
    return {
        "rule_id": rule.rule_id,
        "layer": rule.layer,
        "component": rule.component,
        "state": rule.state,
        "property_name": rule.property_name,
        "expected": rule.default_value,
        "actual": actual,
        "path": str(usage.path),
        "line": usage.line,
        "reason": f"{reason}（{usage.tag} 识别为 {usage.component}）",
        "condition_if": rule.row.get("condition_if", ""),
        "preferred_pattern": rule.row.get("preferred_pattern", ""),
        "anti_pattern": rule.row.get("anti_pattern", ""),
    }


def attr_value(usage: ComponentUsage, name: str) -> str | bool | None:
    return usage.attrs.get(to_kebab_case(name))


def has_truthy_prop(usage: ComponentUsage, name: str) -> bool:
    value = attr_value(usage, name)
    if value is None:
        return False
    if value is True:
        return True
    if is_dynamic_attr_value(value):
        return True
    return normalize_template_value(value) not in {"false", "0", "undefined", "null"}


def has_any_prop(usage: ComponentUsage, names: set[str]) -> bool:
    return any(name in usage.attrs for name in names)


def normalize_template_value(value: str | bool) -> str:
    if value is True:
        return "true"
    normalized = str(value).strip().strip("'\"").lower()
    return re.sub(r"\s+", " ", normalized)


def is_dynamic_attr_value(value: str | bool) -> bool:
    return isinstance(value, str) and value.startswith(DYNAMIC_ATTR_PREFIX)


def is_multiple_select(usage: ComponentUsage) -> bool:
    return has_truthy_prop(usage, "multiple") or normalize_template_value(attr_value(usage, "type") or "") == "multiple"


def has_action_column_marker(usage: ComponentUsage) -> bool:
    text = " ".join(str(value) for value in usage.attrs.values())
    return bool(
        usage.tag.lower().endswith("table-column")
        and (
            normalize_template_value(attr_value(usage, "type") or "") == "action"
            or "操作" in text
            or "action" in text.lower()
        )
    )


def is_primary_component_tag(usage: ComponentUsage) -> bool:
    tag = normalize_component_tag(usage.tag)
    return tag not in IGNORED_TEMPLATE_TAGS and not tag.endswith(("-item", "-option"))


def find_missing_component_states(declarations: list[Declaration], component_rules: list[Rule]) -> list[dict[str, object]]:
    required: dict[str, set[str]] = {}
    properties: dict[tuple[str, str], set[str]] = {}
    for rule in component_rules:
        if rule.component and rule.state and rule.state != "default":
            required.setdefault(rule.component, set()).add(rule.state)
            properties.setdefault((rule.component, rule.state), set()).add(rule.property_name)

    seen: dict[str, dict[str, Declaration]] = {}
    for declaration in declarations:
        lowered = declaration.context.lower()
        for component, states in required.items():
            if not re.search(rf"(\.{re.escape(component)}\b|\b{re.escape(component)}\b)", lowered):
                continue
            bucket = seen.setdefault(component, {})
            bucket.setdefault("default", declaration)
            for state in states:
                if any(marker in lowered for marker in STATE_MARKERS.get(state, (state,))):
                    bucket[state] = declaration

    violations: list[dict[str, object]] = []
    for component, states in required.items():
        component_seen = seen.get(component, {})
        if "default" not in component_seen:
            continue
        anchor = component_seen["default"]
        for state in sorted(states):
            if state in component_seen:
                continue
            violations.append(
                {
                    "rule_id": "CMP-state-coverage",
                    "layer": "component",
                    "component": component,
                    "state": state,
                    "property_name": ",".join(sorted(properties.get((component, state), set()))),
                    "expected": f"{component} 应定义 {state} 状态",
                    "actual": "未找到状态选择器",
                    "path": str(anchor.path),
                    "line": anchor.line,
                    "reason": "组件规范要求的交互状态在已扫描样式中缺失",
                    "condition_if": "",
                    "preferred_pattern": "为已使用组件声明必需的交互状态。",
                    "anti_pattern": "不要在缺少必要视觉状态的情况下交付组件。",
                }
            )
    return violations


def dedupe_violations(violations: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for item in violations:
        key = (item["rule_id"], item["path"], item["line"], item["property_name"], item["state"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def print_violations_markdown(violations: list[dict[str, object]], project: Path) -> None:
    print(f"# UIUX 扫描报告\n\n工程：`{project}`\n\n违规数量：{len(violations)}\n")
    if not violations:
        print("未发现高置信度静态违规。")
        return
    for item in violations:
        print(
            f"- {item['rule_id']} `{item['path']}:{item['line']}`\n"
            f"  - {item['reason']}\n"
            f"  - 属性：`{item['property_name']}`；实际值：`{item['actual']}`；期望值：`{item['expected']}`\n"
            f"  - 禁止/避免：{item['anti_pattern']}\n"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检索 UIUX 规则，或扫描前端工程。")
    parser.add_argument("--rules-dir", default=None, help="包含三个 UIUX 规则 CSV 文件的目录。")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rules_parser = subparsers.add_parser("rules-for-components", help="加载基础/全局规则，并按组件名加载对应组件规则。")
    rules_parser.add_argument("--components", action="append", default=[], help="用英文逗号或空格分隔的组件名称。")

    scan_parser = subparsers.add_parser("scan-project", help="扫描前端工程中的高置信度 UIUX 违规。")
    scan_parser.add_argument("--project", required=True, help="前端工程路径。")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rules_dir = resolve_rules_dir(args.rules_dir)
    rules = load_rules(rules_dir)
    component_aliases = load_component_aliases(rules_dir)

    if args.command == "rules-for-components":
        selected = select_rules(rules, parse_components(args.components))
        payload = [format_rule(rule) for rule in selected]
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_rules_markdown(selected)
        return 0

    if args.command == "scan-project":
        project = Path(args.project).expanduser().resolve()
        violations = scan_project(project, rules, component_aliases)
        if args.format == "json":
            print(json.dumps(violations, ensure_ascii=False, indent=2))
        else:
            print_violations_markdown(violations, project)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
