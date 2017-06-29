from scipy.optimize import curve_fit
from scipy.special import erfc
from scipy import exp
from scipy.integrate import trapz
import numpy as np

class FitFunctions():
    
    @staticmethod
    def eich_model_detached(x, p2, p3, p4, p5, p6):
        """
        p2: q0          Scaling
        p3: lambdaq     Flux e-folding distance
        p4: S           Flux broadening
        p5: qBG         Background flux
        p6: dsDetach    Profile shift due to detachment
        """
        z = p4/2.0/p3
        return 0.5*p2*exp(z*z-(x-p6)/p3)*erfc(z-(x-p6)/p4) + p5

    @staticmethod
    def eich_model(x, p2, p3, p4, p5):
        """
        p2: q0          Scaling
        p3: lambdaq*fx  Flux e-folding distance, flux widening
        p4: S*fx        S-factor, flux widening
        p5: qBG         Background flux
        """
        z = p4/2.0/p3
        return 0.5*p2*exp(z*z-(x)/p3)*erfc(z-(x)/p4) + p5
    
    @staticmethod
    def fit(x, y, p0=None, detachment=False):
        if p0 is None:
            p0 = [
                    1, 
                    10.0e-3, 
                    5.0e-3, 
                    np.median(y),
                    0.01
                 ]
        
        if detachment:
            return curve_fit(FitFunctions.eich_model_detached, x, y, p0=p0)[0]
        else:
            return curve_fit(FitFunctions.eich_model, x, y, p0=p0[:-1])[0]
