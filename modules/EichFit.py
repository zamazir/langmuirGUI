from scipy.optimize import fmin
from scipy.special import erfc
from scipy import exp
from scipy.integrate import trapz

def Eich_model(p, location):
    z = p[3]/2.0/p[2]
    return 0.5*p[1]/p[2]*exp(z*z-(location-p[0])/p[2])*erfc(z-(location-p[0])/p[3]) + p[4]

def fit(location, data, uncertainty = None, use_uncertainty=False):
    p0 = [trapz(data*location, location)/trapz(data, location), abs(trapz(data, location)), 10.0e-3, 5.0e-3, max(1.0, data.mean())]
    pMin = [location.min(), p0[1]*0.5, 0.5e-3, 0.5e-3, 0.0]
    pMax = [location.max(), p0[1]*2, location.ptp(), location.ptp(), data.max()]
    def likelihood(p):
        if any(p<pMin) or any(p>pMax):
            return 99e99
        if use_uncertainty:
            result = Eich_model(p)/uncertainty - data/uncertainty
        else:
            result = Eich_model(p) - data
        result *= result
        result = sum(result)
        return result if result == result else 99e99
    start = True
    counter = 0
    while start:
        pNew = fmin(likelihood, p0, disp=False)
        if all(pNew == p0) or counter > 10:
            start = False
    return pNew
                                                     
