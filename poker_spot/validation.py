"""Strict tool inputs shared by stdio and hosted transports."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .core import RiverSolver, cards, expand_range

Text = Annotated[str, Field(min_length=1, max_length=8000)]
Amount = Annotated[float, Field(gt=0, le=1e9, allow_inf_nan=False)]


class Inputs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    board: Text
    pot: Amount


class SolveInputs(Inputs):
    oop_range: Text
    ip_range: Text
    stack: Amount
    bet_sizes: list[Annotated[float, Field(gt=0, le=3, allow_inf_nan=False)]] = Field(
        default_factory=lambda: [0.5, 1.0], min_length=1, max_length=3)
    iterations: int = Field(default=700, ge=20, le=10000)
    oop_hand: Text | None = None
    ip_hand: Text | None = None


class CallInputs(Inputs):
    hero_hand: Text
    villain_betting_range: Text
    bet: Amount


def validate(name: str, arguments: dict, hosted: bool = False) -> dict:
    models = {'solve_river': SolveInputs, 'evaluate_river_call': CallInputs}
    if name not in models:
        raise ValueError('Unknown tool')
    args = models[name].model_validate(arguments).model_dump()
    if hosted and name == 'solve_river':
        if args['iterations'] > 1500:
            raise ValueError('Hosted iterations must be between 20 and 1500')
        board = cards(args['board'], 5)
        n0 = len(expand_range(args['oop_range'], board))
        n1 = len(expand_range(args['ip_range'], board))
        if max(n0, n1) > 180 or n0*n1 > 22500:
            raise ValueError('Range too large: maximum 180 combos per side and 22500 pairs')
    return args


def calculate(name: str, arguments: dict) -> dict:
    from .core import evaluate_river_call

    args = validate(name, arguments)
    if name == 'evaluate_river_call':
        return evaluate_river_call(**args)
    iterations = args.pop('iterations')
    oop = args.pop('oop_hand')
    ip = args.pop('ip_hand')
    return RiverSolver(**args).solve(iterations, oop, ip)
