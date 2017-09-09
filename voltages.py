from matplotlib.pyplot import *
import dd

shot = 32273
channel1 = ('CH03', 5)
channel2a = ('CH03', 5)
channel2b = ('CH08', 1)
channel3 = ('CH01', 3)
LSCkey1 = 'ZSV1 - $V_{pos}-V_{fl}$'
LSCkey2 = 'ZSV2 - $V_{neg}-V_{fl}$'
LSCkey3 = 'ZSV8 - $V_{fl}-V_{ref}$'
probe = 'ua3'

shot = dd.shotfile('LSF', 32273)

fig, ax = subplots(1, 1)
fig.suptitle('Voltages for probe {} - #{}'.format(probe, 32273))

channel, ind = channel1
x = shot(channel).time
y = shot(channel).data[ind]
p1, = ax.plot(x, y, label='{}[{}] ({})'.format(channel, ind, LSCkey1))

channela, inda = channel2a
channelb, indb = channel2b
x = shot(channela).time
y = shot(channela).data[inda] + shot(channelb).data[indb]
p2, = ax.plot(x, y, label='{}[{}] + {}[{}] ({})'
                          .format(channela, inda, channelb, indb, LSCkey2))

channel, ind = channel3
x = shot(channel).time
y = shot(channel).data[ind]
p3, = ax.plot(x, y, label='{}[{}] ({})'.format(channel, ind, LSCkey3))


legend()
show()
