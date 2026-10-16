# poker-spot-study

Private hosted river-only NLHE post-session study plugin. Connect with OAuth to the separate Free Render solver. No local executor or database is required.

Tools: `solve_river` computes alternating CFR+ frequencies and action EVs in a no-raise/no-rake tree; `evaluate_river_call` computes exact weighted call EV against an assumed betting range. Supply full plausible ranges, report NashConv, and never label results full GTO.

[Source, hosting and validation evidence](https://github.com/eddieyang-97/poker-solver). Runtime limits include a 20-second timeout, one calculation at a time, 1500 iterations, 180 combos per side and 22500 pairs. Free hosting can sleep. No passwords, client secrets or bearer tokens are packaged.

Read `skills/river-review/SKILL.md` for the analysis workflow. The retained Python files are legacy local source; the configured tools execute on the hosted service.
