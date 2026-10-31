# 吹牛策略研究 / Liar's Dice strategy notes

**目前没有经过验证的完整规则 GTO 策略。** 已验证的是特定规则假设下的精确概率，以及只准喊“四”的简化博弈。完整游戏的两种采样实验都明显未收敛，不应照搬其频率。以下用于理解和复盘。

**There is no validated full-game GTO policy yet.** Exact probabilities below assume the [provisional rules](RULES.md). The one-face equilibrium results describe a different, restricted game. Full-game sampling failed the quality checks; its opening frequencies are unsuitable for play recommendations.

## 先数自己的牌 / Count your own contribution

以“四”为例，默认每人单独计算再相加：

| Your hand | 飞 contribution | 斋 contribution |
| --- | ---: | ---: |
| 44411 | 6 | 3 |
| 44423 | 3 | 3 |
| 44235 | 2 | 2 |
| 11235 | 2 | 0 |
| 44444 | 7 | 7 |
| 11111 | 7 | 0 |

最后两列依赖尚未确认的特殊牌规则，尤其是全一和 斋 是否有混合奖励。不要把实体骰子数和有效贡献混为一谈。

The six/seven bonuses make ordinary binomial estimates wrong in the tail. They apply separately to each player's hand under this profile, so a bid can exceed the ten physical dice.

## 开局 / Opening bids

先找自己贡献较高的点数，再比较候选叫法的真实概率。不要把“最可能是真的”误当成“均衡最优”：开局也会暴露手牌，而且对手可以加叫，不一定开你。

Exact pre-action examples against an independent fair opponent roll:

| Own hand, bid face 4 | Mode | Bid quantity | Probability true |
| --- | --- | ---: | ---: |
| 44423 | 飞 | 3 | 100% |
| 44423 | 飞 | 4 | 86.8313% |
| 44423 | 飞 | 5 | 53.9095% |
| 44423 | 飞 | 6 | 20.9877% |
| 44411 | 飞 | 6 | 100% |
| 44411 | 飞 | 7 | 86.8313% |
| 44411 | 飞 | 8 | 53.9095% |
| 44411 | 斋 | 4 | 59.8122% |

These are counts out of 7,776, not fitted estimates. See `outputs/summary.json` for numerators and challenge EVs. A useful probability-only starting point is to compare the strongest faces and avoid blindly jumping to quantities unsupported by your contribution. This is a heuristic, not a computed optimal opening range. No validated full-game opening mix is available.

## 开 / Challenges

若你估计对方当前叫法为真的概率是 `p`，开他的即时期望值为 `1−2p`。`p<50%` 说明开是正期望，但不代表一定优于所有加叫。要比较开与继续叫的价值。

Use a probability **conditioned on the bidding history**, not just the prior table. For example, with own 44423, an independent pre-action bid of five fours 飞 is true with probability 53.9095%, giving challenge EV −0.0781893. That is not the correct EV after a strategic opponent actually chooses that bid unless its choice provides no information about its hand.

For each possible opponent hand h, update its prior weight by the likelihood of the opponent's observed bids under an explicit opponent strategy. Normalize, then evaluate the current claim against those weights. `beliefs.py` implements that operation and rejects an observed history with zero support. A supplied opponent model can be wrong; exact arithmetic about a bad model does not produce reliable human advice.

一个确定的边界：若你自己一手的有效贡献已达到当前数量，当前叫法必真，开必输。这不需要猜对手。相反，若所有仍可能的对手手牌都无法凑足，开必胜。

## 加叫、飞斋转换 / Raises and mode transitions

同模式暂按“数量更大，或数量相同且点数更大”。例如 `3个4 飞 → 3个5 飞`，或 `3个4 飞 → 4个2 飞`。这些顺序仍待确认。

飞→斋可少一个，但一不再百搭。必须重新算贡献，不能只看数量下降。比如自己 44411，`6个4 飞 → 5个4 斋` 时，自身贡献由六降到三；较低数量并不自动更安全。

Under these assumptions, with own 44411 the claim “six fours 飞” is certainly true, but “five fours 斋” has only a 19.6245% pre-action truth probability. That compares the two claims' truth, not their strategic value at a particular history. A mode switch also signals information and changes the opponent's available responses.

斋→飞至少加两个。例如 `3个4 斋 → 5个2 飞` 可行，`→4个6 飞` 不行。切换时是否可任意换点数，仍待确认。In the implemented profile the face can change freely on a mode switch. Recompute every target face from the same full hand; a contribution-only one-face table cannot evaluate this choice.

## 虚张声势 / Bluffing

GTO 的目标不是每次都叫真，而是让对手难以通过固定应对获利。但这里还没有算出完整游戏应有的诈唬比例。不要使用固定的“每三次诈一次”之类数字冒充均衡结果。

The validated toy game illustrates signalling. After 200,000 iterations, its average strategy challenges an opening of three fours with frequency approximately 98.47% / 60.22% / 0.66% for own effective contributions zero / one / two. Those responses depend on what the opponent's opening reveals in that **one-face** game, where every raise must increase the quantity and no other face or mode exists. They are not full-game challenge charts.

Practical study should vary truthful and weak bids under an explicit strategy model, examine the resulting posterior and opponent's response, and compare continuation values. A high unconditional truth probability is useful information; a universal bluffing percentage requires a substantially better solved model.

## 现在能信什么 / What to rely on now

- 精确概率：可复现，但依赖规则假设和明确的先验/对手策略。
- 简化博弈：有精确最佳应对检验，只适用于该简化动作树。
- 完整游戏近似：目前失败；不能给出可信的开局、加叫或诈唬频率。

The next useful milestone is confirmed house rules plus an approximation that survives stronger held-out response tests. Until then, use the exact calculations to understand risk and signalling, not as a complete-game GTO prescription.
