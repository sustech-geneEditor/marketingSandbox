# AI 营销沙盘类设计

## 1. 设计目标

这份文档描述营销沙盘当前实现需要的类，以及每个类在沙盘中的职责、输入、输出和互动方式。

沙盘的核心想法是：

> 搜索层决定本轮要探索哪类策略赢法，决策者在动作空间里出营销策略，消费者代理给真实感反馈，反馈总结者归纳整体感觉，批评者挑出漏洞，沙盘入口控制他们一轮一轮迭代。

当前版本不追求把消费者判断和整体评议压成精确数字，而是先把：

- 策略是怎么出的。
- 消费者为什么买或不买。
- 一批反馈整体透露出什么感觉。
- 哪些风险会让策略看起来好但实际不稳。

讲清楚。

---

## 2. 数字边界：策略动作可数字化，消费者判断去数字化

### 2.1 总原则

当前版本遵守下面的规则：

> 决策者可以输出数值型营销动作；消费者反馈和整体反馈总结不输出假精确数字判断。

这样做是因为：

- 价格、折扣、券、预算分配等本来就是决策者要动的营销按钮。
- 消费者代理并不是真实统计样本，不适合报购买概率和复购概率。
- 反馈总结者应该写出策略感觉和关键问题，不适合凭感觉打精确分。
- 当前版本既要保留可执行的营销动作，也要避免把合成反馈伪装成统计预测。

### 2.2 允许保留数字的地方

`DecisionAgent` 可以在动作空间允许的边界内输出数值型营销动作，例如：

- 产品标价或候选价格。
- 折扣率。
- 满减门槛和优惠额。
- 券面额。
- 首购和回购激励的具体方案。
- 渠道预算分配方案。
- 投放或促销动作的数值参数。

这些数字必须满足两个条件：

- 它们是营销动作，不是消费者结果预测。
- 它们没有突破 `ActionSpace`、产品事实、预算边界、法规边界和品牌底线。

数字还可以来自：

- 人工配置。
- 市场事实。
- 产品规格。
- 竞品信息。
- 预算和 P&L。
- 沙盘运行配置。

### 2.3 需要去数字化的地方

#### 消费者反馈去数字化

`ConsumerAgent` 不输出：

- 购买概率。
- 复购概率。
- 真实市场占比预测。
- 自己对策略的精确评分。

它应说清楚：

- 为什么想买、观望或不买。
- 哪个卖点打动了自己。
- 哪个风险让自己犹豫。
- 什么竞品动作容易把自己带走。

#### 整体反馈总结去数字化

`FeedbackSynthesizer` 不输出：

- 总分。
- 维度分。
- 精确排名分。
- 转化率、复购率和市场结果预测。

它应写出：

- 这套策略整体像什么打法。
- 谁被打动，谁没被打动。
- 它赢在哪里，虚在哪里。
- 下一轮更值得改什么。

### 2.4 其他 LLM 类的数字边界

`CriticAgent` 可以引用已经给定的数值事实来指出风险，但不凭空报风险概率、预算损失和经营预测。

所有 LLM 类都不能凭空生成：

- 产品没有的规格和性能数值。
- 未提供的认证数据。
- 未提供的销量、利润和市场份额预测。

---

## 3. 总体类结构

## 3.1 参与沙盘的 LLM 角色类

| 类 | 大白话角色 | 是否由 LLM 驱动 |
|---|---|---|
| `DecisionAgent` | 出营销招的决策者 | 是 |
| `ConsumerAgent` | 代表某类顾客的消费者 | 是 |
| `FeedbackSynthesizer` | 把一堆顾客反馈总结成整体感觉的人 | 是 |
| `CriticAgent` | 专门挑漏洞的反方 | 是 |

## 3.2 控制沙盘、搜索和约束输出的系统类

| 类 | 大白话角色 | 是否由 LLM 驱动 |
|---|---|---|
| `MarketingSandbox` | 沙盘入口和回合导演 | 否 |
| `ActionSpace` | 决策者能动哪些营销按钮的边界 | 否 |
| `OutputContractGuard` | 按角色检查数字边界和输出契约的守门员 | 否 |
| `UCBSearchController` | 在策略家族之间平衡探索与利用的搜索控制器 | 否 |
| `RewardMapper` | 把受控定性标签映射成内部搜索 reward 的映射器 | 否 |

## 3.3 沙盘结构图

```text
MarketingSandbox
  |
  |-- ActionSpace
  |-- OutputContractGuard
  |-- UCBSearchController?  -- StrategyFamily registry / SearchBrief
  |-- RewardMapper?         -- internal search reward only
  |
  |-- DecisionAgent
  |-- ConsumerAgent[]
  |-- FeedbackSynthesizer
  |-- CriticAgent
```

## 3.4 Web 桥接层类

网站配置和本地沙盘入口之间现在单独放一层 Web 桥接，不把浏览器字段、
session 密钥和连接测试逻辑写进 `MarketingSandbox`。

| 类 | 职责 | 为什么不放进核心类 |
|---|---|---|
| `WebRunConfig` | 接住网站的非敏感运行配置 | 它描述 Web 表单，不是沙盘领域事实本身 |
| `WebRunSession` | 保存当前网站会话的安全配置边界和临时凭据状态 | session 密钥和公开快照边界不应污染沙盘历史 |
| `WebSandboxRunner` | 把 live Web 会话装配成已有 `MarketingSandbox`、agent、scenario 和可选 UCB 搜索层 | 核心沙盘应只主持回合，不负责翻译 UI preset、模型路由和 Web catalog |
| `SandboxWebEventMapper` | 把 `RoundResult` / `SandboxResult` 转成网站可播放事件 | 前端需要 actor id、说话泡泡、面板字段和事件顺序，这些不属于核心沙盘领域对象 |
| `WebRunEventStream` | 把 live runner 的真实运行按事件顺序吐给网站 | 它是 Web 路由和核心沙盘之间的流式桥，不让前端直接碰 `MarketingSandbox` |
| `WebRunLifecycleManager` | 管理 live run 的停止信号、安全边界存档、恢复和断联自动存档 | stop/archive 是网站运行生命周期，不是核心营销推理职责 |
| `WebSandboxApi` | 把 `/api/sandbox/*` 请求路由到事件流、停止、存档、恢复和连接测试 | HTTP 路由是网站接线职责，不应塞进核心沙盘或具体 agent |

`WebSandboxRunner` 的当前边界是：

- 输入是已经验证过的 live `WebRunSession` 和一个角色 backend 工厂。
- 输出是现有 `MarketingSandbox` 对象，或者直接运行完整 round 后的 `SandboxResult`。
- 它负责把网站的 persona id、scenario id、family id 和动作大类翻译成 Python 对象。
- 它不负责停止请求、存档和前端渲染；真实事件流由 `WebRunEventStream` 承接。
- 它不会把 API Key 塞进公开配置、prompt 或沙盘结果；真实模型适配器仍需继续遵守会话密钥边界。

`SandboxWebEventMapper` 的当前边界是：

- 输入是已经完成的 `RoundResult` 或 `SandboxResult`。
- 输出是前端 `run_started`、`round_started`、`family_selected`、`strategy_proposed`、`consumer_feedback_ready`、`feedback_summary_ready`、`critique_ready`、`search_updated`、`round_completed`、`run_completed` 事件。
- 它会携带消费者反馈、总结、批评、策略动作、family selection、search update 和内部搜索指标。
- 内部 `reward`、`meanReward` 和 `ucbScore` 只作为搜索层审计字段展示，并带有“不是购买率、复购率或市场预测”的边界说明。
- 它会递归清理传入的敏感值，避免 session key 进入前端事件 payload。

`WebRunEventStream` 的当前边界是：

- 输入是 live `WebRunSession`、`WebSandboxRunner` 和可选 `round_count`。
- 如果 runner 能 `build_sandbox`，它会先发 `run_started`，再按完成的 round 追加事件，最后发 `run_completed`。
- 如果 runner 只有 `run`，它会退回到“完整结果转事件”的兼容路径。
- 它可以输出事件对象、JSONL chunk 或 SSE chunk，方便后续 Web 框架直接挂路由。
- 它可以接入 `WebRunLifecycleManager`，在完整 round 之间检查 stop 请求；一旦停止，就不再派发后续搜索步骤。
- 它的错误响应会脱敏 session key；停止、存档和 API 断联自动存档由 lifecycle manager 负责。

`WebRunLifecycleManager` 的当前边界是：

- 它区分 `pause` 和 `stop`：`pause` 只暂停浏览器回放，`stop` 才会要求本地 live search 停在安全边界。
- 它记录当前 run 的非敏感 session 快照、事件日志、stop 状态和 safe boundary。
- 它定义存档 schema `marketing-sandbox-archive/v1`。
- 它只把最近 `round_completed` 或 `run_completed` 之前的事件写进存档；半轮事件会被丢弃，不能污染后续 UCB 状态。
- 它支持保存、列出、读取、恢复存档，并能返回“从安全边界继续”的计划。
- 它支持 API 断联超时自动存档，状态标记为 `auto_archived`，并保留错误说明。
- 它会递归删除 `apiKey`、`api_key`、`authorization` 字段，并替换 session secret 值。

`WebSandboxApi` 的当前边界是：

- 输入是本地网站发来的 HTTP-like method、path、headers 和 JSON body。
- 输出是 `WebApiResponse`，可以是普通 JSON，也可以是 SSE / NDJSON byte chunk。
- 它已经挂出 `live-events`、`provider-check`、`runs/stop`、`archives`、`archives/{id}`、`archives/{id}/resume` 和断联自动存档路由。
- 它不直接写营销逻辑，只负责把请求交给 `WebRunSession`、`WebRunEventStream` 和 `WebRunLifecycleManager`。
- 它统一加 CORS 头，并限制请求体大小，避免前端和本地后端接线时出现隐式失败。

标准库 `web_server` 的当前边界是：

- 用 `python -m marketing_sandbox.web_server` 启动本地 HTTP 服务，默认监听 `127.0.0.1:8765`。
- 它只把真实 HTTP 请求翻译给 `WebSandboxApi`，不改沙盘推理、事件契约和存档规则。
- 前端开发环境通过 Vite proxy 把 `/api/sandbox/*` 转到这个本地后端。

---

## 4. `MarketingSandbox`

## 4.1 它是什么

`MarketingSandbox` 是整个系统的入口。

它不扮演营销专家，也不扮演消费者。  
它负责让所有角色按顺序互动，并保存每一轮发生了什么。

大白话：

> 它是沙盘的主持人和导演。

## 4.2 它负责什么

- 加载产品、品牌、市场和竞品上下文。
- 加载消费者人群卡。
- 加载场景卡。
- 创建并持有各类 Agent。
- 把动作集交给决策者。
- 把策略发给消费者群。
- 收集所有消费者反馈。
- 把反馈交给反馈总结者。
- 把策略和反馈交给批评者。
- 保存一轮一轮的沙盘历史。
- 判断沙盘是否继续跑下一轮。
- 输出最后的策略讨论结果。

## 4.3 它拿什么输入

- `SandboxContext`
- `ActionSpace`
- `DecisionAgent`
- `ConsumerAgent` 列表
- `FeedbackSynthesizer`
- `CriticAgent`
- `Scenario` 列表
- 可选 `UCBSearchController`
- 可选 `RewardMapper`
- 沙盘运行配置

## 4.4 它输出什么

它输出 `SandboxResult`。

这个结果应包含：

- 哪些策略被试过。
- 各轮消费者反馈摘要。
- 各轮整体反馈总结。
- 各轮批评意见。
- 当前最值得继续推进的策略方向。
- 当前应该淘汰或暂停的策略方向。
- 仍然需要真实市场证据验证的问题。
- 开启 UCB 时保存每轮 family selection、search updates 和 family search trace。

## 4.5 它的关键行为

概念上它需要这些行为：

- 启动沙盘。
- 跑一轮。
- 测试一个候选策略。
- 保存一轮历史。
- 把上一轮结果喂回决策者。
- 汇总最终结果。
- 如果显式开启 UCB，先 select `StrategyFamily`，再让决策者按 `SearchBrief` 出候选，并在完整 observation 后更新搜索状态。

## 4.6 它如何保证数字边界

`MarketingSandbox` 在每个 LLM 输出回来后，都把结果先交给 `OutputContractGuard`。

守门规则按角色区分：

- `DecisionAgent` 可以输出动作里的数值，但这些数值要落在 `ActionSpace` 和已有约束里。
- `ConsumerAgent` 不能把自己的消费态度写成概率、分数或市场预测。
- `FeedbackSynthesizer` 不能把整体感觉写成打分表。
- `CriticAgent` 不能凭空写风险概率和经营预测。

不符合对应输出契约时，沙盘要求该 Agent 重写。

---

## 5. `DecisionAgent`

## 5.1 它是什么

`DecisionAgent` 是沙盘里的营销决策者。

它负责：

- 提出候选营销策略。
- 根据上一轮反馈改策略。
- 决定下一轮最值得验证什么。

大白话：

> 它负责出招。

## 5.2 它能动什么

它只能在 `ActionSpace` 允许的范围里动营销动作。

当前动作集包括：

- 定位。
- Product。
- 价格动作。
- 渠道。
- 传播。
- 留存。

### 定位

它可以选择主打：

- 功能价值。
- 性价比。
- 品质信任。
- 情绪价值。
- 社交价值。
- 场景便利。
- 目标使用场景、比较参照和希望形成的品牌联想。
- 用什么证据角度支撑这个定位，而不是只写空口号。

### Product

它可以在产品真实边界内调整：

- 主推哪个核心价值。
- 主推哪个真实功能卖点。
- 主推哪个版本或产品形态。
- 包装强调什么感觉。
- 是否使用试用装、新手包、套装、补充装、礼盒等组合。
- 是否增加上手引导、使用支持、售后保障、退换承诺等降低风险的配套。

### 价格动作

它可以提出：

- 产品标价。
- 折扣率。
- 满减方案。
- 券面额。
- 套餐优惠。
- 首购和回购激励的具体参数。
- 价格架构、价格政策和价值解释方式。
- 渠道或传播预算分配方案。

这些数值动作要能说明：

- 为什么这样设。
- 它想降低什么阻力。
- 它会不会带来毛利、预算、品牌和执行风险。
- 它是否符合已给出的动作边界与产品事实。

### 渠道

它可以决定：

- 顾客先在哪个发现触点看到。
- 在哪里比较、建立信任和完成转化。
- 更偏线上直达、平台承接、社交种草后转化、线下体验还是特定场景触达。
- 履约、可得性和购买后服务触点怎么接。

### 传播

它可以决定：

- 主讲哪个卖点。
- 用什么内容风格。
- 更偏体验分享、测评、图文、短视频或直播。
- 是否强调口碑、案例、评论、KOL/KOC 或朋友推荐感。
- 用什么证据格式和激活动作把定位讲清。

### 留存

它可以决定：

- 是否加强复购提醒。
- 是否做 onboarding、补货触发或使用陪伴。
- 是否做会员关系。
- 是否用老客推荐。
- 是否用回购优惠。
- 是否强化售后关怀、服务恢复和关系维护。

## 5.3 它不能动什么

它不能修改：

- Persona。
- Scenario。
- 产品真实能力。
- 市场事实。
- 品牌底线。
- 行为学底层设定。
- 反馈总结者和批评者的输出规则。

## 5.4 它拿什么输入

首次出招时，它需要：

- 产品事实。
- 品牌背景。
- 市场环境。
- 主要竞品。
- 营销目标。
- 动作空间。
- 当前要测试的人群和场景。

后续迭代时，它还需要：

- 上一轮策略。
- 消费者反馈摘要。
- 反馈总结者的总结。
- 批评者的质疑。
- 已经试过的方向。
- 可选 `SearchBrief`，说明本轮被搜索控制器选中的策略家族。

## 5.5 它输出什么

它输出 `StrategyProposal`。

建议包含：

- 候选策略方向。
- 每个候选策略动了哪些营销按钮。
- 每个候选策略想解决什么问题。
- 它预期会打动哪类消费者。
- 它预期会暴露什么风险。
- 下一轮最值得验证的核心问题。
- 当存在 `SearchBrief` 时，每个候选策略要写明 `family_id` 和 `family_fit_note`，并精确覆盖本轮被选中的 family。

## 5.6 它的输出禁区

`DecisionAgent` 可以输出营销动作中的数字，但不输出：

- 凭空销量预测。
- 凭空转化率预测。
- 凭空复购率预测。
- 某策略的精确好坏得分。
- 超出产品事实、预算边界和动作空间的数字动作。

如果它提出数字动作，必须把数字和策略理由绑在一起，而不是只抛一个看似精确的答案。

---

## 6. `ConsumerAgent`

## 6.1 它是什么

`ConsumerAgent` 是一个模拟消费者角色。

同一个类可以实例化很多个不同消费者。  
当前默认沙盘目录先放 `10` 个 benefit-led 覆盖 persona：

- 预算价值务实者。
- 优惠触发尝鲜者。
- 信任风险谨慎者。
- 便利省时行动者。
- 习惯锚定复购者。
- 结果表现优化者。
- 新鲜体验探索者。
- 口碑比较依赖者。
- 身份意义表达者。
- 场合关系购买者。

默认目录在 `marketing_sandbox/persona_catalog.py`。  
它不是固定世界观里的十类人，而是让沙盘一开始别只听少数显眼人群的覆盖基线。

大白话：

> 它负责站在顾客那边接招。

## 6.2 它负责什么

它收到策略后，从自己的人群画像出发回答：

- 第一眼看到了什么。
- 看懂了什么。
- 哪里吸引自己。
- 哪里让自己不信。
- 会买、会考虑，还是直接无感。
- 复购有没有理由。
- 竞品出现后会不会被抢走。
- 会不会愿意推荐或分享。

## 6.3 它拿什么输入

- `Persona`
- `Strategy`
- `Scenario`
- 产品事实。
- 竞品信息。
- 行为学底层设定。

## 6.4 它输出什么

它输出 `ConsumerFeedback`。

建议包含：

- 第一印象。
- 它理解到的产品和卖点。
- 当前消费态度。
- 最主要吸引点。
- 最主要拒绝点。
- 最大感知风险。
- 最大行动摩擦。
- 主要参照对象。
- 对复购的真实感觉。
- 在竞品压力下的变化。
- 传播和推荐意愿的文字判断。

## 6.5 它必须带着哪些行为学设定

每个消费者代理都要考虑：

- 注意力有限。
- 信息不足时会靠启发式线索判断。
- 会拿旧习惯、预期和竞品当参照。
- 会在意买错、麻烦和后悔。
- 会受现在的行动摩擦影响。
- 会受评论、朋友、KOL、身份认同等社会影响。
- 复购和切换会受习惯与惯性影响。
- 涉及价格和套餐时会考虑心理账户。

这些底层设定与当前 `ConsumerAgent` prompt 保持一致。  
搜索层不能把 `family_id`、UCB 分数、reward 或 selection reason 塞给消费者，让消费者替搜索器“配合优化”。

### 6.5.1 这些设定借鉴了什么研究

| 研究入口 | 对消费者代理的作用 |
|---|---|
| Simon 的 bounded rationality | 让消费者先处理有限而显眼的线索，不假装全知穷举 |
| Tversky 与 Kahneman 的 heuristics 研究 | 让不确定场景下的熟悉度、价格线索、评论和替代方案有位置 |
| Prospect theory | 让参照点、风险、后悔和损失感进入判断 |
| Thaler 的 mental accounting | 让价格、套餐、促销和会员被放进预算感觉里判断 |
| Samuelson 与 Zeckhauser；Wood 与 Neal | 让旧习惯、现状偏好、复购触发和切换阻力进入后续行为 |
| Muchnik、Aral 与 Taylor | 让社会反馈成为 persona-sensitive 的信任线索 |
| Iyengar 与 Lepper | 把选择过多造成犹豫保留成按场景开启的模块 |
| Haley 的 benefit segmentation | 默认 persona 先围绕顾客所求利益和阻力，而不是空人口标签 |
| Dickson；Belk 的 person-situation / situational 研究 | `Persona` 必须放进 `Scenario` 测，不假装跨情境答案恒定 |
| Wind 的 segmentation 研究 | 默认十人目录可编辑，最终分群仍要服务项目证据与决策 |

这里的研究只提供行为先验。  
它不把合成消费者变成真实市场样本，也不允许模型拿理论标签代替 persona 和市场证据。

具体论文记录和使用边界见 `consumer_behavior_literature_notes.md`。

## 6.6 它的输出禁区

`ConsumerAgent` 不输出：

- 自己购买的精确概率。
- 自己复购的精确概率。
- “市场上多少人会买”的判断。
- 策略打分。
- 凭空可接受价格数字。

它应该说：

- 我现在愿意尝试。
- 我有兴趣但会先观望。
- 我觉得风险还没被压住。
- 我可能满意，但不一定会自然回来。
- 如果竞品更熟悉又更方便，我会很容易被带走。

---

## 7. `FeedbackSynthesizer`

## 7.1 它是什么

`FeedbackSynthesizer` 是消费者反馈总结者。

它替代“让大模型当精确评分器”的做法。

大白话：

> 它不打假精确分，而是把一堆顾客反应写成一段有感觉的策略评议。

## 7.2 它负责什么

- 汇总多个消费者反馈。
- 找出哪些人被打动。
- 找出哪些人没被打动。
- 找出策略的整体气质。
- 找出当前最明显的优势。
- 找出当前最明显的短板。
- 描述策略在竞品压力下是稳还是脆。
- 给决策者指出下一轮值得改的方向。

## 7.3 它拿什么输入

- 同一轮所有 `ConsumerFeedback`。
- 当前 `Strategy`。
- 当前测试的 `Scenario`。
- 当前核心目标人群说明。
- 沙盘历史中的相关上一轮反馈。

## 7.4 它输出什么

它输出 `FeedbackSummary`。

建议包含：

- 整体感觉。
- 谁被打动了。
- 谁没被打动。
- 最有说服力的部分。
- 最让人犹豫的部分。
- 复购感觉。
- 竞争压力下的感觉。
- 下一轮更值得验证的方向。
- 仍缺少什么市场证据。
- 可选 `search_signals`：只给搜索层使用的受控定性标签与文字说明。

## 7.5 它可以使用的定性标签

它可以给出非数字标签，例如：

- `首购吸引力明显`
- `信任感偏弱`
- `复购理由不足`
- `竞争压力下脆弱`
- `更像短期拉新打法`
- `更像长期品牌打法`
- `对核心人群更有讨论价值`

## 7.6 它的输出禁区

`FeedbackSynthesizer` 不输出：

- 总分。
- 维度分。
- 精确排名分。
- 人群占比预测。
- 购买率预测。

它应该写出类似这样的反馈：

> 这套策略对愿意尝鲜、在意首次门槛的人更有吸引力，但对谨慎型消费者来说，品质信任仍没有被真正建立。它现在像一个容易让人试一下的打法，却还没有充分回答“为什么以后继续选你”。如果竞品也给出相似优惠，它的优势会变薄。

当前 UCB 路径会要求它额外返回 `FeedbackSearchSignals`。  
这些标签只能表达核心目标反应、试用推进感、策略清晰度、复购逻辑、竞品韧性和证据一致性，不能直接输出 reward 或策略分数。

---

## 8. `CriticAgent`

## 8.1 它是什么

`CriticAgent` 是沙盘里的反方。

它不替消费者说话，也不替决策者出主方案。  
它专门质疑：

- 这个策略是不是虚。
- 这个结果是不是被表面反馈带偏。
- 这个方案是不是执行起来会翻车。

大白话：

> 它负责挑刺，防止沙盘自己骗自己。

## 8.2 它负责什么

它要检查：

- 是否过度依赖折扣、赠品和资源堆砌。
- 是否伤害品牌定位。
- 是否缺乏差异化。
- 是否只顾首购，不顾复购。
- 是否在竞品压力下站不住。
- 是否让产品承诺超出真实边界。
- 是否把合成反馈误当真实市场结论。
- 是否忽略关键场景和关键人群。

## 8.3 它拿什么输入

- `Strategy`
- 产品和品牌边界。
- 消费者反馈。
- `FeedbackSummary`
- 当前场景。
- 历史策略方向。

## 8.4 它输出什么

它输出 `CritiqueReport`。

建议包含：

- 最值得警惕的漏洞。
- 不现实的假设。
- 可能自欺的地方。
- 对品牌的风险。
- 对执行的风险。
- 对产品边界的风险。
- 下一轮必须验证的问题。
- 哪些风险现在还不能下结论。
- 可选 `search_risk_signals`：只给搜索层使用的受控风险标签与文字说明。

## 8.5 它的输出禁区

`CriticAgent` 不输出：

- 风险发生的精确概率。
- 精确预算损失。
- 精确经营预测。
- 精确优先级分数。

它可以说：

- 这是一个必须优先验证的漏洞。
- 这是一个可控但不能忽略的风险。
- 这里证据还不够。
- 这里像是短期反馈好看，但长期不稳。

当前 UCB 路径会要求它额外返回 `CriticSearchSignals`。  
这些标签只表达产品边界、品牌、执行和自欺风险是 `contained`、`watch` 还是 `serious`，不能由批评者自己算 UCB。

---

## 9. `ActionSpace`

## 9.1 它是什么

`ActionSpace` 是营销动作边界。

它不是大模型。  
它决定决策者能动哪些按钮，不能动哪些按钮。

大白话：

> 它是决策者的棋盘规则。

## 9.2 它负责什么

- 定义动作大类。
- 定义每类动作可选方向。
- 定义产品不可被随意篡改的边界。
- 定义价格、预算和规格类动作的允许边界。
- 防止 `DecisionAgent` 为了讨好消费者乱发明东西。

## 9.3 它包含什么

当前至少包含：

- 定位动作。
- Product 动作。
- 价格动作。
- 渠道动作。
- 传播动作。
- 留存动作。

动作集的论文基线见 `action_space_literature_notes.md`。  
当前实现不把顾客旅程或服务单独扩成新顶层 category，而是把：

- 使用支持和保障放进 Product。
- 发现、转化、履约和售后触点角色放进 Channel。
- 内容、证据和激活动作放进 Promotion。
- onboarding、复购触发、服务恢复和关系维护放进 Retention。

## 9.4 它与数字的关系

`ActionSpace` 可以允许 `DecisionAgent` 输出数值型营销动作，但要给它边界。

例如：

- 产品事实里给出了当前价格、成本和预算约束，决策者可以提出新的候选价格动作。
- 动作空间允许测试折扣、满减或券，决策者可以提出具体促销参数。
- 如果某类数字动作没有边界，例如供应成本、法规门槛或最大预算未知，决策者必须标记为待验证，而不能装作可执行。

按当前动作集基线，更细的语义按钮适合通过 `parameter_options` 配置，例如：

- `positioning.value_focus`
- `product.offer_shape`
- `price.value_message`
- `channel.conversion_touchpoint`
- `promotion.evidence_format`
- `retention.repeat_trigger`

---

## 10. `OutputContractGuard`

## 10.1 它是什么

`OutputContractGuard` 是 LLM 输出守门员。

大白话：

> 它不一刀切禁数字，而是检查每个角色有没有按自己的输出契约说话。

## 10.2 它负责什么

- 检查 `DecisionAgent` 的数字动作是否属于允许的动作空间。
- 检查 `ConsumerAgent` 是否把感受写成概率、分数或市场预测。
- 检查 `FeedbackSynthesizer` 是否把整体反馈写成假精确评分。
- 检查 `CriticAgent` 是否凭空写风险概率和经营预测。
- 检查是否出现凭空产品参数、认证数据、销量或利润判断。
- 检查输出是否偏离该类职责。
- 在不合格时要求对应 Agent 重写。

## 10.3 它检查什么

它重点检查：

- `DecisionAgent` 的数字是否是数值型营销动作，而不是市场结果预测。
- `DecisionAgent` 的数字动作是否超出动作边界。
- `ConsumerAgent` 是否给了伪概率。
- `FeedbackSynthesizer` 是否写成评分表。
- `CriticAgent` 是否凭空报风险概率。

## 10.4 它输出什么

它输出的是质量检查结果，例如：

- 接受本次输出。
- 要求消费者或反馈总结改写为定性文字。
- 标记某个决策数字动作缺少边界或依据。
- 标记某段内容引用了未提供的数值事实。
- 标记某段内容超出 Agent 职责。

---

## 11. 搜索层补充

### 11.1 `UCBSearchController`

`UCBSearchController` 是 family-level 搜索器。

它负责：

- 注册稳定的 `StrategyFamily` 列表。
- 让没被完整测试过的 family 先 cold start。
- 对已经有 observation 的 family 做确定性 UCB 选择。
- 生成不给出 reward 数字的 `SearchBrief`。
- 只在 selected families 都拿到完整 observation 后更新 arm state。

它不负责：

- 写具体营销策略。
- 代替 `ActionSpace` 做动作合法性检查。
- 把内部搜索统计展示成真实市场表现。

### 11.2 `RewardMapper`

`RewardMapper` 是搜索层的确定性映射器。

它输入：

- `FeedbackSearchSignals`
- `CriticSearchSignals`

它输出：

- `RewardBreakdown`

这个 reward 是内部 search utility。  
它可以被 UCB 使用，但不能回流成消费者购买概率、总结者分数或报告里的真实经营预测。

---

## 12. 主要数据类

下面这些类不负责“思考”，而是负责承载沙盘里传来传去的信息。

## 12.1 `SandboxContext`

装整个沙盘的背景事实：

- 产品背景。
- 品牌背景。
- 市场环境。
- 竞品信息。
- 项目目标。
- 预算与执行边界。

## 12.2 `Persona`

装一个消费者人群卡：

- 核心需求。
- 当前替代方案。
- 购买动机。
- 价格敏感度的定性描述。
- 信任敏感度的定性描述。
- 渠道偏好。
- 社会影响敏感度。
- 复购触发点。
- 切换阻力。

默认 `Persona` coverage 由 `DEFAULT_CONSUMER_PERSONAS` 提供 `10` 张起始卡。  
具体沙盘可以保留全量覆盖，也可以根据产品市场证据重写后再实例化
`ConsumerAgent[]`；改变 persona 卡不等于改变消费者输出契约。

## 12.3 `Scenario`

装一个市场情境：

- 正常首发。
- 竞品更强势。
- 用户预算更紧。
- 渠道便利性变化。
- 口碑和信任受压。
- 其他需要测试的压力情境。

## 12.4 `Strategy`

装一套营销策略。

它应描述：

- 定位方向。
- Product 方向。
- 价格动作。
- 渠道方向。
- 传播方向。
- 留存方向。
- 这套策略想解决的主要问题。

如果含有精确价格、促销或预算动作，它们必须属于 `DecisionAgent` 被允许提出的营销动作，并保留边界说明与策略理由。

开启 family 搜索时，它还带：

- `family_id`
- `family_fit_note`

## 12.5 `StrategyProposal`

装决策者本轮提出的候选方向：

- 候选策略。
- 每个策略调整了什么。
- 每个策略想验证什么。
- 每个策略的预期风险。

## 12.6 `ConsumerFeedback`

装某个消费者代理对某套策略的反馈：

- 第一印象。
- 理解到的卖点。
- 当前消费态度。
- 吸引点。
- 拒绝点。
- 行为学诊断。
- 复购感觉。
- 竞品冲击反应。
- 传播感觉。

## 12.7 `FeedbackSummary`

装反馈总结者的归纳：

- 整体感觉。
- 谁被打动。
- 谁没被打动。
- 当前策略优势。
- 当前策略短板。
- 复购和竞争韧性的文字判断。
- 下一轮建议。
- 可选搜索标签 `FeedbackSearchSignals`。

## 12.8 `CritiqueReport`

装批评者输出：

- 漏洞。
- 不现实假设。
- 品牌风险。
- 产品边界风险。
- 执行风险。
- 下一轮必须验证的问题。
- 可选搜索风险标签 `CriticSearchSignals`。

## 12.9 `StrategyFamily` 与 `SearchBrief`

`StrategyFamily` 装一个高层策略赢法：

- 核心顾客障碍。
- 赢法机制。
- 生成提示。
- 预期动作模式。
- 失败信号。

`SearchBrief` 把被选中的 family、生成意图和受控文字记忆交给 `DecisionAgent`。  
它不给消费者看，也不把 UCB score 暴露给 LLM。

## 12.10 `SearchObservation`、`RewardBreakdown` 与 `SearchUpdate`

这一组数据类记录搜索层审计信息：

- 一次完整 family pull 观察到了什么。
- 定性标签如何被映射成内部 reward。
- family arm state 在 update 前后怎么变化。

## 12.11 `StrategyTestResult`

装一套策略在一轮测试里的证据：

- 当前 `Strategy`。
- 这套策略收到的 `ConsumerFeedback`。
- 对应 `FeedbackSummary`。
- 对应 `CritiqueReport`。
- 开启 UCB 时的完整 `SearchObservation`。

## 12.12 `RoundResult`

装一轮沙盘的完整记录：

- 本轮策略提案。
- 消费者反馈。
- 反馈总结。
- 批评报告。
- 下一轮输入摘要。
- 开启 UCB 时的 selection 与 search updates。

## 12.13 `SandboxResult`

装沙盘最终输出：

- 最值得继续推进的策略方向。
- 被淘汰或暂停的策略方向。
- 主要人群洞察。
- 主要策略风险。
- 仍需真实市场验证的问题。
- 可用于营销计划报告和展示的决策逻辑。
- 开启 UCB 时的 family search trace 与 search notes。

---

## 13. 一轮沙盘如何跑

```text
MarketingSandbox 启动一轮
  |
  v
UCBSearchController? 选择本轮 StrategyFamily 并生成 SearchBrief
  |
  v
DecisionAgent 提出候选策略方向
  |
  v
ActionSpace 检查策略是否在允许动作边界内
  |
  v
ConsumerAgent[] 分别给出消费者反馈
  |
  v
FeedbackSynthesizer 汇总整体感觉
  |
  v
CriticAgent 挑出漏洞和风险
  |
  v
OutputContractGuard 按角色检查输出边界
  |
  v
RewardMapper? 把受控 search signals 映射成内部 reward
  |
  v
UCBSearchController? 更新 family state
  |
  v
MarketingSandbox 保存 RoundResult
  |
  v
把本轮结果交回 DecisionAgent 继续下一轮
```

---

没有注入搜索控制器时，带 `?` 的两段跳过，原来的定性回合仍然成立。

---

## 14. 当前实现范围

当前实现已经包含这些类：

- `MarketingSandbox`
- `DecisionAgent`
- `ConsumerAgent`
- `FeedbackSynthesizer`
- `CriticAgent`
- `ActionSpace`
- `OutputContractGuard`
- `UCBSearchController`
- `RewardMapper`
- `WebRunConfig`
- `WebRunSession`
- `WebSandboxRunner`
- `SandboxWebEventMapper`
- `WebRunEventStream`
- `WebRunLifecycleManager`
- `WebSandboxApi`
- `WebApiResponse`

当前实现已经包含这些主要数据类：

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

---

## 15. 最终类职责总结

| 类 | 一句话职责 |
|---|---|
| `MarketingSandbox` | 控制整场沙盘怎么跑 |
| `DecisionAgent` | 在动作空间里提出和修改营销策略 |
| `ConsumerAgent` | 代表某类消费者给真实感反馈 |
| `FeedbackSynthesizer` | 把一堆反馈归纳成整体策略感觉 |
| `CriticAgent` | 专门找漏洞、找自欺、找不现实假设 |
| `ActionSpace` | 规定决策者能动哪些营销按钮 |
| `OutputContractGuard` | 按角色拦住不合规的数字判断和越界输出 |
| `UCBSearchController` | 在策略家族层控制探索与利用 |
| `RewardMapper` | 把受控定性标签映射成内部搜索 reward |
| `WebRunLifecycleManager` | 控制网站 live run 的停止、存档、恢复和断联自动存档 |
| `WebSandboxApi` | 把网站请求接到真实事件流、停止、存档、恢复和 provider check |

一句话收束：

> 这个沙盘不是让大模型互相打分，而是让决策者不断出招，让不同消费者暴露反应，让总结者讲清整体感觉，让批评者把不稳的地方挖出来。
