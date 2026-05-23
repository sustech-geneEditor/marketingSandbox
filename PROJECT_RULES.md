# AI 营销沙盘项目规则

## 1. 必读规则

任何 agent 在开始为本项目：

- 写代码。
- 修改代码。
- 设计类。
- 补测试。
- 重构类边界。
- 修复类行为。

之前，**必须先阅读本文件**。

如果任务涉及沙盘角色类、沙盘入口类、动作空间、输出守门逻辑或搜索层，还必须同时阅读：

- `marketing_sandbox_class_design.md`
- `marketing_sandbox_full_summary.md`
- `marketing_sandbox_ucb_refactor_design.md`

如果任务涉及消费者行为学先验、消费者 prompt 研究依据或行为学诊断输出，还必须同时阅读：

- `consumer_behavior_literature_notes.md`

如果任务涉及动作空间、营销动作类别、marketing mix 或动作参数选项，还必须同时阅读：

- `action_space_literature_notes.md`

本文件是项目级约束。  
后续实现不能因为“先跑起来”而跳过这里的测试要求。

### 1.1 论文结论记录规则

只要项目在设计、代码、prompt、文档或报告中使用了某篇论文的：

- 研究结论。
- 理论启发。
- 概念定义。
- 分类方法。
- 算法思路。
- 使用边界。

就必须同步写入对应的论文备忘 `md` 文件。

记录时至少要写清：

- 论文基本信息。
- 这篇论文说了什么。
- 本项目借用了它的哪一部分。
- 它落到哪个类、prompt、搜索逻辑或设计判断上。
- 哪些话不能因为引用了它就说过头。

如果当前还没有对应论文备忘文件：

- 先判断它应归入现有论文备忘，还是需要新建一份。
- 不允许只把论文结论散写进实现或设计文档，而不留下论文备忘记录。

---

## 2. 当前项目的类设计基线

当前类设计以 `marketing_sandbox_class_design.md` 为准。  
家族级 UCB 搜索的边界、迁移路径和术语以 `marketing_sandbox_ucb_refactor_design.md` 为补充说明。

核心类包括：

- `MarketingSandbox`
- `DecisionAgent`
- `ConsumerAgent`
- `FeedbackSynthesizer`
- `CriticAgent`
- `ActionSpace`
- `OutputContractGuard`
- `UCBSearchController`
- `RewardMapper`

主要数据类包括：

- `SandboxContext`
- `Persona`
- `Scenario`
- `Strategy`
- `StrategyProposal`
- `ConsumerFeedback`
- `FeedbackSearchSignals`
- `FeedbackSummary`
- `CriticSearchSignals`
- `CritiqueReport`
- `StrategyTestResult`
- `RoundResult`
- `SandboxResult`
- `StrategyFamily`
- `UCBSearchConfig`
- `SearchBrief`
- `SearchSelection`
- `RewardBreakdown`
- `SearchObservation`
- `FamilyArmState`
- `SearchUpdate`

当前实现有两条合法运行路径：

- 不注入 `UCBSearchController` 时，沙盘走原有定性回合流程。
- 显式注入 `UCBSearchController` 和 `RewardMapper` 时，沙盘按 `StrategyFamily` 做 family-level UCB 搜索。

UCB 路径中的 `reward`、`mean_reward` 和 `ucb_score` 只属于系统搜索层。  
它们不是购买概率、复购率、市场份额或财务预测，也不能被写回消费者 prompt。

`ConsumerAgent` 的行为学先验是稳定提示基线。  
如果要改这些先验或研究依据，先同步更新 `consumer_behavior_literature_notes.md`、`marketing_sandbox_full_summary.md` 和 `marketing_sandbox_class_design.md`，再改 prompt 与测试。

如果新增类：

- 必须先说明新增类为什么不能由现有类承担。
- 必须说明它的输入、输出、边界和责任。
- 必须遵守本文件中的测试配额。

---

## 3. 每个类完成时的测试配额

每一个类在被认为“完成”之前，必须有以下测试样例：

| 测试类型 | 数量 |
|---|---|
| 正常样例 | `1` |
| 边界样例 | `3` |
| 特殊样例 | `3` |
| 反例样例 | `2` |
| 极限样例 | `1` |

合计：

> 每个类至少要有 `10` 个有区分度的测试样例。

这些样例不能只是改几个字段名的重复测试。  
它们必须覆盖不同风险。

---

## 4. 各类测试样例是什么意思

## 4.1 正常样例

正常样例验证：

> 在最常见、最合理、输入完整的情况下，这个类能否完成自己的主要职责。

例子：

- `DecisionAgent` 收到完整产品上下文、动作空间和上一轮反馈后，能提出合规策略。
- `ConsumerAgent` 收到完整 persona、策略和场景后，能给出一份完整反馈。
- `MarketingSandbox` 能跑通一轮完整沙盘。

---

## 4.2 边界样例

边界样例验证：

> 输入仍在允许范围内，但已经靠近类的边界时，行为是否仍然正确。

每个类至少要有 `3` 个不同边界方向。

边界方向可以包括：

- 最小合法输入。
- 最大合理长度。
- 空列表但语义允许。
- 只有一个消费者。
- 只有一个策略。
- 只有一个场景。
- 动作空间只开放一个动作类。
- 可选字段缺失但不应崩。

边界样例不能拿非法输入冒充。  
非法输入应归入反例样例。

---

## 4.3 特殊样例

特殊样例验证：

> 业务上会发生、但不属于最普通路径的情况，类是否仍然能做出符合沙盘规则的处理。

每个类至少要有 `3` 个有业务意义的特殊情况。

特殊情况可以包括：

- 核心 persona 与非核心 persona 反馈明显冲突。
- 决策者给出多种风格差异很大的策略。
- 场景卡出现竞品压力或信任压力。
- Product 动作涉及试用装、补充装、礼盒、保障承诺等复杂组合。
- 反馈里出现明显犹豫、矛盾或条件性态度。
- 批评者发现策略短期拉新强、长期品牌感弱。

特殊样例要体现项目业务，不要只体现语言形式变化。

---

## 4.4 反例样例

反例样例验证：

> 当输入、输出或行为违反类边界时，系统能否拒绝、修正、标记或安全失败。

每个类至少要有 `2` 个反例。

反例可以包括：

- `DecisionAgent` 输出超出动作空间的策略。
- `DecisionAgent` 凭空发明产品没有的功能或认证。
- `ConsumerAgent` 输出购买概率或市场占比预测。
- `FeedbackSynthesizer` 输出总分、维度分或假精确排名。
- `CriticAgent` 凭空输出风险概率和经营预测。
- `MarketingSandbox` 缺少必要 agent。
- `MarketingSandbox` 的 UCB 路径缺少 search signals、家族覆盖不完整或 reward mapper。
- `ActionSpace` 收到无法识别的动作类。
- `OutputContractGuard` 遇到越界输出。
- `UCBSearchController` 收到重复 family observation、未知 family 或未覆盖本轮 selection 的 update。

反例测试的目标不是让系统崩溃得更快，而是验证：

- 报错是否清楚。
- 拒绝是否正确。
- 重写或降级路径是否正确。
- 错误不会污染后续回合记录。

---

## 4.5 极限样例

极限样例验证：

> 在当前类被设计要承受的最重、最复杂或最容易失控的合法场景下，它是否仍然守住职责和边界。

每个类至少要有 `1` 个极限样例。

极限样例可以包括：

- 一轮同时有大量消费者反馈需要汇总。
- 决策者同时面对复杂 Product、价格、渠道、传播和留存动作。
- 一套策略在多个压力场景下收到冲突反馈。
- 沙盘历史很长，但决策者仍要基于压缩后的有效反馈出下一轮策略。
- 输出中混杂数值动作、定性反馈和越界数字判断，守门逻辑仍能区分。

极限样例仍然应该是**合法范围内**的场景。  
如果场景本身非法，它应归入反例。

---

## 5. LLM 输出测试的额外规则

本项目有 LLM 角色类，因此测试不能只看“返回了字符串”。

必须验证输出是否符合角色契约。

## 5.1 `DecisionAgent`

测试必须验证：

- 它能在动作空间内提出策略。
- 它可以输出数值型营销动作，例如价格、折扣、券或预算分配。
- 它不能把数值动作写成凭空市场结果预测。
- 它不能偷偷修改 persona、scenario、产品事实和评分边界。
- 它不能发明产品没有的能力、认证和规格。
- 当存在 `SearchBrief` 时，它必须对被选中的 family 各出一个候选策略，并保留 `family_id` 与 `family_fit_note`。
- 它不能把 UCB score、内部 reward 或 family 搜索统计写进策略输出。

## 5.2 `ConsumerAgent`

测试必须验证：

- 它按 persona 和场景反馈。
- 它有第一印象、购买阻力、复购感觉和竞品冲击反馈。
- 它不输出购买概率。
- 它不输出复购概率。
- 它不输出市场占比或策略精确分数。
- 它保留行为学底层设定，但不看到 `family_id`、UCB selection reason、内部 reward 或搜索分数。

## 5.3 `FeedbackSynthesizer`

测试必须验证：

- 它能把多位消费者的反馈写成整体感觉。
- 它能说明谁被打动、谁没被打动。
- 它能指出策略强点、虚点和下一轮方向。
- 它不输出总分。
- 它不输出维度分。
- 它不输出假精确排名和市场结果预测。
- 它如果返回 `search_signals`，只能使用受控定性标签和文字说明，不能直接给 reward 数字。

## 5.4 `CriticAgent`

测试必须验证：

- 它能找出不现实策略、产品越界、品牌风险和执行风险。
- 它能指出需要下一轮验证的问题。
- 它不把批评写成消费者反馈。
- 它不凭空输出风险概率、预算损失和经营预测。
- 它如果返回 `search_risk_signals`，只能使用受控风险标签和文字说明，不能直接更新 UCB。

## 5.5 `OutputContractGuard`

测试必须验证：

- 它能放行合规的决策者数值动作。
- 它能拦住消费者概率输出。
- 它能拦住反馈总结者的假精确评分。
- 它能拦住批评者凭空经营预测。
- 它能区分“输入事实中的数字”和“越界生成的数字判断”。

## 5.6 搜索层

`UCBSearchController` 与 `RewardMapper` 的测试必须验证：

- cold start 和 family 注册顺序下的 tie-break 是确定的。
- tested family 的 UCB 选择只基于完整 observation。
- selection 与 observation 必须精确覆盖同一批 family。
- `RewardMapper` 只接受 `FeedbackSearchSignals` 与 `CriticSearchSignals` 的允许标签。
- serious product-boundary risk 和 serious self-deception risk 会触发内部 reward cap。
- 内部 reward 和 UCB score 不会被伪装成市场结果输出。

---

## 6. 测试设计要求

每个类的测试设计必须满足：

- 测试名称能看出场景意图。
- 测试断言验证行为，不只验证对象存在。
- 测试要覆盖职责边界。
- 测试数据尽量小，但要有业务意义。
- 测试中出现的数值动作要能追溯到动作空间、配置或输入事实。
- 不要把一个大而混乱的端到端测试当成多个类测试的替代品。

如果一个类依赖外部模型：

- 单元测试应优先验证 prompt 输入契约、输出解析、输出守门和失败处理。
- 不应把真实在线模型响应作为唯一测试依据。
- 可以使用固定样例响应、mock 或 fixture 来覆盖输出契约。

---

## 7. 类完成定义

一个类只有同时满足下面条件，才可以说“完成”：

1. 职责清楚。
2. 输入输出清楚。
3. 边界和失败路径清楚。
4. 实现符合 `marketing_sandbox_class_design.md`。
5. 已有：
   - `1` 个正常样例测试。
   - `3` 个边界样例测试。
   - `3` 个特殊样例测试。
   - `2` 个反例样例测试。
   - `1` 个极限样例测试。
6. 测试已实际运行，或明确记录为什么当前不能运行。

---

## 8. Agent 开工检查清单

任何 agent 开始实现前，必须先确认：

- [ ] 我已经读过 `PROJECT_RULES.md`。
- [ ] 我已经读过 `marketing_sandbox_class_design.md`。
- [ ] 如果任务碰到搜索层，我已经读过 `marketing_sandbox_ucb_refactor_design.md`。
- [ ] 我知道当前任务影响哪个类。
- [ ] 我知道这个类的职责边界。
- [ ] 我知道这个类需要的 `10` 个测试样例配额。
- [ ] 我知道哪些数字允许，哪些数字禁止。
- [ ] 我不会为了让测试通过而削弱输出契约。

---

## 9. 简短结论

本项目的代码不是“写完类就算完”。

> 每一个类都必须带着一套有层次的测试完成：正常、边界、特殊、反例、极限，一个都不能少。
