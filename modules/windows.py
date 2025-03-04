import numbers
import os
import sys

from PyQt4 import QtGui, QtCore
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg
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


class FigureCanvas(FigureCanvasQTAgg):
    """ When saving a figure with the standard toolbar, the filename cannot be
    supplied prior to the saving so that it does not have to be typed in.
    Usually this works using the figure.canvas method set_window_title but for
    whatever reason, a QtAgg canvas does not have a figure manager so that the
    method is exited without anything happening (good lord!). This happens for
    FigureCanvasQtAgg since it inherits from FigureCanvasAgg and not from
    FigureCanvasQt where the method is implemented like below (WHY would they
    do that?!).
    I don'T feel like investigating what happens to the manager so I just bind
    the PyQt window to the canvas so it can read its title.
    """
    def set_window(self, window):
        self.window = window

    def get_default_filename(self):
        basename = str(self.window.windowTitle())
        basename = basename.lower().replace(' ', '_').replace(':', '_')
        filetype = self.get_default_filetype()
        filename = basename + '.' + filetype
        return filename

    def set_window_title(self, title):
        return self.window.setWindowTitle(title)


class FigureWindow(QtGui.QMainWindow):
    close = QtCore.pyqtSignal()

    def __init__(self, parent=None, plot=None):
        super(FigureWindow, self).__init__(parent)
        self.axes = []

        if plot is None:
            self.fig = Figure()
            self._currentAxes = self.fig.add_subplot(111)
            self.canvas = FigureCanvas(self.fig)
            self.canvas.set_window(self)
            self._isBreakout = False
        else:
            self._container = plot.container
            try:
                self._geometry = plot.container.geometry()
            except AttributeError:
                pass
            self.fig = plot.fig
            self._currentAxes = plot.axes
            self.canvas = plot.canvas
            #self.canvas.set_window(self)
            self._isBreakout = True

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
        self._cbarlabels = {self._currentAxes: ''}
        self._shared_cbar = None
        self._shared_cax = None
        self._shared_cbarlabel = ''
        self.maxrows = 3
        self.maxcols = 2
        self.orientation = 'vertical'

        runpath = os.path.dirname(os.path.realpath(sys.argv[0]))
        mpl.rcParams['savefig.directory'] = runpath
        mpl.rcParams['savefig.format'] = 'svg'


    def closeEvent(self, event):
        if self._isBreakout:
            self._returnFigure()
        self.close.emit()
        super(FigureWindow, self).closeEvent(event)


    def _returnFigure(self):
        if self._container is not None:
            self._container.addWidget(self.canvas)
            self._container.setGeometry(self._geometry)


    def currentAxes(self):
        return self._currentAxes


    def axes(self):
        return self.axes


    def setMaxRows(self, n):
        if n:
            self.maxrows = n


    def setMaxCols(self, m):
        if m:
            self.maxcols = m


    def setSubplotOrientation(self, orientation):
        self.orientation = orientation.lower()


    def removeSubplot(self, n=None, ax=None):
        if not ax:
            if not n:
                ax = self._currentAxes
            else:
                ax = self.axes[n]
        ax.remove()
        ind = self.axes.index(ax)
        del self.axes[ind]
        self._currentAxes = self.axes[max(0, ind - 1)]
        self.repositionSubplots()


    def repositionSubplots(self):
        n = len(self.axes)
        
        if self.orientation == 'vertical':
            colcount = min(self.maxcols, (n - 1) / self.maxrows + 1)
            rowcount = min(self.maxrows, n)
        elif self.orientation == 'horizontal':
            colcount = min(self.maxcols, n)
            rowcount = min(self.maxrows, (n - 1) / self.maxcols + 1)
            
        width_ratios = [10] * colcount
        if self._shared_cbar:
            print('shared cbar present')
            colcount += 1
            width_ratios = width_ratios.append(1)
        #print('{}x{} grid'.format(rowcount, colcount))
        gs = gridspec.GridSpec(rowcount, colcount)

        # Stack subplots without vertical spacing
        gs.update(hspace=0, wspace=0.2, top=0.93)

        # Position subplots
        for i, ax in enumerate(self.axes):
            if self.orientation == 'vertical':
                col = i / rowcount
                row = i % rowcount
            elif self.orientation == 'horizontal':
                col = i % colcount
                row = i / colcount
            #print("positioning subplot: ({}, {})"
            #      .format(row, col))
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
        #if self._shared_cbar:
        #    self._shared_cbar.cbar.ax.set_position(
        #        gs[:, colcount - 1].get_position(self.fig))
        #    self._shared_cbar.cbar.ax.set_subplotspec(gs[:, colcount - 1])

        # Hide tick labels of upper plots
        ticklbls = [a.get_xticklabels() for a in self.axes]
        for i, tlbls in enumerate(ticklbls):
            if not i % rowcount:
                mpl.artist.setp(tlbls, visible=True)
            else:
                mpl.artist.setp(tlbls, visible=False)
        self.canvas.draw()


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

    
    def clearSettings(self):
        self.plotSettings = {}
        self._outdated = True


    def updatePlot(self):
        if self._outdated:
            self.clearPlot()
            self.plotData()
            self._outdated = False


    def updateCanvas(self):
        self.canvas.draw()


    def feedData(self, xdata, ydata, zdata=[]):
        self.xdata = np.array(xdata, dtype=np.float)
        self.ydata = np.array(ydata, dtype=np.float)
        self.zdata = np.array(zdata, dtype=np.float)

        ind_sort = self.xdata.argsort()
        self.xdata = self.xdata[ind_sort]
        self.ydata = self.ydata[ind_sort]
        if len(self.zdata):
            self.zdata = self.zdata[ind_sort]
        
        ind_finx = np.isfinite(self.xdata)
        self.xdata = self.xdata[ind_finx]
        self.ydata = self.ydata[ind_finx]
        if len(self.zdata):
            self.zdata = self.zdata[ind_finx]

        ind_finy = np.isfinite(self.ydata)
        self.xdata = self.xdata[ind_finy]
        self.ydata = self.ydata[ind_finy]
        if len(self.zdata):
            self.zdata = self.zdata[ind_finy]
        else:
            self.zdata = [np.nan]

        self._outdated = True


    def clearPlot(self):
        self._currentAxes.clear()
        if self._cbar[self._currentAxes]:
            self._cbar[self._currentAxes].disconnect()
            self._cbar[self._currentAxes].cbar.remove()
            self._cbar[self._currentAxes] = None
        if self._shared_cbar:
            self._shared_cbar.disconnect()
            self._shared_cbar.cbar.remove()
            self._shared_cbar = None

    
    def setAutoscale(self, autoscale):
        """
        Autoscale <list>  boolean  specifies which axes to autoscale
        """
        try:
            keys = autoscale.keys()
        except AttributeError:
            if len(autoscale) != 2:
                print("Invalid autoscale instruction", autoscale)
                return
            autoscale = {'x': autoscale[0],
                         'y': autoscale[1]}
            keys = autoscale.keys()
        else:
            if keys != ['x', 'y']:
                print("Invalid autoscale instruction", autoscale)
                return
        for axis, scale in autoscale.items():
            self._currentAxes.autoscale(scale, axis)

    
    def annotate(self, text, x, y, stale=False):
        x = np.array(x, dtype=np.float)
        y = np.array(y, dtype=np.float)
        text = np.array(text)
        # filter non-finite values to avoid posx, posy error when drawing
        # canvas in oblique cases
        ind = np.isfinite(x)
        x = x[ind]
        y = y[ind]
        text = text[ind]
        ind = np.isfinite(y)
        x = x[ind]
        y = y[ind]
        text = text[ind]
        for t, xpos, ypos in zip(text, x, y):
            self._currentAxes.text(xpos, ypos, t, fontsize=8, style='italic')
        if not stale:
            self.canvas.draw()


    def plotData(self, stale=False, shared_cbar=False, **kwargs):
        print('plotting data to axis', self.axes.index(self._currentAxes))
        zlabels = None
        self._plotFunc = getattr(self._currentAxes, self._plotType)
        if self._plotType == 'axvline':
            cs = self._plotFunc(self.xdata, *self.ydata, **self.plotSettings)
        elif (self._plotType == 'scatter' and
              not np.isnan(self.zdata).all()):
            norm = None
            if any(not isinstance(el, numbers.Number) for el in self.zdata):
                zlabels = sorted(list(set(self.zdata)))
                for i, lbl in enumerate(zlabels):
                    self.zdata = [i if el == lbl else el for el in self.zdata]
                norm = mpl.colors.BoundaryNorm(sorted(list(set(self.zdata))),
                                               len(sorted(list(set(self.zdata)))))
                self.plotSettings['vmin'] = min(self.zdata)
                self.plotSettings['vmax'] = max(self.zdata)
            color = (self.zdata if self.zdata.any() else self.plotSettings['color'])
            cs = self._plotFunc(self.xdata,
                                self.ydata,
                                c=color,
                                cmap=mpl.cm.jet,
                                norm=norm,
                                **{key: val 
                                   for key, val in self.plotSettings.items()
                                   if key not in ('cmap', 'norm', 'c', 'color')})
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
                    #    cbar.ax.axhline(z, 0, 1, lw=2, c='w')
                else:
                    if min(self.zdata) != max(self.zdata):
                        cbar = self._cbar[self._currentAxes].cbar
                        cbar.norm.vmin = min(self.zdata)
                        cbar.norm.vmax = max(self.zdata)
                        #cbar.patch.figure.canvas.draw()
                self._shared_cbar.addMappable(cs)
                if zlabels:
                    self._shared_cbar.cbar.ax.set_yticklabels(zlabels)
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
                    if min(self.zdata) != max(self.zdata):
                        cbar = self._cbar[self._currentAxes].cbar
                        cbar.norm.vmin = min(self.zdata)
                        cbar.norm.vmax = max(self.zdata)
                        #cbar.patch.figure.canvas.draw()
                    self._cbar[self._currentAxes].addMappable(cs)
                if zlabels:
                    self._cbar[self._currentAxes].cbar.ax.set_yticklabels(zlabels)
        else:
            print("Creating scatter plot")
            cs = self._plotFunc(self.xdata, self.ydata, **kwargs)#self.plotSettings)

        if not stale:
            self.canvas.draw()
