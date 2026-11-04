"""Count legal suffix states without allocating their private-hand/action tables."""
from game import Game


def inventory(game=None, recalls=(1,2,3)):
    game = Game() if game is None else game
    bids = sorted(range(len(game.bids)), key=lambda a:game.bids[a].rank)
    successors = {a:tuple(b for b in game.actions((a,)) if b != -1) for a in bids}
    parity = {a:set() for a in bids}
    for a in game.actions(()):
        parity[a].add(0)  # actor making the FIRST bid of the suffix
    for a in bids:
        for b in successors[a]:
            if game.bids[b].rank <= game.bids[a].rank:
                raise ValueError('Expected strictly increasing rank')
            parity[b].update(1-p for p in parity[a])

    def extend(counts):
        result = {}
        for a, count in counts.items():
            for b in successors[a]:
                result[b] = result.get(b, 0)+count
        return result

    result = []
    for m in recalls:
        if type(m) is not int or not 1 <= m <= 3:
            raise ValueError('Inventory supports recall 1..3')
        states, entries = 1, len(game.actions(()))
        prefixes = dict.fromkeys(game.actions(()), 1)
        for _ in range(1,m):
            states += sum(prefixes.values())
            entries += sum(c*len(game.actions((a,))) for a,c in prefixes.items())
            prefixes = extend(prefixes)
        suffixes = {a:len(parity[a]) for a in bids if parity[a]}
        for _ in range(1,m):
            suffixes = extend(suffixes)
        states += sum(suffixes.values())
        entries += sum(c*len(game.actions((a,))) for a,c in suffixes.items())
        cells = entries*len(game.hands)
        result.append({'recall':m, 'public_states_with_seat':states,
                       'infosets':states*len(game.hands), 'public_action_edges':entries,
                       'action_entries':cells, 'two_float64_tables_bytes':16*cells,
                       'two_float32_tables_bytes':8*cells})
    return {'rules':'confirmed single-round 5v5, all legal actions, no hand abstraction',
            'includes_forced_action_rows':True, 'seat_symmetry_merged':False,
            'excludes':'graph metadata, working arrays, allocator overhead and checkpoints',
            'memory_is':'calculated dense table storage, not allocated or measured RSS',
            'reachable_bids':sum(bool(p) for p in parity.values()), 'rows':result}
