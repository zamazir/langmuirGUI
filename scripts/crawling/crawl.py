from __future__ import print_function
import sys
#sys.path.insert(0, '/afs/ipp/aug/ads-diags/common/python/lib')
sys.path.insert(0, '../not_used')
import dd
import simplejson
import time
import numpy as np

tdiv_range = [-10, 15]
shotnumber_range = [33895, None]

def check_shotfile_availability(shotnr):
    diags = ['LSF', 'LSD', 'FPG', 'TOT', 'DCN']
    for diag in diags:
        try:
            shotfile = dd.shotfile(diag, shotnr)
        except:
            print("{} not available".format(diag))
            return
    return True

if shotnumber_range[1] is None:
    shotnumber_range[1] = dd.getLastShotNumber('LSF', 100000)

size = len(range(*shotnumber_range))
matches = {}
duration = 0
for i, shotnr in enumerate(range(*shotnumber_range)):
    start_time = time.time()
    time_left = duration * (size - (i + 1))
    minutes_left, seconds_left = divmod(time_left, 60)
    hours_left, minutes_left = divmod(minutes_left, 60)
    progress = float(i + 1) / (shotnumber_range[1] - shotnumber_range[0]) * 100
    status = "\n\n({:.1f}% | {}:{:02}:{:02} left)".format(progress,
                                                     int(hours_left),
                                                     int(minutes_left),
                                                     int(seconds_left))
    try:
        shotfile = dd.shotfile('DDS', shotnr)
        Tdiv = shotfile('Tdiv').data
        shotfile.close()
    except:
        print("{} No DDS shotfile".format(status))
        duration = time.time() - start_time
        continue

    if not check_shotfile_availability(shotnr):
        print("{} Missing vital shotfile(s)".format(status))
        duration = time.time() - start_time
        continue

    mean = np.nanmedian(Tdiv)
    if tdiv_range[0] < mean < tdiv_range[1]:
        matches[shotnr] = mean
        print("{} MATCH {:>7}{:>7.1f}".format(status, shotnr, mean))
    with open('tdiv_results.txt', 'a') as f:
        f.write("{:<7}{:<.1f}\n".format(shotnr, mean))
    duration = time.time() - start_time
