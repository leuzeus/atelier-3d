"""Experimental bounded LSMR factor; no normal equations or admission.

This retains the same metric operator and eliminated fixed controls as the
dense QR experiment. Numerical least-squares completion is reported separately
from material, seam, trust and contact gates.
"""
import math
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import LinearOperator, lsmr
from solve_piece_contact import require


class SparseMetricFactor:
    def __init__(self,cage,fixed,settings,budget):
        self.budget=budget;self.settings=settings;self.reports=[]
        self.initial=np.asarray(cage['target_cm'],dtype=float);uv=np.asarray(cage['uv_cm'],dtype=float)
        faces=np.asarray(cage['triangles']);n=len(uv);rows=2*len(faces)
        require(n<=settings['max_controls'] and rows<=settings['max_gradient_rows'],'SPARSE_DIMENSION_BUDGET')
        self.fixed=np.asarray(sorted(set(fixed)),dtype=int)
        require(len(self.fixed)>0 and len(self.fixed)==len(fixed),'EXPLICIT_DISTINCT_FIXES_REQUIRED')
        self.free=np.asarray([i for i in range(n) if i not in set(fixed)],dtype=int)
        inv=np.linalg.inv(uv[faces[:,1:]]-uv[faces[:,0,None]])
        coeff=np.stack((-inv.sum(axis=2),inv[:,:,0],inv[:,:,1]),axis=2)
        row_ids=np.tile(np.arange(rows),3)
        cols=np.concatenate([np.repeat(faces[:,k],2) for k in range(3)])
        values=np.concatenate([coeff[:,:,k].reshape(-1) for k in range(3)])
        self.operator=sparse.coo_matrix((values,(row_ids,cols)),shape=(rows,n)).tocsr()
        self.center=self.initial[self.fixed].mean(axis=0);self.local_initial=self.initial-self.center
        self.reg=math.sqrt(settings['position_penalty']);self.fixed_effect=self.operator[:,self.fixed]@self.local_initial[self.fixed]
        raw=sparse.vstack((self.operator[:,self.free],self.reg*sparse.eye(len(self.free))),format='csr')
        self.scale=np.sqrt(np.asarray(raw.multiply(raw).sum(axis=0)).ravel())
        require(np.isfinite(self.scale).all() and np.all(self.scale>0),'INVALID_COLUMN_SCALE')
        self.system=raw@sparse.diags(1/self.scale)
        def multiply(x):budget.check();return self.system@x
        def transpose(x):budget.check();return self.system.T@x
        self.linear=LinearOperator(self.system.shape,matvec=multiply,rmatvec=transpose,dtype=float)
        budget.check()

    def step(self,world):
        self.budget.check();deformation=(self.operator@(world-self.center)).reshape((-1,2,3))
        u,_,vt=np.linalg.svd(deformation,full_matrices=False)
        rhs=np.vstack(((u@vt).reshape((-1,3))-self.fixed_effect,self.reg*self.local_initial[self.free]))
        solved=[];reports=[]
        for k in range(3):
            answer=lsmr(self.linear,rhs[:,k],atol=self.settings['lsmr_tolerance'],btol=self.settings['lsmr_tolerance'],
                conlim=self.settings['max_condition_estimate'],maxiter=self.settings['max_linear_iterations'],
                x0=(world[self.free,k]-self.center[k])*self.scale)
            self.budget.check();x,stop,iterations,normr,normar,norma,conda,normx=answer
            residual=self.system@x-rhs[:,k];stationarity=self.system.T@residual
            recomputed=float(np.linalg.norm(stationarity))
            entry={'coordinate':k,'stop':stop,'iterations':iterations,'residual_norm':float(np.linalg.norm(residual)),
                'stationarity_norm':recomputed,'lsmr_stationarity_norm':float(normar),'operator_norm_estimate':float(norma),
                'condition_estimate':float(conda)}
            reports.append(entry);self.reports.append(entry)
            require(stop in (0,1,2,4,5),'SPARSE_LEAST_SQUARES_INCOMPLETE')
            require(np.isfinite(x).all() and math.isfinite(recomputed),'SPARSE_NONFINITE')
            solved.append(x/self.scale+self.center[k])
        result=np.asarray(world).copy();result[self.free]=np.asarray(solved).T;result[self.fixed]=self.initial[self.fixed]
        self.budget.check();return result
