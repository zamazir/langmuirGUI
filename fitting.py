from scipy.optimize import curve_fit
from scipy.special import erfc
from scipy import exp
from scipy.integrate import trapz

class FitFunctions():
    
    @staticmethod
    def eich_model(x, p2, p3, p4, p5):
        z = p4/2.0/p3
        return 0.5*p2*exp(z*z-(x)/p3)*erfc(z-(x)/p4) + p5
    
    @staticmethod
    def fit(x, y, p0=None):
        if p0 is None:
            p0 = [
                    1, 
                    10.0e-3, 
                    5.0e-3, 
                    y.mean()
                 ]
        
        print "Initial guess:", p0

        return curve_fit(FitFunctions.eich_model, x, y, p0=p0)[0]
