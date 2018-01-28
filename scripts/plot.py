"""
Plot a database column over another
Very primitive script replaced by more elaborate scripts in this folder but
still good for quick plots
"""
from __future__ import print_function

import numpy as np
import pandas as pd
from matplotlib.pyplot import *

df = pd.read_csv('../data/csv/db28.csv')
grouped = df.groupby(['Shot', 'CELMA start', 'quantity'])

def calcRow(row):
    try:
        return float(row[feat].split('|')[0])
    except AttributeError:
        return np.nan

feat = 'detachEnd'
for key, group in grouped:
    group = group.set_index('probe').transpose()
    times = group.apply(calcRow)
    diffs = times.as_matrix()[:-1] - times.as_matrix()[1:]
    diffs = np.append(diffs, np.nan)
    df.loc[((df["Shot"] == key[0]) &
            (df["CELMA start"] == key[1]) &
            (df["quantity"] == key[2])), feat] = diffs

grouped = df.groupby('probe')
for name, group in grouped:
    x = group['Tdiv']
    y = group[feat]
    scatter(x, y, label=name)
legend()
show()
