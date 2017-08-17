import sys
import dd
from matplotlib.pyplot import *
import matplotlib as mpl

mpl.rcParams.update({'figure.autolayout':True})

args = sys.argv

shotNumber = int(args[1])

print "Loading shot", shotNumber


fig, axes = subplots(3,1, sharex=True)

# Heating power
ax = axes[0]
shot = dd.shotfile('TOT', shotNumber)
t = shot('P_TOT').time
y = shot('P_TOT').data / 10**6

ax.plot(t,y)
ax.grid(True)
ax.set_ylabel('$P_{tot}$ [MW]')

# Tdiv
ax = axes[1]
shot = dd.shotfile('DDS', shotNumber)
t = shot('Tdiv').time
y = shot('Tdiv').data

ax.plot(t,y)
ax.grid(True)
ax.set_ylabel('$T_{div}$ [eV]')

# Puffing & Seeding
ax = axes[2]
shot = dd.shotfile('UVS', shotNumber)
t = shot('D_tot').time
y = shot('D_tot').data / 10**22
ax.plot(t,y, label='D fuelling')

t = shot('N_tot').time
y = shot('N_tot').data / 10**22
ax.plot(t,y, label='N seeding')

t = shot('Ne_tot').time
y = shot('Ne_tot').data / 10**22
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
