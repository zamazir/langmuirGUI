"""
Compare numpy dumpfiles created with guilangmuir

Examples:
    - Compare all phases of a single or more shots
    - Compare selected phases of selected shots
    - Compare selected or all available dumpfiles
"""

import glob
import sys
import argparse

import numpy as np
import pandas as pd
import matplotlib as mpl
mpl.use('Qt4Agg')
from matplotlib.pyplot import *
import matplotlib.gridspec as gridspec
mpl.rcParams['svg.fonttype'] = 'none'

def parse_args():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('-d', '--dumpfiles', nargs='+', dest='dumps',
                           help='Numpy dump files to be plotted from')
    argparser.add_argument('-p', '--probes', nargs='+',
                           help='Probes to plot')
    argparser.add_argument('-P', '--parameters', nargs='+', dest='params',
                           default=[],
                           help='Parameters to show in bar charts')
    argparser.add_argument('-i', '--directory', default='../results/plots/',
                           dest='path',
                           help='Path to directory containing dump files')
    argparser.add_argument('-s', '--shots', nargs='+', dest='shots',
                           help='Shots to plot')
    argparser.add_argument('-c', '--database', dest='database',
                           help='Database to get probe locations from. ' +
                           'Necessary if plotting nth probe')
    argparser.add_argument('--share', dest='share', action='store_true',
                           help='Plots share one figure')
    argparser.add_argument('--all', dest='all', action='store_true',
                           help='Plot all available dump files and ' +
                           'grouped by shot number')
    argparser.add_argument('--cmap', dest='cmap', default='Set1',
                           help='Matplotlib colormap to be used')
    argparser.add_argument('-r', '--ranges', nargs='+', dest='ranges',
                           type=float,
                           help='Sequence of ranges in the order shot ' +
                           'start end')
    return argparser.parse_args()

class DumpfilePlotter(object):
    def __init__(self):
        super(DumpfilePlotter, self).__init__()
        self.params = []
        self.db = None
        self.cmap = 'plasma'
        self.path = '.'

    def parse_file_name(self, fname):
        parts = fname.split('/')[-1].split('_')
        return [parts[0], float(parts[4]), float(parts[5]), parts[2]]

    def group_dumpfiles_by_shot(self, dfiles):
        grouped_dfiles = {}
        i = 0
        while i < len(dfiles):
            dfile = dfiles[i]
            shot = self.parse_file_name(dfile)[0]
            if shot in grouped_dfiles:
                i += 1
                continue
            shot_files = [f for f in dfiles if shot in f]
            grouped_dfiles[shot] = shot_files
            i += 1
        return grouped_dfiles

    def get_first_probe(self, database, shot, start, end):
        df = pd.read_csv(database)
        match_shot = df['Shot'].astype(str) == str(shot)
        match_start = df['CELMA start'].astype(str) == str(start)
        match_end = df['CELMA end'].astype(str) == str(end)
        df = df[(match_shot) & (match_start) & (match_end)]
        #deltas = []
        firsts = []
        for ind, row in df.iterrows():
            first = row['sepProbe']
            #delta = int(row['probe'][-1]) - int(first[-1])
            #deltas.append(delta)
            firsts.append(first)
        #if len(set(deltas)) < len(deltas):
        #    print ("Ambiguous probe index. Check database for erroneous probe " +
        #           "entries.\nFound probes: {}\nFound first probes: {}\n"
        #           .format(df['probe'], df['sepProbe']) +
        #           "Selecting first delta.")
        if len(set(firsts)) > 1:
            print ("Ambiguous first probe. Check database for erroneous probe " +
                   "entries.\nFound first probes: {}\n"
                   .format(df['sepProbe']) +
                   "Selecting first entry.")
        #delta = deltas[0]
        first = firsts[0].replace('?', '')
        return first

    def cycle_dfiles(self, probes):
        dfiles = glob.glob('{}*.npz'.format(self.path))
        grouped_dfiles = self.group_dumpfiles_by_shot(dfiles)
        for shot, files in grouped_dfiles.items():
            self.plot_dumpfiles(files, probes)

    def plot_shots(self, shots, probes, shared_fig=False):
        """
        Plots all phases belonging to the specified shots. Shots are plotted in
        different figures if shared_fig=False (default).
        """
        dfiles = []
        for shot in shots:
            pattern = "{}{}*.npz".format(self.path, shot)
            if not shared_fig:
                dfiles = glob.glob(pattern)
                self.plot_dumpfiles(dfiles, probes)
            else:
                dfiles += glob.glob(pattern)
        if shared_fig:
            self.plot_dumpfiles(dfiles, probes)

    def plot_ranges(self, ranges, probes, shared_fig=False):
        """
        Plots ranges as given by shot, start, end
        """
        dfiles = []
        def next_range(ranges, n=3):
            for i in xrange(0, len(ranges), n):
                yield ranges[i:i + n]
        for _range in next_range(ranges):
            pattern = "{}{:.0f}*{:.4f}*{:.4f}*.npz".format(self.path, *_range)
            if not shared_fig:
                dfiles = glob.glob(pattern)
                self.plot_dumpfiles(dfiles, probes)
            else:
                dfiles += glob.glob(pattern)
        if shared_fig:
            self.plot_dumpfiles(dfiles, probes)

    #def get_colors(n, shared_fig):
    #    if shared_fig:
    #        for cm in mpl.cm:
    #        yield

    def get_quantities(self, dfiles, ignore=[]):
        quants = []
        for dfile in dfiles:
            shot, start, end, quant = self.parse_file_name(dfile)
            if quant not in ignore:
                quants.append(quant)
        return list(set(quants))

    def get_phases(self, dfiles):
        phases = []
        for dfile in dfiles:
            phase = self.parse_file_name(dfile)
            phase = phase[:-1]
            if phase not in phases:
                phases.append(phase)
        phases.sort(key=lambda x: (x[0], x[1]))
        return phases

    def get_parameter(self, param, shot, start, end, db=None):
        db = db or self.db
        df = pd.read_csv(db)
        match_shot = df['Shot'].astype(str) == str(shot)
        match_start = df['CELMA start'].astype(str) == str(start)
        match_end = df['CELMA end'].astype(str) == str(end)
        df = df[(match_shot) & (match_start) & (match_end)]
        # Should be same value for every entry belonging to same phase
        # so mean() just fetches that value
        param = next((p for p in df.columns if p.lower() == param.lower()),
                     None)
        return df[param].mean()

    def plot_dumpfiles(self, dfiles, probes, colors=None,
                       show_empty_figs=False, params=[]):
        """
        Plots specified dumpfiles
        """
        ion()
        if not len(params):
            params = self.params
        
        if not len(dfiles):
            print "No dumpfiles found"
            return
        quants = self.get_quantities(dfiles)

        # Layout: 2 gridspecs embedded in 1 parent gridspec to enable different
        # wspace and hspace settings
        n = 2 if len(params) else 1
        hratios = [2, 1] if len(params) else None
        gs = gridspec.GridSpec(n, 1, height_ratios=hratios)
        gs.update(hspace=.4)
        gs_data = gridspec.GridSpecFromSubplotSpec(len(quants), 1, gs[0],
                                                   hspace=0)
        if len(params):
            gs_bars = gridspec.GridSpecFromSubplotSpec(1, len(params), gs[1],
                                                       wspace=0.2)

        # Create axes
        axes = {}
        fig = figure(figsize=(5, 6))
        for i, quant in enumerate(quants):
            axes[quant] = fig.add_subplot(gs_data[i, 0])
        for j, param in enumerate(params):
            axes[param] = fig.add_subplot(gs_bars[0, j])

        # Share x-axis
        for quant in quants:
            _quant_axes = [ax for key, ax in axes.items() if key in quants]
            axes[quant]._shared_x_axes.join(*_quant_axes)

        # Colors (ignores possibility of multiple probes so they'll be the same
        # color if they belong to the same phase)
        phases = self.get_phases(dfiles)
        cmap = get_cmap(self.cmap)
        colors = {str(phase): cmap(i)
                  for phase, i in zip(phases, np.linspace(0, 1, len(phases)))}

        # Plot data
        for dfile in dfiles:
            data = np.load(dfile)
            phase = self.parse_file_name(dfile)
            quant = phase.pop()
            color = colors[str(phase)]
            if 'first' in probes:
                probes = [self.get_first_probe(self.db, *phase)]
            for probe in probes:
                signal = 'Linear regression {}'.format(probe)
                try:
                    pdata = data[signal].transpose()
                except KeyError:
                    print("Probe {} not available for {} {}-{}s"
                          .format(probe, *phase))
                    continue
                if shared_fig:
                    label = '{1} ({2:.2f}-{3:.2f}) {0}'.format(probe, *phase)
                else:
                    label = '{1:.2f}-{2:.2f} {0}'.format(probe, *phase[1:])
                x, y = pdata
                # show x in ms
                x *= 1000
                if quant.lower() == 'jsat':
                    y /= 1000
                # 0s are most likely due to failed binning
                y[y == 0] = np.nan
                p, = axes[quant].plot(x, y, label=label, color=color, lw=2)
                axes[quant].set_xlabel('Time since ELM onset [ms]')
                axes[quant].set_ylabel(quant.capitalize())
                xlim = axes[quant].get_xlim()
                axes[quant].set_xlim(-1, xlim[1])
                
        # Plot parameter bar charts
        phases = self.get_phases(dfiles)
        tick_labels = ["{}-{}s".format(start, end) for _, start, end in phases]
        for param in params:
            for i, phase in enumerate(phases):
                if not str(phase) in colors:
                    color = 'black'
                else:
                    color = colors[str(phase)]
                y = self.get_parameter(param, *phase)
                rect, = axes[param].bar(i, y, label=phase, color=color)
                x_pos = rect.get_x() + rect.get_width() / 2.
                y_pos = 0.7 * y
                if param.lower() == 'tdiv':
                    text = "{:.0f}".format(y)
                elif param.lower() == 'ne_tot':
                    text = "{:.1f}".format(y * 100)
                else:
                    text = "{:.1f}".format(y)
                axes[param].text(x_pos, y_pos, text, rotation=270,
                                 ha='center', va='center')
            axes[param].xaxis.set_ticks([])
            #axes[param].yaxis.set_ticklabels([])
            axes[param].grid(axis='y', linestyle='--')
            axes[param].set_xlabel(param)
            

        # Close empty figures
        if not show_empty_figs:
            lines = []
            for ax in axes.values():
                lines.extend(ax.lines)
            if not len(lines):
                close(fig)
                return

        # Show 'No data' for empty axes
        for ax in axes.values():
            if not len(ax.lines) and not len(ax.patches):
                ax.text(0.5, 0.5, 'No data', transform=ax.transAxes)
        axes['jsat'].legend(ncol=2, loc='upper right')
        #                    bbox_to_anchor=(0.3, 1.1))

        if not shared_fig:
            fig.suptitle('{}'.format(phase[0]), x=0.2)


if __name__ == '__main__':
    args = parse_args()
    dfiles = args.dumps
    probes = args.probes or ['ua3']
    shots = args.shots
    ranges = args.ranges
    params = args.params
    cmap = args.cmap
    cycle = args.all
    database = args.database
    shared_fig = args.share
    path = args.path

    if 'first' in probes and not database:
        sys.exit('No database specified')

    plotter = DumpfilePlotter()
    plotter.params = params
    plotter.db = database
    plotter.cmap = cmap
    plotter.path = path
    if cycle:
        plotter.cycle_dfiles(probes)

    if dfiles:
        plotter.plot_dumpfiles(dfiles, probes)

    if shots:
        plotter.plot_shots(shots, probes, shared_fig=shared_fig)

    if ranges:
        if not len(ranges) % 3:
            plotter.plot_ranges(ranges, probes, shared_fig=shared_fig)
        else:
            print "Invalid number of arguments. Ranges must consist of shot, start, end"
    raw_input('Press any key to continue')
