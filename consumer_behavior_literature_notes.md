# 消费者行为学论文备忘

## 1. 这份备忘是干什么的

这份文件记录当前 `ConsumerAgent` 行为学底层设定借鉴的研究入口。

它服务三件事：

1. 让消费者 prompt 里的行为先验有可回溯的研究依据。
2. 让后续 agent 知道这些研究落在沙盘的哪里。
3. 防止把行为研究说成“合成消费者已经能预测真实市场”的证据。

本备忘和 `strategy_family_literature_notes.md` 分工不同：

- 本文件负责消费者判断、复购、切换和社会影响相关研究。
- `strategy_family_literature_notes.md` 负责策略家族、策略 taxonomy 和 bandit 搜索相关研究。

---

## 2. 当前结论先放在前面

当前 `ConsumerAgent` 不被设计成完全理性的效用最大化器。  
它会在 persona、产品事实、策略和场景卡的边界内，借鉴下面这些行为倾向给出定性反馈：

- 注意力和处理能力有限。
- 不确定时会用启发式线索做粗判断。
- 价值判断会参考旧习惯、预期、替代品和竞品。
- 风险、损失感、后悔和麻烦会压住行动。
- 价格、套餐、促销和会员会触发心理账户式的预算感觉。
- 复购和竞品切换会受现状偏好、习惯、触发场景和惯性影响。
- 评论、朋友、热度和专业背书可以成为社会影响线索，但效果取决于 persona 和场景。
- 选择过多等机制不是每次都开，而是按场景开启。
- 默认十人 persona 目录按“主要所求利益”覆盖不同顾客阻力，再由
  `Scenario` 补上使用情境和竞争压力，不把十个人写成永久人格分类。

这些倾向是 prompt 先验，不是每轮都必须出现的标签清单。  
消费者输出仍要优先服从：

- `Persona`
- `ProductContext`
- `Strategy`
- `Scenario`
- 数字边界和输出契约

---

## 3. 当前代码里落到哪里

| 代码或文档位置 | 当前落点 |
|---|---|
| `marketing_sandbox/consumer_agent.py` | `Behavioral priors` prompt block |
| `marketing_sandbox/persona_catalog.py` | 默认十人 benefit-led persona 覆盖目录 |
| `ConsumerFeedback.behavior_diagnosis` | 最先注意线索、参照点、风险、摩擦、主导驱动 |
| `RepeatPurchaseReaction` | 复购感觉、触发条件、习惯和惯性 |
| `CompetitorReaction` | 竞品压力与留存条件 |
| `marketing_sandbox_full_summary.md` | 消费者行为学底层设定和可复用设定块 |
| `marketing_sandbox_class_design.md` | `ConsumerAgent` 行为学边界 |
| `visualization_site/src/config/run-config.js` | 默认十张人群卡准备区 |

搜索层不能把这些研究改写成对消费者的搜索提示。  
`ConsumerAgent` 不应该看到 `family_id`、UCB score、内部 reward 或 selection reason。

---

## 4. 论文清单

## 4.1 Simon：有限理性

### 基本信息

- 作者：Herbert A. Simon
- 年份：1955
- 标题：*A Behavioral Model of Rational Choice*
- 期刊：*The Quarterly Journal of Economics*

### 这篇论文对沙盘有用的结论

Simon 的 bounded rationality 路线提醒我们：  
真实决策者的认知、信息处理和搜索能力不是无限的。

### 在项目里怎么用

当前项目把它落成一个很克制的先验：

> 消费者先处理最显眼、最相关、最容易理解的线索，不假装自己完整穷举所有营销信息。

对应输出是：

- 第一印象。
- 最先注意线索。
- 看懂了什么。
- 哪些复杂信息没有真正进入判断。

### 使用边界

不能因为“有限理性”就让消费者代理变得随意、愚蠢或不读事实。  
persona、产品事实和场景边界仍然优先。

## 4.2 Tversky and Kahneman：不确定判断中的启发式

### 基本信息

- 作者：Amos Tversky, Daniel Kahneman
- 年份：1974
- 标题：*Judgment under Uncertainty: Heuristics and Biases*
- 期刊：*Science*

### 这篇论文对沙盘有用的结论

人在不确定判断中会依赖启发式原则。  
对沙盘来说，这支持我们不要把消费者写成每次都做完整信息比较的机器。

### 在项目里怎么用

当前消费者 prompt 允许这些线索在信息不足时进入粗判断：

- 熟悉度。
- 价格线索。
- 评论和社会证明。
- 品牌可信感。
- 视觉专业感。
- 当前替代方案。

### 使用边界

启发式不是“所有看法都叫偏差”。  
如果产品事实、渠道便利或价格结构本来就不合适，不能用心理偏差替代业务解释。

## 4.3 Kahneman and Tversky：参照点与损失敏感

### 基本信息

- 作者：Daniel Kahneman, Amos Tversky
- 年份：1979
- 标题：*Prospect Theory: An Analysis of Decision under Risk*
- 期刊：*Econometrica*

### 这篇论文对沙盘有用的结论

prospect theory 强调选择并不只看绝对结果。  
参照点和损失侧的感受会改变判断。

### 在项目里怎么用

当前 prompt 要消费者说明：

- 主要参照点是什么。
- 旧习惯、竞品或预期价格如何改变价值感。
- 买错、踩坑、后悔、售后不确定和切换失败是否压住行动。

### 使用边界

这篇论文不是“所有消费决策都等价于一张风险彩票”。  
项目只借鉴参照点和损失敏感方向，不拿它直接推销量或购买概率。

## 4.4 Thaler：心理账户与消费者选择

### 基本信息

- 作者：Richard Thaler
- 年份：1985
- 标题：*Mental Accounting and Consumer Choice*
- 期刊：*Marketing Science*

### 这篇论文对沙盘有用的结论

消费者会以心理账户组织交易感觉。  
同一笔支出放在不同预算感觉里，判断可能不同。

### 在项目里怎么用

当前 prompt 在这些动作出现时要求考虑心理账户：

- 定价。
- 套餐。
- 促销。
- 会员。
- 返券和回购激励。

消费者应说这笔交易像：

- 必需支出。
- 奖励自己。
- 尝鲜成本。
- 有负担的额外消费。

### 使用边界

心理账户不等于凭空报一个“可接受价格”。  
当前 `ConsumerAgent` 仍禁止输出愿付价格数字和可接受价格区间。

## 4.5 Samuelson and Zeckhauser：现状偏好

### 基本信息

- 作者：William Samuelson, Richard Zeckhauser
- 年份：1988
- 标题：*Status Quo Bias in Decision Making*
- 期刊：*Journal of Risk and Uncertainty*

### 这篇论文对沙盘有用的结论

选择会受现状选项影响。  
这对营销里“为什么有替代方案的人不马上切换”很重要。

### 在项目里怎么用

当前 persona 和竞品反应里要看：

- 用户现在用什么替代方案。
- 什么会让他懒得切换。
- 哪种竞品优势会把他留在旧选择里。

### 使用边界

现状偏好不是永远不切换。  
如果新策略明显更贴近需求、风险更低或路径更方便，消费者反馈可以表现出改变。

## 4.6 Wood and Neal：习惯消费者

### 基本信息

- 作者：Wendy Wood, David T. Neal
- 年份：2009
- 标题：*The Habitual Consumer*
- 期刊：*Journal of Consumer Psychology*

### 这篇论文对沙盘有用的结论

重复消费可以被稳定情境和习惯反应带动。  
已有习惯也会成为新品牌切入和旧品牌被替换时的阻力。

### 在项目里怎么用

当前 `RepeatPurchaseReaction` 不只问“满意后会不会再买”，还问：

- 复购在什么条件下感觉自然。
- 提醒、便利、触发场景和周期需求是否成立。
- 旧习惯和惯性如何影响复购或切换。

### 使用边界

复购不能被简化成满意度自动续杯。  
产品本身没有重复场景时，不能为了留存写出假习惯。

## 4.7 Muchnik, Aral and Taylor：社会影响偏差

### 基本信息

- 作者：Lev Muchnik, Sinan Aral, Sean J. Taylor
- 年份：2013
- 标题：*Social Influence Bias: A Randomized Experiment*
- 期刊：*Science*

### 这篇论文对沙盘有用的结论

他人的反馈和可见评价会影响后续评价行为。  
这提醒我们，评论、朋友推荐和热度并不只是传播噪音，也可能是信任线索。

### 在项目里怎么用

当前 prompt 把社会影响写成 persona-sensitive 的线索：

- 有的人更在意评论和朋友。
- 有的人更吃专业背书。
- 有的人对热度和 KOL 并不敏感。

### 使用边界

不能因为有社会影响研究，就默认“上 KOL 一定有效”或“爆款信号一定能转化”。  
它必须落回 persona、场景和品牌可信度。

## 4.8 Iyengar and Lepper：选择过多可能让行动变弱

### 基本信息

- 作者：Sheena S. Iyengar, Mark R. Lepper
- 年份：2000
- 标题：*When Choice Is Demotivating: Can One Desire Too Much of a Good Thing?*
- 期刊：*Journal of Personality and Social Psychology*

### 这篇论文对沙盘有用的结论

更大的选择集合不总能带来更强行动。  
在某些情境下，过多选项会让参与和选择变弱。

### 在项目里怎么用

当前项目没有把它写成每次都注入的固定先验。  
它主要用于这些场景：

- SKU 太多。
- 套餐太复杂。
- 会员权益太绕。
- Product 版本切分让人难理解。

### 使用边界

不能把“选择多”一概判成坏事。  
只有当场景里真的出现理解和决策负担时，才让消费者反馈这个阻力。

## 4.9 Haley：用所求利益组织细分

### 基本信息

- 作者：Russell I. Haley
- 年份：1968
- 标题：*Benefit Segmentation: A Decision-Oriented Research Tool*
- 期刊：*Journal of Marketing*

### 这篇论文对沙盘有用的结论

这篇论文把市场细分的重心从单纯人口统计描述，拉回到顾客从产品中
寻找什么 benefit。  
对策略沙盘来说，benefit 比“大学生”“白领”这种空标签更接近可行动
的营销阻力和卖点。

### 在项目里怎么用

默认十人目录优先按主要 benefit / job 覆盖：

- 预算价值。
- 轻承诺尝鲜。
- 信任与风险缓释。
- 便利省时。
- 习惯连续性。
- 结果表现。
- 新鲜体验。
- 口碑验证。
- 身份意义。
- 场合关系。

这些 benefit 会落入 `Persona.core_need`、`purchase_motivation`、
`main_barrier`、`repeat_trigger` 和 `switching_threshold`。

### 使用边界

benefit segmentation 不等于“论文给了固定十类消费者”。  
沙盘的十人目录只是一个默认覆盖面，具体项目仍要用市场证据修改人群卡。

## 4.10 Dickson：人和使用情境要一起分

### 基本信息

- 作者：Peter R. Dickson
- 年份：1982
- 标题：*Person-Situation: Segmentation's Missing Link*
- 期刊：*Journal of Marketing*

### 这篇论文对沙盘有用的结论

这篇论文提醒分群不能只盯稳定的人，也不能只盯孤立情境。  
不同人放进不同使用情境，营销反应可能不是同一回事。

### 在项目里怎么用

当前项目采用两层结构：

- `Persona` 保存相对稳定的 segment archetype。
- `Scenario` 保存竞品压力、信任压力、渠道摩擦、礼物场合等情境压力。

因此同一位默认 persona 可以在正常比较、竞品压价、信任受压或场合购买
下给出不同反馈。

### 使用边界

不要把 `Persona` 本身写成会在所有场景中给同一答案的固定角色。  
也不要只靠场景卡抹掉人群之间的长期替代方案和动机差异。

## 4.11 Belk：情境变量会改变消费者行为解释

### 基本信息

- 作者：Russell W. Belk
- 年份：1975
- 标题：*Situational Variables and Consumer Behavior*
- 期刊：*Journal of Consumer Research*

### 这篇论文对沙盘有用的结论

Belk 把情境变量作为消费者行为解释的重要一层。  
物理环境、社会环境、时间、任务定义和前置状态都会让同一个消费对象
在不同 moment 里被判断得不一样。

### 在项目里怎么用

`Scenario` 不能只写一句“有竞品”。  
后续场景卡应尽量说明：

- 购买任务是什么。
- 时间和渠道摩擦是什么。
- 是否有他人或社交场合在场。
- 信任和竞争压力从哪里来。

默认十人目录提供覆盖，场景卡负责让这些覆盖在具体 moment 里被测试。

### 使用边界

Belk 的情境框架不是让我们凭空编出无限情境。  
场景卡仍要围绕项目目标、产品事实和可解释的压力点。

## 4.12 Wind：细分研究要服从决策问题

### 基本信息

- 作者：Yoram Wind
- 年份：1978
- 标题：*Issues and Advances in Segmentation Research*
- 期刊：*Journal of Marketing Research*

### 这篇论文对沙盘有用的结论

Wind 把 segmentation 研究放回营销决策流程里讨论：分群设计、变量选择、
数据收集和解释必须与要解决的问题相连。  
这支持沙盘保留可编辑 persona，而不是把默认目录当成最终市场真相。

### 在项目里怎么用

默认十人目录是开局 coverage：

- 帮助第一版别只听三种最显眼顾客。
- 给策略搜索更多阻力面。
- 让课堂演示能解释人群差异。

但进入具体项目后，应根据产品证据、评论、访谈或报告删改、合并或重写。

### 使用边界

不能把十人目录说成被顶刊验证的通用消费者 census。  
它只是由顶刊 segmentation 原则约束的一份沙盘起始目录。

---

## 5. 当前 prompt 先验与论文映射

| 当前 `ConsumerAgent` 先验 | 主要研究入口 |
|---|---|
| Attention is limited | Simon |
| Heuristics under uncertainty | Tversky and Kahneman 1974 |
| Compare against reference points | Kahneman and Tversky 1979 |
| Loss, risk, regret, hassle can outweigh benefit | Kahneman and Tversky 1979 |
| Immediate friction matters | Simon 的有限处理视角，加上当前营销场景工程设定 |
| Social influence depends on persona | Muchnik, Aral and Taylor |
| Satisfaction does not guarantee repeat purchase | Wood and Neal；Samuelson and Zeckhauser |
| Prices, memberships and bundles trigger mental accounting | Thaler |
| Personas start from benefits sought, not empty demographic labels | Haley |
| Personas are tested with situation cards instead of acting the same everywhere | Dickson；Belk |

“即时摩擦”在当前 prompt 里是营销决策工程化表达。  
它和有限理性、切换阻力、等待与学习成本有关，但当前不把它硬归给单一论文。

---

## 6. 固定注入与按场景开启

### 固定注入

每次消费者询问都可以保留：

- 有限注意力。
- 启发式线索。
- 参照点比较。
- 风险、损失感和后悔。
- 行动摩擦。
- persona-sensitive 社会影响。
- 习惯、惯性和复购触发。
- 心理账户。

### 按场景开启

下面这些更适合作为场景模块，而不是每轮强塞：

- 选择过载。
- 限时稀缺。
- 爆款热度。
- 礼物和面子消费。
- 身份表达。
- 沉没投入。
- 情绪冲动购买。

---

## 7. 写报告时建议采用的说法

### 稳妥说法

- 本项目用行为研究启发消费者代理的判断先验，使其在 persona 与场景边界内考虑有限注意、启发式、参照点、风险感、心理账户和习惯惯性。
- 这些行为先验用于暴露营销策略的潜在阻力与触发条件，不用于直接估计真实市场购买率。
- 行为学诊断输出帮助决策者看到“不行动的机制”，而不只是看到一句喜欢或不喜欢。

### 容易说过头的说法

不要写：

- 行为经济学证明本沙盘的消费者反馈等于真实消费者数据。
- 只要按这些偏差设计营销动作，就一定能提高转化。
- 每个不购买反馈都可以用认知偏差解释。

---

## 8. 参考文献清单

1. Simon, H. A. (1955). *A Behavioral Model of Rational Choice*. The Quarterly Journal of Economics.
2. Tversky, A., & Kahneman, D. (1974). *Judgment under Uncertainty: Heuristics and Biases*. Science.
3. Kahneman, D., & Tversky, A. (1979). *Prospect Theory: An Analysis of Decision under Risk*. Econometrica.
4. Thaler, R. (1985). *Mental Accounting and Consumer Choice*. Marketing Science.
5. Samuelson, W., & Zeckhauser, R. (1988). *Status Quo Bias in Decision Making*. Journal of Risk and Uncertainty.
6. Wood, W., & Neal, D. T. (2009). *The Habitual Consumer*. Journal of Consumer Psychology.
7. Muchnik, L., Aral, S., & Taylor, S. J. (2013). *Social Influence Bias: A Randomized Experiment*. Science.
8. Iyengar, S. S., & Lepper, M. R. (2000). *When Choice Is Demotivating: Can One Desire Too Much of a Good Thing?*. Journal of Personality and Social Psychology.
9. Haley, R. I. (1968). *Benefit Segmentation: A Decision-Oriented Research Tool*. Journal of Marketing.
10. Dickson, P. R. (1982). *Person-Situation: Segmentation's Missing Link*. Journal of Marketing.
11. Belk, R. W. (1975). *Situational Variables and Consumer Behavior*. Journal of Consumer Research.
12. Wind, Y. (1978). *Issues and Advances in Segmentation Research*. Journal of Marketing Research.
