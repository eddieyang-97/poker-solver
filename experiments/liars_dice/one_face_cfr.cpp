#include <bits/stdc++.h>
using namespace std;
constexpr int K=7; // contribution states 0,1,2,3,4,6,7
constexpr int M=1<<12; // 3..14
constexpr int A=13; // challenge or raise to any available
int value[K]={0,1,2,3,4,6,7};
double prob[K]={1024./7776,2560./7776,2560./7776,1280./7776,320./7776,30./7776,2./7776};
struct Info {float regret[A] = {}, avg[A] = {};};
vector<Info> infos;
static inline int idx(int p,int typ,int mask){return ((p*K +typ)*M+mask);}
static inline int getPlayer(int mask){return __builtin_popcount((unsigned)mask)&1;}
static inline int getLast(int mask){return 3+31-__builtin_clz((unsigned)mask);}
static inline int legalCount(int mask){return mask==0?12:1+14-getLast(mask);}
static inline int nextMask(int mask,int ai){if(mask==0) return 1<<ai;return mask | (1<<(getLast(mask)-3+ai));}
static inline double challenge(int mask,int t0,int t1){
  bool trueClaim = value[t0]+value[t1]>=getLast(mask);
  // player0 utility, if current player p0 opens challenge, then win if claim false.
  return ((getPlayer(mask)==0) != trueClaim)?1:-1;
}
static inline void getStrategy(const Info& inf,int na,double *s){double sm=0;for(int i=0;i<na;i++){s[i]=max(0.0,(double)inf.regret[i]);sm+=s[i];}if(sm<1e-17){for(int i=0;i<na;i++)s[i]=1.0/na;}else{for(int i=0;i<na;i++)s[i]/=sm;}}

double cfr(int mask,int t0,int t1,double reach0,double reach1){
  int player=getPlayer(mask), typ=(player==0?t0:t1), ni=idx(player,typ,mask);
  Info& inf=infos[ni];int na=legalCount(mask);
  double s[A],uv[A],v=0;
  getStrategy(inf,na,s);
  for(int a=0;a<na;a++){
    if(mask && a==0) uv[a]=challenge(mask,t0,t1);
    else {
      int nxt=nextMask(mask,a);
      uv[a]=cfr(nxt,t0,t1,player==0?reach0*s[a]:reach0,player==1?reach1*s[a]:reach1);
    }
    v+=s[a]*uv[a];
  }
  double rp=player==0?reach0:reach1;
  double ro=player==0?reach1:reach0;
  for(int a=0;a<na;a++){
    double delta=(player==0?1:-1)*ro*(uv[a]-v);
    inf.regret[a]=max(0.,(double)inf.regret[a]+delta);
    inf.avg[a]+=rp*s[a];
  }
  return v;
}
static inline void avgStrategy(int p,int typ,int mask,double *s){const Info& inf=infos[idx(p,typ,mask)];int na=legalCount(mask);double sum=0;for(int a=0;a<na;a++)sum+=inf.avg[a];if(sum==0){for(int a=0;a<na;a++)s[a]=1./na;}else{for(int a=0;a<na;a++)s[a]=inf.avg[a]/sum;}}

double br(int mask,int self,int myType,array<double,K> beliefs){
  int curr=getPlayer(mask);
  if(curr==self){
    double best=-1e100;
    for(int a=0;a<legalCount(mask);a++){
      double v=0;
      if(mask && a==0){for(int i=0;i<K;i++){int t0=self==0?myType:i,t1=self==1?myType:i; v+=beliefs[i]*(self==0?1:-1)*challenge(mask,t0,t1);}}
      else v=br(nextMask(mask,a),self,myType,beliefs);
      best=max(best,v);
    }
    return best;
  }else{
    double total=0;
    for(int a=0;a<legalCount(mask);a++){
      array<double,K> post;
      for(int i=0;i<K;i++){double s[A];avgStrategy(curr,i,mask,s);post[i]=beliefs[i]*s[a];}
      if(mask && a==0){for(int i=0;i<K;i++){int t0=self==0?myType:i,t1=self==1?myType:i; total+=post[i]*(self==0?1:-1)*challenge(mask,t0,t1);}}
      else total+=br(nextMask(mask,a),self,myType,post);
    }
    return total;
  }
}

double selfPlay(int mask,int t0,int t1){int curr=getPlayer(mask);double s[A];avgStrategy(curr,curr==0?t0:t1,mask,s);double ev=0;for(int a=0;a<legalCount(mask);a++) ev+=s[a]*(mask&&a==0?challenge(mask,t0,t1):selfPlay(nextMask(mask,a),t0,t1));return ev;}

int main(int argc,char**argv){int iterations=argc>1?atoi(argv[1]):10000;infos.resize(2*K*M);
  mt19937_64 rng(761245);
  discrete_distribution<int> dd(begin(prob),end(prob));
  auto start=chrono::steady_clock::now();
  for(int i=1;i<=iterations;i++){
    int t0=dd(rng),t1=dd(rng);
    cfr(0,t0,t1,1.,1.);
  }
  cout<<fixed<<setprecision(4);
  cerr<<"train "<<chrono::duration<double>(chrono::steady_clock::now()-start).count()<<" sec\n";
  // EV of average strategies via full enumeration
  double ev=0;
  for(int t0=0;t0<K;t0++)for(int t1=0;t1<K;t1++)ev+=prob[t0]*prob[t1]*selfPlay(0,t0,t1);
  cout<<"EV p0 self-play "<<ev<<"\n";
  double br0=0,br1=0;
  array<double,K> prior;for(int i=0;i<K;i++)prior[i]=prob[i];
  for(int i=0;i<K;i++) {br0+=prob[i]*br(0,0,i,prior);br1+=prob[i]*br(0,1,i,prior);}
  cout<<"BR player0 payoff "<<br0<<" BR player1 payoff "<<br1<<" NashConv "<<br0+br1<<"\n";
  cout<<"opening distribution for each hand type P(3),P(4),P(5),P(6),P(7),P(8),P(>8)\n";
  for(int t=0;t<K;t++){
    double s[A];avgStrategy(0,t,0,s);
    cout<<"my "<<value[t]<<" ("<<prob[t]<<") "; for(int a=0;a<6;a++)cout<<s[a]<<" ";double rest=0;for(int a=6;a<12;a++)rest+=s[a];cout<<rest<<"\n";
  }
  for(int opening: {3,4,5,6}){
    int mask=1<<(opening-3);cout<<"response to opening "<<opening<<":\n";
    for(int t=0;t<K;t++){
      double s[A];avgStrategy(1,t,mask,s);
      cout<<"my "<<value[t]<<": challenge="<<s[0]<<" raise-next="<<(legalCount(mask)>1?s[1]:0) <<" others="<<accumulate(s+2,s+legalCount(mask),0.)<<"\n";
    }
  }
  cerr<<"total "<<chrono::duration<double>(chrono::steady_clock::now()-start).count()<<" sec\n";
  return 0; // Explicit for the audit wrapper that renames main; no solver change.
}
