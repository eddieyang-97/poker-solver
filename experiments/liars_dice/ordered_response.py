"""Incumbent-action ordering with the unchanged finite-response recurrence.

Priority only allocates expansion work. All legal actions/positive opponent
branches remain in the bounds; choices still maximize pooled own-hand values.
Historical ResponseSearch source remains frozen for its recorded corpora.
"""
import numpy as np

from bounded_response import ResponseSearch


class OrderedResponseSearch(ResponseSearch):
    def __init__(self,game,guide,model,seat,depth=2,max_nodes=128,incumbent=None):
        super().__init__(game,guide,model,seat,depth,max_nodes,incumbent)
        self.priority={} if incumbent is None else incumbent.decisions.copy()
        self.own_prior=np.asarray(game.prior)

    def _search(self,history,mass,remaining):
        self.stats['maximum_history']=max(self.stats['maximum_history'],len(history))
        legal=self.game.actions(history)
        challenge=self._claim_value(history[-1],mass,True) if history else None
        if legal==(-1,):
            self.stats['forced_challenges']+=1
            return challenge,challenge.copy()
        if remaining==0 or self.stats['expanded_own_nodes']>=self.max_nodes:
            if challenge is None: raise AssertionError('Opening must be expanded')
            self.stats['depth_frontiers' if remaining==0 else 'budget_frontiers']+=1
            if history in self.bounds:
                self.stats['incumbent_frontiers']+=1
                return self.bounds[history]
            return challenge,np.full(len(mass),mass.sum())
        self.stats['expanded_own_nodes']+=1
        best_lower,best_upper=np.full(len(mass),-np.inf),np.full(len(mass),-np.inf)
        chosen=np.full(len(mass),legal[0],dtype=int)
        old=self.priority.get(history)
        if old is not None:
            weights={a:float(self.own_prior[old==a].sum()) for a in legal}
            legal=tuple(sorted(legal,key=lambda a:(-weights[a],self.game.actions(history).index(a))))
        for action in legal:
            if action==-1:
                lower,upper=challenge,challenge
            else:
                lower,upper=np.zeros(len(mass)),np.zeros(len(mass))
                prefix=history+(action,)
                for response,child_mass in self._branches(1-self.seat,prefix,mass):
                    if response==-1:
                        value=self._claim_value(action,child_mass,False)
                        lower+=value;upper+=value
                    else:
                        child_lower,child_upper=self._search(prefix+(response,),child_mass,remaining-1)
                        lower+=child_lower;upper+=child_upper
            better=lower>best_lower
            chosen[better]=action
            best_lower=np.maximum(best_lower,lower)
            best_upper=np.maximum(best_upper,upper)
        chosen.flags.writeable=False
        if history in self.bounds:
            old_lower,old_upper=self.bounds[history]
            if (best_lower<old_lower-1e-12).any() or (best_upper>old_upper+1e-12).any():
                raise ArithmeticError('Refinement invalidated incumbent bounds')
        best_lower.flags.writeable=best_upper.flags.writeable=False
        self.decisions[history]=chosen
        self.bounds[history]=best_lower,best_upper
        return best_lower,best_upper


def response_envelope(stages,target_sha256):
    """Per-seat feasible maxima and optimistic minima for one exact target."""
    if (not stages or any(s['target_file_sha256']!=target_sha256 for s in stages)
            or any(s['target_probabilities_sha256']!=stages[0]['target_probabilities_sha256']
                   or s['game']!=stages[0]['game'] for s in stages)):
        raise ValueError('Envelope requires one identical target fingerprint')
    seats=[]
    for seat in (0,1):
        rows=[]
        for stage in stages:
            record=stage['seats'][seat]
            if record['seat']!=seat or not np.isfinite([record['lower'],record['upper']]).all():
                raise ValueError('Invalid seat bounds')
            if not -1-1e-12<=record['lower']<=record['upper']+1e-12<=1+2e-12:
                raise ValueError('Invalid bound direction/range')
            rows.append((stage['label'],record))
        lo=max(rows,key=lambda x:x[1]['lower']);hi=min(rows,key=lambda x:x[1]['upper'])
        if lo[1]['lower']>hi[1]['upper']+1e-12: raise ArithmeticError('Inconsistent same-target bounds')
        seats.append({'seat':seat,'lower':lo[1]['lower'],'upper':max(lo[1]['lower'],hi[1]['upper']),
                      'lower_stage':lo[0],'upper_stage':hi[0],'lower_plan':lo[1]['plan']})
    lower=max(0.,sum(s['lower'] for s in seats));upper=min(2.,sum(s['upper'] for s in seats))
    if lower>upper+1e-12: raise ArithmeticError('Inconsistent zero-sum response bounds')
    upper=max(lower,upper)
    return {'seats':seats,'nashconv_lower':lower,'nashconv_upper':upper,'width':upper-lower,
            'exploitability_lower':lower/2,'exploitability_upper':upper/2,
            'arithmetic':'float64 structural envelope, not interval certified'}
