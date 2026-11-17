"""Read-only instrumentation of selective work and its root-bound effect."""
from selective_frontier import SelectiveFrontier


class TracedSelective(SelectiveFrontier):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events = []
        self.nesting = 0

    def root_bounds(self):
        return tuple(float(self.prior @ (self.fixed + sum(getattr(n, name) for n in self.roots)))
                     for name in ('lower', 'upper'))

    def _refine(self, node, weights):
        outer = self.nesting == 0
        if outer:
            before = self.root_bounds()
            queries = self.stats['oracle_queries']
            expansions = self.stats['expanded_own_nodes']
        self.nesting += 1
        try:
            super()._refine(node, weights)
        finally:
            self.nesting -= 1
        if outer:
            after = self.root_bounds()
            self.events.append({'kind': 'query' if self.stats['oracle_queries'] > queries else 'expansion',
                                'queries': self.stats['oracle_queries']-queries,
                                'expansions': self.stats['expanded_own_nodes']-expansions,
                                'lower_before': before[0], 'upper_before': before[1],
                                'lower_after': after[0], 'upper_after': after[1],
                                'width_reduction': (before[1]-before[0])-(after[1]-after[0])})
