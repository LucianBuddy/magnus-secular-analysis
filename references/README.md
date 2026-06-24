# references — 投资大师思维框架

本目录用于存放股票分析技能 (magnus-secular-analysis) 所依赖的各类投资大师思维框架。每个框架一个子目录，包含参考文档和案例。

## 当前已集成

| 大师 | 目录 | 版本 | 文档数 |
|------|------|------|--------|
| Warren Buffett | `buffett/` | v1.0 | 8 个参考文件 |

## 扩展指南（如何添加新的思维框架）

### 步骤 1：创建目录

```bash
mkdir -p references/<大师英文名小写>
```

例如：`references/munger/`、`references/druckenmiller/`

### 步骤 2：编写文档

建议的文件结构（参考 buffett 命名规范）：

| 文件 | 内容 | 必须/可选 |
|------|------|----------|
| `01-core-philosophy.md` | 核心投资哲学 | 必须 |
| `02-key-metrics.md` | 核心财务/分析指标 | 必须 |
| `03-decision-framework.md` | 决策流程/过滤器 | 必须 |
| `04-industry-playbooks.md` | 行业分析手册 | 可选 |

### 步骤 3：在 SKILL.md 中注册

在 `magnus-secular-analysis/SKILL.md` 的「前置判断 2：框架判断」分支中增加新框架的触发条件和读取路径：

```
若用户提及/问题符合 **芒格** 框架特征：
  Read: references/munger/01-core-philosophy.md
  → 走 芒格分支
```

## 注意事项

- 每个框架保持独立目录，不交叉引用
- 文档用 Markdown，纯文本（不要图片/依赖）
- 总文件大小控制在各 20KB 以内避免指令膨胀
- 框架之间的冲突规则在各分支逻辑中处理
