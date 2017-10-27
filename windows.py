from PyQt4 import QtGui, QtCore
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import (FigureCanvasQTAgg
                                                as FigureCanvas)
from matplotlib.backends.backend_qt4agg import (NavigationToolbar2QT
                                                as NavigationToolbar)

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


    def setAxesLabels(self, xlabel, ylabel):
        self._currentAxes.set_xlabel(xlabel)
        self._currentAxes.set_ylabel(ylabel)


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


    def feedData(self, xdata, ydata):
        self.xdata = xdata
        self.ydata = ydata
        self._outdated = True


    def clearPlot(self):
        self._currentAxes.clear()


    def plotData(self, stale=False):
        self._plotFunc = getattr(self._currentAxes, self._plotType)
        if self._plotType == 'axvline':
            self._plotFunc(self.xdata, *self.ydata, **self.plotSettings)
        else:
            self._plotFunc(self.xdata, self.ydata, **self.plotSettings)

        if not stale:
            self.canvas.draw()
