# LevelEval｜AI 游戏关卡生成器评测系统

个人项目，为投递「腾讯 IEG｜AI 产品经理（AI 生成游戏）」而做。**不是**腾讯或任何游戏项目组的生产系统。

一句话产品观：**生成很便宜，判断「生成得好不好」很贵。能用规则算死的不交给模型，模型只做规则写不死的判断，判断不准的交给人。并且，评审本身也要被评测。**

> ⚠️ 本仓库的「参照标注」是 Grok Bot 按同一份 rubric 盲标的 **「待作者人工复核的临时标注」**，**不是人工标注**。所有一致性数字在作者填完 `labels/human_labels.csv` 后要重跑，以重跑结果为准。

## 它做什么
1. **生成**：LLM 按「主题 + 难度 + 玩家画像」生成文字冒险关卡，包括场景、目标、3 个选项，以及每个选项的结果、result 和 next。设三组对照：
   - A：Qwen2.5-7B + 朴素 Prompt
   - B：Qwen2.5-7B + 结构化设计 Prompt（对比 A，看调 Prompt 的效果）
   - C：Qwen2.5-72B + 结构化 Prompt（对比 B，看换模型的效果）
2. **评测集**：6 主题 × 3 难度正交全覆盖，4 种画像按拉丁方轮转，另加 6 条对抗样例（约束冲突、含糊输入、Prompt 注入、时间循环、约束过载、画像与难度错配）。每组 24 关，共 **72 关**。
3. **评测 Agent**：
   - 规则层：10 项硬检查，其中 5 项阻断。
   - LLM 评审：DeepSeek-V3.2，和生成模型不同源；四维锚定 rubric，证据先行；正序、倒序各评一次，分歧大时追加第 3 次取中位数。
   - 规则封顶，并按条件升级到人工。
4. **评审的评测**：25 关标注集，开发集 15 关、留出集 10 关。计算 Spearman、二次加权 κ、Cohen κ、MAE、精确一致率和 ±1 一致率，**并和常数基线对比**。迭代了 v0、v1、v2、v2-cal、v1-cal 五个评审版本。
5. **报告**：badcase 归因，「调 Prompt / 换模型 / fine-tune」决策树，偏差诊断，升级率，成本。另有一个 HTML 浏览器。

设计文档见 [DESIGN.md](DESIGN.md)（市场、STP、PMF、评测集、rubric、评审偏差控制、决策树、线上闭环、风险），面试讲法见 [面试讲法.md](面试讲法.md)。

## 结果（全部来自实测运行）

### 1. 三组生成器对比（每组 24 关）
| 组 | 配置 | 规则层通过率 | 评审 v1 均分 | 评审 v2-cal 均分 (95%CI) | 合格率* | 平均生成时延 |
|---|---|---|---|---|---|---|
| A | 7B + 朴素 Prompt | 14/24 = 58% | 3.15 | 2.88 (2.57–3.18) | 7/24 = 29% | 9.9 s |
| B | 7B + 结构化 Prompt | 21/24 = 88% | 4.09 | 3.37 (3.10–3.60) | 12/24 = 50% | 10.5 s |
| C | 72B + 结构化 Prompt | 24/24 = 100% | 4.52 | 3.82 (3.69–3.93) | 19/24 = 79% | 16.4 s |

\*合格率 = 规则层通过，且 v2-cal 四维都 ≥3。

- **版本排序稳健**：v0、v1、v2、v2-cal 四种评审，加上临时参照标注（A 3.03 / B 3.19 / C 3.69，每组 8–9 关），都给出 **C > B > A**。
- **调 Prompt（A→B）** 主要解决「没按要求做」：JSON 或字段非法 9→3，死局 5→1（见 badcase 表）。
- **换模型（B→C）** 解决「做不到」：B 组「困难」档均分 2.75，反而低于 A 组的 3.21；C 组困难档 3.69，6/6 通过规则层。
- **F2 因果断裂**在三组 badcase 里都是最多的标签（15 / 9 / 3），72B 也没根除。

### 2. 评审与参照标注的一致性（四维合并；参照为临时标注）
| 评审 | 开发集（15 关）ρ / MAE | **留出集（10 关）** ρ (95%CI) / QWK / MAE / 精确一致 |
|---|---|---|
| 常数基线（永远猜中位数） | 0.33 / 0.57 | 0.13 / 0.13 / 0.60 / 42% |
| v0 无 rubric 单次 | 0.59 / 0.62 | 0.16 (−0.17~0.47) / 0.19 / 0.78 / 35% |
| v1 rubric + 证据 + 正反序 + 规则封顶 | 0.61 / 0.97 | 0.39 (0.06~0.67) / 0.20 / 1.11 / 22% |
| v2 找茬清单 + 公式合成 | 0.41 / 0.95 | −0.07 (−0.37~0.24) / −0.09 / 1.30 / 18% |
| v2-cal（公式在开发集校准） | 0.59 / 0.54 | 0.24 (−0.10~0.54) / 0.20 / 0.69 / 38% |
| **v1-cal（v1 + 开发集偏移校准）** | 0.61 / 0.61 | **0.42 (0.12~0.68) / 0.31 / 0.61 / 50%** |

结论（详见 `eval/agreement_holdout.md`、DESIGN §7.5）：
- **v1 的排序能力最稳，但整体偏宽松约 1 分。** 68% 的可解析关卡逻辑自洽性给了 5 分。校准偏移后的 v1-cal 是当前推荐配置。
- **v1-cal 的 MAE（0.61）和常数基线（0.60）持平。** 它的价值在排序（ρ 0.42，CI 不含 0），**还不能单独做门禁**，逻辑维度最弱（留出集 ρ 0.21）。
- v0 在开发集上看着不错（ρ 0.59），到留出集塌到 0.16。没有留出集就会被它骗。
- v2 抓到了 v1 漏掉的逻辑问题，但矫枉过正，见 `eval/badcases.md` §3「评审自己的 badcase」。

### 3. 偏差诊断与升级率
- **位置偏差**：v1 有 18/69 关（26%）正序和倒序至少一维差 ≥2；平均有符号差 −0.04，即没有固定方向的偏好，但存在随机不稳定。这些关卡追加了第 3 次评审取中位数。
- **篇幅偏差**：字数和 v1 分的 ρ=0.42，和参照标注的 ρ=0.45（25 关），没有发现评审比参照更偏爱长文。
- **升级到人工**：72 关中 41 关（57%）；去掉对抗样例强制抽检后是 29/72（40%）。冷启动期偏高，目标是校准后压到 15% 以下（【假设】）。

### 4. 成本
466 次调用，估算 **¥2.55**：72B 生成 ¥0.11，评审 v0 ¥0.12、v1 ¥1.26、v2 ¥1.07，7B 免费。单关评审约 ¥0.016–0.018。见 [COST.md](COST.md)。

## 如何运行
```bash
cd ieg-level-eval
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 或者在 configs/settings.yaml 的 env_file 指向已有 .env；代码只读取 SILICONFLOW_API_KEY 这一个变量
export PYTHONPATH=$PWD
./scripts/run_all.sh   # 生成 → 规则层 + 评审 v0/v1 → 评审 v2 → 校准 → 一致性 → 汇总 → HTML
```
模型调用按请求内容哈希缓存在 `logs/cache/`，复跑不重复计费。`configs/settings.yaml` 里有 ¥5 的预算熔断。

## 作者需要做的：人工标注（约 30–40 分钟）
1. 双击打开 `labels/labeling_sheet.html`。25 关已经盲化：看不到组别、模型和评审分，顺序已打乱。展开顶部的评分标准，逐关打 4 个维度的 1–5 分，并写一句扣分理由。进度会自动保存在浏览器里。
   - 也可以用 Excel 或飞书表格打开 `labels/labeling_sheet_full.csv` 来标注（里面有关卡全文）。
2. 点「导出 CSV」，把下载的文件覆盖到 `labels/human_labels.csv`。
3. 运行：
   ```bash
   for s in all dev holdout; do python scripts/compute_agreement.py --split $s; done
   python scripts/analyze.py
   ```
   `human_labels.csv` 里有 ≥10 行完整分数时，脚本会自动改用真人标注作为参照，报告标题也会随之变化。
4. 建议：标注前**不要**先看 `labels/provisional_reference.csv` 和 viewer 里的分数，避免被锚定。标完之后再拿自己的分和临时标注对比，可以顺便算出「两个标注者之间的一致性」，这是评审能达到的天花板。

## 目录
```
DESIGN.md / 面试讲法.md / COST.md
configs/settings.yaml      模型、价格、预算
configs/grid.yaml          评测集：主题×难度×画像 + 对抗样例
prompts/                   生成 v1/v2、评审 v0/v1/v2、rubric.md（人和模型共用）
levelgen/                  llm.py（客户端、缓存、记账）, checks.py（规则层）, generator.py, judge.py（v0/v1）, judge_v2.py, metrics.py
scripts/                   run_generate / run_judge / run_judge_v2 / calibrate_v2 / compute_agreement / analyze / build_html / run_all.sh
data/levels/*.json         72 关原始输出（含 raw 文本和用量）
eval/results.md            汇总；eval/agreement_{dev,holdout}.md 一致性；eval/badcases.md
labels/                    labeling_sheet.html（盲标页面）、human_labels.csv（待填）、provisional_reference.csv（临时标注）、label_set_mapping.json
viewer/index.html          72 关浏览器：规则检查、v1/v2-cal 分数、逻辑问题清单、升级原因
logs/usage.jsonl           每次调用的 tokens、时延、估算费用
```

## 已知局限
- 参照标注是临时标注，n=25，置信区间很宽；结论只作方向性参考。
- 每组每个规格只生成 1 次，没有估计生成侧的随机方差。
- 7B 和 72B 的生成温度都是 0.8，没有调参。
- 线上闭环、自检–重写、fine-tune 只在 DESIGN 里设计，没有实现。
