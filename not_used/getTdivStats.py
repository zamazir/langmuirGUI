# Intended to be used for finding suitable shots
#
# Each shot until most recent one has not been handled yet
# 1) get most recent shot
# 2) loop over shots
# 3) check if useful plasma shot
# 3) check if Tdiv exists
# 4) get max(Tdiv), mean(Tdiv), min(Tdiv)
import logging
import sys
import dd

logger = logging.getLogger(__name__)
stream_hdlr = logging.StreamHandler(sys.stdout)
stream_hdlr.setLevel(logging.DEBUG)
logger.addHandler(stream_hdlr)

logger.debug('Test')

# Get most recent shot that has DDS diagnostic (contains Tdiv)
lastShot = dd.getLastShotNumber('DDS')

# Get highest shotnumber that has been handled already
maxHandled = 0

# Loop
for shotnr in range(maxHandled + 1, lastShot):
    shot = dd.shotfile('DDS', shotnr)
    # Check if useful and if plasma
    # Get Tdiv
    try:
        Tdiv = shot('Tdiv')
    except:
        pass
