"""
Combine n elm cache files into one
"""
import sys
import pickle
import argparse
import logging

parser = argparse.ArgumentParser()
parser.add_argument('input', nargs='+',
                    help='ELM cache files to be combined')
parser.add_argument('-o', '--output', dest='output', default='elms_combined.p',
                    help='New ELM cache file')
parser.add_argument('-l', '--loglevel', dest='loglevel', default='info',
                    choices=('debug', 'info', 'warning', 'error', 'critical'),
                    help='Logging level')
args = parser.parse_args()
input = args.input
output = args.output
loglevel = args.loglevel
try:
    loglevel = getattr(logging, loglevel.upper())
except AttributeError:
    loglevel = logging.INFO

logger = logging.getLogger(__name__)
logger.setLevel(loglevel)
hdlr = logging.StreamHandler(sys.stdout)
hdlr.setLevel(loglevel)
logger.addHandler(hdlr)

elms = {}
for cfile in input:
    try:
        data = pickle.load(open(cfile, 'r'))
    except IOError, e:
        logger.error(str(e))
        continue
    logger.debug(cfile)
    for shot, elmtimes in data.items():
        if shot not in elms:
            elms[shot] = []
        logger.debug('{} ELM times: {}'.format(shot, elmtimes))
        elms[shot].extend(elmtimes)
        elms[shot] = list(set(elms[shot]))

data = pickle.dump(elms, open(output, 'w'))
logger.info('Combined elm cache saved as {}'.format(output))
