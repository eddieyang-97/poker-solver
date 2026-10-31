from itertools import product
from collections import Counter
from math import comb
hands = list(product(range(1,7),repeat=5))

def fly_count(hand, face=4):
    m = sum(d==1 or d==face for d in hand)
    if m==5:
        return 7 if len(set(hand))==1 else 6
    return m

def zhai_count(hand, face=4):
    m = sum(d==face for d in hand)
    # 5 identical target face => 7; no 1 wild
    return 7 if m==5 else m

cf = Counter(fly_count(hand) for hand in hands)
cz = Counter(zhai_count(hand) for hand in hands)
print('fly freq', sorted(cf.items()), 'zhai freq', sorted(cz.items()))
print('fly baseline 1 or 4 count',[(k,round(v/7776,6)) for k,v in sorted(cf.items())])

for hand in [(4,4,4,1,1), (4,4,4,2,3), (4,4,2,3,5), (1,1,2,3,5), (4,4,4,4,4)]:
    for mode,fn,dist in [('fly',fly_count,cf),('zhai',zhai_count,cz)]:
        own=fn(hand)
        probs=[sum(v for c,v in dist.items() if own+c>=n)/7776 for n in range(3,11)]
        print(hand,mode,own, ' '.join(f'{n}:{p*100:6.2f}%' for n,p in zip(range(3,11),probs)))
