import ctypes
import dd
import numpy as np

__libddww__ = ctypes.cdll.LoadLibrary('./libddww8.so')


def getError(error):
    """ Check if an error/warning occured. """
    try:
        err = ctypes.c_int32(error)
    except TypeError:
        err = ctypes.c_int32(error.value)
    isError = ___libddww____.xxsev_(ctypes.byref(err))==1
    isWarning = ___libddww____.xxwarn_(ctypes.byref(err))==1
    if isError or isWarning:
        id = ctypes.c_char_p(b'')
        lid = ctypes.c_uint64(0)
        text = ctypes.c_char_p(b' '*255)
        ltext = ctypes.c_uint64(255)
        unit = ctypes.byref(ctypes.c_int32(-1))
        ctrl = ctypes.byref(ctypes.c_uint32(3))
        ___libddww____.xxerrprt_(unit, text, ctypes.byref(err), ctrl, id, ltext, lid);
        if isError:
            raise Exception(text.value.strip())
        else:
            warnings.warn(text.value.strip(), RuntimeWarning)



class LSCshotfile(object):
    def __init__(self, shotnr, exp='AUGD', ed=0, shotfile=None):
        self.shot       = shotnr
        self.edition    = ed
        self.experiment = exp
        if shotfile is None:
            self.load()
        else:
            self.shotfile = shotfile


    def load(self):
        self.shotfile = dd.shotfile('LSC',self.shot,self.experiment,self.edition)


    def write(self, exp='zamaz'):
        diag   = 'LSC'
        err    = ctypes.c_int32(0)
        edit   = ctypes.c_int32(self.edition)
        shot   = ctypes.c_int32(self.shot)
        diaref = ctypes.c_int32(1)
        edit   = ctypes.byref(edit)
        shot   = ctypes.byref(shot)
        diaref = ctypes.byref(diaref)
        date   = ctypes.c_char_p(b'123456789012345678')
        signal = 'ua2'

        data = shotfile(signal)
        channel = ['c','H','2','5','_','1']
        while len(channel) < 80:
            channel.append('')
        channel = np.array(channel)
        data['ZSI8'] = channel

        try:
            diag = ctypes.c_char_p(diag)
        except TypeError:
            diag = ctypes.c_char_p(diag.encode())
        try:
            exp = ctypes.c_char_p(exp)
        except TypeError:
            exp = ctypes.c_char_p(exp.encode())
        try:
            signal = ctypes.c_char_p(signal)
        except TypeError:
            signal = ctypes.c_char_p(signal.encode())

        #lexp   = ctypes.c_uint64(len(exp))
        #ldiag  = ctypes.c_uint64(len(diag))
        #ldate  = ctypes.c_uint64(18)

        # write level-1 shotfile
        print "Opening file for writing"
        result = __libddww__.wwopen_(err,exp,diag,shot,"new",edit,diaref,date)
        getError(error)

        #length = 223
        #result = __libddww__.wwtbase_(err,diaref,tname,typ,length,time,stride,8)
        #getError(error)

        #sizes[0] = 16
        #sizes[1] = 0
        #sizes[2] = 0
        #result = __libddww__.wwainsert_(err,diaref,name,k1,k2,typ,adat,sizes,8)
        #getError(error)
        #for k in range(length): 
        #    ind[0] = 1 + k
        #    ind[1] = 0
        #    ind[2] = 0
        #    length = 16
        #    result =__libddww__.wwinsert_(err,diaref,sgname,typ,length,data,stride,ind,8)
        #    getError(error)
        type = ctypes.c_int32(1) # ints
        sride = ctypes.c_int32(1)
        ind = ctypes.c_int32(1)
        print "Writing"
        result =__libddww__.wwinsert_(err,diaref,signal,type,len(data),data,stride,ind)
        getError(error)

        print "Closing"
        result = __libddww__.wwclose_(err,diaref,"lock","maxspace")
        getError(error)


