"""
Superimpose exactly two phases determined by one of the similarity tables
created with similarity.py to directly compare the
most similar phases and their respective plasma parameters
"""
import sys
import os
import argparse
import numpy as np
import pandas as pd
import matplotlib as mpl
import logging
import functools
mpl.use('Qt4Agg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT as NavigationToolbar
from PyQt4.QtGui import *
from PyQt4.QtCore import *

mpl.rcParams['svg.fonttype'] = 'none'
mpl.rcParams['savefig.format'] = 'svg'
mpl.rcParams['savefig.directory'] = \
r'/media/Storage/OneDrive/Uni/TUM/Masterarbeit/Thesis/img/results/equal'


argparser = argparse.ArgumentParser()
argparser.add_argument('input', action='store', help='CSV file')
argparser.add_argument('-i', action='store', dest='directory',
                       help='Directory containing dump files')
argparser.add_argument('-l', '--loglevel', dest='loglevel', default='info',
                       help='Logging level')
argparser.add_argument('-p', '--params', nargs='+', dest='parameters',
                       default=sorted(['tdiv', 'ptot', 'nbar',
                                       'n', 'ne', 'd']),
                       help=('Parameters to be plotted in the bar chart. ' +
                             'Must correspond to parameter name in column ' +
                             '<Signal N> <parameter> of the input database'))
args = argparser.parse_args()
infile = args.input
params = args.parameters
loglevel = args.loglevel
directory = args.directory or '.'

try:
    loglevel = getattr(logging, loglevel.upper())
except AttributeError:
    loglevel = logging.INFO

logger = logging.getLogger()
logger.setLevel(loglevel)
stream_hdlr = logging.StreamHandler(sys.stdout)
stream_hdlr.setLevel(loglevel)
logger.addHandler(stream_hdlr)

class CompareApp(QWidget):
    def __init__(self, df, parameters=None):
        super(CompareApp, self).__init__()
        self._current_row = 0
        self.df = df
        if parameters:
            self.set_parameters(parameters)
        else:
            self.parameters = sorted(['Tdiv', 'Ptot', 'nbar', 'N', 'Ne', 'D'])
        self.signals = ('Signal 1', 'Signal 2')
        self.colors = ('r', 'b')
        self.bar_width = 0.3
        self.params_cbs = []

        self.initUI()
        self._bind_callbacks()
        self.probe = str(self.combo_probe.currentText())
        self.diffs = 'Differences' == str(self.combo_diffs.currentText())

    def initUI(self):
        self.fig = Figure()
        gs = mpl.gridspec.GridSpec(4, 2, width_ratios=[2, 1])
        gs.update(hspace=0)
        self.axes_te = self.fig.add_subplot(gs[:2, 0])
        self.axes_jsat = self.fig.add_subplot(gs[2:4, 0], sharex=self.axes_te)
        self.axes_leg = self.fig.add_subplot(gs[0:, 1])
        self.axes_param = self.fig.add_subplot(gs[1:, 1])
        self.canvas = FigureCanvas(self.fig)
        self.toolbar = NavigationToolbar(self.canvas, self)

        self.axes_leg.xaxis.set_ticks([])
        self.axes_leg.yaxis.set_ticks([])
        for spine in self.axes_leg.spines.values():
            spine.set_visible(False)

        central = QHBoxLayout()

        plot_and_tb = QVBoxLayout()
        # Plot
        plot_layout = QHBoxLayout()
        plot_layout.addWidget(self.canvas)
        plot_and_tb.addLayout(plot_layout)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(self.toolbar)
        plot_and_tb.addLayout(toolbar_layout)
        
        central.addLayout(plot_and_tb)

        # Controls
        controls = QWidget()
        controls.setMaximumWidth(120)
        controls_layout = QVBoxLayout()

        for param in self.parameters:
            cb = QCheckBox(param)
            cb.setTristate(False)
            cb.setChecked(True)
            self.params_cbs.append(cb)
            controls_layout.addWidget(cb)
        
        self.lbl_current_row = QLabel()
        controls_layout.addWidget(self.lbl_current_row)
        self.edit_row = QLineEdit()
        controls_layout.addWidget(self.edit_row)

        self.combo_probe = QComboBox()
        self.combo_diffs = QComboBox()
        self.combo_probe.addItems(['ua3', 'ua4'])
        self.combo_diffs.addItems(['Relative', 'Differences'])
        controls_layout.addWidget(self.combo_probe)
        controls_layout.addWidget(self.combo_diffs)

        self.btn_next = QPushButton('Next')
        self.btn_prev = QPushButton('Previous')
        controls_layout.addWidget(self.btn_prev)
        controls_layout.addWidget(self.btn_next)

        controls.setLayout(controls_layout)
        central.addWidget(controls)

        self.setLayout(central)

    def _toggle_params(self, cb):
        if cb.isChecked():
            self.parameters.append(str(cb.text()))
        else:
            self.parameters.remove(str(cb.text()))
        self.parameters = sorted(list(set(self.parameters)))
        self.update_plot()
        
    @pyqtSlot()
    def _update_current_row(self):
        text = "Current row:\n{} of {}".format(self._current_row + 1,
                                               self.df.shape[0])
        self.lbl_current_row.setText(text)

    @pyqtSlot()
    def _update_current_probe(self):
        self.probe = str(self.combo_probe.currentText())
        self.update_plot()

    @pyqtSlot()
    def _update_bar_chart_method(self):
        method = str(self.combo_diffs.currentText())
        self.diffs = method == 'Differences'
        self.update_plot()

    @pyqtSlot()
    def _set_current_row(self):
        try:
            value = int(self.edit_row.text())
        except ValueError:
            return
        if 0 < value <= self.df.shape[0]:
            self._current_row = value - 1
            self.update_plot()
            logger.debug("Current row: {}".format(self._current_row + 1))

    def _bind_callbacks(self):
        self.btn_next.clicked.connect(self.next_plot)
        self.btn_prev.clicked.connect(self.previous_plot)
        self.combo_probe.currentIndexChanged.connect(self._update_current_probe)
        self.combo_diffs.currentIndexChanged.connect(self._update_bar_chart_method)
        self.edit_row.returnPressed.connect(self._set_current_row)
        for cb in self.params_cbs:
            cb.toggled.connect(
                functools.partial(self._toggle_params, cb))

    def _current_value(self, column):
        i = self._current_row
        row = self.df.iloc[i]
        try:
            val = row[column]
        except KeyError:
            logger.info("{} not in table".format(column))
            val = np.nan
        return val

    def _parse_phase(self, column):
        logger.debug("Parsing phase; column {}".format(column))
        phase = self._current_value(column)
        logger.debug("Phase: {}".format(phase))
        split = phase.split()
        if len(split) == 1:
            # Happens when using old csv files
            shot, start, end = phase.split('_')
        else:
            shot, trange = split
            start, end = trange.strip('()').split('-')
        return shot, float(start), float(end)

    def _assemble_label(self, column):
        phase = self._parse_phase(column)
        label = ('{} ({:.2f}-{:.2f})'.format(*phase))
        return label

    def _get_parameter(self, column):
        param = self._current_value(column)
        try:
            param = float(param)
        except ValueError, TypeError:
            logger.debug("Could not get parameter {}".format(column))
            pass
        return param

    def _get_dump_data(self, column):
        logger.debug("Getting dump data for {}".format(column))
        shot, start, end = self._parse_phase(column)
        fname = self._assemble_file_name(shot, start, end)
        if os.path.isfile(fname):
            data = np.load(fname)
        else:
            logger.error('Could not find file {}'.format(fname))
            return
        try:
            data = data['Linear regression {}'.format(self.probe)]
        except KeyError:
            logger.debug('No linear regression for {} found'
                         .format(self.probe))
            return
        data = data.transpose()
        label = self._assemble_label(column)
        return data, label

    def _assemble_file_name(self, shot, start, end):
        fname = ("{}_temporal_{}_CELMA_{:.4f}_{:.4f}"
                 .format(shot, self.quant, start, end) +
                 "_multiple_default_syncedByStart_RAW.npz")
        path = os.path.join(directory, fname)
        return path

    def next_plot(self):
        nextrow = self._current_row + 1
        maxrows = self.df.shape[0]
        if nextrow < maxrows:
            self._current_row = nextrow
            self.update_plot()
            logger.debug("Current row: {}".format(self._current_row + 1))

    def previous_plot(self):
        prevrow = self._current_row - 1
        if prevrow >= 0:
            self._current_row = prevrow
            self.update_plot()
            logger.debug("Current row: {}".format(self._current_row + 1))

    def _update_timetrace(self, quant, axes):
        axes.clear()
        self.quant = quant
        for signal, color in zip(self.signals, self.colors):
            result = self._get_dump_data(signal)
            if result:
                data, label = result
                x, y = data
                x *= 1000
                if quant == 'jsat':
                    y /= 1000
                np.place(y, y==0, [np.nan])
                axes.plot(x, y, label=label, color=color)

    def set_parameters(self, parameters):
        params = [p.lower() for p in parameters]
        params = [col.split()[-1] for col in self.df.columns
                   if col.startswith('Signal') and
                   col.split()[-1].lower() in params]
        params = list(set(params))
        self.parameters = sorted(params)

    def _update_barchart(self):
        if not self.parameters:
            return
        self.axes_param.clear()
        for signal, color in zip(self.signals, self.colors):
            values = []
            relative_values = []
            magnitudes = []
            for param in self.parameters:
                parameter = signal + ' ' + param
                data = self._get_parameter(parameter)
                relative_val = np.nan

                if not np.isnan(data):
                    # Normalize with respect to parameter values for all
                    # phases
                    columns = [sig + ' ' + param for sig in self.signals]
                    min_val = df[columns].min(axis=0).min()
                    max_val = df[columns].max(axis=0).max()
                    relative_val = data / (abs(max_val) + abs(min_val))
                    magnitudes.append((abs(max_val) + abs(min_val)))
                else:
                    magnitudes.append(1)

                nan2zero = lambda x: x if not np.isnan(x) else 0
                data = nan2zero(data)
                relative_val = nan2zero(relative_val)
                
                values.append(data)
                relative_values.append(relative_val)

            ind = range(len(self.parameters))
            if self.diffs:
                if signal == 'Signal 1':
                    value_buffer = values
                    continue
                else:
                    values = np.array(values) - np.array(value_buffer)
                    values = values / np.array(magnitudes)
                    self.axes_param.bar(ind, values, self.bar_width)
                    for x, y, s in zip(ind, values, values):
                        s = "{:.2f}".format(s)
                        self.axes_param.text(x, y, s)
            else:
                if signal == 'Signal 2':
                    ind = [i + self.bar_width for i in ind]
                self.axes_param.bar(ind, relative_values, self.bar_width,
                                    color=color)
                for x, y, s in zip(ind, relative_values, values):
                    s = "{:.2f}".format(s)
                    self.axes_param.text(x, y, s)

    def update_plot(self):
        # Time traces
        self._update_timetrace('te', self.axes_te)
        self._update_timetrace('jsat', self.axes_jsat)
        self.axes_te.set_ylabel(r'\te [eV]')
        self.axes_jsat.set_ylabel(r'\jsat [\SI{\kilo\ampere\per\square\meter}]')
        self.axes_jsat.set_xlabel(r'Time since \elm onset [ms]')

        # Parameters
        self._update_barchart()

        # Format
        if self.parameters:
            self.axes_param.set_xticks([i + self.bar_width / 2.
                                        for i in range(len(self.parameters))])
            self.axes_param.set_xticklabels(self.parameters)
        artists = self.axes_jsat.lines
        labels = [a.get_label() for a in artists]
        self.axes_leg.legend(artists, labels)
        #self.fig.suptitle("probe {}".format(self.probe))
        self.fig.tight_layout()

        self.canvas.draw()
        self.canvas.update()
        self._update_current_row()


if __name__ == '__main__':
    df = pd.read_csv(infile)
    app = QApplication(sys.argv)
    window = CompareApp(df, params)
    window.update_plot()
    window.show()

    sys.exit(app.exec_())
