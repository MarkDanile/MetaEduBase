# Specs — 需求与设计文档

本目录是插件无关的交付级功能需求、产品设计和验收标准目录。后续无论使用 superpower、compound-engineering-plugin、Codex、Claude Code 或其他工具，已进入交付的新任务 spec 默认放在这里；更前期的路线图、迭代和需求池放在 `docs/01-product-planning/*`。

## 使用规则

- 新功能、较大改动、Schema/API 变更、跨 3 个以上文件且已准备交付的工作，优先在本目录建立 spec。
- 插件可以参与生成或修改 spec，但目录和文件本身不绑定某个插件。
- 历史 `docs/90-compat-legacy/superpowers/specs/*` 保留为兼容来源；新任务不要因为使用 superpower 就默认继续放入该目录。
- superpower、compound-engineering-plugin 或其他插件生成的新 spec，如果要作为本次开发依据，必须迁移或镜像到本目录；原始插件输出只登记到任务卡片的 `插件输出` 字段。
- 如果插件仍输出到旧 superpower 顶层目录或兼容目录，不能把该文件直接写入任务卡片的 `Spec` 字段；必须先在本目录建立规范副本。
- 每个进入开发的 spec 必须在 `docs/03-engineering-governance/current-work.md` 的任务卡片中登记。

## 文件命名

```text
YYYY-MM-DD-short-topic.md
```

示例：

```text
2026-06-04-template-contracts.md
```
