from pathlib import Path
import shutil
R=Path(__file__).resolve().parent;D=R/'joint-final'
shutil.copytree(R/'fused-final',D,ignore=shutil.ignore_patterns('__pycache__','*.so','*.pyc'))
p=D/'joint.cpp'
p.write_text(p.read_text()+'''
// Geometry and offset uncertainty have already been evaluated by the Python planner.
// Keep one common program per exposure; choose one target per fibre for each choice.
extern "C" void evaluate_cells(int n, int choices, int fibers, const int* fiber_ids,
    const double* chance, const int* target_ids, const double* const* gains,
    int* picks, double* totals) {
    std::vector<double> best(choices*fibers,0.0);
    std::fill(picks,picks+choices*fibers,-1);
    std::fill(totals,totals+choices,0.0);
    for(int j=0;j<n;++j) {
        for(int k=0;k<choices;++k) {
            double g=gains[j][k]*chance[j];
            int at=k*fibers+fiber_ids[j];
            int old=picks[at];
            if(g>0 && (g>best[at] || (g==best[at] && (old<0 || target_ids[j]>target_ids[old])))) {
                best[at]=g;picks[at]=j;
            }
        }
    }
    for(int k=0;k<choices;++k)
        for(int f=0;f<fibers;++f)totals[k]+=best[k*fibers+f];
}
''')
p=D/'native.py';p.write_text(p.read_text()+'''

CELL_LIB = None
if LIB is not None:
    try:
        LIB.evaluate_cells.argtypes=[C.c_int,C.c_int,C.c_int,C.POINTER(C.c_int),
            C.POINTER(C.c_double),C.POINTER(C.c_int),C.POINTER(C.POINTER(C.c_double)),
            C.POINTER(C.c_int),C.POINTER(C.c_double)]
        LIB.evaluate_cells.restype=None
        CELL_LIB=LIB
    except AttributeError:pass

class CellEvaluator:
    def __init__(self,fibers,choices,gains):
        self.fibers,self.choices,self.gains=fibers,choices,gains
        self.rows={}
    def evaluate(self,cells):
        rows=[(f,j,p) for f,items in cells.items() for j,p in items]
        n=len(rows);m=len(self.choices)
        for _,j,_ in rows:
            if j not in self.rows:self.rows[j]=(C.c_double*m)(*self.gains(j))
        fiber_ids=(C.c_int*n)(*(f for f,j,p in rows))
        probabilities=(C.c_double*n)(*(p for f,j,p in rows))
        targets=(C.c_int*n)(*(j for f,j,p in rows))
        pointers=(C.POINTER(C.c_double)*n)(*(C.cast(self.rows[j],C.POINTER(C.c_double)) for _,j,_ in rows))
        picks=(C.c_int*(m*self.fibers))();totals=(C.c_double*m)()
        CELL_LIB.evaluate_cells(n,m,self.fibers,fiber_ids,probabilities,targets,pointers,picks,totals)
        return rows,picks,totals
''')
p=D/'fusion_core/planner.py';s=p.read_text()
s=s.replace('from .bandfit import BandFit','from .bandfit import BandFit\nfrom native import CELL_LIB, CellEvaluator\n\nJOINT_PROGRAM = int(os.environ.get("FUSION_JOINT_PROGRAM", "1"))')
s=s.replace('        def gain(i, T):','        def gain(i, T, program=None):')
s=s.replace('            m = self.multipliers[self._band(model * band_scale)]\n            g = self.weight[i]', '            band = self._band(model * band_scale)\n            m = self.multipliers[band] if program is None or band == program else self.mismatch\n            g = self.weight[i]',1)
s=s.replace('dur_index = {T: k for k, T in enumerate(durations)}','choices = [(T,p) for T in durations for p in (("DARK","BRIGHT","BACKUP") if JOINT_PROGRAM else (None,))]\n        dur_index = {choice:k for k,choice in enumerate(choices)}')
s=s.replace('[gain(j, T) for T in durations]','[gain(j,T,p) for T,p in choices]')
s=s.replace('        vcache3: dict = {}','        cell_evaluator = CellEvaluator(self.grid.n,choices,gains) if CELL_LIB else None\n        vcache3: dict = {}')
a=s.index('            cell_gains = [[');b=s.index('\n        best_near = None',a)
s=s[:a]+'''            native_rows=native_picks=native_totals=None
            if cell_evaluator is not None:
                native_rows,native_picks,native_totals=cell_evaluator.evaluate(cells)
            else:
                cell_gains=[[(gains(j),p) for j,p in js] for js in cells.values()]
            found=None
            for k,(T,program) in enumerate(choices):
                if T not in durs:continue
                if native_totals is not None:
                    total=native_totals[k]
                else:
                    total=sum(max((g[k]*p for g,p in gl),default=0.) for gl in cell_gains)
                if total<=0:continue
                best_rate[0]=max(best_rate[0],total/T)
                net=total-lam*T
                if found is None or net>found[0]:found=(net,T,k,total,program)
            if found is None:return None
            net,T,k,total,program=found
            pick={};chance={}
            if native_picks is not None:
                for fib in cells:
                    at=native_picks[k*self.grid.n+fib]
                    if at>=0:
                        _,j,p=native_rows[at];pick[fib]=j;chance[fib]=p
            else:
                for fib,js in cells.items():
                    g,j,p=max((gains(j)[k]*p,j,p) for j,p in js)
                    if g>0:pick[fib]=j;chance[fib]=p
            return net,T,pick,total,chance,program
''' + s[b:]
s=s.replace('found[3], found[4])','found[3], found[4], found[5])')
s=s.replace('_, c_alt, c_az, T, pick, _, chance = best','_, c_alt, c_az, T, pick, _, chance, selected_program = best')
s=s.replace('        program = max(votes, key=lambda p:', '        program = selected_program or max(votes, key=lambda p:')
p.write_text(s)
import json
p=D/'observer.project.json';d=json.loads(p.read_text());d['environment']['FUSION_JOINT_PROGRAM']='1';p.write_text(json.dumps(d,indent=2)+'\n')
