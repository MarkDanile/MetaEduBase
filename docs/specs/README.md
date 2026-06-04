# Specs — 需求与设计文档

本目录是插件无关的功能需求、产品设计和验收标准目录。后续无论使用 superpower、compound-engineering-plugin、Codex、Claude Code 或其他工具，新任务的长期 spec 默认放在这里。

## 使用规则

- 新功能、较大改动、Schema/API 变更、跨 3 个以上文件的工作，优先在本目录建立 spec。
- 插件可以参与生成或修改 spec，但目录和文件本身不绑定某个插件。
- 历史 `docs/superpowers/specs/*` 保留为兼容来源；新任务不要因为使用 superpower 就默认继续放入该目录。
- 每个进入开发的 spec 必须在 `docs/engineering/current-work.md` 的任务卡片中登记。

## 文件命名

```text
YYYY-MM-DD-short-topic.md
```

示例：

```text
2026-06-04-template-contracts.md
```
