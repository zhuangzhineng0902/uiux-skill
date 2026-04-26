# UIUX Skill

本工程提供一个本地 UI/UX 规范能力，用于在前端开发前检索规范规则，或在已有前端工程中扫描高置信度的 UI/UX 违规点。

## 能力概览

- 规则检索：根据组件清单输出基础规范、全局布局规范，以及匹配组件的专项规范。
- 工程扫描：扫描前端项目中的 CSS 类声明，输出规则 ID、文件位置、实际值、期望值和违规原因。
- 规则数据化：以 `data/` 下的 CSV 作为唯一事实来源，便于维护、扩展和版本管理。
- Skill 集成：通过 `SKILL.md` 和 `agents/openai.yaml` 描述能力，可作为 Codex/OpenAI agent 的可调用技能。
- 示例验证：`example/` 提供一个 Vue 3 + Vite 示例工程，可用于扫描和调试规则效果。

## 目录结构

```text
.
├── SKILL.md                    # Skill 触发说明和使用流程
├── agents/openai.yaml          # Agent 展示名称、简介和默认提示词
├── data/
│   ├── foundation-rules.csv    # 基础规范规则，当前 20 条
│   ├── global-layout-rules.csv # 全局布局规则，当前 88 条
│   └── component-rules.csv     # 组件规范规则，当前 48 条
├── scripts/
│   └── uiux_rules.py           # 规则检索与工程扫描脚本
├── example/                    # Vue 3 + Vite 示例工程
└── 需求样例全.md                # 详情页需求样例
```

## 规则来源

`data/` 目录中的三个 CSV 文件是规则的唯一事实来源：

- `foundation-rules.csv`：颜色、字体、间距、圆角、阴影、透明度、边框等基础令牌规范，默认全量加载。
- `global-layout-rules.csv`：页面全局布局和交互行为断言，默认全量加载。
- `component-rules.csv`：按钮、输入框、选择器、表格、工具栏等组件规则，按组件清单或扫描上下文加载。

组件规则当前覆盖：

```text
button, collapse, datepicker, dropdown, form, input, link, select, table, toolbar
```

全局规则中还包含通用布局、详情页、创建页、列表页、审批页等页面级或交互规则。

## 使用方式

查看命令帮助：

```bash
python3 scripts/uiux_rules.py --help
```

按组件检索规则：

```bash
python3 scripts/uiux_rules.py \
  --rules-dir data \
  rules-for-components \
  --components "button,input,table"
```

输出 JSON：

```bash
python3 scripts/uiux_rules.py \
  --rules-dir data \
  --format json \
  rules-for-components \
  --components "button,input,table"
```

扫描前端工程：

```bash
python3 scripts/uiux_rules.py \
  --rules-dir data \
  scan-project \
  --project /absolute/path/to/frontend
```

扫描本仓库示例工程：

```bash
python3 scripts/uiux_rules.py \
  --rules-dir data \
  scan-project \
  --project example
```

## 扫描范围

脚本会扫描以下前端文件类型：

```text
.css, .scss, .sass, .less, .pcss, .html, .vue, .svelte, .jsx, .tsx, .js, .ts
```

默认跳过：

```text
.git, .next, .nuxt, .svelte-kit, build, coverage, dist, node_modules, out, target, vendor
```

扫描器会展开 `padding`、`margin`、`border` 等常见简写属性，并对基础规范、全局布局规范和组件状态规范做静态比较。

## 输出说明

规则检索输出按层级分组：

- 基础规范规则
- 全局布局规则
- 组件规范规则

工程扫描输出包含：

- 规则 ID
- 规则层级
- 组件和状态
- 属性名
- 期望值和实际值
- 文件路径和行号
- 违规原因
- 推荐做法和反模式

## 边界与注意事项

- 扫描结果是第一轮高置信度静态检查，不等同于完整人工 UI/UX 审查。
- Toast、Skeleton、二次确认、遮罩点击关闭等语义交互规则，需要结合代码上下文或运行时行为人工复核。
- 动态样式、运行时 class 拼接、组件库内部样式和 CSS-in-JS 复杂表达式可能无法完全证明。
- 若组件名称有歧义，应先检查 `data/component-rules.csv` 中的 `component` 字段，再执行规则检索。

## 示例工程

`example/` 是 Vue 3 + Vite 工程，可用于验证扫描能力：

```bash
cd example
npm install
npm run dev
```

也可以在仓库根目录直接扫描示例工程：

```bash
python3 scripts/uiux_rules.py --rules-dir data scan-project --project example
```

## 维护规则

新增或调整规则时，优先编辑对应 CSV：

- 基础令牌和设计系统基础约束放入 `foundation-rules.csv`。
- 页面布局、响应式布局、全局交互断言放入 `global-layout-rules.csv`。
- 组件默认态、悬浮态、聚焦态、禁用态、错误态等组件约束放入 `component-rules.csv`。

保持每条规则尽量原子化，确保一个规则 ID 对应一个可描述、可定位、可验证的 UI/UX 要求。
