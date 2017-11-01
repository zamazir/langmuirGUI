from PyQt4 import QtGui, QtCore
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import (FigureCanvasQTAgg
                                                as FigureCanvas)
from matplotlib.backends.backend_qt4agg import (NavigationToolbar2QT
                                                as NavigationToolbar)
from matplotlib.ticker import MaxNLocator
import matplotlib as mpl
from matplotlib import gridspec
import numpy as np

class DraggableColorbar(object):
    def __init__(self, cbar, mappable):

        self.cbar = cbar
        self.mappables = [mappable]
        self.press = None
        self.cycle = sorted([i for i in dir(mpl.cm)
                             if hasattr(getattr(mpl.cm, i), 'N')])
        self.index = self.cycle.index(cbar.get_cmap().name)

    def connect(self):
        """connect to all the events we need"""
        self.cidpress = self.cbar.patch.figure.canvas.mpl_connect(
            'button_press_event', self.on_press)
        self.cidrelease = self.cbar.patch.figure.canvas.mpl_connect(
            'button_release_event', self.on_release)
        self.cidmotion = self.cbar.patch.figure.canvas.mpl_connect(
            'motion_notify_event', self.on_motion)
        self.keypress = self.cbar.patch.figure.canvas.mpl_connect(
            'key_press_event', self.key_press)

    def on_press(self, event):
        """on button press we will see if the mouse is over us and store some
        data"""
        if event.inaxes != self.cbar.ax:
            return
        self.press = event.x, event.y

    def key_press(self, event):
        if event.key == 'down':
            self.index += 1
        elif event.key == 'up':
            self.index -= 1
        if self.index < 0:
            self.index = len(self.cycle)
        elif self.index >= len(self.cycle):
            self.index = 0
        cmap = self.cycle[self.index]
        self.cbar.set_cmap(cmap)
        self.cbar.draw_all()
        for mappable in self.mappables:
            mappable.set_cmap(cmap)
            mappable.get_axes().set_title(cmap)
        self.cbar.patch.figure.canvas.draw()

    def on_motion(self, event):
        'on motion we will move the rect if the mouse is over us'
        if self.press is None:
            return
        if event.inaxes != self.cbar.ax:
            return
        xprev, yprev = self.press
        #dx = event.x - xprev
        dy = event.y - yprev
        self.press = event.x, event.y
        scale = self.cbar.norm.vmax - self.cbar.norm.vmin
        perc = 0.03
        if event.button == 1:
            self.cbar.norm.vmin -= (perc * scale) * np.sign(dy)
            self.cbar.norm.vmax -= (perc * scale) * np.sign(dy)
        elif event.button == 3:
            self.cbar.norm.vmin -= (perc * scale) * np.sign(dy)
            self.cbar.norm.vmax += (perc * scale) * np.sign(dy)
        self.cbar.draw_all()
        for mappable in self.mappables:
            mappable.set_norm(self.cbar.norm)
        self.cbar.patch.figure.canvas.draw()


    def on_release(self, event):
        """on release we reset the press data"""
        self.press = None
        for mappable in self.mappables:
            mappable.set_norm(self.cbar.norm)
        self.cbar.patch.figure.canvas.draw()

    def addMappable(self, mappable):
        self.mappables.append(mappable)

    def disconnect(self):
        """disconnect all the stored connection ids"""
        self.cbar.patch.figure.canvas.mpl_disconnect(self.cidpress)
        self.cbar.patch.figure.canvas.mpl_disconnect(self.cidrelease)
        self.cbar.patch.figure.canvas.mpl_disconnect(self.cidmotion)

class FigureWindow(QtGui.QMainWindow):
    close = QtCore.pyqtSignal()

    def __init__(self, parent=None, plot=None):
        super(FigureWindow, self).__init__(parent)
        self.axes = []

        if plot is None:
            self.fig = Figure()
            self._currentAxes = self.fig.add_subplot(111)
            self.canvas = FigureCanvas(self.fig)
            self._isBreakout = False
        else:
            self.fig = plot.fig
            self._currentAxes = plot.axes
            self.canvas = plot.canvas
            self._isBreakout = True
            self._container = plot.container

        self.toolbar = NavigationToolbar(self.canvas, self)

        container = QtGui.QWidget()
        layout = QtGui.QVBoxLayout()
        layout.addWidget(self.canvas)
        layout.addWidget(self.toolbar)
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.setGeometry(QtCore.QRect(100, 100, 800, 400))

        self.plotSettings = {}
        self.axes.append(self._currentAxes)
        self._plotFunc = self._currentAxes.plot
        self._plotTypes = ('scatter', 'plot', 'axvline', 'axhline',
                           'axvspan', 'axhspan')
        self._plotType = 'plot'
        self._cbar = {self._currentAxes: None}
        self._cbarlabels = {self.currentAxes: ''}
        self._shared_cbar = None
        self._shared_cax = None
        self._shared_cbarlabel = ''
        self.maxrows = 4


    def closeEvent(self, event):
        if self._isBreakout:
            self._returnFigure()
        self.close.emit()
        super(FigureWindow, self).closeEvent(event)


    def _returnFigure(self):
        if self._container is not None:
            self._container.addWidget(self.canvas)
            self._container.setGeometry(self.container.geometry())


    def currentAxes(self):
        return self._currentAxes


    def axes(self):
        return self.axes


    def setMaxRows(self, n):
        self.maxrows = n


    def removeSubplot(self, n=None, ax=None):
        if not ax:
            if not n:
                ax = self._currentAxes
            else:
                ax = self.axes[n]
        ax.remove()
        self.axes = [a for a in self.axes if a != ax]
        self.repositionSubplots()


    def repositionSubplots(self):
        n = len(self.axes)
        print("number of axes:", n)
        colcount = (n - 1) / self.maxrows + 1
        rowcount = min(n, self.maxrows)
        m = colcount
        width_ratios = [10] * m
        if self._shared_cbar:
            m += 1
            width_ratios = width_ratios.append(1)
        print('{}x{} grid'.format(rowcount, m))
        gs = gridspec.GridSpec(rowcount, m,
                               width_ratios=width_ratios)

        # Stack subplots without vertical spacing
        gs.update(hspace=0, wspace=0.05, top=0.93)

        # Position subplots
        for i, ax in enumerate(self.axes):
            col = i % colcount
            row = i / colcount
            print("positioning subplot: ({}, {})"
                  .format(row, col))
            ax.set_position(gs[row, col].get_position(self.fig))
            ax.set_subplotspec(gs[row, col])

        if len(self.axes) > 1:
            # Remove uppermost tick labels so they don't overlap
            # Setting the same locator for all plots (inluding the top one)
            # makes for a more uniform look
            for ax in self.axes:
                ax.yaxis.set_major_locator(MaxNLocator(nbins=5,
                                                       prune='upper'))

            # Align y-axis labels (ignore missing labels with coords (0,0))
            xmin = min([ax.yaxis.label.get_position()[0] for ax in self.axes
                        if ax.yaxis.label.get_position()[0] > 0])
            for ax in self.axes:
                trafo = ax.yaxis.label.get_transform()
                ax.yaxis.set_label_coords(xmin, 0.5, trafo)

        # For some reason, this is not necessary but actually messes up the
        # layout of, and only of, the first plot \('_')/
        if self._shared_cbar:
            self._shared_cbar.cbar.ax.set_position(
                gs[:, m].get_position(self.fig))
            self._shared_cbar.cbar.ax.set_subplotspec(gs[:, m])

        # Hide tick labels of upper plots
        ticklbls = [a.get_xticklabels() for a in self.axes]
        for i, tlbls in enumerate(ticklbls):
            if not i % rowcount:
                mpl.artist.setp(tlbls, visible=True)
            else:
                mpl.artist.setp(tlbls, visible=False)


    def addSubplot(self, xdata=None, ydata=None, sharex=None):
        #axes = self.fig.add_subplot(n + 1, 1, n + 1, sharex=sharex)
        axes = self.fig.add_subplot(111, sharex=sharex)
        self.axes.append(axes)
        self._cbar[axes] = None
        self._cbarlabels[axes] = None

        if xdata is not None and ydata is not None:
            self.xdata = xdata
            self.ydata = ydata
            self.plotData()

        self.repositionSubplots()
        self.canvas.draw()

        return axes


    def setAxesLabels(self, xlabel, ylabel, zlabel):
        self._currentAxes.set_xlabel(xlabel)
        self._currentAxes.set_ylabel(ylabel)
        if self._cbar[self._currentAxes]:
            self._cbar[self._currentAxes].cbar.set_label(zlabel)
            self._cbarlabels[self._currentAxes] = zlabel
        elif self._shared_cbar:
            self._shared_cbar.cbar.ax.set_ylabel(zlabel)
            self._shared_cbar.cbar.set_label(zlabel)
            self._shared_cbarlabel = zlabel


    def setCurrentAxes(self, ax):
        self._currentAxes = ax


    def setPlotType(self, tp):
        if tp in self._plotTypes:
            self._plotType = tp
        else:
            pass
            #print "Error: unrecognized plotting method passed"


    def feedSettings(self, overrule=False, **kwargs):
        if overrule:
            self.plotSettings = kwargs
        else:
            self.plotSettings.update(kwargs)
        self._outdated = True


    def updatePlot(self):
        if self._outdated:
            self.clearPlot()
            self.plotData()
            self._outdated = False


    def updateCanvas(self):
        self.canvas.draw()


    def feedData(self, xdata, ydata, zdata=None):
        self.xdata = xdata
        self.ydata = ydata
        self.zdata = zdata
        self._outdated = True


    def clearPlot(self):
        self._currentAxes.clear()
        if self._cbar[self._currentAxes]:
            self._cbar[self._currentAxes].disconnect()
            self._cbar[self._currentAxes].cbar.remove()
            self._cbar[self._currentAxes] = None


    def plotData(self, stale=False, shared_cbar=False):
        self._plotFunc = getattr(self._currentAxes, self._plotType)
        if self._plotType == 'axvline':
            cs = self._plotFunc(self.xdata, *self.ydata, **self.plotSettings)
        elif self._plotType == 'scatter' and self.zdata:
            cs = self._plotFunc(self.xdata,
                                self.ydata,
                                c=self.zdata,
                                cmap=mpl.cm.jet,
                                **self.plotSettings)
            if shared_cbar:
                if not self._shared_cbar:
                    cax = self.fig.add_subplot(111)
                    lbl = self._shared_cbarlabel
                    cbar = self.fig.colorbar(cs,
                                             ax=cax,
                                             label=lbl,
                                             orientation='vertical')
                    self._shared_cbar = DraggableColorbar(cbar, cs)
                    self._shared_cbar.connect()
                    self._shared_cax = cax
                    #for z in self.zdata:
                    #    cbar.ax.plot([0, 1], [z]*2, lw=2, c='w')
                self._shared_cbar.addMappable(cs)
                #self._shared_cax.set_position([0.9, 0.1, 0.05, 0.8])
            else:
                if not self._cbar[self._currentAxes]:
                    lbl = self._cbarlabels[self._currentAxes]
                    cbar = self.fig.colorbar(cs,
                                             ax=self._currentAxes,
                                             label=lbl,
                                             orientation='vertical')
                    self._cbar[self._currentAxes] = DraggableColorbar(cbar, cs)
                    self._cbar[self._currentAxes].connect()
                else:
                    self._cbar[self._currentAxes].addMappable(cs)
        else:
            cs = self._plotFunc(self.xdata, self.ydata, **self.plotSettings)

        if not stale:
            self.canvas.draw()
