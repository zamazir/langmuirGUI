from PyQt4 import QtGui, QtCore
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import (FigureCanvasQTAgg
                                                as FigureCanvas)
from matplotlib.backends.backend_qt4agg import (NavigationToolbar2QT
                                                as NavigationToolbar)
import matplotlib as mpl
import numpy as np

class DraggableColorbar(object):
    def __init__(self, cbar, mappable):

        self.cbar = cbar
        self.mappables = [mappable]
        self.press = None
        self.cycle = sorted([i for i in dir(mpl.cm) if hasattr(getattr(mpl.cm,i),'N')])
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
        """on button press we will see if the mouse is over us and store some data"""
        if event.inaxes != self.cbar.ax: return
        self.press = event.x, event.y

    def key_press(self, event):
        if event.key=='down':
            self.index += 1
        elif event.key=='up':
            self.index -= 1
        if self.index<0:
            self.index = len(self.cycle)
        elif self.index>=len(self.cycle):
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
        if self.press is None: return
        if event.inaxes != self.cbar.ax: return
        xprev, yprev = self.press
        dx = event.x - xprev
        dy = event.y - yprev
        self.press = event.x,event.y
        #print 'x0=%f, xpress=%f, event.xdata=%f, dx=%f, x0+dx=%f'%(x0, xpress, event.xdata, dx, x0+dx)
        scale = self.cbar.norm.vmax - self.cbar.norm.vmin
        perc = 0.03
        if event.button==1:
            self.cbar.norm.vmin -= (perc*scale)*np.sign(dy)
            self.cbar.norm.vmax -= (perc*scale)*np.sign(dy)
        elif event.button==3:
            self.cbar.norm.vmin -= (perc*scale)*np.sign(dy)
            self.cbar.norm.vmax += (perc*scale)*np.sign(dy)
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
        self.subplots = []

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
        self.subplots.append(self._currentAxes)
        self._plotFunc = self._currentAxes.plot
        self._plotTypes = ('scatter', 'plot', 'axvline', 'axhline',
                           'axvspan', 'axhspan')
        self._plotType = 'plot'
        self._cbar = None
        self._cbarlabel = ''


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
        return self.subplots


    def addSubplot(self, xdata=None, ydata=None):
        n = len(self.subplots)
        for i, ax in enumerate(self.subplots):
            ax.change_geometry(n + 1, 1, i + 1)

        axes = self.fig.add_subplot(n + 1, 1, n + 1)
        self.subplots.append(axes)

        if xdata is not None and ydata is not None:
            axes.plot(xdata, ydata)

        return axes


    def setAxesLabels(self, xlabel, ylabel, zlabel):
        self._currentAxes.set_xlabel(xlabel)
        self._currentAxes.set_ylabel(ylabel)
        if self._cbar:
            self._cbar.cbar.set_label(zlabel)
        self._cbarlabel = zlabel


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
        if self._cbar:
            self._cbar.disconnect()
            self._cbar.cbar.remove()
            self._cbar = None


    def plotData(self, stale=False):
        self._plotFunc = getattr(self._currentAxes, self._plotType)
        if self._plotType == 'axvline':
            self._plotFunc(self.xdata, *self.ydata, **self.plotSettings)
        elif self._plotType == 'scatter' and self.zdata:
            cs = self._plotFunc(self.xdata,
                                self.ydata,
                                c=self.zdata,
                                cmap=mpl.cm.jet,
                                **self.plotSettings)
            if not self._cbar:
                cbar = self.fig.colorbar(cs,
                                         label=self._cbarlabel,
                                         orientation='vertical')
                self._cbar = DraggableColorbar(cbar, cs)
                self._cbar.connect()
            else:
                self._cbar.addMappable(cs)
        else:
            self._plotFunc(self.xdata, self.ydata, **self.plotSettings)

        if not stale:
            self.canvas.draw()
