# 策略家族与分层搜索论文备忘

## 1. 这份备忘是干什么的

这份文件记录我们在讨论 `StrategyFamily`、UCB 和营销沙盘搜索结构时查到的论文。

消费者行为学先验的论文依据另见 `consumer_behavior_literature_notes.md`。
动作空间和 marketing mix 论文依据另见 `action_space_literature_notes.md`。

它主要服务两个后续任务：

1. 给沙盘设计文档补理论依据。
2. 以后写总结或报告时，知道哪些说法可以引用，哪些说法只是项目里的工程定义。

## 2. 当前结论先放在前面

### 2.1 `StrategyFamily` 不是一个已经确认的标准营销术语

目前查到的材料里，更接近它的营销学概念是：

- marketing strategy type
- marketing strategy typology
- taxonomy of marketing strategies
- integrated pattern of marketing decisions

所以在本项目里，比较稳妥的写法是：

> `StrategyFamily` 是沙盘为了做高层搜索而定义的策略类型。它把同一种核心赢法下的具体营销方案归为一组。

不要直接写成：

> 营销学中已经有一个标准概念叫 `StrategyFamily`。

### 2.2 这批论文能支持什么

它们可以支持三件事：

1. 营销策略不只是某一个动作，而是一组围绕市场、产品、活动和资源的联动决策。
2. 营销研究中确实存在把策略分成不同类型、不同分类体系的做法。
3. 在 bandit 搜索里，把大量候选动作先按类别或层级组织，再做探索与利用，是有对应研究脉络的。

### 2.3 对我们的沙盘意味着什么

`StrategyFamily` 可以作为 UCB 的 arm 粒度之一：

- UCB 先决定本轮探索哪一类策略赢法。
- `DecisionAgent` 再在这个策略家族内部生成具体营销方案。
- `ConsumerAgent`、`FeedbackSynthesizer` 和 `CriticAgent` 返回沙盘反馈。
- 搜索层再把反馈转成可用于更新该策略家族状态的内部搜索信号。

这样做的核心好处是：

- 避免把每一个具体参数组合都当成一个独立 arm。
- 避免决策者只围着当前方案小修小改。
- 让探索从“策略方向”开始，再进入“具体参数”。

当前代码已经把这条路径落下来了：

- `StrategyFamily`、`SearchBrief` 和 family state 数据类在 `marketing_sandbox/search_models.py`。
- `UCBSearchController` 负责 cold start、family 选择和 update。
- `DecisionAgent` 在 `SearchBrief` 存在时按 selected families 出具体策略。
- `FeedbackSynthesizer` 与 `CriticAgent` 输出受控定性 search signals。
- `RewardMapper` 把这些标签映射成内部 search utility。

## 3. 论文清单

## 3.1 Varadarajan: 营销策略是联动决策

### 基本信息

- 作者：Rajan Varadarajan
- 年份：2010
- 标题：*Strategic Marketing and Marketing Strategy: Domain, Definition, Fundamental Issues and Foundational Premises*
- 期刊：*Journal of the Academy of Marketing Science*
- 类型：概念与理论论文

### 这篇论文在说什么

这篇论文给出了一个很重要的营销策略定义：

- 营销策略不是单个战术动作。
- 它是一种整合后的决策模式。
- 这些决策涉及产品、市场、营销活动和营销资源。
- 它的目标是创造、传递和沟通顾客价值，并服务组织目标。

### 对沙盘设计的帮助

这篇论文最适合用来支撑：

> 一个策略方案不应该只是一组孤立参数，而应该是 Product、Price、Place、Promotion 以及目标市场选择之间有内在逻辑的一组决策。

它也能支撑我们为什么要让 `StrategyFamily` 按“核心赢法”和“决策组合模式”来分，而不是只按：

- 打不打折
- 投哪个渠道
- 选哪个卖点

### 以后写总结时可以怎么用

可以写：

> 本沙盘把营销策略视为一组相互关联的决策，而不是单一促销动作。这一处理与 Varadarajan 对营销策略作为整合决策模式的界定相一致。

### 使用时的边界

这篇论文能支撑“策略是整合决策”，但它并没有直接提出我们项目里的 `StrategyFamily` 类。

## 3.2 Sashittal and Wilemon: 营销策略行为可以做类型划分

### 基本信息

- 作者：Hemant C. Sashittal, David Wilemon
- 年份：1996
- 标题：*A Typology of Marketing Strategy Behaviors: Understanding Why Marketing Strategies Turn Out the Way They Do*
- 期刊：*The Journal of Marketing Management*
- 类型：探索性研究

### 这篇论文在说什么

这篇论文基于工业组织中的营销实施过程，讨论：

- 营销策略行为为什么会呈现不同形态。
- 如何用 typology 的方式理解这些不同策略行为。
- 策略内容、策略过程和与顾客关系之间不是完全割裂的。

### 对沙盘设计的帮助

这篇论文对我们最有价值的点不是拿来照抄它的分类，而是证明：

> 在营销研究里，把营销策略行为做成“类型”来讨论，是合理的研究路径。

它能给 `StrategyFamily` 这个工程概念提供一个温和的学术落点：

- 我们不是把一堆随机 prompt 标签硬塞给搜索器。
- 我们是在项目里定义策略类型，用来组织不同营销赢法的搜索。

### 以后写总结时可以怎么用

可以写：

> 营销策略研究中已有通过 typology 理解不同策略行为的路径，因此本沙盘将具体方案先归入若干策略类型，再在类型内部搜索具体动作组合。

### 使用时的边界

这篇论文是较早的探索性研究。

它能支撑“策略可类型化”，但不能单独支撑：

- 我们的每一个策略家族分类都必然正确。
- UCB 按策略家族搜索一定优于其他搜索方式。

## 3.3 Li, Larimo and Leonidou: 策略 taxonomy 可以按目标、活动和能力来分

### 基本信息

- 作者：Fangfang Li, Jorma Larimo, Leonidas C. Leonidou
- 年份：2020 在线发表，2021 期刊卷期
- 标题：*Social Media Marketing Strategy: Definition, Conceptualization, Taxonomy, Validation, and Future Agenda*
- 期刊：*Journal of the Academy of Marketing Science*
- 类型：概念化、分类体系构建与验证

### 这篇论文在说什么

这篇论文研究社交媒体营销策略，并提出 taxonomy。

它把不同策略类型放在一个成熟度谱系上，讨论它们在这些方面的差异：

- 战略目标
- 营销活动
- 顾客参与行为
- 组织资源与能力
- 企业与顾客的互动方式

### 对沙盘设计的帮助

这篇论文对我们很有启发，因为它说明策略分类不一定只能按一个单点动作分。

策略类型可以同时考虑：

- 想解决什么营销问题
- 希望顾客发生什么行为变化
- 需要什么产品、渠道、传播和服务组合
- 对执行能力有什么要求

这和我们讨论的 `StrategyFamily` 分类标准很接近。

### 以后写总结时可以怎么用

可以写：

> 本沙盘的策略家族不是单纯按促销动作划分，而是按策略目标、顾客行为变化和配套决策模式组织。这种思路与营销策略 taxonomy 研究中对策略类型的多维刻画相呼应。

### 使用时的边界

这篇论文研究的是社交媒体营销策略，不是通用 4Ps 动作搜索。

它提供的是分类方法启发，不是我们策略家族的现成标签表。

## 3.4 Jedor, Perchet and Louedec: bandit 里可以先按 category 组织 arms

### 基本信息

- 作者：Matthieu Jedor, Vianney Perchet, Jonathan Louedec
- 年份：2019
- 标题：*Categorized Bandits*
- 会议：*Advances in Neural Information Processing Systems 32*
- 类型：bandit 算法研究

### 这篇论文在说什么

这篇论文讨论一种 bandit 结构：

- arms 不是完全平铺的。
- arms 先被组织到 categories 里。
- 类别结构可以被算法利用。
- 文中动机之一来自电商场景中用户对不同品类偏好的差异。

### 对沙盘设计的帮助

这篇论文最接近我们说的：

> 不要直接对所有具体营销参数组合做平铺 UCB，而是先把候选方案按上层类别组织起来。

在我们的沙盘里可以这样类比：

- arm category 类似 `StrategyFamily`
- family 内部的具体 strategy 类似 category 内的具体 arm

### 以后写总结时可以怎么用

可以写：

> 当候选动作具有类别结构时，bandit 研究中已有利用 category structure 组织探索的工作。本沙盘据此将大规模具体营销方案先归入策略家族，再考虑分层搜索。

### 使用时的边界

这篇论文里的 category 有明确数学设定。

我们的策略家族最开始更像人为定义的高层搜索结构，因此不能直接声称：

- 我们完全复现了论文算法。
- 论文的理论 regret 保证直接迁移到了营销沙盘。

## 3.5 Yue, Hong and Guestrin: 先粗后细的层级探索

### 基本信息

- 作者：Yisong Yue, Sue Ann Hong, Carlos Guestrin
- 年份：2012
- 标题：*Hierarchical Exploration for Accelerating Contextual Bandits*
- 类型：contextual bandit 与层级探索研究

### 这篇论文在说什么

这篇论文提出 coarse-to-fine 的探索思路：

- 大特征空间下，直接探索会很慢。
- 可以先利用较粗粒度的先验结构探索。
- 只有在需要时，再进入更细粒度的空间。

### 对沙盘设计的帮助

这篇论文非常适合支撑我们讨论的两层搜索：

1. 先探索策略家族。
2. 再在被选中的家族里探索具体策略参数。

它也能解释为什么我们不希望 `DecisionAgent` 一开始就在超大的动作组合空间里乱走。

### 以后写总结时可以怎么用

可以写：

> 为降低高维动作组合下的探索成本，本沙盘采用先粗后细的设计思路：先选择策略家族，再生成和比较家族内部的具体策略。

### 使用时的边界

这篇论文讨论的是 contextual bandit 的层级探索。

我们的沙盘如果暂时还没有严格定义：

- context
- reward
- family 内策略生成分布
- 更新公式

那么现在最多说“借鉴层级探索思路”，不要提前说“已经实现论文方法”。

## 4. 这些论文分别支持沙盘里的哪一块

| 沙盘问题 | 可参考论文 | 能支持的结论 |
|---|---|---|
| 为什么一个营销策略不能只看单个动作 | Varadarajan | 营销策略是一组整合决策 |
| 为什么可以把策略分成类型 | Sashittal and Wilemon | 营销策略行为存在 typology 研究路径 |
| 策略类型可以按什么维度刻画 | Li, Larimo and Leonidou | 可以按目标、活动、顾客行为、能力和互动结构分类 |
| 为什么 UCB 不直接平铺所有参数组合 | Categorized Bandits | 候选 arm 有类别结构时可以利用类别组织探索 |
| 为什么要先选策略方向再细调方案 | Hierarchical Exploration | 大空间下可以借鉴 coarse-to-fine 层级探索 |

## 5. 对 `StrategyFamily` 的建议定义

当前项目里建议写成：

> `StrategyFamily` 是营销沙盘中的高层策略搜索单位。它按照同一种核心顾客障碍、同一种赢法逻辑和一组相互配合的营销动作模式，把多个具体策略方案归为一类。

这个定义里有四个关键点：

1. 它是搜索单位，不是单个动作。
2. 它对应一类赢法，不是一个参数值。
3. 它覆盖一组配套动作，不局限于 4Ps 里的单一 P。
4. 它是项目定义，需要用反馈和实验不断校正。

## 6. 暂定分类标准

后续如果真的做 `StrategyFamily`，建议每个家族都回答下面四个问题：

1. 它要解决的核心顾客障碍是什么？
2. 它靠什么机制赢？
3. 它通常会带出怎样的一组 Product、Price、Place、Promotion 和留存动作？
4. 它在什么反馈下说明自己可能走错了？

举例：

| 策略家族方向 | 核心障碍 | 主要赢法 |
|---|---|---|
| 清晰定位型 | 顾客看不懂你是谁、为什么需要你 | 让价值主张更快被理解 |
| 信任降险型 | 顾客怕踩坑、怕不值、怕承诺不可信 | 降低感知风险 |
| 试用入门型 | 顾客有兴趣但首次尝试门槛高 | 降低第一次行动阻力 |
| 产品匹配型 | 顾客觉得产品形态和真实使用场景不贴 | 调整产品组合与场景适配 |
| 便利触达型 | 顾客想买但发现、比较、购买或履约不顺 | 减少路径摩擦 |
| 留存习惯型 | 顾客买过但没有形成持续理由 | 建立复购触发和使用习惯 |

## 7. 写报告时建议采用的说法

### 7.1 稳妥说法

可以写：

- 本项目借鉴营销策略 typology 和 taxonomy 的研究思路，把具体营销方案组织为若干高层策略类型。
- 本项目将 `StrategyFamily` 作为搜索层概念，用于把同一赢法逻辑下的动作组合归类。
- 本项目借鉴 categorized bandit 与 hierarchical exploration 的思想，降低在大规模策略组合空间中直接探索的难度。

### 7.2 容易说过头的说法

尽量不要写：

- `StrategyFamily` 是营销学里公认的标准术语。
- 只要用了 UCB 就一定能找到最优营销策略。
- 论文已经证明这种多智能体沙盘能预测真实市场销量。
- 这些论文直接验证了大模型消费者能替代真实消费者实验。

## 8. 后续还值得补的论文方向

如果后面要把总结写得更扎实，可以继续补三类文献：

1. 营销策略分类与竞争策略分类
   - 目的：把策略家族定义得更像营销理论，而不只是搜索工程标签。
2. 消费者行为模拟与 synthetic consumers 的可靠性
   - 目的：说明大模型消费者能做什么，不能做什么。
3. LLM agent 评估、偏差控制和 reward construction
   - 目的：解释为什么沙盘反馈不能直接被当成真实市场数字。

## 9. 参考文献清单

1. Varadarajan, R. (2010). *Strategic Marketing and Marketing Strategy: Domain, Definition, Fundamental Issues and Foundational Premises*. Journal of the Academy of Marketing Science.
2. Sashittal, H. C., & Wilemon, D. (1996). *A Typology of Marketing Strategy Behaviors: Understanding Why Marketing Strategies Turn Out the Way They Do*. The Journal of Marketing Management.
3. Li, F., Larimo, J., & Leonidou, L. C. (2021). *Social Media Marketing Strategy: Definition, Conceptualization, Taxonomy, Validation, and Future Agenda*. Journal of the Academy of Marketing Science.
4. Jedor, M., Perchet, V., & Louedec, J. (2019). *Categorized Bandits*. Advances in Neural Information Processing Systems 32.
5. Yue, Y., Hong, S. A., Guestrin, C., et al. (2012). *Hierarchical Exploration for Accelerating Contextual Bandits*.
