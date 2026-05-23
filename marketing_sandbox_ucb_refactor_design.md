# 营销沙盘 UCB 搜索改造设计

## 0. 当前实现状态

截至当前版本，这份改造设计已经落到代码里，文档同时承担：

- 当前搜索层设计说明。
- 后续迭代时的边界检查清单。

已落地模块如下：

| 模块 | 当前状态 |
|---|---|
| `search_models.py` | 已实现 `StrategyFamily`、`SearchBrief`、observation、state 和 search update 数据契约 |
| `ucb_search_controller.py` | 已实现 family cold start、确定性 UCB 选择和完整 observation update |
| `reward_mapper.py` | 已实现受控定性标签到内部 reward 的映射与风险 cap |
| `DecisionAgent` | 已支持 optional `SearchBrief`、`family_id` 和 `family_fit_note` |
| `FeedbackSynthesizer` | 已支持 `FeedbackSearchSignals` |
| `CriticAgent` | 已支持 `CriticSearchSignals` |
| `MarketingSandbox` | 已支持 old path 与显式 UCB path，并保存 search trace |

当前仍坚持一条边界：

> UCB reward 只是沙盘搜索效用，不是真实市场预测。

---

## 1. 这次改造要解决什么

当前沙盘已经能完成一个完整回合：

1. `DecisionAgent` 提出候选策略。
2. `ConsumerAgent[]` 对策略给定性反馈。
3. `FeedbackSynthesizer` 汇总整体感觉。
4. `CriticAgent` 挑漏洞。
5. `MarketingSandbox` 保存历史，并把上一轮证据喂回决策者。

这个流程有一个明显风险：

> 如果后续策略始终由 `DecisionAgent` 基于上一轮方案继续修，搜索会越来越像局部微调，容易过早围住一个看起来不错的方向。

UCB 改造要解决的是：

- 在“继续利用看起来不错的策略方向”和“探索还没充分试过的策略方向”之间做显式平衡。
- 不把每一个具体营销参数组合都平铺成一个 arm。
- 不要求消费者代理、总结者和批评者重新输出假精确评分。
- 保留当前 `ActionSpace`、数字边界和角色契约。

这份文档给出并记录：

- UCB 应该放在哪一层。
- 每个类要改什么。
- 哪些类不该被 UCB 污染。
- 定性反馈如何转成 UCB 可以更新的内部 reward。
- 推荐的实施顺序和测试顺序。

相关概念背景可以看 `strategy_family_literature_notes.md`。

---

## 2. 先给结论

### 2.1 UCB 放在沙盘外层搜索控制，不放进消费者模型

推荐结构是：

```text
UCBSearchController
  |
  | choose StrategyFamily slots for this round
  v
DecisionAgent
  |
  | generate concrete Strategy inside selected families
  v
MarketingSandbox
  |
  | test strategies with consumers, synthesis, critic
  v
RewardMapper
  |
  | convert structured qualitative search signals to internal reward
  v
UCBSearchController.update(...)
```

这样分层后：

- UCB 决定本轮优先试哪一类赢法。
- `DecisionAgent` 在被选中的赢法里生成具体策略。
- `ConsumerAgent` 仍然只像消费者一样反应。
- `FeedbackSynthesizer` 和 `CriticAgent` 仍然输出定性判断。
- 数字 reward 只在搜索控制层出现，并且由确定性的 `RewardMapper` 产生。

### 2.2 UCB 的 arm 不是一个具体策略，而是 `StrategyFamily`

第一版不建议把 arm 定义成：

- 某一个具体折扣。
- 某一个渠道组合。
- 某一条传播话术。
- 某一整套一次性生成的具体策略。

推荐把 arm 定义成：

> `StrategyFamily`，也就是一类有共同核心障碍、共同赢法逻辑和相近动作组合模式的策略方向。

例子：

| `family_id` | 大白话 |
|---|---|
| `clarity_positioning` | 先让顾客迅速看懂你是谁、解决什么 |
| `trust_risk_reduction` | 先压住不信、踩坑和后悔风险 |
| `trial_value_entry` | 先降低第一次尝试门槛 |
| `product_offer_fit` | 先把产品形态、组合和场景贴合起来 |
| `convenience_access` | 先减少发现、购买、履约和切换摩擦 |
| `retention_habit_defense` | 先建立复购触发和不容易被竞品带走的理由 |

这些家族是沙盘搜索概念，不是要冒充营销学里的固定标准术语。

### 2.3 reward 是内部搜索效用，不是真实市场结果

后续文档里如果出现 `reward`、`mean_reward`、`ucb_score`，它们都表示：

> 在当前沙盘人群、场景、定性反馈结构和 reward 映射规则下的内部搜索信号。

它们不是：

- 真实购买率。
- 真实复购率。
- 真实市场份额。
- 财务收益预测。
- 对真实市场最优策略的保证。

---

## 3. 不可破坏的设计约束

### 3.1 当前数字边界不能倒退

保持当前原则：

- `DecisionAgent` 可以提出有边界的数值型营销动作。
- `ConsumerAgent` 不输出购买概率、复购概率、市场份额和策略分数。
- `FeedbackSynthesizer` 不输出总分、维度分、排名分和市场预测。
- `CriticAgent` 不输出风险概率、预算损失和经营预测。

UCB 需要数字 reward，但这个数字必须由系统层根据结构化标签生成，不能让 LLM 直接打分。

### 3.2 `ActionSpace` 仍是硬边界

`StrategyFamily` 只描述策略赢法和搜索方向。

`ActionSpace` 仍负责硬约束：

- 哪些动作类别能用。
- 哪些产品 claims 能用。
- 数字参数有没有边界。
- 语义参数是不是在允许选项内。

一个被 UCB 选中的策略家族不能绕过 `ActionSpace`。

### 3.3 搜索控制器不能污染消费者判断

消费者不应该知道：

- 这个策略来自哪个策略家族。
- 这个策略是探索还是利用。
- 当前 UCB 觉得哪个 family 更有希望。
- reward 映射规则是什么。

否则消费者代理很容易被搜索过程提示带偏。

### 3.4 第一版先做可审计的确定性搜索

第一版 UCB 改造建议：

- family 注册顺序固定。
- UCB tie-break 固定。
- reward 映射规则固定。
- 每个策略测试完成后才允许 update。
- 被 `ActionSpace` 或输出契约拒绝的结果不能进入 UCB 状态。

这样更好测，也更容易解释。

---

## 4. 当前结构里 UCB 应该插在哪里

当前 `MarketingSandbox.run_round()` 的核心顺序是：

```text
build DecisionContext
  -> DecisionAgent proposal
  -> guard proposal
  -> test every strategy
  -> build RoundEvidence
  -> save RoundResult
```

改造后，开启 UCB 时顺序应变成：

```text
build DecisionContext
  -> UCBSearchController.select(...)
  -> SearchBrief
  -> DecisionAgent proposal constrained by SearchBrief
  -> guard proposal and validate family coverage
  -> test every strategy
  -> FeedbackSearchSignals + CriticSearchSignals
  -> RewardMapper.map(...)
  -> UCBSearchController.update(...)
  -> build RoundEvidence
  -> save RoundResult with search trace
```

不开启 UCB 时，原流程保留。

---

## 5. 核心搜索设计

## 5.1 `StrategyFamily` 的定义

一个 `StrategyFamily` 应回答四个问题：

1. 它要解决什么核心顾客障碍。
2. 它靠什么赢。
3. 它通常会带出怎样的一组动作模式。
4. 什么反馈说明这个方向本轮不稳。

建议第一版字段：

| 字段 | 作用 |
|---|---|
| `family_id` | 稳定机器标识，建议 ASCII，例如 `trust_risk_reduction` |
| `name` | 给人看的家族名 |
| `core_barrier` | 它主要解决的顾客障碍 |
| `win_mechanism` | 它希望靠什么改变顾客反应 |
| `generation_guidance` | 给 `DecisionAgent` 的家族内生成说明 |
| `expected_action_patterns` | 这一家族常见的动作组合提示 |
| `failure_signals` | 哪些反馈说明它可能走偏 |

第一版不建议让 `StrategyFamily` 直接替代 `ActionSpace` 做硬验证。

原因：

- 一个信任型策略也可能合理使用价格动作。
- 一个试用型策略也可能需要产品保障动作。
- 如果 family 直接硬禁动作类别，策略搜索会过早僵住。

后续如果确实需要 family 内更窄的动作边界，应做 `ActionSpace` 的受限视图或约束叠加，而不是把硬规则散落进 prompt。

## 5.2 family 级 UCB

每个 family 维护一个 arm state：

- `pull_count`
- `reward_sum`
- `mean_reward`
- `last_selected_round`
- 该 family 的历史 observations

第一版推荐 UCB 分数：

```text
ucb_score(family) =
    mean_reward(family)
    + exploration_coefficient * sqrt(log(total_pulls) / pull_count(family))
```

未被测试过的 family 先 cold start：

- 未测试 family 的优先级高于已测试 family。
- 如果一轮 slot 不够，就按 family 注册顺序取前几个未测试 family。
- 等每个 family 至少有 observation 后，再进入常规 UCB 比较。

第一版 tie-break：

- 分数相同按 family 注册顺序。
- 不引入随机数。

这样方便测试和复现。

## 5.3 一个 pull 算什么

第一版定义：

> 一个被选中的 family 生成一个具体 `Strategy`，该策略在完整消费者、场景、总结和批评流程跑完，并产生一个合法 reward observation，才算这个 family 的一次 pull。

不算 pull 的情况：

- `DecisionAgent` 没有按要求生成该 family 的候选策略。
- 策略被 `ActionSpace` 拒绝。
- 任一 LLM 输出被 `OutputContractGuard` 拒绝。
- `FeedbackSearchSignals` 或 `CriticSearchSignals` 缺失，导致 reward 不能映射。

这些情况应让该轮失败或明确报错，不应偷偷给 family 记一个零分。

## 5.4 每轮 family slot

第一版建议：

- `candidate_slots_per_round` 由搜索配置给出。
- 一个 slot 选一个 family。
- 一个 family 在同一轮默认最多占一个 slot。
- `DecisionAgent.max_candidates` 必须大于等于 slot 数。

这样能避免一个 family 在一轮里连出多个候选，把 observation 数量堆得比其他 family 快很多。

后续如果要允许同一 family 在一轮占多个 slot，需要明确：

- 是要加速 exploitation。
- 还是要在一个 family 内做局部变体探索。
- UCB update 是否对同轮多 observation 做折扣。

第一版先不做。

## 5.5 family selection 与策略生成分工

搜索控制器只负责：

- 选 family。
- 告诉 `DecisionAgent` 本轮每个 family 是 cold start、继续探索还是细化 promising direction。
- 保存 family state。

`DecisionAgent` 负责：

- 在 family 内提出具体策略。
- 选择具体 Product、Price、Place、Promotion、Retention 动作。
- 解释每个动作想解决什么阻力。

这能避免把 UCB 变成“用公式直接拼营销策略”。

## 5.6 `SearchBrief` 给决策者什么，不给什么

`SearchBrief` 是 UCB controller 和 `DecisionAgent` 之间的隔离层。

建议它至少包含：

| 字段 | 内容 |
|---|---|
| `selected_families` | 本轮被选中的 `StrategyFamily` 定义 |
| `generation_intents` | 每个 family 本轮是 cold start、变体探索还是细化 |
| `qualitative_memory` | 每个 family 已暴露出的强点、弱点和待验证问题 |
| `strategies_per_family` | 第一版固定为 `1` |

建议 generation intent 先用三类：

| intent | 大白话 |
|---|---|
| `cold_start` | 这个 family 还没好好试过，先出一个代表性方案 |
| `explore_variant` | 这个 family 有信息但还不够，出一个和旧方案有实质差异的变体 |
| `refine_promising` | 这个 family 已出现好信号，围绕已知阻力做有方向的细化 |

`qualitative_memory` 只应来自已经通过守门的历史证据，例如：

- 过去该 family 哪些消费者被打动。
- 过去该 family 哪些弱点反复出现。
- 过去该 family 哪些风险被 critic 点名。
- 上次还没验证的问题。

它不应包含：

- `ucb_score`
- `mean_reward`
- family 数字排名
- 其他 family 的内部 reward 细节

这样决策者能理解为什么要往某个 family 里出招，但不会直接迎合 bandit 数字。

## 5.7 observation 原子性

UCB update 必须以一个完整 observation 为原子单位。

一个 `SearchObservation` 至少要把这些东西绑在一起：

- `round_index`
- `family_id`
- `strategy_name`
- `FeedbackSearchSignals`
- `CriticSearchSignals`
- `RewardBreakdown`

只有当它们都存在且合法时，controller 才更新 arm state。

这样可以避免三类脏更新：

- strategy 没测完就 update。
- 只有正向 summary、没有 critic 风险就 update。
- summary 或 critic 被 output guard 拦住后仍 update。

---

## 6. 定性反馈如何变成 reward

## 6.1 为什么不能直接用现有长文本

当前反馈已经有很多文字证据：

- 消费者态度。
- 总结者的整体感觉。
- 批评者的漏洞和风险。

但直接从长文本里用字符串搜索做 reward 会很脆：

- 同一个意思会有很多表达。
- 大模型措辞轻微变化就会改变 reward。
- 很难解释 reward 是怎么来的。

所以第一版应给总结者和批评者补一层受控的非数字搜索信号。

## 6.2 `FeedbackSearchSignals`

`FeedbackSynthesizer` 仍输出原来的定性总结，同时新增一个结构化字段。

建议 `FeedbackSearchSignals` 字段如下：

| 字段 | 允许标签 | 含义 |
|---|---|---|
| `core_target_response` | `moved`, `mixed`, `unmoved` | 核心目标人群是否被推近 |
| `trial_momentum` | `pulled_closer`, `conditional`, `pushed_away` | 首次尝试感觉 |
| `strategy_clarity` | `clear`, `partial`, `confusing` | 定位和 offer 是否被看懂 |
| `repeat_logic` | `natural`, `conditional`, `weak` | 复购理由是否自然 |
| `competitor_resilience` | `holds`, `fragile`, `displaced` | 竞品压力下是否还站得住 |
| `evidence_consistency` | `consistent`, `mixed`, `thin` | 本轮消费者反馈是否足够一致和有根据 |
| `signal_note` | 任意定性文本 | 说明标签为什么这样落 |

这里的标签仍然是定性判断，不是得分。

## 6.3 `CriticSearchSignals`

`CriticAgent` 仍输出漏洞和质疑，同时新增一个结构化字段。

建议 `CriticSearchSignals` 字段如下：

| 字段 | 允许标签 | 含义 |
|---|---|---|
| `product_boundary_risk` | `contained`, `watch`, `serious` | 产品 claim 或真实能力边界风险 |
| `brand_risk` | `contained`, `watch`, `serious` | 品牌定位和长期资产风险 |
| `execution_risk` | `contained`, `watch`, `serious` | 落地复杂度和执行假设风险 |
| `self_deception_risk` | `contained`, `watch`, `serious` | 沙盘是否被表面反馈哄住 |
| `risk_note` | 任意定性文本 | 说明标签背后的漏洞 |

这里也不让批评者输出：

- 风险概率。
- 预算损失。
- 精确优先级分数。

## 6.4 `RewardMapper`

`RewardMapper` 是系统类，不是 LLM。

它读取：

- `FeedbackSearchSignals`
- `CriticSearchSignals`

然后生成：

- `reward`
- 正向部分拆解
- 风险扣减拆解
- 映射说明

### 6.4.1 第一版标签数值表

正向标签建议映射：

| 信号强度 | 数值 |
|---|---|
| 强正向标签 | `1.0` |
| 中间或条件性标签 | `0.5` |
| 弱或负向标签 | `0.0` |

具体落表：

| 字段 | `1.0` | `0.5` | `0.0` |
|---|---|---|---|
| `core_target_response` | `moved` | `mixed` | `unmoved` |
| `trial_momentum` | `pulled_closer` | `conditional` | `pushed_away` |
| `strategy_clarity` | `clear` | `partial` | `confusing` |
| `repeat_logic` | `natural` | `conditional` | `weak` |
| `competitor_resilience` | `holds` | `fragile` | `displaced` |
| `evidence_consistency` | `consistent` | `mixed` | `thin` |

风险标签建议映射：

| 标签 | 风险值 |
|---|---|
| `contained` | `0.0` |
| `watch` | `0.5` |
| `serious` | `1.0` |

### 6.4.2 第一版 reward 权重

正向 utility：

| 维度 | 权重 |
|---|---|
| `core_target_response` | `0.25` |
| `trial_momentum` | `0.20` |
| `strategy_clarity` | `0.15` |
| `repeat_logic` | `0.15` |
| `competitor_resilience` | `0.15` |
| `evidence_consistency` | `0.10` |

风险扣减：

| 维度 | 扣减权重 |
|---|---|
| `product_boundary_risk` | `0.14` |
| `brand_risk` | `0.08` |
| `execution_risk` | `0.05` |
| `self_deception_risk` | `0.08` |

第一版公式：

```text
positive_utility =
    weighted_sum(feedback_search_signals)

risk_penalty =
    weighted_sum(critic_search_signals)

raw_reward =
    positive_utility - risk_penalty

reward =
    clamp(raw_reward, 0.0, 1.0)
```

第一版额外 cap：

- `product_boundary_risk == serious` 时，`reward <= 0.35`
- `self_deception_risk == serious` 时，`reward <= 0.45`

这样做的原因：

- 一个策略即使表面上吸引人，只要真实产品边界明显危险，就不能在搜索里被当成高希望方向。
- 一个策略如果明显依赖沙盘自我陶醉，也不能靠正向反馈直接冲到顶部。

### 6.4.3 这个 reward 不应该喂回 LLM

`DecisionAgent` 应看到：

- 被选中的 family。
- 该 family 的定性记忆。
- 上一轮消费者、总结和批评证据。

它不应直接看到：

- `mean_reward`
- `ucb_score`
- 每个 family 的数字排序

让 LLM 看数字 reward 容易让它开始迎合映射器，而不是继续做营销推理。

---

## 7. 新增类设计

## 7.1 新增行为类

| 类 | 为什么不能让现有类承担 | 主要责任 |
|---|---|---|
| `UCBSearchController` | `MarketingSandbox` 是回合导演，不该同时承担搜索算法状态；`DecisionAgent` 是策略生成器，不该保存 bandit 统计 | 选择 family、维护 arm state、接受 observation、更新 UCB 状态 |
| `RewardMapper` | 反馈角色不能直接打数字 reward；控制器不应把标签映射规则和 UCB 状态更新揉在一起 | 把受控定性标签确定性映射成内部 reward |

## 7.2 新增搜索数据类

这些类建议放在搜索相关模块中，例如 `marketing_sandbox/search_models.py`。

| 类 | 主要字段 | 责任 |
|---|---|---|
| `StrategyFamily` | family 定义字段 | 表示一个高层策略 arm |
| `UCBSearchConfig` | slot 数、探索系数、cold start 配置 | 固定一轮搜索规则 |
| `SearchBrief` | 本轮被选 family、生成意图、family 定性记忆 | 给 `DecisionAgent` 的搜索指令 |
| `SearchSelection` | round、selected families、内部分数快照、选择原因 | 保存 controller 本轮选择 |
| `FamilyArmState` | family id、pull count、reward sum、last round | 保存 family 统计状态 |
| `RewardBreakdown` | reward、正向 utility、风险 penalty、component values | 保存 reward 映射审计 |
| `SearchObservation` | family、strategy、summary signals、critic signals、reward breakdown | 表示一次合法 pull 的证据 |
| `SearchUpdate` | family 更新前后摘要、observation | 记录一次 controller update |

## 7.3 新增输出信号数据类

建议和原输出类放在一起：

| 类 | 建议位置 | 原因 |
|---|---|---|
| `FeedbackSearchSignals` | `feedback_synthesizer.py` | 它是 `FeedbackSummary` 的一部分 |
| `CriticSearchSignals` | `critic_agent.py` | 它是 `CritiqueReport` 的一部分 |

---

## 8. 每一个现有类怎么改

## 8.1 `MarketingSandbox`

### 当前职责

- 组装回合。
- 调用决策、消费者、总结、批评。
- 保存历史。
- 构建 `SandboxResult`。

### 改动级别

> 大改。

### 要加的输入

构造函数新增可选参数：

- `search_controller: UCBSearchController | None = None`
- `reward_mapper: RewardMapper | None = None`

推荐关系：

- 如果 controller 自己持有 mapper，则 sandbox 只拿 `search_controller`。
- 如果 mapper 独立注入更容易测试，则 sandbox 同时拿 controller 和 mapper。

第一版更推荐：

> `MarketingSandbox` 显式持有 `search_controller` 和 `reward_mapper`。

这样 `test_strategy()` 跑完后的 observation 生成点更清楚。

### `run_round()` 要改的顺序

开启 UCB 时：

1. 构建 `DecisionContext`。
2. 让 `search_controller.select(round_index, history)` 返回 `SearchSelection`。
3. 从 `SearchSelection` 取 `SearchBrief`。
4. 调用 `DecisionAgent` 时传入 `SearchBrief`。
5. 校验 proposal 覆盖了本轮选中的 family。
6. 测试每个 strategy。
7. 从每个 `StrategyTestResult` 取 summary/critic signals。
8. 调用 `RewardMapper` 生成 `RewardBreakdown`。
9. 构建 `SearchObservation`。
10. 调用 `search_controller.update(observations)`。
11. 把 selection 和 update 记录进 `RoundResult`。

不开 UCB 时：

- 走当前逻辑。
- 不要求 strategy 带 family。
- 不要求 summary 和 critic 一定有 search signals。

### `test_strategy()` 要改什么

当前 `test_strategy()` 返回：

- strategy
- consumer feedbacks
- summary
- critique

改造后它仍然只负责测策略。

建议不要让它直接 update UCB。  
它可以返回足够的 evidence，让 `run_round()` 统一做 search observation 和 update。

### 新增校验

开启 UCB 时必须校验：

- `DecisionAgent.max_candidates` 能覆盖本轮 slot。
- proposal 中每个 candidate 都有合法 `family_id`。
- candidate family 只来自本轮 selected families。
- 每个 selected family 恰好有一个 candidate。
- reward 所需 search signals 不缺。

### 不该做的事

`MarketingSandbox` 不应该：

- 自己写 UCB 公式。
- 从自由文本里手搓 reward。
- 把数字 reward 塞回 `RoundEvidence` 给 LLM。

## 8.2 `DecisionAgent`

### 当前职责

- 在 `ActionSpace` 内生成候选策略。
- 读上一轮定性证据后修策略。

### 改动级别

> 中到大改。

### 方法签名建议

保留原方法，并加可选搜索 brief：

```python
propose_initial_strategies(context, search_brief=None)
revise_strategies(context, evidence, search_brief=None)
build_prompt(context, evidence=None, mode="initial", search_brief=None)
```

### prompt 要新增什么

当 `search_brief` 存在时，prompt 要写清：

- 本轮只能为选中的 family 生成候选。
- 每个 selected family 生成一个候选策略。
- family 是赢法方向，不是动作硬边界。
- 具体动作仍必须服从 `ActionSpace`。
- 不要输出 reward、UCB score、市场预测或策略分数。

### 输出 JSON 要改什么

candidate 新增：

- `family_id`
- `family_fit_note`

建议 candidate 结构变成：

```json
{
  "family_id": "trust_risk_reduction",
  "family_fit_note": "This candidate reduces perceived risk before asking for repeat behavior.",
  "name": "Trust-first trial",
  "hypothesis": "what this strategy is trying to change",
  "target_consumers": ["qualitative target segment"],
  "expected_tradeoffs": ["qualitative tradeoff"],
  "actions": []
}
```

### 数据类要改什么

`Strategy` 新增：

- `family_id: str = ""`
- `family_fit_note: str = ""`

为什么加在 `Strategy`：

- UCB update 要知道具体策略属于哪个 family。
- 这个关联必须随 strategy 进入 `StrategyTestResult` 和历史。
- 不能只靠 strategy 名字或 prompt 位置猜。

### 校验要新增什么

`DecisionAgent` 在有 `SearchBrief` 时应校验：

- `family_id` 非空。
- `family_id` 在本轮 selected family 集合内。
- family 覆盖完整。
- 同一 family 不重复占 slot。
- `family_fit_note` 是定性理由，不含结果预测。

### 不该改什么

`DecisionAgent` 不应该：

- 自己算 UCB。
- 决定哪一个 family 被 pull。
- 用 reward 数字重写策略假设。

## 8.3 `ConsumerAgent`

### 当前职责

- 站在 persona 和 scenario 里给消费者反馈。

### 改动级别

> 第一版不改核心接口。

### 要保持的行为

- `react_to_strategy(strategy, scenario, product_context)` 不变。
- 它仍只看到具体 strategy。
- 它的 prompt 不显示 `family_id`、UCB selection reason、reward。

### 可能被动受影响的地方

如果 `Strategy` 新增 `family_id` 和 `family_fit_note`：

- `ConsumerAgent._render_strategy()` 仍只渲染 name、hypothesis、actions、target consumers 和 tradeoffs。
- 不要把 family 内部搜索标签渲染给消费者。

### 为什么不改

探索和利用是搜索器的问题，不是消费者心理状态的一部分。

## 8.4 `FeedbackSynthesizer`

### 当前职责

- 把消费者反馈归纳成整体策略感觉。

### 改动级别

> 中改。

### 输出要新增什么

`FeedbackSummary` 新增：

- `search_signals: FeedbackSearchSignals | None = None`

迁移期建议先允许 `None`：

- 非 UCB 流程可继续跑。
- UCB 流程必须要求它存在。

### prompt 要新增什么

输出 schema 新增 `search_signals`。

同时强调：

- search signals 必须用允许标签。
- 标签是为了帮助搜索层组织定性证据。
- 不要输出 reward、score、probability、market forecast。

### 解析和校验要新增什么

- 校验每个 signal label 在允许枚举中。
- `signal_note` 必须是定性文本。
- 继续保留当前 forbidden summary terms 和 keys。

### 不该做什么

`FeedbackSynthesizer` 不应该：

- 直接输出 `reward`。
- 直接输出“这个 family 值得多试几次”的 UCB 决策。
- 代替批评者做风险扣分。

## 8.5 `CriticAgent`

### 当前职责

- 挑策略漏洞、边界风险、自欺风险和验证问题。

### 改动级别

> 中改。

### 输出要新增什么

`CritiqueReport` 新增：

- `search_risk_signals: CriticSearchSignals | None = None`

迁移期也建议先允许 `None`，但 UCB 流程必须要求它存在。

### prompt 要新增什么

输出 schema 新增 `search_risk_signals`。

同时强调：

- 只能落受控标签。
- 风险标签仍是定性风险判断。
- 不输出风险概率、预算损失、收入预测和精确分数。

### 解析和校验要新增什么

- 校验 risk signal label 枚举。
- `risk_note` 必须是定性文本。
- 保持现有 forbidden critic terms、keys 和 consumer voice 检查。

### 不该做什么

`CriticAgent` 不应该：

- 给 UCB 直接发 reward。
- 把批评报告写成数值经营预测。

## 8.6 `ActionSpace`

### 当前职责

- 营销动作硬边界。

### 改动级别

> UCB 第一版不改。

### 为什么不改

UCB 选择的是策略方向。  
具体策略动作仍然已经由 `ActionSpace` 检查：

- category。
- product claims。
- numeric limits。
- semantic options。

### 未来可能加什么

只有当 family 内确实需要更窄动作限制时，再考虑：

- `ActionSpace` 的 family-specific view。
- 或者单独的 constraint overlay。

第一版不要先做。

## 8.7 `OutputContractGuard`

### 当前职责

- 按角色守住输出契约。

### 改动级别

> 小改或只补测试。

### 为什么不是大改

新增 `FeedbackSearchSignals` 和 `CriticSearchSignals` 都是 nested dataclass 和字符串标签。

当前 guard 会递归扫描 dataclass 文本和禁止字段。  
只要 LLM 输出不出现分数、概率、预测字段，guard 的主职责仍成立。

### 建议补的检查和测试

- 确认 summary 的 categorical search signals 能放行。
- 确认 critic 的 categorical risk signals 能放行。
- 确认 summary 或 critic 输出 `reward`、`score`、`probability` 仍被拦。
- 确认 decision proposal 新增 `family_fit_note` 时仍会扫描 forbidden result terms。

### 不该做什么

`OutputContractGuard` 不负责：

- 算 reward。
- 算 UCB。
- 维护 family state。

## 8.8 `RoundEvidence`

### 当前职责

- 给 `DecisionAgent` 的跨轮定性证据。

### 改动级别

> 第一版不改结构，最多改构建内容。

### 建议

- 继续只放消费者、总结、批评的定性证据。
- 不把 reward 和 UCB score 写进去。
- 如果需要 family 定性记忆，放进 `SearchBrief.qualitative_memory`，不要把 `RoundEvidence` 变成搜索状态垃圾桶。

## 8.9 `DecisionContext`

### 当前职责

- 给决策者事实、目标、人群、场景和已测策略名。

### 改动级别

> 第一版不改。

### 原因

family selection 是本轮搜索指令，不是长期背景事实。  
它更适合单独通过 `SearchBrief` 传入。

## 8.10 `Strategy`

### 改动级别

> 小改，但很关键。

### 新增字段

- `family_id`
- `family_fit_note`

### 兼容策略

- 字段给默认空值，保持非 UCB 创建策略的老路径。
- UCB 模式下由 `DecisionAgent` 和 `MarketingSandbox` 强制非空。

## 8.11 `StrategyProposal`

### 改动级别

> 第一版不一定加字段。

### 原因

- candidate 自己已经带 family。
- proposal 仍然负责一批 candidate 和下一轮验证问题。

如果后面需要保存“本轮覆盖了哪个 SearchBrief”，更适合把 `SearchSelection` 存在 `RoundResult`，不要让 LLM proposal 持有内部搜索分数。

## 8.12 `FeedbackSummary`

### 改动级别

> 小改。

### 新增字段

- `search_signals`

其他原字段保留。

## 8.13 `CritiqueReport`

### 改动级别

> 小改。

### 新增字段

- `search_risk_signals`

其他原字段保留。

## 8.14 `StrategyTestResult`

### 当前职责

- 保存一套具体策略的测试结果。

### 改动级别

> 小到中改。

### 建议新增字段

- `search_observation: SearchObservation | None = None`

是否把 `reward_breakdown` 单独再放一份：

- 不建议重复。
- `RewardBreakdown` 已经在 `SearchObservation` 内。

非 UCB 模式该字段为空。

## 8.15 `RoundResult`

### 当前职责

- 保存一整轮候选策略测试。

### 改动级别

> 中改。

### 建议新增字段

- `search_selection: SearchSelection | None = None`
- `search_updates: tuple[SearchUpdate, ...] = ()`

这样一轮里能回答：

- 本轮为什么挑了这些 family。
- 每个 family 最终由哪套 strategy 形成 observation。
- controller 怎么更新了。

## 8.16 `SandboxResult`

### 当前职责

- 输出沙盘最终结果。

### 改动级别

> 小到中改。

### 建议新增字段

- `family_search_trace: tuple[SearchUpdate, ...] = ()`
- `search_notes: tuple[str, ...] = ()`

不建议直接把 `best_family_by_reward` 当营销结论字段。

更稳的输出是：

- `recommended_strategy_directions` 仍来自最终被保留的策略方向。
- 搜索 trace 作为内部审计，明确标注是 sandbox search signal。

## 8.17 `SandboxContext`

### 改动级别

> 第一版不改。

### 原因

搜索配置不属于市场事实。  
UCB config 应注入 controller，不应塞进产品与市场上下文。

## 8.18 `Persona`, `Scenario`, `ProductContext`

### 改动级别

> 不改。

### 原因

它们描述测试环境，不描述搜索算法。

## 8.19 其他消费者反馈数据类

下面这些类第一版不改：

- `BehaviorDiagnosis`
- `RepeatPurchaseReaction`
- `CompetitorReaction`
- `AdvocacyReaction`
- `ConsumerFeedback`

原因：

- 它们已经承载了 consumer evidence。
- UCB 需要的是总结层和批评层的受控搜索信号，不是让每个消费者开始打标签争夺 reward。

## 8.20 `__init__.py`

### 改动级别

> 小改。

### 要做什么

如果搜索类作为包公开 API，要补导出：

- `StrategyFamily`
- `UCBSearchConfig`
- `SearchBrief`
- `SearchSelection`
- `FamilyArmState`
- `RewardBreakdown`
- `SearchObservation`
- `SearchUpdate`
- `RewardMapper`
- `UCBSearchController`
- `FeedbackSearchSignals`
- `CriticSearchSignals`

---

## 9. 新的回合流转细图

```text
MarketingSandbox.run_round()
  |
  |-- build DecisionContext
  |
  |-- if UCB disabled:
  |     use old decision path
  |
  |-- if UCB enabled:
  |     UCBSearchController.select(round_index)
  |       -> SearchSelection
  |       -> SearchBrief
  |
  |-- DecisionAgent.propose or revise(..., search_brief)
  |       -> StrategyProposal with Strategy.family_id
  |
  |-- OutputContractGuard.check_decision_proposal(...)
  |-- MarketingSandbox.validate_selected_family_coverage(...)
  |
  |-- for each Strategy:
  |     for each Scenario and ConsumerAgent:
  |       ConsumerAgent.react_to_strategy(...)
  |       OutputContractGuard.check_consumer_feedback(...)
  |
  |     FeedbackSynthesizer.synthesize(...)
  |       -> FeedbackSummary + FeedbackSearchSignals
  |       OutputContractGuard.check_feedback_summary(...)
  |
  |     CriticAgent.critique(...)
  |       -> CritiqueReport + CriticSearchSignals
  |       OutputContractGuard.check_critique_report(...)
  |
  |     RewardMapper.map(summary.search_signals, critique.search_risk_signals)
  |       -> RewardBreakdown
  |
  |     SearchObservation(...)
  |
  |-- UCBSearchController.update(observations)
  |     -> SearchUpdate[]
  |
  |-- RoundEvidence stays qualitative
  |-- save RoundResult with search trace
```

---

## 10. 模块布局建议

第一版建议文件布局：

```text
marketing_sandbox/
  action_space.py
  consumer_agent.py
  critic_agent.py
  decision_agent.py
  feedback_synthesizer.py
  marketing_sandbox.py
  output_contract_guard.py
  search_models.py
  reward_mapper.py
  ucb_search_controller.py
```

理由：

- `search_models.py` 收纳搜索层数据类，避免把 `marketing_sandbox.py` 堆成大文件。
- `reward_mapper.py` 单独承载 reward policy，避免混进 LLM 输出类。
- `ucb_search_controller.py` 单独承载选择和 update 逻辑，方便测试。

---

## 11. 兼容性和迁移策略

## 11.1 先做 optional，不先翻旧流程

推荐第一轮实现保持：

- `search_controller` optional。
- `Strategy.family_id` 默认空。
- `FeedbackSummary.search_signals` 迁移期可为 `None`。
- `CritiqueReport.search_risk_signals` 迁移期可为 `None`。

但开启 UCB 时：

- family 必须存在。
- summary signals 必须存在。
- critic signals 必须存在。

这样可以边迁移边验证，不会把当前 90 个测试一下全炸开。

## 11.2 老路径不能悄悄变语义

不开启 UCB 时：

- `DecisionAgent` 仍可以像现在一样提出一批自由候选。
- `MarketingSandbox.run()` 仍能跑旧闭环。
- `SandboxResult` 仍是 qualitative 结果。

## 11.3 新路径必须显式

开启 UCB 的方式必须显式注入：

- family registry。
- `UCBSearchConfig`。
- `UCBSearchController`。
- `RewardMapper`。

不要让 `MarketingSandbox` 在看到某个字段后隐式猜“现在是不是要 bandit search”。

---

## 12. 测试设计要求

项目规则已经要求：

- 1 个正常样例。
- 3 个边界样例。
- 3 个特殊样例。
- 2 个反例样例。
- 1 个极限样例。

UCB 改造不能绕开这条规则。

## 12.1 新增类测试重点

### `StrategyFamily`

- 正常 family 定义。
- 空 family id。
- 重复或脏 family id 在 registry 层被拒。
- guidance 和 failure signals 缺失时边界策略。

### `RewardMapper`

- 正常信号映射出 reward breakdown。
- 中间标签映射。
- risk penalty 扣减。
- serious product boundary cap。
- serious self deception cap。
- 未知标签拒绝。
- 缺 summary or critic signals 拒绝。
- reward clamp。

### `UCBSearchController`

- cold start 优先未测试 family。
- 每轮 slot 数边界。
- UCB 分数在已测试 family 间选择。
- tie-break 稳定。
- update 增加 pull count 和 mean reward。
- 拒绝未知 family observation。
- 拒绝 selected family 缺 observation。
- 长历史下分数仍可计算。

## 12.2 现有类回归重点

### `DecisionAgent`

- 无 UCB 时旧 proposal 仍可解析。
- 有 `SearchBrief` 时 candidate 必须带 selected family。
- family 覆盖缺失时报错。
- family 重复占 slot 报错。
- `family_fit_note` 仍不能藏预测。

### `FeedbackSynthesizer`

- 原 qualitative summary 仍成立。
- search signals 只接受允许标签。
- search signals 不能带 reward/score/probability。

### `CriticAgent`

- 原 critique 仍成立。
- risk signals 只接受允许标签。
- risk signals 不能带 risk probability 或 forecast。

### `MarketingSandbox`

- 无 controller 时旧 round 跑通。
- 有 controller 时 select -> proposal -> observation -> update 跑通。
- rejected role output 不 update UCB。
- selected family 没有 candidate 不 update UCB。
- 多轮 history 能保存 search trace。

### `OutputContractGuard`

- 新 categorical signals 放行。
- 新 numeric judgement 字段仍拦住。

---

## 13. 推荐实施步骤

## Step 0: 固定设计和术语

先把下面几件事固定：

- family 是 UCB arm。
- reward 是 sandbox search utility。
- reward 由 `RewardMapper` 映射，不由 LLM 打分。
- first version one family one slot one strategy one observation。

这一步完成后再改代码。

## Step 1: 加搜索层数据类，不接入主流程

新增：

- `StrategyFamily`
- `UCBSearchConfig`
- `SearchBrief`
- `SearchSelection`
- `FamilyArmState`
- `RewardBreakdown`
- `SearchObservation`
- `SearchUpdate`

目标：

- 数据模型稳定。
- 能测试 family 定义、状态快照和 observation 基本合法性。

## Step 2: 让 `Strategy` 和 `DecisionAgent` 认识 family

改：

- `Strategy`
- `DecisionAgent`

具体动作：

1. `Strategy` 加 `family_id` 和 `family_fit_note` 默认值。
2. `DecisionAgent` 增加 optional `search_brief`。
3. prompt 在 search brief 存在时要求按 family 出候选。
4. parser 支持 family 字段。
5. validator 在 UCB family brief 存在时强制覆盖关系。

这一步先不接 UCB controller。  
测试重点是 family-aware proposal 本身。

## Step 3: 给总结和批评补非数字 search signals

改：

- `FeedbackSynthesizer`
- `FeedbackSummary`
- `CriticAgent`
- `CritiqueReport`
- `OutputContractGuard` 回归测试

具体动作：

1. 新增 `FeedbackSearchSignals`。
2. 新增 `CriticSearchSignals`。
3. 扩展两个 prompt schema。
4. 扩展 parser 和 enum validation。
5. 保证原 forbidden score/probability 检查不松。

这一步结束后，LLM 输出仍然没有 reward 数字。

## Step 4: 实现 `RewardMapper`

输入：

- summary search signals。
- critic risk signals。

输出：

- `RewardBreakdown`。

目标：

- 固定映射表。
- 固定权重。
- 固定 caps。
- 对缺失和未知标签 fail fast。

这一步要把 reward 逻辑测透，因为 UCB 全靠它。

## Step 5: 实现 `UCBSearchController`

具体动作：

1. family registry 初始化。
2. cold start 选择。
3. 常规 UCB 分数选择。
4. `SearchBrief` 构造。
5. observation update。
6. arm state snapshot。

这一步不先改 `MarketingSandbox`。  
可以用 fake observations 独立测试 controller。

## Step 6: 把 controller 接到 `MarketingSandbox`

改：

- `MarketingSandbox`
- `StrategyTestResult`
- `RoundResult`
- `SandboxResult`

具体动作：

1. 构造函数加入 optional search dependencies。
2. `run_round()` 分出 old path 与 UCB path。
3. UCB path 先 select 再让 DecisionAgent 出 family-aware proposal。
4. 测完 strategy 后 map reward。
5. 构造 observations 并 update controller。
6. RoundResult 保存 selection 和 updates。
7. SandboxResult 保存 search trace 和 search notes。

这一步必须保证：

- old path 回归测试过。
- UCB path 端到端测试过。

## Step 7: 补导出、文档和示例

改：

- `marketing_sandbox/__init__.py`
- 类设计文档或补充文档
- 最小示例或 fixture

示例至少要展示：

- 如何定义 family registry。
- 如何开启 UCB controller。
- 如何看一轮 search trace。

## Step 8: 全量验证

最低验证：

- `python -m unittest discover -s tests -v`
- `python -m compileall marketing_sandbox`

如果项目后续有可视化站点，还要在站点层确认：

- 显示的是 family 搜索轨迹。
- 不把内部 reward 文案包装成真实购买概率。

---

## 14. 推荐实现顺序为什么这样排

这个顺序刻意让风险从小到大：

1. 先定数据契约。
2. 再让决策者带 family。
3. 再补定性搜索信号。
4. 再固定 reward 映射。
5. 再实现 UCB 算法。
6. 最后改主编排。

如果一上来先把 UCB 塞进 `MarketingSandbox.run_round()`：

- 很快会发现策略没有稳定 family 归属。
- reward 没有合法来源。
- summary 和 critic 没有受控标签。
- 失败时不知道该 blame prompt、reward 还是 controller。

先把输入输出契约打稳，主流程改动会干净很多。

---

## 15. 第一版不做什么

为了避免第一版失控，先不做：

- 在具体参数空间上做连续 UCB。
- Thompson Sampling、Bayesian Optimization 和 UCB 混用。
- 同一轮一个 family 生成很多策略后再做 family 内 bandit。
- 让 reward 权重由 LLM 自己解释或自调。
- 让消费者反馈直接决定 numeric reward。
- 让 UCB 结果直接宣称真实市场最优。
- 用 family 把 `ActionSpace` 的硬边界重新写一遍。

---

## 16. 最终目标状态

UCB 改造完成后，系统应能回答两层问题。

第一层是搜索层问题：

- 哪些策略家族试过。
- 哪些家族因为反馈与风险组合值得继续探索。
- 哪些家族还没充分探索。
- 一轮选择是更多 exploitation 还是更多 exploration。

第二层是营销层问题：

- 具体哪套策略打动了谁。
- 哪些顾客阻力还没被压住。
- 复购和竞品压力下哪套策略更稳。
- 哪些风险需要真实市场验证。

这两层要同时存在，但不能混成一句：

> UCB reward 最高，所以真实消费者一定最会买。

更准确的说法是：

> 在当前沙盘定义的人群、场景和定性搜索信号下，这一策略家族积累了更值得继续投入下一轮生成和验证的证据。
