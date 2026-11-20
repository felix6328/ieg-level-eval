# Phase 6 · 产品验收

本次验收使用 IEG 临时 SQLite 数据库和本机 Chrome。工作台静态资源、API、Worker、数据迁移与报告均从当前分支运行。项目使用 Terra 的 40 条模型标签，独立真人配对保留为 0。

| 检查 | 结果 |
| --- | --- |
| Python 全量测试 | 14 项通过，覆盖原版冒烟、归档、版本冻结、规则、Terra 证据、审核、重写、Golden 和报表分母 |
| JS 语法 | `node --check levelgen/ieg/web/app.js` 通过 |
| 全量历史 Replay | 216 次任务，212 份解析成功，4 份解析失败仍保留，216 份已完成规则评测 |
| Judge | Terra 40/40 份原文可验证。三家历史 Judge 的结构、证据、分歧和重测均可查看，真人一致性显示样本不足 |
| 历史复盘 | 打开对应 Bad Case，执行一次原归档重写并显示重新检查结果；按配置和任务追踪 |
| Golden 与 Regression | 使用明确标记的测试身份，验证草稿、断言、审批、发布和冻结版本回归；测试数据限临时库 |
| 浏览器 | Chrome 打开总览，校准、实验、证据、审核、Golden 和选型报告页面可用；验证窄屏无横向溢出 |
| REAL | 在线 Provider 与 Judge 路径已接入；本轮无凭证与新模型调用，在线验收尚待配置 |
| 数据隔离 | 原始 24 题、216 个生成文件、历史评测结果与标签未写入；新结果落在 IEG SQLite |

## 复现

```bash
.venv/bin/python -m unittest discover -s tests -v
node --check levelgen/ieg/web/app.js
LEVEL_EVAL_DB="$(mktemp -d)/ieg.sqlite" LEVEL_EVAL_PORT=8873 scripts/run_ieg.sh
```

另开终端在同一仓库运行。

```bash
.venv/bin/python scripts/smoke_ieg.py --base http://127.0.0.1:8873 --output /tmp/leveleval-acceptance.json
```

浏览器验证状态和回归 JSON 的质量数值只适用于示例范围。选型报告先展示结构候选，同时保留语义、人审和费用证据缺口。
