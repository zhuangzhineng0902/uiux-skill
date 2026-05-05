#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const DYNAMIC_ATTR_PREFIX = "__dynamic__:";
const repoRoot = path.resolve(__dirname, "..");
const modulePaths = [repoRoot, path.join(repoRoot, "example"), process.cwd()];

function loadModule(name) {
  return require(require.resolve(name, { paths: modulePaths }));
}

let parseSfc;
let parseTemplate;
let babelParser;
try {
  ({ parse: parseSfc } = loadModule("@vue/compiler-sfc"));
  ({ parse: parseTemplate } = loadModule("@vue/compiler-dom"));
  babelParser = loadModule("@babel/parser");
} catch (error) {
  console.error(`AST dependency unavailable: ${error.message}`);
  process.exit(2);
}

function readInput() {
  const raw = fs.readFileSync(0, "utf8").trim();
  return raw ? JSON.parse(raw) : { files: [] };
}

function normalizeContext(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function literalFromVueExpression(exp) {
  if (!exp || !exp.content) {
    return true;
  }
  const text = exp.content.trim();
  if (/^['"].*['"]$/.test(text)) {
    return text.slice(1, -1);
  }
  if (/^(true|false)$/i.test(text)) {
    return text.toLowerCase();
  }
  if (/^-?\d+(\.\d+)?$/.test(text)) {
    return text;
  }
  return `${DYNAMIC_ATTR_PREFIX}${text}`;
}

function collectVueAttrs(props) {
  const attrs = {};
  for (const prop of props || []) {
    if (prop.type === 6) {
      attrs[prop.name] = prop.value ? prop.value.content : true;
      continue;
    }
    if (prop.type !== 7) {
      continue;
    }
    if (prop.name === "bind" && prop.arg && prop.arg.type === 4 && prop.arg.content) {
      attrs[prop.arg.content] = literalFromVueExpression(prop.exp);
    } else if (prop.name === "model") {
      attrs["v-model"] = literalFromVueExpression(prop.exp);
    }
  }
  return attrs;
}

function walkVueNode(node, visitor) {
  visitor(node);
  for (const child of node.children || []) {
    walkVueNode(child, visitor);
  }
}

function extractVueTemplate(file, template, lineOffset) {
  const ast = parseTemplate(template, { comments: false });
  const usages = [];
  walkVueNode(ast, (node) => {
    if (node.type !== 1) {
      return;
    }
    usages.push({
      path: file,
      line: lineOffset + Math.max((node.loc && node.loc.start && node.loc.start.line) || 1, 1) - 1,
      tag: node.tag,
      attrs: collectVueAttrs(node.props),
      context: normalizeContext((node.loc && node.loc.source) || `<${node.tag}>`),
    });
  });
  return usages;
}

function extractVueFile(file, code) {
  const parsed = parseSfc(code, { filename: file });
  const template = parsed.descriptor && parsed.descriptor.template;
  if (!template || !template.content || !template.content.trim()) {
    return [];
  }
  const startLine = (template.loc && template.loc.start && template.loc.start.line) || 1;
  return extractVueTemplate(file, template.content, startLine);
}

function jsxName(node) {
  if (!node) {
    return "";
  }
  if (node.type === "JSXIdentifier") {
    return node.name;
  }
  if (node.type === "JSXMemberExpression") {
    return `${jsxName(node.object)}.${jsxName(node.property)}`;
  }
  if (node.type === "JSXNamespacedName") {
    return `${jsxName(node.namespace)}:${jsxName(node.name)}`;
  }
  return "";
}

function literalFromBabelExpression(expression, code) {
  if (!expression) {
    return true;
  }
  if (expression.type === "StringLiteral") {
    return expression.value;
  }
  if (expression.type === "NumericLiteral") {
    return String(expression.value);
  }
  if (expression.type === "BooleanLiteral") {
    return String(expression.value);
  }
  const source = typeof expression.start === "number" && typeof expression.end === "number"
    ? code.slice(expression.start, expression.end)
    : "";
  return `${DYNAMIC_ATTR_PREFIX}${source.trim()}`;
}

function collectJsxAttrs(attributes, code) {
  const attrs = {};
  for (const attr of attributes || []) {
    if (attr.type !== "JSXAttribute") {
      continue;
    }
    const name = jsxName(attr.name);
    if (!name) {
      continue;
    }
    if (!attr.value) {
      attrs[name] = true;
    } else if (attr.value.type === "StringLiteral") {
      attrs[name] = attr.value.value;
    } else if (attr.value.type === "JSXExpressionContainer") {
      attrs[name] = literalFromBabelExpression(attr.value.expression, code);
    }
  }
  return attrs;
}

function walkBabelNode(node, visitor) {
  if (!node || typeof node !== "object") {
    return;
  }
  visitor(node);
  for (const key of Object.keys(node)) {
    if (key === "loc" || key === "start" || key === "end") {
      continue;
    }
    const value = node[key];
    if (Array.isArray(value)) {
      for (const child of value) {
        walkBabelNode(child, visitor);
      }
    } else if (value && typeof value.type === "string") {
      walkBabelNode(value, visitor);
    }
  }
}

function extractJsxFile(file, code) {
  const ast = babelParser.parse(code, {
    sourceType: "unambiguous",
    plugins: [
      "jsx",
      "typescript",
      "decorators-legacy",
      "classProperties",
      "classPrivateProperties",
      "classPrivateMethods",
      "objectRestSpread",
      "dynamicImport",
      "optionalChaining",
      "nullishCoalescingOperator",
    ],
  });
  const usages = [];
  walkBabelNode(ast, (node) => {
    if (node.type !== "JSXOpeningElement") {
      return;
    }
    usages.push({
      path: file,
      line: (node.loc && node.loc.start && node.loc.start.line) || 1,
      tag: jsxName(node.name),
      attrs: collectJsxAttrs(node.attributes, code),
      context: normalizeContext(code.slice(node.start, node.end)),
    });
  });
  return usages;
}

function extractFile(file) {
  const code = fs.readFileSync(file, "utf8");
  const suffix = path.extname(file).toLowerCase();
  if (suffix === ".vue") {
    return extractVueFile(file, code);
  }
  if (suffix === ".html" || suffix === ".svelte") {
    return extractVueTemplate(file, code, 1);
  }
  if ([".jsx", ".tsx", ".js", ".ts"].includes(suffix) && code.includes("<")) {
    return extractJsxFile(file, code);
  }
  return [];
}

const input = readInput();
const result = [];
const diagnostics = {
  ast_enabled: true,
  files_total: (input.files || []).length,
  parsed_files: 0,
  failed_files: [],
  fallback_used: false,
};
for (const file of input.files || []) {
  const resolved = path.resolve(file);
  try {
    result.push(...extractFile(resolved));
    diagnostics.parsed_files += 1;
  } catch (error) {
    diagnostics.failed_files.push({ path: resolved, reason: error.message });
  }
}
diagnostics.fallback_used = diagnostics.failed_files.length > 0;

if (input.includeDiagnostics) {
  process.stdout.write(JSON.stringify({ items: result, diagnostics }));
} else {
  process.stdout.write(JSON.stringify(result));
}
