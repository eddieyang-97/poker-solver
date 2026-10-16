# Repository instructions

- Scope: HEADS-UP NLHE river-only constrained decision analysis. The engine is not a full GTO solver.
- Keep the core deterministic and dependency-light; separate game logic from MCP transports.
- Never invent equilibrium frequencies or quote action EVs without computed outputs.
- Results depend on caller-supplied river arrival ranges and simplified no-raise tree.
- Maintain tests for card removal, rank evaluation, pot odds and transport authorization.
- Bound resource use on hosted endpoints. Secrets are environment variables only.
- Do not enable publicly unauthenticated solve requests or publish user-supplied tokens.
- Initial HTTP auth is a bearer token for compatible clients; ChatGPT OAuth integration is not complete.
- Educational/post-session use only; do not add live real-money in-hand assistance.
