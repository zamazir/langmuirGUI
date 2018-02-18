import sys
#sys.path.insert(0, '/afs/ipp/aug/ads-diags/common/python/lib')
sys.path.insert(0, '../not_used')
import dd
from matplotlib.pyplot import *
import matplotlib as mpl

mpl.rcParams.update({'figure.autolayout':True})

args = sys.argv

shotNumber = int(args[1])

print "Loading shot", shotNumber


fig, axes = subplots(3,1, sharex=True)
fig.suptitle('#' + str(shotNumber))

# Heating power
ax = axes[0]
try:
    shot = dd.shotfile('TOT', shotNumber)
    t = shot('P_TOT').time
    y = shot('P_TOT').data / 10**6
except:
    print "No heating power data"
else:
    ax.plot(t,y)
ax.grid(True)
ax.set_ylabel('$P_{tot}$ [MW]')

# Tdiv
ax = axes[1]
try:
    shot = dd.shotfile('DDS', shotNumber)
    t = shot('Tdiv').time
    y = shot('Tdiv').data
except:
    print "No divertor temperature data"
else:
    ax.plot(t,y)
ax.grid(True)
ax.set_ylabel('$T_{div}$ [eV]')

# Puffing & Seeding
ax = axes[2]
try:
    shot = dd.shotfile('UVS', shotNumber)
except:
    print "No seeding data"
else:
    try:
        t = shot('D_tot').time
        y = shot('D_tot').data / 10**22
    except:
        print "No D fuelling data"
    else:
        ax.plot(t,y, label='D fuelling')

    try:
        t = shot('N_tot').time
        y = shot('N_tot').data / 10**22
    except:
        print "No N seeding data"
    else:
        ax.plot(t,y, label='N seeding')

    try:
        t = shot('Ne_tot').time
        y = shot('Ne_tot').data / 10**22
    except:
        print "No Ne seeding data"
    else:
        ax.plot(t,y, label='Ne seeding')
ax.grid(True)
ax.set_ylabel('Puffing/Seeding [$10^{22}$/s]')

# Line integrated density
#ax = axes[2]
#shot = dd.shotfile('TOT', shotNumber)
#t = shot('P_TOT').time
#y = shot('P_TOT').data
#
#ax.plot(t,y)
#ax.grid(True)
#ax.set_ylabel('$T_{div}$ [eV]')

legend()
draw()
show()
