"""
Assess similarity of time traces based on dynamic time warping (directly from
raw data) or on the distances between features (read from database).
Produce a CSV report that can be evaluated with superimpose.py.
"""

#from sklearn.metrics.pairwise import euclidean_distances
from math import *
import numpy as np
import pandas as pd
import sys
import os
import logging
import argparse
import datetime

argparser = argparse.ArgumentParser()
argparser.add_argument('-x', '--axis', default='x', choices=('x', 'y', 'xy'),
                       dest='axis',
                       help='Axis with respect to which the data should ' +
                       'be compared')
argparser.add_argument('-m', '--method', default='quadratic_mean',
                       dest='method',
                       choices=('euclidean', 'DTW', 'quadratic_mean'),
                       help='Method with which to calculate the total ' + 
                       'distance')
argparser.add_argument('mode', default='csv', choices=('csv', 'dumps'),
                       help='Compare by features or whole timetrace')
argparser.add_argument('-l', '--loglevel', default='info', dest='loglevel',
                       help='Logging level')
argparser.add_argument('-q', '--quantity', default='jsat', dest='quant',
                       choices=('jsat', 'te'),
                       help='Quantity to compare' + 
                       'distance')
argparser.add_argument('-P', '--penalty', default='ignore', dest='penalty',
                       choices=('ignore', 'likewise', 'absolute', 'relative'),
                       help='Penalty to apply if feature is missing')
argparser.add_argument('-n', '--norm', default='minmax', dest='norm',
                       choices=('minmax', 'mean'),
                       help='Method to use for probability conversion')
argparser.add_argument('-p', '--probe', default='first', dest='probe',
                       help='Probe signal to compare')
argparser.add_argument('-d', '--database', dest='database',
                       help='CSV database to get features from')
argparser.add_argument('-o', '--output', dest='output',
                       help='Path to output csv file')
argparser.add_argument('-f', '--folder', dest='folder',
                       help='Directory containing numpy dumpfiles')
argparser.add_argument('-e', '--features', dest='features', nargs='+',
                       default=['bump', 'detachStart', 'detachMax',
                                'detachEnd', 'HRpeak', 'HRend'],
                       help='Features to be compared when reading from db')
argparser.add_argument('--tmax', dest='tmax', type=float, default=12,
                       help='Maximum x value for dumpfiles to be considered')
argparser.add_argument('--sortby', default='method', dest='sortby',
                       help='Column to sort resulting csv file by')
argparser.add_argument('--selfcheck', dest='selfcheck', action='store_true',
                       help='Whether or not to check phases of the same ' +
                       'shot against each other')
args = argparser.parse_args()
method = args.method
directory = args.folder
database = args.database
penalty = args.penalty
norm = args.norm
sortby = args.sortby
selfcheck = args.selfcheck
axis = args.axis
probe = args.probe
outfile = args.output
quant = args.quant
mode = args.mode
features = args.features
max_t = args.tmax / 1000

try:
    loglevel = getattr(logging, args.loglevel.upper())
except AttributeError:
    loglevel = logging.INFO

logger = logging.getLogger(__name__)
logger.setLevel(loglevel)
formatter = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s',
                              datefmt='%d/%m/%Y %I:%M:%S %p')
file_hdlr = logging.FileHandler('similarity.log', mode='w')
file_hdlr.setLevel(loglevel)
stream_hdlr = logging.StreamHandler(sys.stdout)
stream_hdlr.setLevel(loglevel)
logger.addHandler(stream_hdlr)
logger.addHandler(file_hdlr)
file_hdlr.setFormatter(formatter)


def get_file_data(f, probe, max_t):
    """
    Extract linear regression data from file. Needs numpy zip file with one
    dump named 'Linear regression <probe>'. Only consider data for x values
    smaller than <max_t>.
    """
    data = np.load(f)
    signal = 'Linear regression {}'.format(probe)

    if signal in data:
        x, y = data[signal].transpose()
        result = y[x < max_t]
    else:
        result = None
    return result

def parse_file_name(f):
    """
    Extract shot phase (shot number, start, and end time) from a filename. The
    filename parts must be delimited by '_' and the shot, start, and end must
    be on positions 0, 4, and 5, respectively.
    """
    f = os.path.split(f)[1]
    parts = f.split('_')
    try:
        shot = parts[0]
        start = float(parts[4]) #'{:.2f}'.format(float(parts[4]))
        end = float(parts[5]) #'{:.2f}'.format(float(parts[5]))
    except KeyError, ValueError:
        logger.warning("Bad filename format: {}".format(f))
        return
    return [shot, start, end]

def fmt_phase(phase):
    """
    Format shot phase. <phase> needs to be an ordered iterable containing shot
    number as well as start and end time of the phase.
    """
    return "{} ({:.2f}-{:.2f})".format(*phase)

def already_assessed(df, sig1, sig2, method=None):
    """
    Check if the combination of the two given signals has alread be assessed
    and saved in df. If <method> is given, this happens with respect to the
    given method.
    """
    if 'Signal 1' not in df.columns:
        logger.debug('Result df columns not initialized yet')
        return
    sig1 = fmt_phase(sig1)
    sig2 = fmt_phase(sig2)
    rows = df[(df['Signal 1'] == sig1) & (df['Signal 2'] == sig2)]
    rows = rows.append(df[(df['Signal 1'] == sig2) & (df['Signal 2'] == sig1)])
    if method:
        rows = rows[rows[method] != np.nan]
    return not rows.empty

class Measures():
    """
    Various distance measures
    """
    @staticmethod
    def euclidean(x, y):
        x = np.array(x)
        y = np.array(y)
        return np.sum(np.abs(x - y))

    @staticmethod
    def quadratic_mean(x):
        return np.sqrt(np.mean(np.square(x)))

    @staticmethod
    def DTW(A, B, window = sys.maxint, d = lambda x,y: abs(x-y)):
        # create the cost matrix
        A, B = np.array(A), np.array(B)
        M, N = len(A), len(B)
        cost = sys.maxint * np.ones((M, N))

        # initialize the first row and column
        cost[0, 0] = d(A[0], B[0])
        for i in range(1, M):
            cost[i, 0] = cost[i-1, 0] + d(A[i], B[0])

        for j in range(1, N):
            cost[0, j] = cost[0, j-1] + d(A[0], B[j])
        # fill in the rest of the matrix
        for i in range(1, M):
            for j in range(max(1, i - window), min(N, i + window + 1)):
                choices = cost[i - 1, j - 1], cost[i, j-1], cost[i-1, j]
                cost[i, j] = min(choices) + d(A[i], B[j])

        # find the optimal path
        n, m = N - 1, M - 1
        path = []

        while (m, n) != (0, 0):
            path.append((m, n))
            m, n = min((m - 1, n), (m, n - 1), (m - 1, n - 1), key = lambda x: cost[x[0], x[1]])
        
        path.append((0,0))
        return cost[-1, -1], path

def missing(x):
    logger.debug("Checking if missing: {}".format(x))
    empty = False
    isnan = False
    try:
        empty = not len(x)
    except TypeError:
        empty = False
    if not empty:
        try:
            isnan = np.isnan(x.iloc[0])
        except TypeError:
            isnan = False
    logger.debug("empty: {}, isnan: {}".format(empty, isnan))
    return empty or isnan

def from_csv(axis, probe, quantity, penalty, norm, sortby, selfcheck,
             database, features=None, outfile=None):
    """
    Determine distance by features with data from database
    """
    df = pd.read_csv(database, delimiter=',')
    #with pd.option_context('mode.use_inf_as_null', True):
    #    df.dropna()
    #df = df[~df.isnull()]
    result = pd.DataFrame()
    df_grouped = df.groupby(['Shot', 'CELMA start', 'CELMA end'])
    features = features or ['bump', 'detachStart', 'detachMax', 'detachEnd',
                            'HRpeak', 'HRend']
    quant = quantity
    distance = getattr(Measures, method)

    for phase, df in df_grouped:
        shot, start, end = phase
        logger.debug("{} ({}-{}s)".format(shot, start, end))
        if probe == 'first':
            data = df[(df['quantity'] == quant) &
                      (df['probe'] == df['sepProbe'])]
        else:
            data = df[(df['quantity'] == quant) &
                      (df['probe'] == probe)]
        data = data.reset_index(drop=True)
        if data[features].dropna(axis=0, how='all').empty:
            logger.debug("{}, probe {}: no {} data"
                         .format(phase, probe, quant))
            continue

        for ophase, odf in df_grouped:
            oshot, ostart, oend = ophase
            if ophase == phase:
                continue
            if not selfcheck and shot == oshot:
                continue
            if already_assessed(result, phase, ophase, method):
                logger.debug("{} - {} already assessed".format(phase, method))
                continue
            logger.debug("{} ({}-{}s)".format(oshot, ostart, oend))
            if probe == 'first':
                odata = odf[(odf['quantity'] == quant) &
                            (odf['probe'] == odf['sepProbe'])]
            else:
                odata = odf[(odf['quantity'] == quant) &
                            (odf['probe'] == probe)]
            odata = odata.reset_index(drop=True)

            if odata[features].dropna(axis=0, how='all').empty:
                logger.debug("{}, probe {}: no {} data"
                              .format(ophase, probe, quant))
                continue

            # Calculate distance for each feature
            alike = True
            distances = []
            for feature in features:
                logger.debug(feature)
                featdata = data[feature]
                ofeatdata = odata[feature]

                # Handle missing features
                if missing(featdata) or missing(ofeatdata):
                    if penalty == 'ignore':
                        continue
                    if penalty == 'likewise':
                        alike = False
                        break
                elif missing(featdata) and not missing(ofeatdata):
                    # relative not implemented. mean needed
                    if penalty in ('absolute', 'relative'):
                        featdata = pd.Series([0 | 0])
                        axis = 'y'
                elif not missing(featdata) and missing(ofeatdata):
                    if penalty in ('absolute', 'relative'):
                        ofeatdata = pd.Series([0 | 0])
                        axis = 'y'
                elif missing(featdata) and missing(ofeatdata):
                    # If both are missing, ignore the feature
                    continue
                xy1 = [float(el) for el in featdata.iloc[0].split('|')]
                xy2 = [float(el) for el in ofeatdata.iloc[0].split('|')]

                # Calculate distance of this feature
                if axis == 'x':
                    d = abs(xy1[0] - xy2[0])
                elif axis == 'y':
                    d = abs(xy1[1] - xy2[1])
                elif axis == 'xy':
                    d = sqrt(pow(xy1[0] - xy2[0], 2) + pow(xy1[1] - xy2[1], 2))
                logger.debug("{}: {}".format(feature, d))
                if np.isnan(d):
                    logger.error("{} - {}: {} distance is nan"
                                 .format(phase, ophase, feature))
                    logger.error("xy1: {}, xy2: {}"
                                 .format(xy1, xy2))
                distances.append(d)

            if not alike:
                continue

            # Calculate overall distance
            total_distance = distance(distances)
            logger.debug("total: {}".format(total_distance))
            get_value_one = (lambda x: data[x].iloc[0]
                             if not missing(data[x]) else np.nan)
            get_value_two = (lambda x: odata[x].iloc[0]
                             if not missing(odata[x]) else np.nan)
            scen1 = get_value_one('scenario')
            scen2 = get_value_two('scenario')
            tdiv1 = float(get_value_one('Tdiv'))
            tdiv2 = float(get_value_two('Tdiv'))
            ptot1 = float(get_value_one('Ptot'))
            ptot2 = float(get_value_two('Ptot'))
            nbar1 = float(get_value_one('nbar'))
            nbar2 = float(get_value_two('nbar'))
            netot1 = float(get_value_one('Ne_tot'))
            netot2 = float(get_value_two('Ne_tot'))
            ntot1 = float(get_value_one('N_tot'))
            ntot2 = float(get_value_two('N_tot'))
            dtot1 = float(get_value_one('D_tot'))
            dtot2 = float(get_value_two('D_tot'))
            logData = False
            if np.isnan(total_distance):
                logger.error("{} - {}: Total distance is nan. Distances: {}"
                             .format(phase, ophase, distances))
            if np.isnan([tdiv1, tdiv2]).any():
                logger.info("delta tdiv unavailable: at least one value nan")
                logData = True
            if np.isnan([ptot1, ptot2]).any():
                logger.info("delta ptot unavailable: at least one value nan")
                logData = True
            if np.isnan([nbar1, nbar2]).any():
                logger.info("delta nbar unavailable: at least one value nan")
                logData = True
            if logData:
                logger.info("data {}:\n{}"
                            .format(phase, data[['Ptot', 'Tdiv', 'nbar']]))
                logger.info("odata {}:\n{}"
                            .format(ophase, odata[['Ptot', 'Tdiv', 'nbar']]))
                logData = False
            row = {'Quantity': quant,
                   'Signal 1': fmt_phase(phase),
                   'Scenario 1': scen1,
                   'Signal 2': fmt_phase(ophase),
                   'Scenario 2': scen2,
                   'Delta Tdiv': np.abs(tdiv1 - tdiv2),
                   'Delta Ptot': np.abs(ptot1 - ptot2),
                   'Delta nbar': np.abs(nbar1 - nbar2),
                   'Signal 1 Ptot': ptot1,
                   'Signal 2 Ptot': ptot2,
                   'Signal 1 Tdiv': tdiv1,
                   'Signal 2 Tdiv': tdiv2,
                   'Signal 1 nbar': nbar1,
                   'Signal 2 nbar': nbar2,
                   'Signal 1 N': ntot1,
                   'Signal 2 N': ntot2,
                   'Signal 1 Ne': netot1,
                   'Signal 2 Ne': netot2,
                   'Signal 1 D': dtot1,
                   'Signal 2 D': dtot2,
                   method: total_distance}
            result = result.append(row, ignore_index=True)
    res = result[method].astype(float)
    # Fails with "cannot convert series to type float"
    #if norm == 'minmax':
    #    value = (round(100 - (res - res.min()) /
    #             (res.max() - res.min()) * 100, 2))
    #    result['minmaxnorm'] = value
    #elif norm == 'mean':
    #    value = (round(100 - (res - res.mean()) /
    #             (res.max() - res.min()) * 100, 2))
    #    result['meannorm'] = value
    if sortby == 'method':
        result = result.sort_values(method)
    else:
        result = result.sort_values(sortby)
    for col in result.columns:
        result[col] = pd.to_numeric(result[col], errors='ignore')
    if not outfile:
        outfile = 'similarity_features.csv'
    result.to_csv(outfile)

def from_dump(probe, quantity, method, sortby, selfcheck, directory, max_t,
              outfile, database):
    """
    DTW with raw data
    """
    def parse_file_name(fname):
        parts = fname.split('/')[-1].split('_')
        return [parts[0], float(parts[4]), float(parts[5]), parts[2]]
    df = pd.DataFrame(columns=['Quantity', 'Signal 1', 'Signal 2', 'DTW'])
    quant = quantity
    distance = getattr(Measures, method)
    files = [os.path.join(directory, f) for f in os.listdir(directory)]
    if not len(files):
        logger.critical("No files found!")
    archives = [f for f in files if (os.path.isfile(f) and
                                     f.endswith('.npz') and
                                     quant in f)]
    
    param_df = pd.read_csv(database)
    if not len(archives):
        logger.critical("No archives found!")
    for f in archives:
        logger.debug(f)
        otherfiles = [_f for _f in archives if _f != f]
        phase = parse_file_name(f)[:-1]
        A = get_file_data(f, probe, max_t)
        sig1 = parse_file_name(f)
        this_shot = param_df['Shot'].astype(str) == str(phase[0])
        this_start = param_df['CELMA start'].astype(str) == str(phase[1])
        this_end = param_df['CELMA end'].astype(str) == str(phase[2])
        data = param_df[this_shot & this_start & this_end]
        for of in otherfiles:
            logger.debug('\t{}'.format(of))
            ophase = parse_file_name(of)[:-1]
            this_shot = param_df['Shot'].astype(str) == str(ophase[0])
            this_start = param_df['CELMA start'].astype(str) == str(ophase[1])
            this_end = param_df['CELMA end'].astype(str) == str(ophase[2])
            odata = param_df[this_shot & this_start & this_end]
            B = get_file_data(of, probe, max_t)
            if A is None or B is None:
                logger.debug('Could not retreive {} data'.format(probe))
                continue
            else:
                sig2 = parse_file_name(of)
                logger.debug('{} vs. {}:'.format(sig1, sig2))

                if not selfcheck and sig1[0] == sig2[0]:
                    continue
                if already_assessed(df, sig1, sig2, method):
                    logger.debug("{} - {} already assessed"
                                 .format(sig1, sig2))
                    continue
                try:
                    cost, path = distance(A, B, window = 4)
                except:
                    cost = 'FAILED'
                logger.debug('\tTotal Distance is {}'.format(cost))

            get_value_one = (lambda x: data[x].iloc[0]
                             if not missing(data[x]) else np.nan)
            get_value_two = (lambda x: odata[x].iloc[0]
                             if not missing(odata[x]) else np.nan)
            scen1 = get_value_one('scenario')
            scen2 = get_value_two('scenario')
            tdiv1 = float(get_value_one('Tdiv'))
            tdiv2 = float(get_value_two('Tdiv'))
            ptot1 = float(get_value_one('Ptot'))
            ptot2 = float(get_value_two('Ptot'))
            nbar1 = float(get_value_one('nbar'))
            nbar2 = float(get_value_two('nbar'))
            netot1 = float(get_value_one('Ne_tot'))
            netot2 = float(get_value_two('Ne_tot'))
            ntot1 = float(get_value_one('N_tot'))
            ntot2 = float(get_value_two('N_tot'))
            dtot1 = float(get_value_one('D_tot'))
            dtot2 = float(get_value_two('D_tot'))
            logData = False
            if np.isnan([tdiv1, tdiv2]).any():
                logger.info("delta tdiv unavailable: at least one value nan")
                logData = True
            if np.isnan([ptot1, ptot2]).any():
                logger.info("delta ptot unavailable: at least one value nan")
                logData = True
            if np.isnan([nbar1, nbar2]).any():
                logger.info("delta nbar unavailable: at least one value nan")
                logData = True
            if logData:
                logger.info("data {}:\n{}"
                            .format(phase, data[['Ptot', 'Tdiv', 'nbar']]))
                logger.info("odata {}:\n{}"
                            .format(ophase, odata[['Ptot', 'Tdiv', 'nbar']]))
                logData = False
            row = {'Quantity': quant,
                   'Signal 1': fmt_phase(sig1),
                   'Signal 2': fmt_phase(sig2),
                   'Delta Tdiv': np.abs(tdiv1 - tdiv2),
                   'Delta Ptot': np.abs(ptot1 - ptot2),
                   'Delta nbar': np.abs(nbar1 - nbar2),
                   'Signal 1 Ptot': ptot1,
                   'Signal 2 Ptot': ptot2,
                   'Signal 1 Tdiv': tdiv1,
                   'Signal 2 Tdiv': tdiv2,
                   'Signal 1 nbar': nbar1,
                   'Signal 2 nbar': nbar2,
                   'Signal 1 N': ntot1,
                   'Signal 2 N': ntot2,
                   'Signal 1 Ne': netot1,
                   'Signal 2 Ne': netot2,
                   'Signal 1 D': dtot1,
                   'Signal 2 D': dtot2,
                   method: cost}
            df = df.append(row, ignore_index=True)
    df = df.sort_values(method)
    logger.debug("Result:")
    logger.debug(df)
    date = datetime.datetime.now().strftime('%Y-%b-%d_%H-%M')
    if not outfile:
        outfile = 'similarity_DTW_{}_{}.csv'.format(probe, date)
    df.to_csv(outfile)
    logger.info("Done")
    #import matplotlib.pyplot as plt
    #offset = 5
    #plt.xlim([-1, max(len(A), len(B)) + 1])
    #plt.plot(A, lw=3)
    #plt.plot(B + offset, lw=3)
    #for (x1, x2) in path:
    #    plt.plot([x1, x2], [A[x1], B[x2] + offset])
    #plt.show()

if __name__ == '__main__':
    if mode == 'csv':
        if not database:
            logger.critical("You have to specify a database to read " +
                            "features from")
            sys.exit()
        from_csv(axis, probe, quant, penalty, norm, sortby, selfcheck,
                 database, features, outfile)
    elif mode == 'dumps':
        if not directory:
            logger.critical("You have to specify the directory to search " +
                            "for dumpfiles")
            sys.exit()
        from_dump(probe, quant, method, sortby, selfcheck, directory, max_t,
                  outfile, database)
