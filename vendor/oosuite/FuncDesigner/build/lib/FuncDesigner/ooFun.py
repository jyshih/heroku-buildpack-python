# created by Dmitrey
PythonSum = sum
from numpy import inf, asfarray, copy, all, any, atleast_2d, zeros, dot, asarray, atleast_1d, \
ones, ndarray, where, array, nan, vstack, eye, array_equal, isscalar, log, hstack, sum as npSum, prod, nonzero,\
isnan, asscalar, zeros_like, ones_like, amin, amax, logical_and, logical_or, isinf, logical_not, logical_xor, flipud, \
tile, float64, searchsorted, int8, int16, int32, int64, isfinite, log2, string_, asanyarray, bool_
#from logic import AND
#from traceback import extract_stack 
try:
    from bottleneck import nanmin, nanmax
except ImportError:
    from numpy import nanmin, nanmax
    
from FDmisc import FuncDesignerException, Diag, Eye, pWarn, scipyAbsentMsg, scipyInstalled, \
raise_except, DiagonalType, isPyPy
from ooPoint import ooPoint
from FuncDesigner.multiarray import multiarray
from Interval import Interval, adjust_lx_WithDiscreteDomain, adjust_ux_WithDiscreteDomain
import inspect
from baseClasses import OOArray, Stochastic

Copy = lambda arg: asscalar(arg) if type(arg)==ndarray and arg.size == 1 else arg.copy() if hasattr(arg, 'copy') else copy(arg)
Len = lambda x: 1 if isscalar(x) else x.size if type(x)==ndarray else x.values.size if isinstance(x, Stochastic) else len(x)

try:
    from DerApproximator import get_d1, check_d1
    DerApproximatorIsInstalled = True
except:
    DerApproximatorIsInstalled = False


try:
    import scipy
    #from scipy import sparse
    from scipy.sparse import hstack as HstackSP, vstack as VstackSP, isspmatrix_csc, isspmatrix_csr, eye as SP_eye, lil_matrix as SparseMatrixConstructor
    def Hstack(Tuple):
        ind = where([isscalar(elem) or prod(elem.shape)!=0 for elem in Tuple])[0].tolist()
        elems = [Tuple[i] for i in ind]
        if any([isspmatrix(elem) for elem in elems]):
            return HstackSP(elems)
        
        s = set([(0 if isscalar(elem) else elem.ndim) for elem in elems])
        ndim = max(s)
        if ndim <= 1:  return hstack(elems)
        assert ndim <= 2 and 1 not in s, 'bug in FuncDesigner kernel, inform developers'
        return hstack(elems) if 0 not in s else hstack([atleast_2d(elem) for elem in elems])
    def Vstack(Tuple):
        ind = where([isscalar(elem) or prod(elem.shape)!=0 for elem in Tuple])[0].tolist()
        elems = [Tuple[i] for i in ind]
        if any([isspmatrix(elem) for elem in elems]):
            return VstackSP(elems)
        else:
            return vstack(elems)
#        s = set([(0 if isscalar(elem) else elem.ndim) for elem in elems])
#        ndim = max(s)
#        if ndim <= 1:  return hstack(elems)
#        assert ndim <= 2 and 1 not in s, 'bug in FuncDesigner kernel, inform developers'
#        return hstack(elems) if 0 not in s else hstack([atleast_2d(elem) for elem in elems])        
    from scipy.sparse import isspmatrix
except:
    scipy = None
    isspmatrix = lambda *args,  **kwargs:  False
    Hstack = hstack
    Vstack = vstack

class oofun:
    #TODO:
    #is_oovarSlice = False
    tol = 0.0
    d = None # derivative
    input = None#[] 
    #usedIn =  set()
    is_oovar = False
    #is_stoch = False
    isConstraint = False
    #isDifferentiable = True
    discrete = False
    _isSum = False
    _isProd = False
    
    stencil = 3 # used for DerApproximator
    
    #TODO: modify for cases where output can be partial
    evals = 0
    same = 0
    same_d = 0
    evals_d  = 0

    # finite-difference aproximation step
    diffInt = 1.5e-8
    maxViolation = 1e-2
    _unnamedFunNumber = 1
    _lastDiffVarsID = 0
    _lastFuncVarsID = 0
    _lastOrderVarsID = 0
    criticalPoints = None
    vectorized = False
    getDefiniteRange = None
    _neg_elem = None # used in render into quadratic 

    _usedIn = 0
    _level = 0
    #_directlyDwasInwolved = False
    _id = 0
    _BroadCastID = 0
    _broadcast_id = 0
    _point_id = 0
    _point_id1 = 0
    _f_key_prev = None
    _f_val_prev = None
    _d_key_prev = None
    _d_val_prev = None
    __array_priority__ = 15# set it greater than 1 to prevent invoking numpy array __mul__ etc
    
    hasDefiniteRange = True
    
    pWarn = lambda self, msg: pWarn(msg)
    
    def disp(self, msg): 
        print(msg)
    
    nlh = lambda self, *args, **kw: raise_except("probably you have involved boolean operation on continuous function, that is error")
    lh = lambda self, *args, **kw: raise_except("probably you have involved boolean operation on continuous function, that is error")
    
    def __getattr__(self, attr):
        if attr == '__len__':
            # TODO: fix it
            if isPyPy:
                return 1
            else:
                raise AttributeError('using len(oofun) is not possible yet, try using oofun.size instead')
        elif attr == 'isUncycled':
            self._getDep()
            return self.isUncycled
        elif attr == 'isCostly':
            return self.d is None
        elif attr != 'size': 
            raise AttributeError('you are trying to obtain incorrect attribute "%s" for FuncDesigner oofun "%s"' %(attr, self.name))
        
        # to prevent creating of several oofuns binded to same oofun.size
        r = oofun(lambda x: asarray(x).size, self, discrete = True, getOrder = lambda *args, **kwargs: 0)
        self.size = r 

        return r

    """                                         Class constructor                                   """

    def __init__(self, fun, input=None, *args, **kwargs):
    #def __init__(self, fun, input=[], *args, **kwargs):
        assert len(args) == 0 #and input is not None
        self.fun = fun
        
        #self._broadcast_id = 0
        self._id = oofun._id
        self.attachedConstraints = set()
        self.args = ()
        oofun._id += 1 # CHECK: it should be int32! Other types cannot be has keys!

        if 'name' not in kwargs.keys():
            self.name = 'unnamed_oofun_' + str(oofun._unnamedFunNumber)
            oofun._unnamedFunNumber += 1
        
        for key, item in kwargs.items():
            #assert key in self.__allowedFields__ # TODO: make set comparison
            setattr(self, key, item)
            
        if isinstance(input, (tuple, list)): 
            self.input = [(elem if isinstance(elem, (oofun, OOArray)) else array(elem, 'float')) for elem in input]
        elif input is not None: 
            self.input = [input]
        else: 
            self.input = [None] # TODO: get rid of None, use input = [] instead

        # TODO: fix it for ooarray!
#        if input is not None:
#            levels = [0]
#            for elem in self.input: # if a
#                if isinstance(elem, oofun):
#                    elem._usedIn += 1
#                    levels.append(elem._level)
#            self._level = max(levels)+1

    __hash__ = lambda self: self._id
        
    def attach(self, *args,  **kwargs):
        if len(kwargs) != 0:
            raise FuncDesignerException('keyword arguments are not implemented for FuncDesigner function "attach"')
        assert len(args) != 0
        Args = args[0] if len(args) == 1 and type(args[0]) in (tuple, list, set) else args
        for arg in Args:
            if not isinstance(arg, BaseFDConstraint):
                raise FuncDesignerException('the FD function "attach" currently expects only constraints')
        self.attachedConstraints.update(Args)
        return self
        
    def removeAttachedConstraints(self):
        self.attachedConstraints = set()    
    __repr__ = lambda self: self.name
    
    def _interval_(self, domain, dtype):
        criticalPointsFunc = self.criticalPoints
        if len(self.input) == 1 and criticalPointsFunc is not None:
            arg_lb_ub, definiteRange = self.input[0]._interval(domain, dtype)
            arg_infinum, arg_supremum = arg_lb_ub[0], arg_lb_ub[1]
            if (not isscalar(arg_infinum) and arg_infinum.size > 1) and not self.vectorized:
                raise FuncDesignerException('not implemented for vectorized oovars yet')
            tmp = [arg_lb_ub]
            if criticalPointsFunc is not False:
                tmp += criticalPointsFunc(arg_lb_ub)
            Tmp = self.fun(vstack(tmp))
            
            if self.getDefiniteRange is not None:
                definiteRange = logical_and(definiteRange, self.getDefiniteRange(arg_infinum, arg_supremum))
            
            if not self.hasDefiniteRange:
                # TODO: rework it as matrix operations
                definiteRange = False #logical_and(definiteRange, a)

            #indDefinite = all(isfinite)
            #Tmp = self.fun(array(tmp))
            return vstack((nanmin(Tmp, 0), nanmax(Tmp, 0))), definiteRange
        else:
            raise FuncDesignerException('interval calculations are unimplemented for the oofun (%s) yet' % self.name)
    
    def interval(self, domain, dtype = float, resetStoredIntervals = True):
        if type(domain) != ooPoint:
            domain = ooPoint(domain, skipArrayCast = True)
        lb_ub, definiteRange = self._interval(domain, dtype) #if type(domain) != ooPoint else self._interval2(domain, dtype)
        
        # TODO: MB GET RID OF IT?
        if resetStoredIntervals:
            domain.storedIntervals = {}
        
        return Interval(lb_ub[0], lb_ub[1], definiteRange)
    
    def _interval(self, domain, dtype):
        tmp = domain.dictOfFixedFuncs.get(self, None)
        if tmp is not None:
            return tile(tmp, (2, 1)), True
            
        v = domain.modificationVar

        if v is None or ((v not in self._getDep() or self.is_oovar) and self is not v): 
            r = domain.storedIntervals.get(self, None)
            if r is not None: 
                return r
        
        if v is not None:
            r = domain.localStoredIntervals.get(self, None)
            if r is not None: 
                return r
       
        r = self._interval_(domain, dtype)
        if domain.useSave:
            domain.storedIntervals[self] = r 
        if v is not None:
            domain.localStoredIntervals[self] = r
        return r
            
    
    def iqg(self, domain, dtype = float, lb=None, ub=None, UB = None):
        if type(domain) != ooPoint:
            domain = ooPoint(domain, skipArrayCast=True)
            domain.isMultiPoint=True
        domain.useSave = True
        r0 = self.interval(domain, dtype, resetStoredIntervals = False)
        
        r0.lb, r0.ub = atleast_1d(r0.lb).copy(), atleast_1d(r0.ub).copy() # is copy required?
        
        # TODO: get rid of useSave
        domain.useSave = False
        
        
        # TODO: rework it with indexation of required data
        if lb is not None and ub is not None:
            
            #debug start
#            ind = logical_or(logical_or(r0.ub < lb, r0.lb > ub), all(logical_and(r0.lb >= lb, r0.ub <= ub)))
#            sz = where(ind)[0]
#            if sz.size != asarray(r0.lb).size:
#                print('!', sz.size, asarray(r0.lb).size)
            #debug end
            ind = logical_or(logical_or(r0.ub < lb, r0.lb > ub), all(logical_and(r0.lb >= lb, r0.ub <= ub)))
        elif UB is not None:
            #print(where(r0.lb > UB)[0].size, asarray(r0.lb).size)
            ind = r0.lb > UB
        else:
            ind = None
        
        useSlicing = False
        
#        print('-'*20)
#        print(r0.lb.size)
        if ind is not None:
            
            if all(ind):
                return {}, r0
            j = where(~ind)[0]
            #DOESN'T WORK FOR FIXED OOVARS AND DefiniteRange != TRUE YET
            if 0 and j.size < 0.85*ind.size:  # at least 15% of values to skip
                useSlicing = True
                tmp = []
                for key, val in domain.storedIntervals.items():
                    Interval, definiteRange = val
                    if type(definiteRange) not in (bool, bool_):
                        definiteRange = definiteRange[j]
                    tmp.append((key, (Interval[:, j], definiteRange)))
                _storedIntervals = dict(tmp)
                
                Tmp = []
                for key, val in domain.storedSums.items():
                    # TODO: rework it
                    R0, DefiniteRange0 = val.pop(-1)
                    #R0, DefiniteRange0 = val[-1]
                    R0 = R0[:, j]
                    if type(DefiniteRange0) not in (bool, bool_):
                        DefiniteRange0 = DefiniteRange0[j]
                    tmp = []
                    for k,v in val.items():
                        # TODO: rework it
#                        if k is (-1): continue
                        v = v[:, j]
                        tmp.append((k,v))
                    val = dict(tmp)
                    val[-1] = (R0, DefiniteRange0)
                    Tmp.append((key,val))
                _storedSums = dict(Tmp)
                #domain.storedSums = dict(tmp)
                
                Tmp = []
                for key, val in domain.items():
                    lb_,ub_ = val
                    # TODO: rework it when lb, ub will be implemented as 2-dimensional
                    Tmp.append((key, (lb_[j],ub_[j])))
                dictOfFixedFuncs = domain.dictOfFixedFuncs
                domain2 = ooPoint(Tmp, skipArrayCast=True)
                domain2.storedSums = _storedSums
                domain2.storedIntervals = _storedIntervals
                domain2.dictOfFixedFuncs = dictOfFixedFuncs
                domain2.isMultiPoint=True
                domain = domain2
                
        domain.useAsMutable = True
        
        r = {}
        Dep = (self._getDep() if not self.is_oovar else set([self])).intersection(domain.keys())
        
##        #debug
#        if useSlicing:
##            print('ind', ind)
##            print('r0.ub:', r0.ub)
#            r1 = {}
#            for i, v in enumerate(Dep):
#                domain.modificationVar = v
#                r_l, r_u = self._iqg(domain, dtype, r0)
#                
#                domain2.useAsMutable = True
#                domain2.modificationVar = v
#                r_l2, r_u2 = self._iqg(domain2, dtype, r0)
#                if useSlicing and not (r_l is r0):# r_l is r0 when array_equal(lb, ub)
#                    lf1, lf2, uf1, uf2 = r_l2.lb, r_u2.lb, r_l2.ub, r_u2.ub
#                    Lf1, Lf2, Uf1, Uf2 = Copy(r0.lb), Copy(r0.lb), Copy(r0.ub), Copy(r0.ub)
#                    Lf1[:, j], Lf2[:, j], Uf1[:, j], Uf2[:, j] = lf1, lf2, uf1, uf2
#                    r_l2.lb, r_u2.lb, r_l2.ub, r_u2.ub = Lf1, Lf2, Uf1, Uf2
#    #                if type(r0.definiteRange) not in (bool, bool_) and r0.definiteRange.size != 1:
#    #                    d1, d2 = r_l.definiteRange, r_u.definiteRange
#    #                    D1, D2 = Copy(r0.definiteRange), Copy(r0.definiteRange)
#    #                    D1[:, j], D2[:, j] = d1, d2
#    #                    r_l.definiteRange, r_u.definiteRange = D1, D2
#                from numpy.linalg import norm
#                if norm(r_u2.ub- r_u.ub) > 1e-7: 
#                    print('uu')
#                    print(r_u2.ub, r_u.ub)
#                    print(r_u2.ub - r_u.ub)
##                    raise 0                    
#                input()

#            domain = domain2 
##        #debug end
        
        for i, v in enumerate(Dep):
            domain.modificationVar = v
            r_l, r_u = self._iqg(domain, dtype, r0)
            if useSlicing and r_l is not r0:# r_l is r0 when array_equal(lb, ub)
                lf1, lf2, uf1, uf2 = r_l.lb, r_u.lb, r_l.ub, r_u.ub
                Lf1, Lf2, Uf1, Uf2 = Copy(r0.lb), Copy(r0.lb), Copy(r0.ub), Copy(r0.ub)
                Lf1[:, j], Lf2[:, j], Uf1[:, j], Uf2[:, j] = lf1, lf2, uf1, uf2
                r_l.lb, r_u.lb, r_l.ub, r_u.ub = Lf1, Lf2, Uf1, Uf2
                if type(r0.definiteRange) not in (bool, bool_):
                    print('!')
                    d1, d2 = r_l.definiteRange, r_u.definiteRange
                    D1, D2 = atleast_1d(r0.definiteRange).copy(), atleast_1d(r0.definiteRange).copy()
                    D1[j], D2[j] = d1, d2
                    r_l.definiteRange, r_u.definiteRange = D1, D2
                
            r[v] = r_l, r_u
            if not self.isUncycled:
                lf1, lf2, uf1, uf2 = r_l.lb, r_u.lb, r_l.ub, r_u.ub
                lf, uf = nanmin(vstack((lf1, lf2)), 0), nanmax(vstack((uf1, uf2)), 0)
                if i == 0:
                    L, U = lf.copy(), uf.copy()
                else:
                    L[L<lf] = lf[L<lf].copy()
                    U[U>uf] = uf[U>uf].copy()
        if not self.isUncycled:
            for R in r.values():
                r1, r2 = R
                if type(r1.lb) != ndarray:
                    r1.lb, r2.lb, r1.ub, r2.ub = atleast_1d(r1.lb), atleast_1d(r2.lb), atleast_1d(r1.ub), atleast_1d(r2.ub)
                r1.lb[r1.lb < L] = L[r1.lb < L]
                r2.lb[r2.lb < L] = L[r2.lb < L]
                r1.ub[r1.ub > U] = U[r1.ub > U]
                r2.ub[r2.ub > U] = U[r2.ub > U]
            
            r0.lb[r0.lb < L] = L[r0.lb < L]
            r0.ub[r0.ub > U] = U[r0.ub > U]
            
        # for more safety
        domain.useSave = True
        domain.useAsMutable = False
        domain.modificationVar = None 
        domain.storedIntervals = {}
        
        return r, r0
    
    def _iqg(self, domain, dtype, r0):
        #dep = self._getDep()
        v = domain.modificationVar
        v_0 = domain[v]
        lb, ub = v_0[0], v_0[1]

        if v.domain is not None and array_equal(lb, ub):
            return r0,r0 

        assert dtype in (float, float64, int32, int16),  'other types unimplemented yet'
        middle = 0.5 * (lb+ub)
        
        if v.domain is not None:
            middle1, middle2 = middle.copy(), middle.copy()
            adjust_ux_WithDiscreteDomain(middle1, v)
            adjust_lx_WithDiscreteDomain(middle2, v)
        else:
            middle1 = middle2 = middle
        
        domain[v] = (v_0[0], middle1)
        domain.localStoredIntervals = {}
        r_l = self.interval(domain, dtype, resetStoredIntervals = False)

        domain[v] = (middle2, v_0[1])
        domain.localStoredIntervals = {}
        r_u = self.interval(domain, dtype, resetStoredIntervals = False)
        
        domain[v] = v_0
        domain.localStoredIntervals = {}
        return r_l, r_u
            
    __pos__ = lambda self: self

        
    # overload "a+b"
    # @checkSizes
    def __add__(self, other):
#        if isinstance(other, Stochastic):
#            return other.__add__(self)
        
        for frame_tuple in inspect.stack():
            frame = frame_tuple[0]
            if 'func_code' in dir(frame) and 'func_code' in dir(npSum) and frame.f_code is npSum.func_code:
                pWarn('''
                seems like you use numpy.sum() on FuncDesigner object(s), 
                using FuncDesigner.sum() instead is highly recommended''')
#
##            elif frame.f_code is PythonSum.func_code:
##                print("python sum!") 
#        
##
##        for S in stk:
##            if not S[0].endswith('ooFun.py') and not S[0].endswith('overloads.py') and \
##            S[2] == '<module>' and S[3] is not None and 'sum(' in S[3]:
##                pWarn('''
##                seems like you use Python sum() on FuncDesigner object(s), 
##                using FuncDesigner.sum() instead is highly recommended''')                
        
        if not isinstance(other, (oofun, list, ndarray, tuple)) and not isscalar(other):
            raise FuncDesignerException('operation oofun_add is not implemented for the type ' + str(type(other)))
        
        other_is_sum = isinstance(other, oofun) and other._isSum
        
        from overloads import sum
        if self._isSum and other_is_sum:
            return sum(self._summation_elements + other._summation_elements)
        elif self._isSum:
            return sum(self._summation_elements + [other])
        elif other_is_sum:
            return sum(other._summation_elements + [self])
            
        # TODO: check for correct sizes during f, not only f.d 
    
        def aux_d(x, y):
            Xsize, Ysize = Len(x), Len(y)
            if Xsize == 1:
                return ones(Ysize)
            elif Ysize == 1:
                return Eye(Xsize)
            elif Xsize == Ysize:
                return Eye(Ysize) if not isinstance(x, multiarray) else ones(Ysize).view(multiarray)
            else:
                raise FuncDesignerException('for oofun summation a+b should be size(a)=size(b) or size(a)=1 or size(b)=1')        

        if isinstance(other, oofun):
            r = oofun(lambda x, y: x+y, [self, other], d = (lambda x, y: aux_d(x, y), lambda x, y: aux_d(y, x)), _isSum = True)
            r._summation_elements = [self, other]
            r.discrete = self.discrete and other.discrete
            r.getOrder = lambda *args, **kwargs: max((self.getOrder(*args, **kwargs), other.getOrder(*args, **kwargs)))
            
            # TODO: move it outside the func, to prevent recreation each time
            def interval(domain, dtype): 
                domain1, definiteRange1 = self._interval(domain, dtype)
                domain2, definiteRange2 = other._interval(domain, dtype)
                #return domain1[0] + domain2[0], domain1[1] + domain2[1]
                return domain1 + domain2, logical_and(definiteRange1, definiteRange2)
            r._interval_ = interval
        else:
            if isscalar(other) and other == 0: return self # sometimes triggers from other parts of FD engine 
            #if isinstance(other,  (OOArray, Stochastic)): return other + self
            if isinstance(other,  OOArray): return other + self
            if isinstance(other,  ndarray): other = other.copy() 
#            if other.size == 1:
#                #r = oofun(lambda *ARGS, **KWARGS: None, input = self.input)
#                r = oofun(lambda a: a+other, self)
#                #r._D = lambda *args,  **kwargs: self._D(*args,  **kwargs)
#                r.d = lambda x: aux_d(x, other)
#                #assert len(r._getDep())>0
#                #r._c = self._c + other
#            else:
            r = oofun(lambda a: a+other, self, _isSum=True)
            r._summation_elements = [self, other]
            r.d = lambda x: aux_d(x, other)
            r._getFuncCalcEngine = lambda *args,  **kwargs: self._getFuncCalcEngine(*args,  **kwargs) + other
            r.discrete = self.discrete
            r.getOrder = self.getOrder
            
            # TODO: move it outside 
            Other2 = tile(other, (2, 1))
            def interval(domain, dtype): 
                r, definiteRange = self._interval(domain, dtype)
                return r + Other2, definiteRange
            r._interval_ = interval
            
            if isscalar(other) or asarray(other).size == 1 or ('size' in self.__dict__ and self.size is asarray(other).size):
                r._D = lambda *args,  **kwargs: self._D(*args,  **kwargs) 
        r.vectorized = True
        return r
    
    __radd__ = lambda self, other: self.__add__(other)
    
    # overload "-a"
    def __neg__(self): 
        if self._neg_elem is not None:
            return self._neg_elem
        if self._isSum:
            from overloads import sum as FDsum
            return FDsum([-elem for elem in self._summation_elements])
        r = oofun(lambda a: -a, self, d = lambda a: -Eye(Len(a)))
        r._neg_elem = self
        r._getFuncCalcEngine = lambda *args,  **kwargs: -self._getFuncCalcEngine(*args,  **kwargs)
        r.getOrder = self.getOrder
        r._D = lambda *args, **kwargs: dict([(key, -value) for key, value in self._D(*args, **kwargs).items()])
        r.d = raise_except
        r.criticalPoints = False
        r.vectorized = True
        def _interval(domain, dtype):
            r, definiteRange = self._interval(domain, dtype)
            assert r.shape[0] == 2
            return -flipud(r), definiteRange
            #return (-r[1], -r[0])
        r._interval_ = _interval
        return r
        
    # overload "a-b"
    __sub__ = lambda self, other: self + (-asfarray(other).copy()) if type(other) in (list, tuple, ndarray) else self + (-other)
    __rsub__ = lambda self, other: other + (-self)

    # overload "a/b"
    def __div__(self, other):
        if isinstance(other, OOArray):
            return other.__rdiv__(self)
        if isinstance(other, list): other = asarray(other)
        if isscalar(other) or type(other) == ndarray:
            return self * (1.0 / other) # to make available using _prod_elements
        if isinstance(other, oofun):
            r = oofun(lambda x, y: x/y, [self, other])
            def aux_dx(x, y):
                # TODO: handle float128
                y = asfarray(y) 
                Xsize, Ysize = x.size, y.size
                if Xsize != 1:
                    assert Xsize == Ysize or Ysize == 1, 'incorrect size for oofun devision'
                if Xsize != 1:
                    if Ysize == 1: 
                        r = Diag(None, size=Xsize, scalarMultiplier = 1.0/y)
                    else:
                        r = Diag(1.0/y)
                else:
                    r = 1.0 / y
                return r                
            def aux_dy(x, y):
                # TODO: handle float128
                x = asfarray(x)
                Xsize, Ysize = Len(x), Len(y)
                r = -x / y**2
                if Ysize != 1:
                    assert Xsize == Ysize or Xsize == 1, 'incorrect size for oofun devision'
                    r = Diag(r)
                return r
            r.d = (aux_dx, aux_dy)
            def getOrder(*args, **kwargs):
                order1, order2 = self.getOrder(*args, **kwargs), other.getOrder(*args, **kwargs)
                return order1 if order2 == 0 else inf
            r.getOrder = getOrder
            def interval(domain, dtype):
                lb1_ub1, definiteRange1 = self._interval(domain, dtype)
                lb1, ub1 = lb1_ub1[0], lb1_ub1[1]
                lb2_ub2, definiteRange2 = other._interval(domain, dtype)
                lb2, ub2 = lb2_ub2[0], lb2_ub2[1]
                lb2, ub2 = asarray(lb2, dtype), asarray(ub2, dtype)

                tmp = vstack((lb1/lb2, lb1/ub2, ub1/lb2, ub1/ub2))
                r1, r2 = nanmin(tmp, 0), nanmax(tmp, 0)
                
                ind = logical_or(lb1==0.0, ub1==0.0)
                r1[atleast_1d(logical_and(ind, r1>0.0))] = 0.0
                r2[atleast_1d(logical_and(ind, r2<0.0))] = 0.0

                # adjust inf
#                ind1_zero_minus = logical_and(lb1<0, ub1>=0)
#                ind1_zero_plus = logical_and(lb1<=0, ub1>0)
                
                ind2_zero_minus = logical_and(lb2<0, ub2>=0)
                ind2_zero_plus = logical_and(lb2<=0, ub2>0)
                
                r1[atleast_1d(logical_or(logical_and(ind2_zero_minus, ub1>0), logical_and(ind2_zero_plus, lb1<0)))] = -inf
                r2[atleast_1d(logical_or(logical_and(ind2_zero_minus, lb1<0), logical_and(ind2_zero_plus, ub1>0)))] = inf
                
                #assert not any(isnan(r1)) and not any(isnan(r2))
                #assert all(r1 <= r2)
                return vstack((r1, r2)), logical_and(definiteRange1, definiteRange2)

            r._interval_ = interval
        else:
            # TODO: mb remove it?
            other = array(other,'float')# TODO: handle float128
            r = oofun(lambda a: a/other, self, discrete = self.discrete)# TODO: involve sparsity if possible!
            r.getOrder = self.getOrder
            r._getFuncCalcEngine = lambda *args,  **kwargs: self._getFuncCalcEngine(*args,  **kwargs) / other
            #r.d = lambda x: 1.0/other if (isscalar(x) or x.size == 1) else Diag(ones(x.size)/other) if other.size > 1 \
            #else Diag(None, size=x.size, scalarMultiplier=1.0/other)
            r.d = lambda x: 1.0/other if (isscalar(x) or x.size == 1) else Diag(ones(x.size)/other) #if other.size > 1 \
            #else Diag(None, size=x.size, scalarMultiplier=1.0/other)
            # commented code is unreacheble, see r._D definition below for other.size == 1
            
            r.criticalPoints = False
#            if other.size == 1 or 'size' in self.__dict__ and self.size in (1, other.size):
            if other.size == 1:
                r._D = lambda *args, **kwargs: dict([(key, value/other) for key, value in self._D(*args, **kwargs).items()])
                r.d = raise_except
            
        # r.discrete = self.discrete and (?)
        #r.isCostly = True
        r.vectorized = True
        return r

    def __rdiv__(self, other):
        
        # without the code it somehow doesn't fork in either Python3 or latest numpy
        #if isinstance(other,  Stochastic) or (isinstance(other, OOArray) and any([isinstance(elem, oofun) for elem in atleast_1d(other)])):
        if isinstance(other, OOArray) and any([isinstance(elem, oofun) for elem in atleast_1d(other)]):
            return other.__div__(self)
       
        other = array(other, 'float') # TODO: sparse matrices handling!
        r = oofun(lambda x: other/x, self, discrete = self.discrete)
        r.d = lambda x: Diag((- other) / x**2)
        def interval(domain, dtype):
            arg_lb_ub, definiteRange = self._interval(domain, dtype)
            arg_infinum, arg_supremum = arg_lb_ub[0], arg_lb_ub[1]
            if other.size != 1: 
                raise FuncDesignerException('this case for interval calculations is unimplemented yet')
            r = vstack((other / arg_supremum, other / arg_infinum))
            r1, r2 = amin(r, 0), amax(r, 0)
            ind_zero_minus = logical_and(arg_infinum<0, arg_supremum>=0)
            r1[atleast_1d(logical_and(ind_zero_minus, other>0))] = -inf
            r2[atleast_1d(logical_and(ind_zero_minus, other<0))] = inf
            
            ind_zero_plus = logical_and(arg_infinum<=0, arg_supremum>0)
            r1[atleast_1d(logical_and(ind_zero_plus, other<0))] = -inf
            r2[atleast_1d(logical_and(ind_zero_plus, other>0))] = inf

            return vstack((r1, r2)), definiteRange
            
        r._interval_ = interval
        #r.isCostly = True
        def getOrder(*args, **kwargs):
            order = self.getOrder(*args, **kwargs)
            return 0 if order == 0 else inf
        r.getOrder = getOrder
        r.vectorized = True
        return r

    # overload "a*b"
    def __mul__(self, other):
        if isinstance(other, OOArray):#if isinstance(other, (OOArray, Stochastic)):
            return other.__mul__(self)
        
        isOtherOOFun = isinstance(other, oofun)
        if isinstance(other, list): other = asarray(other)
        
        if self._isProd:
            if not isOtherOOFun and not isinstance(self._prod_elements[-1], (oofun, OOArray)):
                assert len(self._prod_elements) == 2, 'bug in FD kernel'
                return self._prod_elements[0] * (other * self._prod_elements[-1])
        
        if isOtherOOFun:
            r = oofun(lambda x, y: x*y, [self, other])
            r.d = (lambda x, y: mul_aux_d(x, y), lambda x, y: mul_aux_d(y, x))
            r.getOrder = lambda *args, **kwargs: self.getOrder(*args, **kwargs) + other.getOrder(*args, **kwargs)
        else:
            other = other.copy() if isinstance(other,  ndarray) else asarray(other)
            r = oofun(lambda x: x*other, self, discrete = self.discrete)
            r.getOrder = self.getOrder
            r._getFuncCalcEngine = lambda *args,  **kwargs: other * self._getFuncCalcEngine(*args,  **kwargs)
            r.criticalPoints = False

            if isscalar(other) or asarray(other).size == 1:  # other may be array-like
                r._D = lambda *args, **kwargs: dict([(key, value * other) for key, value in self._D(*args, **kwargs).items()])
                r.d = raise_except
            else:
                r.d = lambda x: mul_aux_d(x, other)
        
        r._interval_ = lambda *args, **kw: mul_interval(self, other, isOtherOOFun, *args, **kw)
        r.vectorized = True
        #r.isCostly = True
        r._isProd = True
        r._prod_elements = [self, other]
        return r

    __rmul__ = lambda self, other: self.__mul__(other)

    def __pow__(self, other):
        if isinstance(other, OOArray):#if isinstance(other, (OOArray, Stochastic)):
            return other.__rpow__(self)
#            if 'size' not in self.__dict__ or (isscalar(self.size) and self.size == 1):
#                return ooarray([self ** other[i] for i in range(other.size)])
#            elif isscalar(self.size):# and is not 1
#                return ooarray([self[i] ** other[i] for i in range(other.size)])

        d_x = lambda x, y: \
            (y * x ** (y - 1) if (isscalar(x) or x.size == 1 or isinstance(x, multiarray)) else Diag(y * x ** (y - 1))) if y is not 2 else Diag(2 * x)

        d_y = lambda x, y: x ** y * log(x) if (isscalar(y) or y.size == 1) and not isinstance(x, multiarray) else Diag(x ** y * log(x))
        

        if not isinstance(other, oofun):
            if isscalar(other):
                if type(other) == int: # TODO: handle numpy integer types
                    pass
                    #other = asarray(other, dtype='float')
                else:
                    other = asarray(other, dtype= type(other))# with same type, mb float128
            elif not isinstance(other, ndarray): 
                # TODO: fix it wrt int32, int64 etc
                other = asarray(other, dtype='float' if type(other) == int else type(other)).copy()
            
            f = lambda x: asanyarray(x) ** other
            d = lambda x: d_x(x, other)
            input = self
            def interval(domain, dtype):
                lb_ub, definiteRange = self._interval(domain, dtype)
                
                Tmp = lb_ub ** other
                #Tmp = vstack((lb**other, ub**other))
                
                t_min, t_max = nanmin(Tmp, 0), nanmax(Tmp, 0)
                #lb2, ub2 = other._interval(domain, dtype) if isinstance(other, oofun) else other, other # TODO: improve it
                lb, ub = lb_ub[0], lb_ub[1]
                ind = lb < 0.0
                if any(ind):
                    isNonInteger = other != asarray(other, int) # TODO: rational numbers?
                    
                    # TODO: rework it properly, with matrix operations
                    if any(isNonInteger):
                        definiteRange = False
                    
                    ind_nan = logical_and(logical_and(ind, isNonInteger), ub < 0)
                    if any(ind_nan):
                        t_max[atleast_1d(ind_nan)] = nan
                    
                    #1
                    t_min[atleast_1d(logical_and(ind, logical_and(t_min>0, ub >= 0)))] = 0.0
                    
#                    #2
#                    if asarray(other).size == 1:
#                        IND = not isNonInteger
#                    else:
#                        ind2 = logical_not(isNonInteger)
#                        IND = other[ind2] % 2 == 0
#                    
#                    if any(IND):
#                        t_min[logical_and(IND, atleast_1d(logical_and(lb<0, ub >= 0)))] = 0.0
                return vstack((t_min, t_max)), definiteRange
        else:
            f = lambda x, y: asanyarray(x) ** y
            d = (d_x, d_y)
            input = [self, other]
            def interval(domain, dtype): 
                # TODO: handle discrete cases
                lb1_ub1, definiteRange1 = self._interval(domain, dtype)
                lb1, ub1 = lb1_ub1[0], lb1_ub1[1]
                lb2_ub2, definiteRange2 = other._interval(domain, dtype)
                lb2, ub2 = lb2_ub2[0], lb2_ub2[1]
                T = vstack((lb1 ** lb2, lb1** ub2, ub1**lb1, ub1**ub2))
                t_min, t_max = nanmin(T, 0), nanmax(T, 0)
                definiteRange = logical_and(definiteRange1, definiteRange2)
                ind1 = lb1 < 0
                # TODO: check it, especially with integer "other"
                if any(ind1):
                    
                    # TODO: rework it with matrix operations
                    definiteRange = False
                    
                    ind2 = ub1 >= 0
                    t_min[atleast_1d(logical_and(logical_and(ind1, ind2), logical_and(t_min > 0.0, ub2 > 0.0)))] = 0.0
                    t_max[atleast_1d(logical_and(ind1, logical_not(ind2)))] = nan
                    t_min[atleast_1d(logical_and(ind1, logical_not(ind2)))] = nan
                return vstack((t_min, t_max)), definiteRange
                
        r = oofun(f, input, d = d, _interval_=interval)
        if isinstance(other, oofun) or (not isinstance(other, int) or (type(other) == ndarray and other.flatten()[0] != int)): 
            r.attach((self>0)('pow_domain_%d'%r._id, tol=-1e-7)) # TODO: if "other" is fixed oofun with integer value - omit this
        r.isCostly = True
        r.vectorized = True
        return r

    def __rpow__(self, other):
        assert not isinstance(other, oofun)# if failed - check __pow__implementation
        
        if isscalar(other):
            if type(other) == int: # TODO: handle numpy integer types
                other = float(other)
        elif not isinstance(other, ndarray): 
            other = asarray(other, 'float' if type(other) in (int, int32, int64, int16, int8) else type(other))
        
        f = lambda x: other ** x
        #d = lambda x: Diag(asarray(other) **x * log(asarray(other)))
        d = lambda x: Diag(other **x * log(other)) 
        r = oofun(f, self, d=d, criticalPoints = False)
        #r.isCostly = True
        r.vectorized = True
        return r

    def __xor__(self, other): raise FuncDesignerException('For power of oofuns use a**b, not a^b')
        
    def __rxor__(self, other): raise FuncDesignerException('For power of oofuns use a**b, not a^b')
        
    def __getitem__(self, ind): # overload for oofun[ind]
        if isinstance(ind, oofun):# NOT IMPLEMENTED PROPERLY YET
            self.pWarn('Slicing oofun by oofun IS NOT IMPLEMENTED PROPERLY YET')
            f = lambda x, _ind: x[_ind]
            def d(x, _ind):
                r = zeros(x.shape)
                r[_ind] = 1
                return r
        elif type(ind) not in (int, int32, int64, int16, int8):
            # Python 3 slice
            return self.__getslice__(ind.start, ind.stop)
        else:
            if not hasattr(self, '_slicesIndexDict'):
                self._slicesIndexDict = {}
            if ind in self._slicesIndexDict:
                return self._slicesIndexDict[ind]
                
            f = lambda x: x[ind] 
            def d(x):
                Xsize = Len(x)
                condBigMatrix = Xsize > 100 
                if condBigMatrix and scipyInstalled:
                    r = SparseMatrixConstructor((1, x.shape[0]))
                    r[0, ind] = 1.0
                else: 
                    if condBigMatrix and not scipyInstalled: self.pWarn(scipyAbsentMsg)
                    r = zeros_like(x)
                    r[ind] = 1
                return r
                
        r = oofun(f, self, d = d, size = 1, getOrder = self.getOrder)
        # TODO: check me!
        # what about a[a.size/2:]?
            
        # TODO: edit me!
#        if self.is_oovar:
#            r.is_oovarSlice = True
        self._slicesIndexDict[ind] = r
        return r
    
    def __getslice__(self, ind1, ind2):# overload for oofun[ind1:ind2]
        #TODO: mb check if size is known then use it instead of None?
        if ind1 is None: 
            ind1 = 0
        if ind2 is  None: 
            if 'size' in self.__dict__ and type(self.size) in (int, int8, int16, int32, int64):
                ind2 = self.size
            else:
                raise FuncDesignerException('if oofun.size is not provided then you should provide full slice coords, e.g. x[3:10], not x[3:]')
        assert not isinstance(ind1, oofun) and not isinstance(ind2, oofun), 'slicing by oofuns is unimplemented yet'
        f = lambda x: x[ind1:ind2]
        def d(x):
            condBigMatrix = Len(x) > 100 #and (ind2-ind1) > 0.25*x.size
            if condBigMatrix and not scipyInstalled:
                self.pWarn(scipyAbsentMsg)
            
            if condBigMatrix and scipyInstalled:
                r = SP_eye(ind2-ind1, ind2-ind1)
                if ind1 != 0:
                    m1 = SparseMatrixConstructor((ind2-ind1, ind1))
                    r = Hstack((SparseMatrixConstructor((ind2-ind1, ind1)), r))
                if ind2 != x.size:
                   r = Hstack((r, SparseMatrixConstructor((ind2-ind1, x.size - ind2))))
            else:
                m1 = zeros((ind2-ind1, ind1))
                m2 = eye(ind2-ind1)
                m3 = zeros((ind2-ind1, x.size - ind2))
                r = hstack((m1, m2, m3))
            return r
        r = oofun(f, self, d = d, getOrder = self.getOrder)

        return r
   
    #def __len__(self):
        #return self.size
        #raise FuncDesignerException('using len(obj) (where obj is oovar or oofun) is not possible (at least yet), use obj.size instead')

    def sum(self):
        def d(x):
            if type(x) == ndarray and x.ndim > 1: raise FuncDesignerException('sum(x) is not implemented yet for arrays with ndim > 1')
            return ones_like(x)        
        def interval(domain, dtype):
            if type(domain) == ooPoint and domain.isMultiPoint:
                raise FuncDesignerException('interval calculations are unimplemented for sum(oofun) yet')
            lb_ub, definiteRange = self._interval(domain, dtype)
            lb, ub = lb_ub[0], lb_ub[1]
            return vstack((npSum(lb, 0), npSum(ub, 0))), definiteRange
        r = oofun(npSum, self, getOrder = self.getOrder, _interval_ = interval, d=d)
        return r
    
    def prod(self):
        # TODO: consider using r.isCostly = True
        r = oofun(prod, self)
        #r.getOrder = lambda *args, **kwargs: self.getOrder(*args, **kwargs)*self.size
        def d(x):
            x = asarray(x) # prod is used rarely, so optimizing it is not important
            if x.ndim > 1: raise FuncDesignerException('prod(x) is not implemented yet for arrays with ndim > 1')
            ind_zero = where(x==0)[0].tolist()
            ind_nonzero = nonzero(x)[0].tolist()
            numOfZeros = len(ind_zero)
            r = prod(x) / x
            
            if numOfZeros >= 2: 
                r[ind_zero] = 0
            elif numOfZeros == 1:
                r[ind_zero] = prod(x[ind_nonzero])

            return r 
        r.d = d
        return r


    """                                     Handling constraints                                  """
    
    # TODO: optimize for lb-ub imposed on oovars
    
    # TODO: fix it for discrete problems like MILP, MINLP
    def __gt__(self, other): # overload for >
    
        if self.is_oovar and not isinstance(other, (oofun, OOArray)) and not (isinstance(other, ndarray) and str(other.dtype) =='object'):
            r = BoxBoundConstraint(self, lb = other)
        elif isinstance(other, OOArray) or (isinstance(other, ndarray) and str(other.dtype) =='object'):
            return other.__le__(self)
        else:
            r = Constraint(self - other, lb=0.0) # do not perform check for other == 0, copy should be returned, not self!
        return r

    # overload for >=
    __ge__ = __gt__

    # TODO: fix it for discrete problems like MILP
    def __lt__(self, other): # overload for <
        # TODO:
        #(self.is_oovar or self.is_oovarSlice)
        if self.is_oovar and not isinstance(other, (oofun, OOArray)) and not(isinstance(other, ndarray) and str(other.dtype) =='object'):
            r = BoxBoundConstraint(self, ub = other)
        elif isinstance(other, OOArray) or (isinstance(other, ndarray) and str(other.dtype) =='object'):
            return other.__ge__(self)
        else:
            r = Constraint(self - other, ub = 0.0) # do not perform check for other == 0, copy should be returned, not self!
        return r            

    # overload for <=
    __le__ = __lt__
    
    __eq__ = lambda self, other: self.eq(other)
  
    def eq(self, other):
        #if other in (None, (), []): return False
        if other is None or other is () or (type(other) == list and len(other) == 0): return False
        if type(other) in (str, string_): 
        #if self.domain is not None and self.domain is not bool and self.domain is not 'bool':
            if 'aux_domain' not in self.__dict__:
                if not self.is_oovar:
                    raise FuncDesignerException('comparing with non-numeric data is allowed for string oovars, not for oofuns')
                self.formAuxDomain()
#            if len(self.domain) != len(self.aux_domain):
#                raise FuncDesignerException('probably you have changed domain of categorical oovar, that is not allowed')
            ind = searchsorted(self.aux_domain, other, 'left')
            if self.aux_domain[ind] != other:
                raise FuncDesignerException('compared value %s is absent in oovar %s domain' %(other, self.name))
            #r = (self == ind)(tol=0.5)
            r = Constraint(self - ind, ub = 0.0, lb = 0.0, tol=0.5)
            #print (self, other)
            # TODO: use it instead
            if self.is_oovar: r.nlh = lambda Lx, Ux, p, dataType: self.nlh(Lx, Ux, p, dataType, ind)
            return r
        
        if 'startswith' in dir(other): return False
        #if self.is_oovar and not isinstance(other, oofun):
            #raise FuncDesignerException('Constraints like this: "myOOVar = <some value>" are not implemented yet and are not recommended; for openopt use freeVars / fixedVars instead')
        r = Constraint(self - other, ub = 0.0, lb = 0.0) # do not perform check for other == 0, copy should be returned, not self!
        if self.is_oovar and isscalar(other) and self.domain is not None:
            if self.domain is bool or self.domain is 'bool':
                if other not in [0, 1]:# and type(other) not in (int, int16, int32, int64):
                    raise FuncDesignerException('bool oovar can be compared with [0,1] only')
                r.nlh = self.nlh if other == 1.0 else (~self).nlh
                r.alt_nlh_func = True
            elif self.domain is not int and self.domain is not 'int':# and type(other) in (str, string_):
                pass
#                if self.is_oovar:
#                    self.formAuxDomain()
#                    print('2', other)
#                    ind = searchsorted(self.aux_domain, other, 'left')
#                    #r.nlh = lambda Lx, Ux, p, dataType: self.nlh(Lx, Ux, p, dataType, ind)
#                    r = Constraint(self - ind, ub = 0.0, lb = 0.0)
#                    r.nlh = lambda Lx, Ux, p, dataType: self.nlh(Lx, Ux, p, dataType, ind)
                    
                
           #                print (self.domain, other)
#                r_nlh = r.nlh
#                def nlh_c(Lx, Ux, p, dataType):
#                    r1 = nlh2(Lx, Ux, p, dataType)
#                    r2 = r_nlh(Lx, Ux, p, dataType)
#                    print(r1)
#                    print(r2)
#                    raw_input()
#                #r.nlh = lambda Lx, Ux, p, dataType: self.nlh(Lx, Ux, p, dataType, other)
#                r.nlh = nlh_c
##                r.nlh = lambda Lx, Ux, p, dataType: self.nlh(Lx, Ux, p, dataType, other)
##                r.alt_nlh_func = True
        return r  

    """                                             getInput                                              """
    def _getInput(self, *args, **kwargs):
#        self.inputOOVarTotalLength = 0
        r = []
        for item in self.input:
            tmp = item._getFuncCalcEngine(*args, **kwargs) if isinstance(item, oofun) else item(*args, **kwargs) if isinstance(item, OOArray) else item
            r.append(tmp if type(tmp) not in (list, tuple, Stochastic) else asanyarray(tmp))
        return tuple(r)

    """                                                getDep                                             """
    def _getDep(self):
        # returns Python set of oovars it depends on
        if hasattr(self, 'dep'):
            return self.dep
        elif self.input is None:
            self.dep = None
        else:
            if type(self.input) not in (list, tuple) and not isinstance(self.input, OOArray):
                self.input = [self.input]
            #OLD
#            r = set()
#            for oofunInstance in self.input:
#                if not isinstance(oofunInstance, oofun): continue
#                if oofunInstance.is_oovar:
#                    r.add(oofunInstance)
#                    continue
#                tmp = oofunInstance._getDep()
#                if tmp is None: continue
#                r.update(tmp)
#            self.dep = r    
            # / OLD
            
            # NEW
            r_oovars = []
            r_oofuns = []
            isUncycled = True
            Tmp = set()
            for Elem in self.input:
                if isinstance(Elem, OOArray):
                    for _elem in Elem:
                        if isinstance(_elem, oofun):
                            Tmp.add(_elem)
#                        _tmp = _elem._getDep()
#                        if _tmp is not None or (isinstance(_tmp, oofun) and _tmp.is_oovar):
#                            Tmp.add(_tmp)
                    
            #Tmp.update([[_elem._getDep() for _elem in Elem] for Elem in self.input if isinstance(Elem, OOArray)])
            for Elem in (list(Tmp) + self.input):
                if not isinstance(Elem, oofun): continue
                if Elem.is_oovar:
                    r_oovars.append(Elem)
                    continue
                
                tmp = Elem._getDep()
                if not Elem.isUncycled: isUncycled = False
                if tmp is None or len(tmp)==0: continue # TODO: remove None, use [] instead
                r_oofuns.append(tmp)
            r = set(r_oovars)

            # Python 2.5 sel.update fails on empty input
            if len(r_oofuns)!=0: r.update(*r_oofuns)
            if len(r_oovars) + sum([len(elem) for elem in r_oofuns]) != len(r):
                isUncycled = False
            self.isUncycled = isUncycled            
            
            self.dep = r    
            # /NEW
            
        return self.dep


    """                                                getFunc                                             """
    def _getFunc(self, *args, **kwargs):
        Args = args
        if len(args) == 0 and len(kwargs) == 0:
            raise FuncDesignerException('at least one argument is required')
        if len(args) != 0:
            if type(args[0]) != str:
                assert not isinstance(args[0], oofun), "you can't invoke oofun on another one oofun"
                x = args[0]
                if isinstance(x, dict) and not isinstance(x, ooPoint): 
                    x = ooPoint(x)
                    Args = (x,)+args[1:]
                if self.is_oovar:
                    return self._getFuncCalcEngine(*Args, **kwargs)
#                    if isinstance(x, dict):
#                        tmp = x.get(self, None)
#                        if tmp is not None:
#                            # currently tmp hasn't to be sparse matrix, mb for future
#                            if isinstance(tmp, Stochastic):
#                                r = getattr(x, 'maxDistributionSize', inf)
#                                tmp.maxDistributionSize = r
#                                return tmp
#                            else:
#                                return float(tmp) if isscalar(tmp) and type(tmp)==int else asfarray(tmp) if not isspmatrix(tmp) else tmp
#                        elif self.name in x:
#                            tmp = x[self.name]
#                            return float(tmp) if isscalar(tmp) and type(tmp)==int else asfarray(tmp) if not isspmatrix(tmp) else tmp
#                        else:
#                            s = 'for oovar ' + self.name + \
#                            " the point involved doesn't contain neither name nor the oovar instance. Maybe you try to get function value or derivative in a point where value for an oovar is missing"
#                            raise FuncDesignerException(s)
#                    elif hasattr(x, 'xf'):
#                        if x.probType == 'MOP': # x is MOP result struct
#                            s = 'evaluation of MOP result on arguments is unimplemented yet, use r.solutions'
#                            raise FuncDesignerException(s)
#                        # TODO: possibility of squeezing
#                        return x.xf[self]
#                    else:
#                        raise FuncDesignerException('Incorrect data type (%s) while obtaining oovar %s value' %(type(x), self.name))
            
            else:
                self.name = args[0]
                return self
        else:
            for fn in ['name', 'size', 'tol']:
                if fn in kwargs:
                    setattr(self, fn, kwargs[fn])
            return self
        
        if hasattr(x, 'probType') and x.probType == 'MOP':# x is MOP result struct
            s = 'evaluation of MOP result on arguments is unimplemented yet, use r.solutions'
            raise FuncDesignerException(s)

        
        return self._getFuncCalcEngine(*Args, **kwargs)


    def _getFuncCalcEngine(self, *args, **kwargs):
        x = args[0]
        
        dep = self._getDep()
        
        CondSamePointByID = True if type(x) == ooPoint and not x.isMultiPoint and self._point_id == x._id else False

        fixedVarsScheduleID = kwargs.get('fixedVarsScheduleID', -1)
        fixedVars = kwargs.get('fixedVars', None)
        Vars = kwargs.get('Vars', None) 
        
        sameVarsScheduleID = fixedVarsScheduleID == self._lastFuncVarsID 
        rebuildFixedCheck = not sameVarsScheduleID
        if fixedVarsScheduleID != -1: self._lastFuncVarsID = fixedVarsScheduleID
        
        if rebuildFixedCheck:
            self._isFixed = (fixedVars is not None and dep.issubset(fixedVars)) or (Vars is not None and dep.isdisjoint(Vars))
        
        if isinstance(x, ooPoint) and x.isMultiPoint:
            cond_same_point = False
        else:
            cond_same_point = CondSamePointByID or \
            (self._f_val_prev is not None and (self._isFixed or (self.isCostly and  all([array_equal((x if isinstance(x, dict) else x.xf)[elem], self._f_key_prev[elem]) for elem in (dep & set((x if isinstance(x, dict) else x.xf).keys()))]))))
            
        if cond_same_point:
            self.same += 1
            tmp =  self._f_val_prev
            return tmp.copy() if isinstance(tmp, (ndarray, Stochastic)) else tmp 
            
        self.evals += 1
        
        #TODO: add condition "and self in x._p.dictOfLinearFuncs" instead of self._order == 1
        #use_line_points = hasattr(x,'_p') and x._p.solver.useLinePoints and self._order == 1
#        if use_line_points:
#            _linePointDescriptor = getattr(x, '_linePointDescriptor', None)
#            if _linePointDescriptor is not None:
#                #point1, alp, point2 = _linePointDescriptor
#                alp = _linePointDescriptor
#                r1, r2 = self._p._firstLinePointDict[self], self._p._secondLinePointDict[self]
#                #assert r1 is not None and r2 is not None
#                return r1 * (1-alp) + r2 * alp
        
        if type(self.args) != tuple:
            self.args = (self.args, )
            
        Input = self._getInput(*args, **kwargs) 
        
#        if not isinstance(x, ooPoint) or not x.isMultiPoint or (self.vectorized and not any([isinstance(inp, Stochastic) for inp in Input])):
        if not isinstance(x, ooPoint) or not x.isMultiPoint or self.vectorized:
            if self.args != ():
                Input += self.args
            Tmp = self.fun(*Input)
            if isinstance(Tmp, (list, tuple)):
                tmp = hstack(Tmp) if len(Tmp) > 1 else Tmp[0]
            else:
                tmp = Tmp
        else:
            if hasattr(x, 'N'):
                N = x.N
            else:
                # TODO: fix it for x.values() is Stochastic
                N = 1
                for inp in Input:
                    if not isinstance(inp,  Stochastic):
                        N = inp.size if type(inp) == ndarray else 1
                        break
            inputs = zip(*[(atleast_1d(inp) if not isinstance(inp, Stochastic) and type(inp) == ndarray and inp.size == N else [inp]*N) for inp in Input])
            
            # Check it!
            Tmp = [self.fun(*inp) if self.args == () else self.fun(*(inp + self.args)) for inp in inputs]
            if N == 1:
                tmp = Tmp[0]
            else:
                tmp = array([elem for elem in Tmp], object).view(multiarray)
        
        #if self._c != 0.0: tmp += self._c
        
        #self.outputTotalLength = ([asarray(elem).size for elem in self.fun(*Input)])#self.f_val_prev.size # TODO: omit reassigning
        
        #!! TODO: handle case tmp is multiarray of Stochastic
        if isinstance(tmp, Stochastic):
            if 'xf' in x.__dict__:
                maxDistributionSize = getattr(x.xf, 'maxDistributionSize', 0)
            else:
                maxDistributionSize = getattr(x, 'maxDistributionSize', 0)
            if maxDistributionSize == 0:
                s = '''
                    if one of function arguments is stochastic distribution 
                    without resolving into quantified value 
                    (e.g. uniform(-10,10) instead of uniform(-10,10, 100), 100 is number of point to emulate)
                    then you should evaluate the function 
                    onto oopoint with assigned parameter maxDistributionSize'''
                raise FuncDesignerException(s)
            if tmp.size > maxDistributionSize:
                tmp.reduce(maxDistributionSize)
            tmp.maxDistributionSize = maxDistributionSize
        
        
        if ((type(x) == ooPoint and not x.isMultiPoint) and not (isinstance(tmp, ndarray) and type(tmp) != ndarray)) or self._isFixed:# or self.isCostly:

            # TODO: rework it (for input with ooarays)
            try:
                self._f_key_prev = dict([(elem, copy((x if isinstance(x, dict) else x.xf)[elem])) for elem in dep]) if self.isCostly else None
                self._f_val_prev = tmp.copy() if isinstance(tmp, (ndarray, Stochastic)) else tmp
                if type(x) == ooPoint: 
                    self._point_id = x._id                
            except:
                pass
            
        r = tmp
#        if use_line_points:
#            self._p._currLinePointDict[self] = r
#        if fixedVarsScheduleID != -1: 
#            self._lastSize = tmp.size
        return r


    """                                                getFunc                                             """
    __call__ = lambda self, *args, **kwargs: self._getFunc(*args, **kwargs)


    """                                              derivatives                                           """
    def D(self, x, Vars=None, fixedVars = None, resultKeysType = 'vars', useSparse = False, exactShape = False, fixedVarsScheduleID = -1):
        
        # resultKeysType doesn't matter for the case isinstance(Vars, oovar)
        if Vars is not None and fixedVars is not None:
            raise FuncDesignerException('No more than one argument from "Vars" and "fixedVars" is allowed for the function')
        #assert type(Vars) != ndarray and type(fixedVars) != ndarray
        if not isinstance(x, ooPoint): x = ooPoint(x)
        initialVars = Vars
        #TODO: remove cloned code
        if Vars is not None:
            if type(Vars) in [list, tuple]:
                Vars = set(Vars)
            elif isinstance(Vars, oofun):
                if not Vars.is_oovar:
                    raise FuncDesignerException('argument Vars is expected as oovar or python list/tuple of oovar instances')
                Vars = set([Vars])
        if fixedVars is not None:
            if type(fixedVars) in [list, tuple]:
                fixedVars = set(fixedVars)
            elif isinstance(fixedVars, oofun):
                if not fixedVars.is_oovar:
                    raise FuncDesignerException('argument fixedVars is expected as oovar or python list/tuple of oovar instances')
                fixedVars = set([fixedVars])
        r = self._D(x, fixedVarsScheduleID, Vars, fixedVars, useSparse = useSparse)
        r = dict([(key, (val if type(val)!=DiagonalType else val.resolve(useSparse))) for key, val in r.items()])
        is_oofun = isinstance(initialVars, oofun)
        if is_oofun and not initialVars.is_oovar:
            # TODO: handle it with input of type list/tuple/etc as well
            raise FuncDesignerException('Cannot perform differentiation by non-oovar input')

        if resultKeysType == 'names':
            raise FuncDesignerException("""This possibility is out of date, 
            if it is still present somewhere in FuncDesigner doc inform developers""")
        elif resultKeysType == 'vars':
            rr = {}
            #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! TODO: remove the cycle!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            
            for oov, val in x.items():
                #if not isinstance(oov not in r, bool): print oov not in r
                if oov not in r or (fixedVars is not None and oov in fixedVars):
                    continue
                tmp = r[oov]
                if useSparse == False and hasattr(tmp, 'toarray'): tmp = tmp.toarray()
                if not exactShape and not isspmatrix(tmp) and not isscalar(tmp):
                    if tmp.size == 1: tmp = asscalar(tmp)
                    elif min(tmp.shape) == 1: tmp = tmp.flatten()
                rr[oov] = tmp
            return rr if not is_oofun else rr[initialVars]
        else:
            raise FuncDesignerException('Incorrect argument resultKeysType, should be "vars" or "names"')
            
            
    def _D(self, x, fixedVarsScheduleID, Vars=None, fixedVars = None, useSparse = 'auto'):
        if self.is_oovar: 
            if (fixedVars is not None and self in fixedVars) or (Vars is not None and self not in Vars):
                return {} 
            tmp = x[self]
            return {self:Eye(asarray(tmp).size)} if not isinstance(tmp, multiarray) else {self: ones_like(tmp).view(multiarray)}
            
        if self.input[0] is None: return {} # fixed oofun. TODO: implement input = [] properly
            
        if self.discrete: 
            return {}
            #raise FuncDesignerException('The oofun or oovar instance has been declared as discrete, no derivative is available')
        
        CondSamePointByID = True if isinstance(x, ooPoint) and self._point_id1 == x._id else False
        sameVarsScheduleID = fixedVarsScheduleID == self._lastDiffVarsID 
        
        dep = self._getDep()
        
        rebuildFixedCheck = not sameVarsScheduleID
        if rebuildFixedCheck:
            self._isFixed = (fixedVars is not None and dep.issubset(fixedVars)) or (Vars is not None and dep.isdisjoint(Vars))
        if self._isFixed: return {}
        ##########################
        
        # TODO: optimize it. Omit it for simple cases.
        #isTransmit = self._usedIn == 1 # Exactly 1! not 0, 2, ,3, 4, etc
        #involveStore = not isTransmit or self._directlyDwasInwolved
        involveStore = self.isCostly

        #cond_same_point = hasattr(self, '_d_key_prev') and sameDerivativeVariables and (CondSamePointByID or (involveStore and         all([array_equal(x[elem], self.d_key_prev[elem]) for elem in dep])))
        
        cond_same_point = sameVarsScheduleID and \
        ((CondSamePointByID and self._d_val_prev is not None) or \
        (involveStore and self._d_key_prev is not None and all([array_equal(x[elem], self._d_key_prev[elem]) for elem in dep])))
        
        if cond_same_point:
            self.same_d += 1
            #return deepcopy(self.d_val_prev)
            return dict([(key, Copy(val)) for key, val in self._d_val_prev.items()])
        else:
            self.evals_d += 1

        if isinstance(x, ooPoint): self._point_id1 = x._id
        if fixedVarsScheduleID != -1: self._lastDiffVarsID = fixedVarsScheduleID

        derivativeSelf = self._getDerivativeSelf(x, fixedVarsScheduleID, Vars, fixedVars)

        r = Derivative()
        ac = -1
        for i, inp in enumerate(self.input):
            if not isinstance(inp, oofun): continue
            if inp.discrete: continue

            if inp.is_oovar: 
                if (Vars is not None and inp not in Vars) or (fixedVars is not None and inp in fixedVars):
                    continue                
                ac += 1
                tmp = derivativeSelf[ac]
                val = r.get(inp, None)
                if val is not None:
                    if isscalar(tmp) or (type(val) == type(tmp) == ndarray and prod(tmp.shape) <= prod(val.shape)): # some sparse matrices has no += implemented 
                        r[inp] += tmp
                    else:
                        if isspmatrix(val) and type(tmp) == DiagonalType:
                            tmp = tmp.resolve(True)
                        r[inp] = r[inp] + tmp
                else:
                    r[inp] = tmp
            else:
                ac += 1
                
                elem_d = inp._D(x, fixedVarsScheduleID, Vars=Vars, fixedVars=fixedVars, useSparse = useSparse) 
                
                t1 = derivativeSelf[ac]
                
                for key, val in elem_d.items():
                    #if isinstance(t1, Stochastic) or isinstance(val, Stochastic):
                        #rr = t1 * val
                    if isinstance(t1, Stochastic) or ((isscalar(val) or isinstance(val, multiarray)) and (isscalar(t1) or isinstance(t1, multiarray))):
                        rr = t1 * val
                    elif isinstance(val, Stochastic):
                        rr = val * t1
                    elif type(t1) == DiagonalType and type(val) == DiagonalType:
                        rr = t1 * val
                    elif type(t1) == DiagonalType or type(val) == DiagonalType:
                        if isspmatrix(t1): # thus val is DiagonalType
                            rr = t1._mul_sparse_matrix(val.resolve(True))
                        else:
                            if not isPyPy or type(val) != DiagonalType:
                                rr = t1 *  val #if  type(t1) == DiagonalType or type(val) not in (ndarray, DiagonalType) else (val.T * t1).T   # for PyPy compatibility
                            else:
                                rr = (val * t1.T).T
                    elif isscalar(val) or isscalar(t1) or prod(t1.shape)==1 or prod(val.shape)==1:
                        rr = (t1 if isscalar(t1) or prod(t1.shape)>1 else asscalar(t1) if isinstance(t1, ndarray) else t1[0, 0]) \
                        * (val if isscalar(val) or prod(val.shape)>1 else asscalar(val) if isinstance(val, ndarray) else val[0, 0])
                    else:
                        if val.ndim < 2: val = atleast_2d(val)
                        if useSparse is False:
                            t2 = val
                        else:
                            t1, t2 = self._considerSparse(t1, val)
                        
                        if not type(t1) == type(t2) ==  ndarray:
                            # CHECKME: is it trigger somewhere?
                            if not scipyInstalled:
                                self.pWarn(scipyAbsentMsg)
                                rr = dot(t1, t2)
                            else:
                                t1 = t1 if isspmatrix_csc(t1) else t1.tocsc() if isspmatrix(t1)  else scipy.sparse.csc_matrix(t1)
                                t2 = t2 if isspmatrix_csr(t2) else t2.tocsr() if isspmatrix(t2)  else scipy.sparse.csr_matrix(t2)
                                if t2.shape[0] != t1.shape[1]:
                                    if t2.shape[1] == t1.shape[1]:
                                        t2 = t2.T
                                    else:
                                        raise FuncDesignerException('incorrect shape in FuncDesigner function _D(), inform developers about the bug')
                                rr = t1._mul_sparse_matrix(t2)
                                if useSparse is False:
                                    rr = rr.toarray() 
                        else:
                            rr = dot(t1, t2)
                    #assert rr.ndim>1
                    
                    Val = r.get(key, None)
                    ValType = type(Val)
                    if Val is not None:
                        if type(rr) == DiagonalType:
                            if ValType == DiagonalType:
                                
                                Val = Val + rr # !!!! NOT inplace! (elseware will overwrite stored data used somewhere else)
                                
                            else:
                                tmp  = rr.resolve(useSparse)
                                if type(tmp) == ndarray and hasattr(Val, 'toarray'):
                                    Val = Val.toarray()
                                if type(tmp) == ValType == ndarray and Val.size >= tmp.size:
                                    Val += tmp
                                else: # may be problems with sparse matrices inline operation, which are badly done in scipy.sparse for now
                                    Val = Val + tmp
                        else:
                            if isinstance(Val, ndarray) and hasattr(rr, 'toarray'): # i.e. rr is sparse matrix
                                rr = rr.toarray() # I guess r[key] will hardly be all-zeros
                            elif hasattr(Val, 'toarray') and isinstance(rr, ndarray): # i.e. Val is sparse matrix
                                Val = Val.toarray()
                            if type(rr) == ValType == ndarray and rr.size == Val.size: 
                                Val += rr
                            else: 
                                Val = Val + rr
                        r[key] = Val
                    else:
                        r[key] = rr
        self._d_val_prev = dict([(key, Copy(value)) for key, value in r.items()])
        self._d_key_prev = dict([(elem, Copy(x[elem])) for elem in dep]) if involveStore else None
        return r

    # TODO: handle 2**15 & 0.25 as parameters
    def _considerSparse(self, t1, t2):  
        if int64(prod(t1.shape)) * int64(prod(t2.shape)) > 2**15 and   (isinstance(t1, ndarray) and t1.nonzero()[0].size < 0.25*t1.size) or \
        (isinstance(t2, ndarray) and t2.nonzero()[0].size < 0.25*t2.size):
            if scipy is None: 
                self.pWarn(scipyAbsentMsg)
                return t1,  t2
            if not isinstance(t1, scipy.sparse.csc_matrix): 
                t1 = scipy.sparse.csc_matrix(t1)
            if t1.shape[1] != t2.shape[0]: # can be from flattered t1
                assert t1.shape[0] == t2.shape[0], 'bug in FuncDesigner Kernel, inform developers'
                t1 = t1.T
            if not isinstance(t2, scipy.sparse.csr_matrix): 
                t2 = scipy.sparse.csr_matrix(t2)
        return t1,  t2

    def _getDerivativeSelf(self, x, fixedVarsScheduleID, Vars,  fixedVars):
        Input = self._getInput(x, fixedVarsScheduleID=fixedVarsScheduleID, Vars=Vars,  fixedVars=fixedVars)
        expectedTotalInputLength = sum([Len(elem) for elem in Input])
        
#        if hasattr(self, 'size') and isscalar(self.size): nOutput = self.size
#        else: nOutput = self(x).size 

        hasUserSuppliedDerivative = self.d is not None
        if hasUserSuppliedDerivative:
            derivativeSelf = []
            if type(self.d) == tuple:
                if len(self.d) != len(self.input):
                   raise FuncDesignerException('oofun error: num(derivatives) not equal to neither 1 nor num(inputs)')
                   
                for i, deriv in enumerate(self.d):
                    inp = self.input[i]
                    if not isinstance(inp, oofun) or inp.discrete: 
                        #if deriv is not None: 
                            #raise FuncDesignerException('For an oofun with some input oofuns declared as discrete you have to set oofun.d[i] = None')
                        continue
                    
                    #!!!!!!!!! TODO: handle fixed cases properly!!!!!!!!!!!!
                    #if hasattr(inp, 'fixed') and inp.fixed: continue
                    if inp.is_oovar and ((Vars is not None and inp not in Vars) or (fixedVars is not None and inp in fixedVars)):
                        continue
                        
                    if deriv is None:
                        if not DerApproximatorIsInstalled:
                            raise FuncDesignerException('To perform gradients check you should have DerApproximator installed, see http://openopt.org/DerApproximator')
                        derivativeSelf.append(get_d1(self.fun, Input, diffInt=self.diffInt, stencil = self.stencil, \
                                                     args=self.args, varForDifferentiation = i, pointVal = self._getFuncCalcEngine(x), exactShape = True))
                    else:
                        # !!!!!!!!!!!!!! TODO: add check for user-supplied derivative shape
                        tmp = deriv(*Input)
                        if not isscalar(tmp) and type(tmp) in (ndarray, tuple, list) and type(tmp) != DiagonalType: # i.e. not a scipy.sparse matrix
                            tmp = atleast_2d(tmp)
                            
                            ########################################

                            _tmp = Input[i]
                            Tmp = 1 if isscalar(_tmp) or prod(_tmp.shape) == 1 else len(Input[i])
                            if tmp.shape[1] != Tmp: 
                                # TODO: add debug msg
#                                print('incorrect shape in FD AD _getDerivativeSelf')
#                                print tmp.shape[0], nOutput, tmp
                                if tmp.shape[0] != Tmp: raise FuncDesignerException('error in getDerivativeSelf()')
                                tmp = tmp.T
                                    
                            ########################################

                        derivativeSelf.append(tmp)
            else:
                tmp = self.d(*Input)
                if not isscalar(tmp) and type(tmp) in (ndarray, tuple, list): # i.e. not a scipy.sparse matrix
                    tmp = atleast_2d(tmp)
                    
                    if tmp.shape[1] != expectedTotalInputLength: 
                        # TODO: add debug msg
                        if tmp.shape[0] != expectedTotalInputLength: raise FuncDesignerException('error in getDerivativeSelf()')
                        tmp = tmp.T
                        
                ac = 0
                if isinstance(tmp, ndarray) and hasattr(tmp, 'toarray') and not isinstance(tmp, multiarray): tmp = tmp.A # is dense matrix
                
                #if not isinstance(tmp, ndarray) and not isscalar(tmp) and type(tmp) != DiagonalType:
                if len(Input) == 1:
#                    if type(tmp) == DiagonalType: 
#                            # TODO: mb rework it
#                            if Input[0].size > 150 and tmp.size > 150:
#                                tmp = tmp.resolve(True).tocsc()
#                            else: tmp =  tmp.resolve(False) 
                    derivativeSelf = [tmp]
                else:
                    for i, inp in enumerate(Input):
                        t = self.input[i]
                        if t.discrete or (t.is_oovar and ((Vars is not None and t not in Vars) or (fixedVars is not None and t in fixedVars))):
                            ac += inp.size
                            continue                                    
                        if isinstance(tmp, ndarray):
                            TMP = tmp[:, ac:ac+Len(inp)]
                        elif isscalar(tmp):
                            TMP = tmp
                        elif type(tmp) == DiagonalType: 
                            if tmp.size == inp.size and ac == 0:
                                TMP = tmp
                            else:
                                # print debug warning here
                                # TODO: mb rework it
                                if inp.size > 150 and tmp.size > 150:
                                    tmp = tmp.resolve(True).tocsc()
                                else: tmp =  tmp.resolve(False) 
                                TMP = tmp[:, ac:ac+inp.size]
                        else: # scipy.sparse matrix
                            TMP = tmp.tocsc()[:, ac:ac+inp.size]
                        ac += Len(inp)
                        derivativeSelf.append(TMP)
                    
            # TODO: is it required?
#                if not hasattr(self, 'outputTotalLength'): self(x)
#                
#                if derivativeSelf.shape != (self.outputTotalLength, self.inputTotalLength):
#                    s = 'incorrect shape for user-supplied derivative of oofun '+self.name+': '
#                    s += '(%d, %d) expected, (%d, %d) obtained' % (self.outputTotalLength, self.inputTotalLength,  derivativeSelf.shape[0], derivativeSelf.shape[1])
#                    raise FuncDesignerException(s)
        else:
            if Vars is not None or fixedVars is not None: raise FuncDesignerException("sorry, custom oofun derivatives don't work with Vars/fixedVars arguments yet")
            if not DerApproximatorIsInstalled:
                raise FuncDesignerException('To perform this operation you should have DerApproximator installed, see http://openopt.org/DerApproximator')
                
            derivativeSelf = get_d1(self.fun, Input, diffInt=self.diffInt, stencil = self.stencil, args=self.args, pointVal = self._getFuncCalcEngine(x), exactShape = True)
            if type(derivativeSelf) == tuple:
                derivativeSelf = list(derivativeSelf)
            elif type(derivativeSelf) != list:
                derivativeSelf = [derivativeSelf]
        
        #assert all([elem.ndim > 1 for elem in derivativeSelf])
       # assert len(derivativeSelf[0])!=16
        #assert (type(derivativeSelf[0]) in (int, float)) or derivativeSelf[0][0]>480.00006752 or derivativeSelf[0][0]<480.00006750
        return derivativeSelf

    def D2(self, x):
        raise FuncDesignerException('2nd derivatives for obj-funcs are not implemented yet')

    def check_d1(self, point):
        if self.d is None:
            self.disp('Error: no user-provided derivative(s) for oofun ' + self.name + ' are attached')
            return # TODO: return non-void result
        separator = 75 * '*'
        self.disp(separator)
        assert type(self.d) != list
        val = self(point)
        input = self._getInput(point)
        ds= self._getDerivativeSelf(point, fixedVarsScheduleID = -1, Vars=None,  fixedVars=None)
        self.disp(self.name + ': checking user-supplied gradient')
        self.disp('according to:')
        self.disp('    diffInt = ' + str(self.diffInt)) # TODO: ADD other parameters: allowed epsilon, maxDiffLines etc
        self.disp('    |1 - info_user/info_numerical| < maxViolation = '+ str(self.maxViolation))        
        j = -1
        for i in range(len(self.input)):
            if len(self.input) > 1: self.disp('by input variable number ' + str(i) + ':')
            if isinstance(self.d, tuple) and self.d[i] is None:
                self.disp('user-provided derivative for input number ' + str(i) + ' is absent, skipping the one;')
                self.disp(separator)
                continue
            if not isinstance(self.input[i], oofun):
                self.disp('input number ' + str(i) + ' is not oofun instance, skipping the one;')
                self.disp(separator)
                continue
            j += 1
            check_d1(lambda *args: self.fun(*args), ds[j], input, \
                 func_name=self.name, diffInt=self.diffInt, pointVal = val, args=self.args, \
                 stencil = max((3, self.stencil)), maxViolation=self.maxViolation, varForCheck = i)

    def getOrder(self, Vars=None, fixedVars=None, fixedVarsScheduleID=-1):
        
        # TODO: improve it wrt fixedVarsScheduleID
        
        # returns polinomial order of the oofun
        if isinstance(Vars, oofun): Vars = set([Vars])
        elif Vars is not None and type(Vars) != set: Vars = set(Vars)
        
        if isinstance(fixedVars, oofun): fixedVars = set([fixedVars])
        elif fixedVars is not None and type(fixedVars) != set: fixedVars = set(fixedVars)
        
        sameVarsScheduleID = fixedVarsScheduleID == self._lastOrderVarsID 
        rebuildFixedCheck = not sameVarsScheduleID
        if fixedVarsScheduleID != -1: self._lastOrderVarsID = fixedVarsScheduleID
        
        if rebuildFixedCheck:
            # ajust new value of self._order wrt new free/fixed vars schedule
            if self.discrete: self._order = 0
       
            if self.is_oovar:
                if (fixedVars is not None and self in fixedVars) or (Vars is not None and self not in Vars):
                    self._order = 0
                else:
                    self._order = 1
            else:
#                orders = [(inp.getOrder(Vars, fixedVars) if isinstance(inp, oofun) else 0) for inp in self.input]
                orders = []
                for inp in self.input:
                    if isinstance(inp, oofun):
                        orders.append(inp.getOrder(Vars, fixedVars))
                    elif isinstance(inp, OOArray):
                        orders += [(elem.getOrder(Vars, fixedVars) if isinstance(elem, oofun) else 0) for elem in inp.view(ndarray)]
                self._order = inf if any(asarray(orders) != 0) else 0

        return self._order
    
    # TODO: should broadcast return non-void result?
    def _broadcast(self, func, useAttachedConstraints, *args, **kwargs):
        if self._broadcast_id == oofun._BroadCastID: 
            return # already done for this one
            
        self._broadcast_id = oofun._BroadCastID
        
        # TODO: possibility of reverse order?
        if self.input is not None:
            for inp in self.input: 
                if not isinstance(inp, oofun): continue
                inp._broadcast(func, useAttachedConstraints, *args, **kwargs)
        if useAttachedConstraints:
            for c in self.attachedConstraints:
                c._broadcast(func, useAttachedConstraints, *args, **kwargs)
        func(self, *args, **kwargs)
        
#    def isUncycled(self):
#        # TODO: speedup the function via omitting same oofuns
#        # TODO: handle fixed variables
#        deps = []
#        oofuns = []
#        dep_num = []
#        for elem in self._getDep():
#            if isinstance(elem, oofun):
#                if elem.is_oovar:
#                    deps.append(elem)
#                    dep_num.append(1)
#                else:
#                    tmp = elem._getDep()
#                    dep_num.append(len(tmp))
#                    if tmp is not None:
#                        deps.append(tmp)
#                    oofuns.append(elem)
#                    
#        if any([not elem.isUncycled() for elem in oofuns]):
#            return False
#        r1 = set()
#        r1.update(deps)
#        return True if len(r1) == sum(dep_num) else False
        
    def uncertainty(self, point, deviations, actionOnAbsentDeviations='warning'):
        ''' 
        result = oofun.uncertainty(point, deviations, actionOnAbsentDeviations='warning')
        point and deviations should be Python dicts of pairs (oovar, value_for_oovar)
        actionOnAbsentDeviations = 
        'error' (raise FuncDesigner exception) | 
        'skip' (treat as fixed number with zero deviation) |
        'warning' (print warning, treat as fixed number) 
        
        Sparse large-scale examples haven't been tested,
        we could implement and test it properly on demand
        '''
        dep = self._getDep()
        dev_keys = set(deviations.keys())
        set_diff = dep.difference(dev_keys)
        nAbsent = len(set_diff)
        if actionOnAbsentDeviations != 'skip':
            if len(set_diff) != 0:
                if actionOnAbsentDeviations == 'warning':
                    pWarn('''
                    dict of deviations miss %d variables (oovars): %s;
                    they will be treated as fixed numbers with zero deviations
                    ''' % (nAbsent, list(set_diff)))
                else:
                    raise FuncDesignerException('dict of deviations miss %d variable(s) (oovars): %s' % (nAbsent, list(set_diff)))
        
        d = self.D(point, exactShape=True) if nAbsent == 0 else self.D(point, fixedVars = set_diff, exactShape=True)
        tmp = [dot(val, (deviations[key] if isscalar(deviations[key]) else asarray(deviations[key]).reshape(-1, 1)))**2 for key, val in d.items()]
        tmp = [asscalar(elem) if isinstance(elem, ndarray) and elem.size == 1 else elem for elem in tmp]
        r = atleast_2d(hstack(tmp)).sum(1)
        return r ** 0.5
        
    # For Python 3:
    __rtruediv__ = __rdiv__
    __truediv__ = __div__
    
    def IMPLICATION(*args, **kw): 
        raise FuncDesignerException('oofun.IMPLICATION is temporary disabled, use ifThen(...) or IMPLICATION(...) instead')
    
    """                                             End of class oofun                                             """

# TODO: make it work for ooSystem as well
def broadcast(func, oofuncs, useAttachedConstraints, *args, **kwargs):
    if isinstance(oofuncs, oofun):
        oofuncs = [oofuncs]
    oofun._BroadCastID += 1
    for oof in oofuncs:
        if oof is not None: 
            oof._broadcast(func, useAttachedConstraints, *args, **kwargs)

def _getAllAttachedConstraints(oofuns):
    from FuncDesigner import broadcast
    r = set()
    def F(oof):
        #print len(oof.attachedConstraints)
        r.update(oof.attachedConstraints)
    broadcast(F, oofuns, useAttachedConstraints=True)
    return r


#def discreteNLH(_input_bool_oofun, Lx, Ux, p, dataType):
#    
#    T0, res, DefiniteRange = _input_bool_oofun.nlh(Lx, Ux, p, dataType)
#    #T = 1.0 - T0
#    #R = dict([(v, 1.0-val) for v, val in res.items()])
#    return T.flatten(), R, DefiniteRange

def nlh_and(_input, dep, Lx, Ux, p, dataType):
    nlh_0 = array(0.0)
    R = {}
    DefiniteRange = True
    
    elems_nlh = [(elem.nlh(Lx, Ux, p, dataType) if isinstance(elem, oofun) \
                  else (0, {}, None) if elem is True 
                  else (inf, {}, None) if elem is False 
                  else raise_except()) for elem in _input]
                  
    for T0, res, DefiniteRange2 in elems_nlh:
        DefiniteRange = logical_and(DefiniteRange, DefiniteRange2)
        
    for T0, res, DefiniteRange2 in elems_nlh:
        if T0 is None or T0 is True: continue
        if T0 is False or all(T0 == inf):
            return inf, {}, DefiniteRange
        if all(isnan(T0)):
            raise FuncDesignerException('unimplemented for non-oofun or fixed oofun input yet')
        
        if type(T0) == ndarray:
            if nlh_0.shape == T0.shape:
                nlh_0 += T0
            elif nlh_0.size == T0.size:
                nlh_0 += T0.reshape(nlh_0.shape)
            else:
                nlh_0 = nlh_0 + T0
        else:
            nlh_0 += T0
        
        # debug 
#    if not any(isfinite(nlh_0)):
#        return inf, {}, DefiniteRange
#    for T0, res, DefiniteRange2 in elems_nlh:
        #debug end
        
        T_0_vect = T0.reshape(-1, 1) if type(T0) == ndarray else T0
        
        for v, val in res.items():
            r = R.get(v, None)
            if r is None:
                R[v] = val - T_0_vect
            else:
                r += (val if r.shape == val.shape else val.reshape(r.shape)) - T_0_vect
        
    nlh_0_shape = nlh_0.shape
    nlh_0 = nlh_0.reshape(-1, 1)
    for v, val in R.items():
        # TODO: check it
        #assert all(isfinite(val))
        tmp =  val + nlh_0
        tmp[isnan(tmp)] = inf # when val = -inf summation with nlh_0 == inf
        R[v] = tmp

    return nlh_0.reshape(nlh_0_shape), R, DefiniteRange


def nlh_xor(_input, dep, Lx, Ux, p, dataType):
    nlh_0 = array(0.0)
    nlh_list = []
    nlh_list_m = {}
    num_inf_m = {}
    S_finite = array(0.0)
    num_inf_0 = atleast_1d(0)
    num_inf_elems = []
    R_diff = {}
    R_inf = {}
    #S_finite_diff = {}
    
    DefiniteRange = True
    
#    elems_nlh = [(elem.nlh(Lx, Ux, p, dataType) if isinstance(elem, oofun) \
#                  else (0, {}, None) if elem is True 
#                  else (inf, {}, None) if elem is False 
#                  else raise_except()) for elem in _input]

    elems_lh = [(elem.lh(Lx, Ux, p, dataType) if isinstance(elem, oofun) \
                  else (inf, {}, None) if elem is True 
                  else (0, {}, None) if elem is False 
                  else raise_except()) for elem in _input]


    for T0, res, DefiniteRange2 in elems_lh:
        DefiniteRange = logical_and(DefiniteRange, DefiniteRange2)

    for j, (T0, res, DefiniteRange2) in enumerate(elems_lh):
        if T0 is None: 
            raise FuncDesignerException('probably bug in FD kernel')
            # !!!!!!!!!!!!!!!!! check "len(elems_lh)" below while calculating P_t
            #continue
        if all(isnan(T0)):
            raise FuncDesignerException('unimplemented for non-oofun or fixed oofun input yet')

        #T_0_vect = T0.reshape(-1, 1) if type(T0) == ndarray else T0
        
        T_inf = where(isfinite(T0), 0, 1)
        num_inf_elems.append(T_inf)
        T0 = where(isfinite(T0), T0, 0.0)
        two_pow_t0 = 2.0 ** T0
        if type(T0) == ndarray:
            if nlh_0.shape == T0.shape:
                nlh_0 += T0
                num_inf_0 += T_inf
                S_finite += two_pow_t0
            elif nlh_0.size == T0.size:
                nlh_0 += T0.reshape(nlh_0.shape)
                num_inf_0 += T_inf.reshape(nlh_0.shape)
                S_finite += two_pow_t0.reshape(nlh_0.shape)
            else:
                nlh_0 = nlh_0 + T0
                num_inf_0 = num_inf_0 + T_inf
                S_finite = S_finite + two_pow_t0.reshape(nlh_0.shape)
        else:
            nlh_0 += T0
            num_inf_0 += T_inf
            S_finite += two_pow_t0
            
        nlh_list.append(T0)
        
        for v, val in res.items():
            T_inf_v = where(isfinite(val), 0, 1)
            val_noninf = where(isfinite(val), val, 0)
            T0v = val_noninf - T0.reshape(-1, 1)
            
            r = nlh_list_m.get(v, None)
            if r is None:
                nlh_list_m[v] = [(j, T0v)]
                num_inf_m[v] = [(j, T_inf_v.copy())]
                #num_inf_m[v] = T_inf_v.copy()
            else:
                r.append((j, T0v))
                num_inf_m[v].append((j, T_inf_v.copy()))
                #num_inf_m[v] +=T_inf_v
                
            r = R_inf.get(v, None)
            T_inf = T_inf.reshape(-1, 1)
            if r is None:
                R_inf[v] = T_inf_v - T_inf#.reshape(-1, 1)
                R_diff[v] = T0v.copy()
            else:
                # TODO: check for 1st elem of size 1
                r += (T_inf_v if r.shape == T_inf_v.shape else T_inf_v.reshape(r.shape))  - T_inf#.reshape(-1, 1)
                R_diff[v] += T0v
                
        
    nlh_1 = [nlh_0 - elem for elem in nlh_list]
    # !!! TODO: speedup it via matrix insted of sequence of vectors
    num_infs = [num_inf_0 - t for t in num_inf_elems]

    S1 = PythonSum([2.0 ** where(num_infs[j] == 0, -t, -inf) for j, t in enumerate(nlh_1)])
    S2 = atleast_1d(len(elems_lh)  * 2.0 ** (-nlh_0))
    S2[num_inf_0 != 0] = 0
    #nlh_t = -log(S2 - S1 + 1.0)
    #nlh_t = -log1p(S2 - S1) * 1.4426950408889634
    nlh_t = -log2(S1-S2)
#    assert not any(isnan(nlh_t))
#    if not all(isfinite(nlh_t)):
#        print('='*10)
#        print(nlh_t)
#        print(elems_lh)
#        raise 0
    #print(elems_lh)
#    print(R_inf)
    #raise 0
    R = {}
    nlh_0 = nlh_0.reshape(-1, 1)
    num_inf_0 = num_inf_0.reshape(-1, 1)

    for v, nlh_diff in R_diff.items():
        nlh = nlh_0 + nlh_diff
        nlh_1 = [nlh - elem.reshape(-1, 1) for elem in nlh_list]
        
        for j, val in nlh_list_m[v]:
            nlh_1[j] -= val
        Tmp = R_inf[v] + num_inf_0
        num_infs = [Tmp] * len(nlh_1)
        for j, num_inf in num_inf_m[v]:
            num_infs[j] = num_inf
        
        num_infs2 = [Tmp - elem for elem in num_infs]
        #num_infs = num_inf - num_inf_m[v]
        S1 = PythonSum([2.0 ** where(num_infs2[j] == 0, -elem, -inf) for j, elem in enumerate(nlh_1)])
        S2 = atleast_1d(len(elems_lh)  * 2.0 ** (-nlh))
        S2[Tmp.reshape(S2.shape) != 0] = 0
        R[v] = -log2(S1 - S2)
        #R[v] = -log1p(S2 - S1) * 1.4426950408889634
        
    for v, val in R.items():
        val[isnan(val)] = inf
        val[val < 0.0] = 0.0
#    print('-'*10)
#    #print(Lx, Ux)
#    print('elems_lh:', elems_lh)
#    print(nlh_t, R, DefiniteRange)
    #raw_input()
#    if nlh_t.size > 2:
#        raise 0
    return nlh_t, R, DefiniteRange


#def nlh_not(_input_bool_oofun, dep, Lx, Ux, p, dataType):
#    if _input_bool_oofun is True or _input_bool_oofun is False:
#        raise 'unimplemented for non-oofun input yet'
#    T0, res, DefiniteRange = _input_bool_oofun.nlh(Lx, Ux, p, dataType)
#    T = 1.0 - T0
#    R = dict([(v, 1.0-val) for v, val in res.items()])
#    return T, R, DefiniteRange

def nlh_not(_input_bool_oofun, dep, Lx, Ux, p, dataType):
    if _input_bool_oofun is True or _input_bool_oofun is False:
        raise 'unimplemented for non-oofun input yet'
       
    T0, res, DefiniteRange = _input_bool_oofun.nlh(Lx, Ux, p, dataType)
    T = reverse_l2P(T0)
    R = dict([(v, reverse_l2P(val)) for v, val in res.items()])
    return T, R, DefiniteRange


def reverse_l2P(l2P):
    l2P = atleast_1d(l2P)# elseware bug "0-d arrays cannot be indexed"
    #l2P[l2P<0]=0
    r = 1.0 / l2P
    ind = l2P < 15
    r[ind] = -log2(1-2**(-l2P[ind]))
    #r[r<0] = 0
    return r
    

def AND(*args):
    Args = args[0] if len(args) == 1 and isinstance(args[0], (ndarray, tuple, list, set)) else args
#    for arg in Args:
#        if isinstance(arg, SmoothFDConstraint) and arg.lb == arg.ub and arg.tol == 0 and not arg.alt_nlh_func:
#            pass
            #raise FuncDesignerException('equality constraint for smooth func inside logical FD func should have user-assigned tolerance')
    assert not isinstance(args[0], ndarray), 'unimplemented yet' 
    for arg in Args:
        if not isinstance(arg, oofun):
            raise FuncDesignerException('FuncDesigner logical AND currently is implemented for oofun instances only')
    #if other is True: return self
    
    f  = logical_and if len(Args) == 2 else alt_AND_engine
    r = BooleanOOFun(f, Args, vectorized = True)
    r.nlh = lambda *arguments: nlh_and(Args, r._getDep(), *arguments)
    r.oofun = r
    return r
    
def alt_AND_engine(*input):
    tmp = input[0]
    for i in range(1, len(input)):
        tmp = logical_and(tmp, input[i])
    return tmp

# TODO: multiple args
XOR_prev = lambda arg1, arg2: (arg1 & ~arg2) | (~arg1 & arg2)

def XOR(*args):
    Args = args[0] if len(args) == 1 and isinstance(args[0], (ndarray, tuple, list, set)) else args
#    for arg in Args:
#        if isinstance(arg, SmoothFDConstraint) and arg.lb == arg.ub and arg.tol == 0 and not arg.alt_nlh_func:
#            pass
            #raise FuncDesignerException('equality constraint for smooth func inside logical FD func should have user-assigned tolerance')
    assert not isinstance(args[0], ndarray), 'unimplemented yet' 
    for arg in Args:
        if not isinstance(arg, oofun):
            raise FuncDesignerException('FuncDesigner logical XOR currently is implemented for oofun instances only')
    #if other is True: return self
    
    #f = lambda *args: logical_xor(hstack([asarray(elem).reshape(-1, 1) for elem in args]))
    r = BooleanOOFun(f_xor, Args, vectorized = True)
    r.nlh = lambda *arguments: nlh_xor(Args, r._getDep(), *arguments)
    r.oofun = r # is it required?
    return r
def f_xor(*args):
    r = sum(array(args), 0)
    return r == 1


EQUIVALENT = lambda arg1, arg2: ((arg1 & arg2) | (~arg1 & ~arg2))
    
def NOT(_bool_oofun):
    assert not isinstance(_bool_oofun, (ndarray, list, tuple, set)), 'disjunctive and other logical constraint are not implemented for ooarrays/ndarrays/lists/tuples yet' 
    #Args = args[0] if len(args) == 1 and type(args[0]) in (tuple, list, set) else args
    #Args = args if type(args) in (tuple, list, set) else [args]
    if not isinstance(_bool_oofun, oofun):
        raise FuncDesignerException('FuncDesigner logical NOT currently is implemented for oofun instances only')
#    if isinstance(_bool_oofun, SmoothFDConstraint) and _bool_oofun.lb == _bool_oofun.ub and _bool_oofun.tol == 0 and not _bool_oofun.alt_nlh_func:
#        raise FuncDesignerException('equality constraint for smooth func inside logical FD func should have user-assigned tolerance')
        
    #if other is True: return False
    r = BooleanOOFun(logical_not, [_bool_oofun], vectorized = True)
    r.oofun = r

    if _bool_oofun.is_oovar:
        r.lh = lambda *arguments: nlh_not(_bool_oofun, r._getDep(), *arguments)
        r.nlh = _bool_oofun.lh
    else:
        r.nlh = lambda *arguments: nlh_not(_bool_oofun, r._getDep(), *arguments)
    return r

NAND = lambda *args, **kw: NOT(AND(*args, **kw))
NOR = lambda *args, **kw: NOT(OR(*args, **kw))


def OR(*args):
    Args = args[0] if len(args) == 1 and isinstance(args[0], (ndarray, list, tuple, set)) else args
    assert not isinstance(args[0], ndarray), 'unimplemented yet' 
    for arg in Args:
        if not isinstance(arg, oofun):
            raise FuncDesignerException('FuncDesigner logical AND currently is implemented for oofun instances only')
    
    r = ~ AND([~elem for elem in Args])
    #r.fun = np.logical_or
    r.oofun = r
    return r

class BooleanOOFun(oofun):
    _unnamedBooleanOOFunNumber = 0
    discrete = True
    #alt_nlh_func = False
    # an oofun that returns True/False
    def __init__(self, func, _input, *args, **kwargs):
        oofun.__init__(self, func, _input, *args, **kwargs)
        #self.input = oofun_Involved.input
        BooleanOOFun._unnamedBooleanOOFunNumber += 1
        self.name = 'unnamed_boolean_oofun_' + str(BooleanOOFun._unnamedBooleanOOFunNumber)
        self.oofun = oofun(lambda *args, **kw: asanyarray(func(*args, **kw), int8), _input, vectorized = True)
        # TODO: THIS SHOULD BE USED IN UP-LEVEL ONLY
        self.lb = self.ub = 1
    
    __hash__ = lambda self: self._id
        
    def size(self, *args, **kwargs): raise FuncDesignerException('currently BooleanOOFun.size() is disabled')
    def D(self, *args, **kwargs): raise FuncDesignerException('currently BooleanOOFun.D() is disabled')
    def _D(self, *args, **kwargs): raise FuncDesignerException('currently BooleanOOFun._D() is disabled')
    
    def nlh(self, *args, **kw):
        raise FuncDesignerException('This is virtual method to be overloaded in derived class instance')
    
    __and__ = AND
    
    #IMPLICATION = IMPLICATION
    __eq__ = EQUIVALENT
    __ne__ = lambda self, arg: NOT(self==arg)
    
    def __or__(self, other):
        #if other is False: return self
        
        return ~((~self) & (~other))
        
#        print('__or__')
#        r = BooleanOOFun(logical_or, (self, other), vectorized = True)
#        r.nlh = lambda *args: nlh_or((self, other), r._getDep(), *args)
#        r.oofun = r
#        return r
        
    
    def __xor__(self, other):
        return BooleanOOFun(logical_xor, (self, other), vectorized = True)
    
    def __invert__(self):
        r = BooleanOOFun(logical_not, self, vectorized = True)
        r.nlh = lambda *args: nlh_not(self, r._getDep(), *args)
        r.oofun = r
        return r
    
class BaseFDConstraint(BooleanOOFun):
    isConstraint = True
    tol = 0.0 
    expected_kwargs = set(['tol', 'name'])
    #def __getitem__(self, point):

    def __call__(self, *args,  **kwargs):
        expected_kwargs = self.expected_kwargs
        if not set(kwargs.keys()).issubset(expected_kwargs):
            raise FuncDesignerException('Unexpected kwargs: should be in '+str(expected_kwargs)+' got: '+str(kwargs.keys()))
            
        for elem in expected_kwargs:
            if elem in kwargs:
                setattr(self, elem, kwargs[elem])
        
        if len(args) > 1: raise FuncDesignerException('No more than single argument is expected')
        
        if len(args) == 0:
           if len(kwargs) == 0: raise FuncDesignerException('You should provide at least one argument')
           return self
           
        if isinstance(args[0], str):
            self.name = args[0]
            return self
        elif hasattr(args[0], 'xf'):
            return self(args[0].xf)
            
        return self._getFuncCalcEngine(*args,  **kwargs)
        
    def _getFuncCalcEngine(self, *args,  **kwargs):
        
        if not isinstance(args[0], dict): 
            raise FuncDesignerException('unexpected type: %s' % type(args[0]))
            
        isMultiPoint = isinstance(args[0], ooPoint) and args[0].isMultiPoint == True
        
        val = self.oofun(args[0])
        Tol = max((0.0, self.tol))
        
        if isMultiPoint:
            return logical_and(self.lb-Tol<= val, val <= self.ub + Tol)
        elif any(isnan(val)):
            return False
        if any(atleast_1d(self.lb-val)>Tol):
            return False
        elif any(atleast_1d(val-self.ub)>Tol):
            return False
        return True
            

    def __init__(self, oofun_Involved, *args, **kwargs):
        BooleanOOFun.__init__(self, oofun_Involved._getFuncCalcEngine, (oofun_Involved.input if not oofun_Involved.is_oovar else oofun_Involved), *args, **kwargs)
        #oofun.__init__(self, lambda x: oofun_Involved(x), input = oofun_Involved)
        if len(args) != 0:
            raise FuncDesignerException('No args are allowed for FuncDesigner constraint constructor, only some kwargs')
            
        # TODO: replace self.oofun by self.engine
        self.oofun = oofun_Involved
        

class SmoothFDConstraint(BaseFDConstraint):
        
    __getitem__ = lambda self, point: self.__call__(point)
        
    def __init__(self, *args, **kwargs):
        BaseFDConstraint.__init__(self, *args, **kwargs)
        self.lb, self.ub = -inf, inf
        for key, val in kwargs.items():
            if key in ['lb', 'ub', 'tol']:
                setattr(self, key, asfarray(val))
            else:
                raise FuncDesignerException('Unexpected key in FuncDesigner constraint constructor kwargs')
    
    def lh(self, *args, **kw): # overwritten in ooVar, mb something else
        if '_invert' not in self.__dict__:
            self._invert = NOT(self)
        return self._invert.nlh(*args, **kw)
    
    def nlh(self, Lx, Ux, p, dataType):
        m = Lx.shape[0] # is changed in the cycle
        if m == 0:
            assert 0, 'bug in FuncDesigner'
            #return None, None, None
            
        DefiniteRange = True
        
        tol = self.tol if self.tol > 0.0 else p.contol if self.tol == 0 else 0.0 # 0 for negative tolerances
        # TODO: check it
        if p.solver.dataHandling == 'sorted': tol = 0
        selfDep = (self.oofun._getDep() if not self.oofun.is_oovar else set([self.oofun]))
        
        # prev
        #domainData = [(v, (Lx[:, k], Ux[:, k])) for k, v in enumerate(p._freeVarsList)]
        
        # new
        # TODO: improve it
        domainData = [(v, (Lx[:, k], Ux[:, k])) for k, v in enumerate(p._freeVarsList) if v in selfDep]

        domain = ooPoint(domainData, skipArrayCast=True)
        domain.isMultiPoint = True
        domain.dictOfFixedFuncs = p.dictOfFixedFuncs
        
        r, r0 = self.oofun.iqg(domain, dataType, self.lb, self.ub)
        Lf, Uf = r0.lb, r0.ub
        tmp = getSmoothNLH(tile(Lf, (2, 1)), tile(Uf, (2, 1)), self.lb, self.ub, tol, m, dataType)
        T02 = tmp
        T0 = T02[:, tmp.shape[1]/2:].flatten()
        
        res = {}
        if len(r):
            dep = selfDep.intersection(domain.keys()) # TODO: Improve it
            for v in dep:
                Lf, Uf = vstack((r[v][0].lb, r[v][1].lb)), vstack((r[v][0].ub, r[v][1].ub))
                
                # TODO: 1) FIX IT it for matrix definiteRange
                # 2) seems like DefiniteRange = (True, True) for any variable is enough for whole range to be defined in the involved node
                DefiniteRange = logical_and(DefiniteRange, r[v][0].definiteRange)
                DefiniteRange = logical_and(DefiniteRange, r[v][1].definiteRange)
                
                tmp = getSmoothNLH(Lf, Uf, self.lb, self.ub, tol, m, dataType) #- T02
                #tmp[isnan(tmp)] = inf
                res[v] = tmp 
        return T0, res, DefiniteRange
        
def getSmoothNLH(Lf, Uf, lb, ub, tol, m, dataType):

    M = prod(Lf.shape) / (2*m)
    #init
    Lf, Uf  = Lf.reshape(2*M, m).T, Uf.reshape(2*M, m).T
    #1
    #Lf, Uf  = Lf.reshape(m, 2*M), Uf.reshape(m, 2*M)
    
    lf1, lf2, uf1, uf2 = Lf[:, 0:M], Lf[:, M:2*M], Uf[:, 0:M], Uf[:, M:2*M]

    UfLfDiff = Uf - Lf
    if UfLfDiff.dtype.type in [int8, int16, int32, int64, int]:
        UfLfDiff = asfarray(UfLfDiff)
    #UfLfDiff[UfLfDiff > 1e200] = 1e200
    if lb == ub:
        val = ub
        
        ind1, ind2 = val - tol > Uf, val+tol < Lf
#        residual[ind1] += val - tol - Uf[ind1]
#        residual[ind2] += Lf[ind2] - (val + tol)
        
        Uf_t,  Lf_t = Uf.copy(), Lf.copy()
        if Uf.dtype.type in [int8, int16, int32, int64, int] or Lf.dtype.type in [int8, int16, int32, int64, int]:
            Uf_t,  Lf_t = asfarray(Uf_t), asfarray(Lf_t)
        
        
        Uf_t[Uf_t > val + tol] = val + tol
        Lf_t[Lf_t < val - tol] = val - tol
        allowedLineSegmentLength = Uf_t - Lf_t
        tmp = allowedLineSegmentLength / UfLfDiff
        #tmp[tmp>1] = 1
        tmp[logical_or(isinf(Lf), isinf(Uf))] = 1e-10 #  (to prevent inf/inf=nan); TODO: rework it
        
        tmp[allowedLineSegmentLength == 0.0] = 1.0 # may be encountered if Uf == Lf, especially for integer probs
        tmp[tmp<1e-300] = 1e-300 # TODO: improve it

        # TODO: for non-exact interval quality increase nlh while moving from 0.5*(Ux-Lx)
        tmp[val - tol > Uf] = 0
        tmp[val + tol < Lf] = 0

    elif isfinite(lb) and not isfinite(ub):
        tmp = (Uf - (lb - tol)) / UfLfDiff
        
        #ind = Lf < lb-tol
        #residual[ind] += lb-Lf[ind]
        
        tmp[logical_and(isinf(Lf), logical_not(isinf(Uf)))] = 1e-10 # (to prevent inf/inf=nan); TODO: rework it
        tmp[isinf(Uf)] = 1-1e-10 # (to prevent inf/inf=nan); TODO: rework it
        
        tmp[tmp<1e-300] = 1e-300 # TODO: improve it
        tmp[tmp>1.0] = 1.0
        
        #tmp[lb-tol> Uf] = 0
        tmp[lb-tol > Uf] = 0
        
        tmp[lb <= Lf] = 1
        #tmp[lb <= Lf] = 1
        
    elif isfinite(ub) and not isfinite(lb):
        tmp = (ub + tol - Lf ) / UfLfDiff
        
        #ind = Uf > ub+tol
        #residual[ind] += Uf[ind]-ub
        
        tmp[isinf(Lf)] = 1-1e-10 # (to prevent inf/inf=nan);TODO: rework it
        tmp[logical_and(isinf(Uf), logical_not(isinf(Lf)))] = 1e-10 # (to prevent inf/inf=nan); TODO: rework it
        
        tmp[tmp<1e-300] = 1e-300 # TODO: improve it
        tmp[tmp>1.0] = 1.0
        
        tmp[ub+tol < Lf] = 0
        #tmp[ub < Lf] = 0
        
        tmp[ub >= Uf] = 1
        #tmp[ub >= Uf] = 1

    else:
        raise FuncDesignerException('this part of interalg code is unimplemented for double-box-bound constraints yet')
    
    tmp = -log2(tmp)
    tmp[isnan(tmp)] = inf # to prevent some issues in disjunctive cons    
    return tmp

class Constraint(SmoothFDConstraint):
    def __init__(self, *args, **kwargs):
        
        SmoothFDConstraint.__init__(self, *args, **kwargs)
        
        
class BoxBoundConstraint(SmoothFDConstraint):
    def __init__(self, *args, **kwargs):
        SmoothFDConstraint.__init__(self, *args, **kwargs)
        
class Derivative(dict):
    def __init__(self):
        pass


#def ooFun(*args, **kwargs):
#    r = oofun(*args, **kwargs)
#    r.isCostly = True
#    return r

def atleast_oofun(arg):
    if isinstance(arg, oofun):
        return arg
    elif hasattr(arg, 'copy'):
        tmp = arg.copy()
        return oofun(lambda *args, **kwargs: tmp, input = None, getOrder = lambda *args,  **kwargs: 0, discrete=True)#, isConstraint = True)
    elif isscalar(arg):
        tmp = array(arg, 'float')
        return oofun(lambda *args, **kwargs: tmp, input = None, getOrder = lambda *args,  **kwargs: 0, discrete=True)#, isConstraint = True)
    else:
        #return oofun(lambda *args, **kwargs: arg(*args,  **kwargs), input=None, discrete=True)
        raise FuncDesignerException('incorrect type for the function _atleast_oofun')

def mul_aux_d(x, y):
    Xsize, Ysize = Len(x), Len(y)
    if Xsize == 1:
        return Copy(y)
    elif Ysize == 1:
        return Diag(None, scalarMultiplier = y, size = Xsize)
    elif Xsize == Ysize:
        return Diag(y)
    else:
        raise FuncDesignerException('for oofun multiplication a*b should be size(a)=size(b) or size(a)=1 or size(b)=1')   

def mul_interval(self, other, isOtherOOFun, domain, dtype):#*args, **kw):
    if domain.isMultiPoint and isOtherOOFun and self.is_oovar and (self.domain is bool or self.domain is 'bool'):
        #ind_nz = where(domain[self][1]!=0)[0]
        lb_ub, definiteRange = other._interval(domain, dtype)
        n = domain[self][1].size
        R = zeros((2, n), dtype)
        ind = domain[self][0]!=0
        R[0][ind] = lb_ub[0][ind]
        ind = domain[self][1]!=0
        R[1][ind] = lb_ub[1][ind]
        return R, definiteRange
#                    if ind_nz.size == 0:
#                        n = domain[self][1].size
#                        R = zeros((2, n), dtype)
#                        definiteRange = empty(n, bool)
#                        definiteRange.fill(True)# TODO: sometimes it may be wrong
#                        return R, definiteRange
            
            # TODO: implement it
#                    subdomain = ooPoint([(v, (d[0][ind_nz], d[1][ind_nz])) for v, d in domain.items()], skipArrayCast=True)
#                    subdomain.isMultiPoint = True
#                    #subdomain.modificationVar = domain.modificationVar
#                    #subdomain.useSave = domain.useSave
#                    #subdomain.localStoredIntervals = {}
#                    lb_ub, definiteRange2 = other._interval(subdomain, dtype)
#                    R[:, ind_nz] = lb_ub.copy()
#                    definiteRange[ind_nz] = definiteRange2
#                    return R, definiteRange
#                    
#                elif isOtherOOFun:
#                    # TODO: implement it
#                    pass
#            
#            # changes end
    
    lb1_ub1, definiteRange = self._interval(domain, dtype)
    lb1, ub1 = lb1_ub1[0], lb1_ub1[1]
    
    if isOtherOOFun:
        lb2_ub2, definiteRange2 = other._interval(domain, dtype)
        definiteRange = logical_and(definiteRange, definiteRange2)
        lb2, ub2 = lb2_ub2[0], lb2_ub2[1]
    else:
        lb2, ub2 = other, other # TODO: improve it
        
    if all(lb2 >= 0) and all(lb1 >= 0):
        t_min, t_max = atleast_1d(lb1 * lb2), atleast_1d(ub1 * ub2)
    elif isscalar(other):
        t_min, t_max = (lb1 * other, ub1 * other) if other >= 0 else (ub1 * other, lb1 * other)
    else:
        if isOtherOOFun:
            t = vstack((lb1 * lb2, ub1 * lb2, \
                        lb1 * ub2, ub1 * ub2))# TODO: improve it
        else:
            t = vstack((lb1 * other, ub1 * other))# TODO: improve it
        t_min, t_max = atleast_1d(nanmin(t, 0)), atleast_1d(nanmax(t, 0))
    #assert isinstance(t_min, ndarray) and isinstance(t_max, ndarray), 'Please update numpy to more recent version'
    
    if any(isinf(lb1)) or any(isinf(lb2)) or any(isinf(ub1)) or any(isinf(ub2)):
        ind1_zero_minus = logical_and(lb1<0, ub1>=0)
        ind1_zero_plus = logical_and(lb1<=0, ub1>0)
        
        ind2_zero_minus = logical_and(lb2<0, ub2>=0)
        ind2_zero_plus = logical_and(lb2<=0, ub2>0)
        
        has_plus_inf_1 = logical_or(logical_and(ind1_zero_minus, lb2==-inf), logical_and(ind1_zero_plus, ub2==inf))
        has_plus_inf_2 = logical_or(logical_and(ind2_zero_minus, lb1==-inf), logical_and(ind2_zero_plus, ub1==inf))
        
        # !!!! lines with zero should be before lines with inf !!!!
        ind = logical_or(logical_and(lb1==-inf, ub2==0), logical_and(lb2==-inf, ub1==0))
        t_max[atleast_1d(logical_and(ind, t_max<0.0))] = 0.0
        
        t_max[atleast_1d(logical_or(has_plus_inf_1, has_plus_inf_2))] = inf
        t_max[atleast_1d(logical_or(logical_and(lb1==0, ub2==inf), logical_and(lb2==0, ub1==inf)))] = inf
        
        has_minus_inf_1 = logical_or(logical_and(ind1_zero_plus, lb2==-inf), logical_and(ind1_zero_minus, ub2==inf))
        has_minus_inf_2 = logical_or(logical_and(ind2_zero_plus, lb1==-inf), logical_and(ind2_zero_minus, ub1==inf))
        # !!!! lines with zero should be before lines with -inf !!!!
        t_min[atleast_1d(logical_or(logical_and(lb1==0, ub2==inf), logical_and(lb2==0, ub1==inf)))] = 0.0
        t_min[atleast_1d(logical_or(logical_and(lb1==-inf, ub2==0), logical_and(lb2==-inf, ub1==0)))] = 0.0
        
        t_min[atleast_1d(logical_or(has_minus_inf_1, has_minus_inf_2))] = -inf
    
#            assert not any(isnan(t_min)) and not any(isnan(t_max))
   
    return vstack((t_min, t_max)), definiteRange
