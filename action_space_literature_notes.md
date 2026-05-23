# 营销动作集论文备忘

## 1. 这份备忘是干什么的

这份文件记录当前 `ActionSpace` 与营销动作集借鉴的论文。

它回答四个问题：

1. 当前动作集为什么以营销 mix 为骨架。
2. 为什么当前实现保留 `positioning`、`product`、`price`、`channel`、`promotion`、`retention` 六个顶层类别。
3. 每个类别下面哪些动作更值得开放成搜索按钮。
4. 哪些研究启发不应该被直接误写成新的动作类别或真实市场结论。

和其他论文备忘的分工：

- 消费者行为学先验看 `consumer_behavior_literature_notes.md`。
- 策略家族与 UCB 搜索看 `strategy_family_literature_notes.md`。
- 本文件只管动作空间、marketing mix、顾客触点、关系动作和 offer 边界。

---

## 2. 当前采用结论

### 2.1 顶层类别先不改

当前代码中的 `ActionSpace` 仍保留六个顶层类别：

| 当前类别 | 在动作集里的角色 |
|---|---|
| `positioning` | 决定顾客先把你理解成什么价值和差异 |
| `product` | 决定核心 offer、产品形态、包装、体验和保障 |
| `price` | 决定价格架构、交易门槛和促销价值表达 |
| `channel` | 决定发现、购买、履约和服务触点怎么接上 |
| `promotion` | 决定信息、证据、内容形式和激活动作 |
| `retention` | 决定购买后的关系、复购触发和流失防守 |

这不是在说营销学里只有这六个标准动作。  
这是本项目对搜索空间的工程切法：

- 用 marketing mix 保留基本营销控制面。
- 把 positioning 单列，避免策略只有战术按钮没有顾客心智方向。
- 把 retention 单列，避免沙盘只优化首购。

### 2.2 文献借鉴后动作集新增的重点

本轮研究后，动作集文档要明确新增或强化下面这些按钮：

| 类别 | 建议强化的动作按钮 |
|---|---|
| `positioning` | 价值焦点、目标使用场景、比较参照、希望形成的品牌联想、支撑证据角度 |
| `product` | 核心 offer、版本/SKU、包装角色、上手支持、服务保障、退换或风险缓释 |
| `price` | 标准价、入门门槛、折扣/券/套餐、价格政策、价值理由和价格呈现方式 |
| `channel` | 发现触点、转化触点、履约/可得性、售后触点、线上线下或伙伴触点角色 |
| `promotion` | 主信息、内容形式、传播触点、可信证据、社交证明、试用或激活动作 |
| `retention` | onboarding、复购触发、补货/提醒、会员或忠诚动作、推荐动作、服务恢复与关系维护 |

这些按钮大多可以先写成 semantic options。  
只有价格、折扣、券、预算分配等确实需要数值边界的动作，才进入 `parameter_limits`。

---

## 3. 采用的论文

## 3.1 Borden：marketing mix 的控制面比四个词更细

### 基本信息

- 作者：Neil H. Borden
- 年份：1964
- 标题：*The Concept of the Marketing Mix*
- 期刊：*Journal of Advertising Research*

### 论文对动作集有用的点

Borden 回顾 marketing mix 时列出了一组管理者会组合的营销要素。  
除了 product planning、pricing、channels、advertising 和 promotions 外，还包含 branding、packaging、servicing、physical handling 以及 fact finding and analysis。

### 本项目采用什么

当前动作集采用它作为基础骨架：

- `product` 不只等于功能，还可以包含 packaging 和 servicing 相关 offer。
- `channel` 不只等于“在哪卖”，还要考虑可得性、履约和接触路径。
- `promotion` 不只等于广告投放，还要覆盖信息和激活动作。

### 不采用什么

`fact finding and analysis` 不作为 `DecisionAgent` 可乱改的营销动作。  
在本项目里，它属于市场证据、测试和验证问题，不属于为了赢沙盘而拨动的按钮。

## 3.2 Constantinides：4Ps 有用，但不能只站在品牌内部看按钮

### 基本信息

- 作者：E. Constantinides
- 年份：2006
- 标题：*The Marketing Mix Revisited: Towards the 21st Century Marketing*
- 期刊：*Journal of Marketing Management*

### 论文对动作集有用的点

这篇综述保留了 marketing mix 作为管理框架的价值，也梳理了它在消费者导向、互动性和 personalization 上的局限。

### 本项目采用什么

动作集不能只列：

- 打几折。
- 投哪个渠道。
- 发什么广告。

每个动作都要和下面这些上下文绑在一起：

- persona。
- 场景卡。
- 顾客阻力。
- 产品事实。
- 品牌和执行边界。

这也是为什么当前沙盘把 `ActionSpace` 当硬边界，而不是把动作集本身当作“最优营销答案”。

### 使用边界

这篇论文不要求我们把当前实现改成某一套新的固定 mix。  
它更像一个提醒：传统动作按钮要放进顾客和互动情境里测试。

## 3.3 Keller：定位和品牌意义不能被埋进促销文案

### 基本信息

- 作者：Kevin Lane Keller
- 年份：1993
- 标题：*Conceptualizing, Measuring, and Managing Customer-Based Brand Equity*
- 期刊：*Journal of Marketing*

### 论文对动作集有用的点

Keller 把 customer-based brand equity 连到消费者的 brand knowledge，并强调 brand awareness 与 brand image。

### 本项目采用什么

`positioning` 要继续单列，不能完全折叠进 `promotion`：

- 先规定希望顾客把品牌或 offer 理解成什么。
- 再让 `promotion` 决定用什么内容和触点把这个意义讲出去。

动作集因此补强这些 positioning 按钮：

- 价值焦点。
- 比较参照。
- 希望形成的品牌联想。
- 与竞品或替代方案的差异角度。
- 支撑定位的证据角度。

### 使用边界

品牌联想不是一句空口号。  
如果产品事实和证据不支持，`DecisionAgent` 不能为了定位漂亮就发明 claim。

## 3.4 Zeithaml：价格动作要连着价值判断，不只是打折数字

### 基本信息

- 作者：Valarie A. Zeithaml
- 年份：1988
- 标题：*Consumer Perceptions of Price, Quality, and Value: A Means-End Model and Synthesis of Evidence*
- 期刊：*Journal of Marketing*

### 论文对动作集有用的点

这篇论文把消费者对 price、quality 和 value 的判断放在同一条研究线上讨论。

### 本项目采用什么

`price` 动作集要区分：

- 数值交易条件：标准价、折扣率、券、套餐优惠、满减门槛。
- 语义价值解释：为什么这笔交易显得值、稳、低门槛或不伤品质感。

因此 `price` 不只开放“折扣更大”这个方向，还要允许：

- 入门价门槛。
- 套餐价值逻辑。
- 首购与回购激励分开。
- 价格政策和价格呈现方式。

### 使用边界

价格价值判断最终仍要通过 persona、场景和产品事实检验。  
消费者代理不能因此凭空报愿付价格数字。

## 3.5 Lemon and Verhoef：渠道、传播和购买后体验要按触点看

### 基本信息

- 作者：Katherine N. Lemon, Peter C. Verhoef
- 年份：2016
- 标题：*Understanding Customer Experience Throughout the Customer Journey*
- 期刊：*Journal of Marketing*

### 论文对动作集有用的点

这篇文章把 customer experience 放在 customer journey 中讨论，并强调多个 touchpoints、多个渠道和媒体环境会共同影响体验。

### 本项目采用什么

`channel` 不能只问“在哪卖”。  
它要允许搜索：

- 顾客先在哪发现。
- 在哪里比较和建立信任。
- 在哪里完成购买。
- 如何拿到货或接入服务。
- 购买后在哪里获得支持。

`promotion` 也不只问“发什么广告”，而要声明内容触点和证据角色。  
`retention` 要负责购买后的 onboarding、提醒、支持和复购触发。

### 使用边界

customer journey 是组织动作的视角，不是新的无边界搜索空间。  
每个触点仍要落回允许渠道、预算和执行能力。

## 3.6 Grönroos：动作集要留住关系动作

### 基本信息

- 作者：Christian Grönroos
- 年份：1994
- 标题：*From Marketing Mix to Relationship Marketing: Towards a Paradigm Shift in Marketing*
- 期刊：*Management Decision*

### 论文对动作集有用的点

这篇论文讨论从单纯 marketing mix 管理视角转向 relationship marketing 的必要性。

### 本项目采用什么

`retention` 继续作为独立动作类别，而不是被折回 promotion：

- onboarding 和使用陪伴。
- 复购提醒与补货触发。
- 会员、忠诚和推荐动作。
- 售后关怀与服务恢复。
- 关系维护，而不只是下一次促销。

### 使用边界

不是每个产品都天然需要复杂会员体系。  
关系动作只有在产品复购逻辑、服务逻辑或顾客关系价值成立时才值得开放。

## 3.7 Vargo and Lusch：产品动作要承认服务和使用价值

### 基本信息

- 作者：Stephen L. Vargo, Robert F. Lusch
- 年份：2004
- 标题：*Evolving to a New Dominant Logic for Marketing*
- 期刊：*Journal of Marketing*

### 论文对动作集有用的点

这篇文章推动营销理论从 goods-dominant 的视角看向服务、交换过程和使用中的价值。

### 本项目采用什么

当前 `product` 动作继续包含：

- 使用体验。
- 上手支持。
- 服务保障。
- 交付和售后相关承诺。

这些动作不是“产品外的杂项”，而是 offer 如何真正被顾客用起来的一部分。  
如果售后触点和长期关系更强，也可以由 `retention` 承接。

### 使用边界

服务逻辑不能让 `DecisionAgent` 凭空扩大产品能力。  
没有供应、履约或售后边界支持的服务承诺，仍然要被 `ActionSpace` 和 critic 拦住。

---

## 4. 文献到动作类别的映射

| 动作类别 | 主要研究借鉴 | 当前动作集怎么落 |
|---|---|---|
| `positioning` | Keller；Constantinides | 价值焦点、品牌联想、比较参照和证据方向 |
| `product` | Borden；Vargo and Lusch | 产品规划、包装、服务、保障和使用体验 |
| `price` | Borden；Zeithaml | 价格结构、促销价格、价值解释和交易门槛 |
| `channel` | Borden；Lemon and Verhoef | 发现、购买、履约和售后触点 |
| `promotion` | Borden；Keller；Lemon and Verhoef | 信息、内容形式、证据、社交证明和激活 |
| `retention` | Grönroos；Lemon and Verhoef | onboarding、复购触发、服务恢复、关系和推荐 |

---

## 5. 对 `ActionSpace` 的实现含义

当前代码不用因为这批论文立刻加新顶层 category。  
更合适的下一步是按产品配置：

- `allowed_categories`
- `allowed_product_claims`
- `parameter_limits`
- `parameter_options`

建议优先把下面这些做成 semantic options：

| 类别 | 候选 option 字段 |
|---|---|
| `positioning` | `value_focus`、`comparison_frame`、`association_target`、`proof_angle` |
| `product` | `hero_benefit`、`offer_shape`、`packaging_role`、`usage_support`、`service_assurance` |
| `price` | `price_architecture`、`value_message`、`entry_incentive_type`、`repeat_incentive_type` |
| `channel` | `discovery_touchpoint`、`conversion_touchpoint`、`fulfillment_mode`、`post_purchase_touchpoint` |
| `promotion` | `message_angle`、`content_format`、`evidence_format`、`activation_type` |
| `retention` | `onboarding_mode`、`repeat_trigger`、`relationship_action`、`service_recovery_action` |

数值项再单独给 limit，例如：

- `base_price`
- `discount_rate`
- `coupon_value`
- `bundle_saving`
- `channel_budget_share`

没有产品事实、预算边界或执行边界支持时，不开放对应 limit。

---

## 6. 写报告时建议采用的说法

### 稳妥说法

- 本项目以 marketing mix 研究为动作空间骨架，并用品牌意义、顾客旅程和关系营销研究补足 positioning、触点与留存动作。
- 当前动作空间保留六个顶层 category，以便搜索具体营销动作时同时控制首购、体验和复购关系。
- 文献启发用于决定动作按钮和边界，不把动作集本身说成已被证明的最优营销模型。

### 容易说过头的说法

不要写：

- 论文证明当前六类动作集一定覆盖所有营销决策。
- 只要把 customer journey 触点写全，策略就会赢。
- relationship marketing 意味着所有产品都应该上会员、积分和订阅。

---

## 7. 参考文献清单

1. Borden, N. H. (1964). *The Concept of the Marketing Mix*. Journal of Advertising Research.
2. Constantinides, E. (2006). *The Marketing Mix Revisited: Towards the 21st Century Marketing*. Journal of Marketing Management.
3. Keller, K. L. (1993). *Conceptualizing, Measuring, and Managing Customer-Based Brand Equity*. Journal of Marketing.
4. Zeithaml, V. A. (1988). *Consumer Perceptions of Price, Quality, and Value: A Means-End Model and Synthesis of Evidence*. Journal of Marketing.
5. Lemon, K. N., & Verhoef, P. C. (2016). *Understanding Customer Experience Throughout the Customer Journey*. Journal of Marketing.
6. Grönroos, C. (1994). *From Marketing Mix to Relationship Marketing: Towards a Paradigm Shift in Marketing*. Management Decision.
7. Vargo, S. L., & Lusch, R. F. (2004). *Evolving to a New Dominant Logic for Marketing*. Journal of Marketing.
