##############################################################################
#
# guilangmuir.py -  A graphical user interface for investigating detachment
#                   states at ASDEX Upgrade 
#
# This program was written as part of the master's thesis of Amazigh Zerzour. 
# Its aim is to provide a visual and interactive way of recognizing and 
# classifying detachment regimes using langmuir data from the outer divertor 
# probes.
#
# Author: Amazigh Zerzour
# E-Mail: amazigh.zerzour@gmail.com
#
# Version: Feb. 2017
#
#
# Issues:
# - Data evaluation will fail if the time data arrays vary from probe to probe
#
# - At application start, jPlot is not synced with the others
#
# To do:
# - Add options to change all parameters like
#       * Indicator.color
#       * SpatialPlot.coloring = 1
#       * SpatialPlot.defaultColor = 'b'
#       * CurrentPlot.mapDir
#       * CurrentPlot.mapDiag
#       * CurrentPlot.diag
#       * Path to calibrations
#       * Path to probe positions
#   from within the GUI and store them in a config file
#
##############################################################################

import sys
import os
import pickle
import functools
import subprocess
import threading
import gc

import matplotlib as mpl
mpl.use('Qt4Agg')
from matplotlib import cm
from matplotlib import pyplot as plt
from matplotlib import patches
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT as NavigationToolbar
from PyQt4 import QtGui, QtCore, Qt
from PyQt4.QtGui import (QWidget, QMessageBox, QPainter, QColor)
from PyQt4.QtCore import pyqtSlot, pyqtSignal
from PyQt4.QtCore import QObject
from PyQt4.uic import loadUiType
from configobj import ConfigObj
from validate import Validator
from scipy import interpolate
import numpy as np
import logging

import dd
from fitting import FitFunctions
from slider import SchizoSlider
from FeaturePicking import FeaturePicker, Plotter
from windows import FigureWindow

logging.basicConfig(
                filename='langmuirAnalyzer.log', 
                filemode='a', 
                format='%(asctime)s [%(levelname)s]: %(message)s', 
                datefmt='%d/%m/%Y %I:%M:%S %p', 
                level=logging.ERROR)
logging.info('\n++++++++++++++ Program started +++++++++++++++++')

# Set recursion limit high so using the slider won't crash the app
sys.setrecursionlimit(10000)
# Don't cut off axes labels or ticks
#mpl.rcParams.update({'figure.autolayout': True})
# Render text as text so it can be changed by graphics programs
mpl.rcParams['svg.fonttype'] = 'none'

# Load UI
Ui_MainWindow, QMainWindow = loadUiType('GUI.ui')


class Sync():
    @staticmethod
    def unsync(*args):
        """ Lifts the sharing of axes. If only one axis is given, unsync unbinds all shared axes. If given multiple axes, each axes will be unbound from the respective other axes. """
        if len(args) == 0:
            pass

        # If only on argument, unbind all shared axes
        elif len(args) == 1:
            del args.axes._shared_x_axes[:] 

        # If multiple arguments, try to remove the respective other axes from each given axes 
        else:
            for triggerPlot in args:
                for receiverPlot in args:
                    if triggerPlot != receiverPlot:
                        try:
                            triggerPlot.axes._shared_x_axes.remove(receiverPlot.axes)
                        except:
                            pass


    @staticmethod
    def sync(*args):
        """ Expects n>1 plots as arguments and joins their axes so they are always at the same zoom level. """
        if len(args) == 1:
            try:
                args = [el for el in args]
            except TypeError, e:
                print "Expected either iterable object with plots to sync "\
                        "as elements or the elements passed one-by-one. "\
                        "Instead, I got this:", str(e)
                return
        if len(args) < 2:
            print "Need at least 2 plots to sync"
            pass
        else:
            for triggerPlot in args:
                for receiverPlot in args:
                    if triggerPlot != receiverPlot:
                        triggerPlot.axes._shared_x_axes.join(triggerPlot.axes, receiverPlot.axes)
                        triggerPlot.axes.callbacks.connect('xlim_changed', receiverPlot.rescaleyAxis)



class Probe():
    def __init__(self, name=None):
        self.type = 'GenericProbe'
        self.name = name
        self.position = (0.,0.)
        self._plotted = {}
        self._visible = {}
        self._selected = {}
        self.color = (0,0,0)
        self.CELMA = False


    def __str__(self):
        return self.name


    def x(self):
        return self.position[0]


    def y(self):
        return self.position[1]


    def setColor(self, color):
        self.color = color


    def getPosition(self):
        return self.position


    def isVisible(self, canvas=None):
        if canvas is None:
            raise ValueError('Canvas must be specified')
        if canvas not in self._visible:
            return False
        return self._visible[canvas]


    def isPlotted(self, canvas=None):
        if canvas is None:
            raise ValueError('Canvas must be specified')
        if canvas not in self._plotted:
            return False
        return self._plotted[canvas]


    def isSelected(self, canvas=None):
        if canvas is None:
            raise ValueError('Canvas must be specified')
        if canvas not in self._selected:
            return False
        return self._selected[canvas]


    def setPosition(self, pos):
        if len(pos) == 2:
            for i, el in enumerate(pos):
                try:
                    pos[i] = float(el)
                except ValueError:
                    raise ValueError('Probe position arguments must be numbers')
            self.position = pos
        else:
            raise ValueError('Probe position must be an iterable of length 2')


    def setPlotted(self, canvas=None, plotted=None):
        if canvas is None:
            raise ValueError('Canvas must be specified')
        if canvas not in self._plotted:
            self._plotted[canvas] = True
            return
        if plotted is None:
            self._plotted[canvas] = not self._plotted[canvas]
        else:
            self._plotted[canvas] = plotted
        

    def setSelected(self, canvas=None, selected=None):
        if canvas is None:
            raise ValueError('Canvas must be specified')
        if canvas not in self._selected:
            self._selected[canvas] = True
            return
        if selected is None:
            self._selected[canvas] = not self._selected[canvas]
        else:
            self._selected[canvas] = selected
        

    def setVisible(self, canvas=None, visible=None):
        if canvas is None:
            raise ValueError('Canvas must be specified')
        if visible is None:
            raise ValueError('Visibility must be specified')
            #self._visible[canvas] = not self._visible[canvas]
        if canvas not in self._visible:
            self._visible[canvas] = True
            return
        else:
            self._visible[canvas] = visible


    def toggle(self, canvas=None):
        if canvas is None:
            raise ValueError('Canvas must be specified')
        self._visible[canvas] = not self._visible[canvas]



class LangmuirProbe(Probe):
    def __init__(self, name=None):
        Probe.__init__(self, name)
        self.type = 'LangmuirProbe'
        self.channel = (0,0)
        self.geometry = (0,0)


    def length(self):
        return self.geometry[0]


    def width(self):
        return self.geometry[1]


    def getChannel(self):
        return self.channel
    

    def getSegment(self):
        return self.segment


    def setSegment(self, seg):
        try:
            self.segment = int(seg)
        except ValueError:
            raise ValueError('Probe segment must be a number')


    def setGeometry(self, geom):
        assert not isinstance(geom, basestring),\
                'Probe geometry must be provided as a list or tuple'
        if len(geom) == 2:
            for i, el in enumerate(geom):
                try:
                    geom[i] = float(el)
                except ValueError:
                    raise ValueError('Probe dimensions must be numbers')
            self.geometry = geom
        else:
            raise ValueError('Probe geometry must be a sequence of length 2')


    def setChannel(self, ch):
        assert not isinstance(geom, basestring),\
                'Probe channel must be provided as a list or tuple'
        if len(ch) == 2:
            for i, el in enumerate(ch):
                try:
                    ch[i] = int(el)
                except ValueError:
                    raise ValueError('Probe channel identifiers must be integers')
            self.channel = channel
        else:
            raise ValueError('Probe channel must be a sequence of length 2')



class CheckAndEditDialog(QtGui.QDialog):
    def __init__(self, parent=None, editLabel=None, checkLabel=None):
        super(CheckAndEditDialog,self).__init__(parent)


    def value(self):
        value = self.edit.text()
        checked = self.check.isChecked()
        if not checked:
            value = None
        return value 


    def init(self, title, value, editLabel, checkLabel):
        layout = QtGui.QFormLayout()
        if editLabel is None:
            self.lblEdit = QtGui.QLabel('Check to activate:')
        else:
            self.lblEdit = QtGui.QLabel(str(editLabel))
        if checkLabel is None:
            self.lblCheck = QtGui.QLabel('Insert value:')
        else:
            self.lblCheck = QtGui.QLabel(str(checkLabel))
        if title is None:
            self.setWindowTitle('Change or toggle setting')
        else:
            self.setWindowTitle(title)
        if value is None:
            value = ''

        self.edit = QtGui.QLineEdit()
        self.edit.setText(value)
        self.check = QtGui.QCheckBox()
        self.check.setTristate(False)
        self.check.setChecked(True)

        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok
                | QtGui.QDialogButtonBox.Cancel, QtCore.Qt.Horizontal)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        layout.addRow(self.lblEdit, self.edit)
        layout.addRow(self.lblCheck, self.check)
        layout.addRow(buttonBox)

        self.setLayout(layout)


    @staticmethod
    def getValue(parent=None, title=None, editLabeL=None, checkLabel=None, value=None):
        dialog = CheckAndEditDialog(parent)
        dialog.init(title, value, editLabeL, checkLabel)
        result = dialog.exec_()
        value = dialog.value()
        return (value, result == QtGui.QDialog.Accepted)



class ApplicationWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, ):
        super(ApplicationWindow, self).__init__()
        QtCore.QCoreApplication.setOrganizationName('IPP Garching')
        QtCore.QCoreApplication.setApplicationName('Langmuir Data Analyzer')
        QtCore.QCoreApplication.setOrganizationDomain('www.ipp.de')

        # Default configuration. Used when validation of config file fails
        self.defaultConfig = {}
        self.defaultConfig['Application'] = {
                'Dt': 15,
                'avgNum': 3,
                'colorScheme': 'gist_rainbow',
                'langmuirDiag': 'LSD',
                'strikelineDiag': 'FPG',
        }
        self.defaultConfig['Indicators'] = {
                'color': 'b',
        }
        self.defaultConfig['Plots'] = {
                'region': 'ua',
                'segment': '8',
                'dpi': 80,
        }
        self.defaultConfig['Plots']['Spatial'] = {
                'coloring': True,
                'defaultColor': 'b',
                'ignoreNans': True,
                'positionsFile': 'Position_pins_08-2015.txt',
        }
        self.defaultConfig['Plots']['Temporal'] = {
                'axTitles': {
                    'te': 'Temperature [eV]',
                    'ne': 'Density [1/m$^3]',
                }
        }
        self.defaultConfig['Plots']['Temporal']['Current'] = {
                'mapDir': '/afs/ipp/home/d/dacar/divertor/',
                'mapFile':
                '/afs/ipp/home/d/dacar/divertor/Configuration_32163_DAQ_28_IX_2015.txt',
                'mapDiag': 'LSC',
                'diag': 'LSF',
                'calibFile': './calibrations.txt',
        }

        # Read config file
        configFile = 'config.ini'
        validFile = 'validation.ini'
        
        if not os.path.isfile(validFile):
            validFile = None
        if os.path.isfile(configFile):
            self.loadConfig(configFile, validFile)
        else:
            self.createConfig(configFile, validFile)

        # Reference configuration for this class
        config = self.config['Application']

        # Configuration
        self.avgNum = config['avgNum']
        self.Dt = config['Dt']
        self.langdiag = config['langmuirDiag']
        self.sldiag = config['strikelineDiag']
        self.ELMdiag = config['ELMDiag']
        self.defaultExtension = config['defaultExtension'] 
        self.colorScheme= config['colorScheme']
        self.playIncrement = config['playIncrement']
        self.defaultFilter = '{} (*.{})'.format(self.defaultExtension[1:].upper(),
                                                self.defaultExtension[1:].lower())
        self.fitNum = 1000
        self.POIpositions = sorted(['-20','20','50'])
        self.CELMAexists = False
        self.plots = []
        self._stop = False
        self._playing = False
        self._record = False
        self.voltageNames = {
                'Vfl-Vrf': '8',
                'Vpos-Vfl': '1',
                'Vneg-Vpos': '2'}
        self.shotfiles = []
        self.stats = {}
        self.plotter = None

        # Set up UI
        self.setupUi(self)
        #splitter = QtGui.QSplitter()
        #splitter.addWidget(self.spatialDomain)
        #splitter.addWidget(self.temporalDomain)
        #layout = QtGui.QVBoxLayout()
        #layout.addWidget(splitter)
        #self.setLayout(layout)
        
        self.btnRecord.setVisible(False)
        self.btnRecordCELMA.setVisible(False)
        self.xTimeSlider.setTickPosition(QtGui.QSlider.NoTicks)
        self.POISlider = SchizoSlider(Qt.Qt.Horizontal)
        self.CELMAnavigationLayout.addWidget(self.POISlider)
        self.btnPlayCELMA.setVisible(False)
        self.POISlider.setRange(-100,100)
        self.POISlider.setLow(self.POIpositions[0])
        self.POISlider.setMiddle(self.POIpositions[1])
        self.POISlider.setHigh(self.POIpositions[2])
        self.btnCELMAupdate.setVisible(False)
        self.btnShotUpdate.setVisible(False)
        self.radioDistancesNoAveraging.setChecked(True)
        self.setWindowTitle('Langmuir Data Analyzer')
        self.insertLinks()
        self.journalLink = None

        # Logger
        logTextBox = QPlainTextEditLogger(self)
        #logTextBox.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s'))
        logging.getLogger().addHandler(logTextBox)
        self.setLoggerLevel()
        self.logLayout.addWidget(logTextBox.widget)

        # Shortcuts
        shortcut = QtGui.QShortcut(self)
        shortcut.setKey('Ctrl+P')
        shortcut.activated.connect(self.activatePan)

        shortcut = QtGui.QShortcut(self)
        shortcut.setKey('Ctrl+Z')
        shortcut.activated.connect(self.activateZoom)

        shortcut = QtGui.QShortcut(self)
        shortcut.setKey('Ctrl+R')
        shortcut.activated.connect(self.resetPlots)

        shortcut = QtGui.QShortcut(self)
        shortcut.setKey('Ctrl+Y')
        shortcut.activated.connect(self.toggleCELMAs)

        shortcut = QtGui.QShortcut(self)
        shortcut.setKey('Ctrl+U')
        shortcut.activated.connect(self.updateCELMAs)

        self.actionToLabel('Temporal Plot')
        self.actionToLabel('Spatial Plot')

        self.comboSwitchxPlot.insertItem(0, 'Ion saturation current density', ('jsat',))
        self.comboSwitchxPlot.insertItem(1, 'Electron density', ('ne',))
        self.comboSwitchxPlot.insertItem(2, 'Electron temperature', ('te',))

        self.multiplePOIs = self.menuSimultaneousCELMAs.isChecked()

        self.POIs = [0]
        self.POI_current_ind = 0
        self.ELMstart_current_ind = 0
        self.indicator_range = [None,None]

        # Set GUI options to what was read from config.ini
        self.menuFixxPlotyLim.setChecked(self.config['Plots']['Spatial']['fixyLim'])
        self.menuShowGaps.setChecked(self.config['Plots']['Temporal']['showGaps'])
        self.menuIgnoreNaNsSpatial.setChecked(self.config['Plots']['ignoreNans'])

        seg = self.config['Plots']['segment']
        reg = self.config['Plots']['region']
        self.addSegment(seg)
        self.addRegion(reg)

        # Resize columns to fit table width
        header = self.probeTable.horizontalHeader()
        for i in range(header.count()):
            header.setResizeMode(i, QtGui.QHeaderView.Stretch)

        # Prepare feature table
        self.stdFeatures = ['Ptot', 'nbar', 'Tdiv', 'impN',
                            'impNe', 'impAr', 'DWmhd', 'ELMdt',
                            'EED']
        self.tblFeatures.verticalHeader().hide()
        self.featurePicker = FeaturePicker(self.tblFeatures)
        self.featurePicker.addFeature('Shot', meta=True)
        self.featurePicker.addFeature('CELMA start', meta=True)
        self.featurePicker.addFeature('CELMA end', meta=True)
        self.featurePicker.addFeature('quantity', meta=True)
        for feat in self.stdFeatures:
            self.featurePicker.addFeature(feat, meta=True)

        # Add progress bar to the status bar
        self.progBar = QtGui.QProgressBar()
        self.progBar.setMinimum(0)
        self.progBar.setMaximum(100)
        self.progBar.setVisible(False)
        self.statusbar.addPermanentWidget(self.progBar)

        # Set general behavior of GUI
        self.shotNumberEdit = self.comboShotNumber.lineEdit()
        self.loadRecentShotNumbers()
        self.shotNumberEdit.returnPressed.connect(self.load)
        self.xTimeEdit.setMaxLength(7)
        self.shotNumberEdit.setMaxLength(5)
        self.shotNumberEdit.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        #self.menuRestoreShot.triggered.connect(self.loadShotsFromPickle)
        self.btnToggleSettings.clicked.connect(self.toggleMainSettings)
        self.menuSimultaneousCELMAs.triggered.connect(self.toggleMultiplePOIs)
        self.menuExit.triggered.connect(self.quit)
        self.menuAbout.triggered.connect(self.about)
        self.menuCELMApad.triggered.connect(self.changeCELMApad)
        self.menuExport.triggered.connect(self.saveSettings)
        self.menuImport.triggered.connect(self.restoreSettings)
        self.menuCELMAmarkerSpatial.triggered.connect(
                functools.partial(self.changeCELMAmarker, 'spatial'))
        self.menuCELMAmarkerTemporal.triggered.connect(
                functools.partial(self.changeCELMAmarker, 'temporal'))
        self.tabWidget.setCurrentIndex(0)
        self.comboExpInt.activated.connect(
                        functools.partial(self.addUser, self.comboExpInt))
        self.comboExpWmhd.activated.connect(
                        functools.partial(self.addUser, self.comboExpWmhd))
        self.comboExpRaw.activated.connect(
                        functools.partial(self.addUser, self.comboExpRaw))
        self.comboExpLSC.activated.connect(
                        functools.partial(self.addUser, self.comboExpLSC))
        self.comboExpELM.activated.connect(
                        functools.partial(self.addUser, self.comboExpELM))
        self.comboExpEqu.activated.connect(
                        functools.partial(self.addUser, self.comboExpEqu))
        self.comboLogLevel.currentIndexChanged.connect(self.setLoggerLevel)

        self.shotNumberEdit.setFocus()


    def loadRecentShotNumbers(self):
        dir = '.'
        fileName = 'recentShotnumbers.txt'
        filePath = os.path.join(dir,fileName)
        try:
            with open(filePath,'r') as f:
               lines = f.readlines()
        except IOError:
            return
        for line in lines:
            self.comboShotNumber.addItem(line)


    def saveShotNumberToRecents(self):
        dir = '.'
        fileName = 'recentShotnumbers.txt'
        filePath = os.path.join(dir,fileName)
        try:
            with open(filePath,'r') as f:
               lines = f.readlines()
        except IOError:
            with open(filePath,'w+') as f:
               lines = []

        shotnr = str(self.shotnr)
        lines = [line for line in lines if not line.startswith(shotnr)]
        lines = lines[:4]
        lines.insert(0, shotnr)

        with open(filePath,'w+') as f:
            for line in lines:
                line = line.rstrip('\n')
                f.write(line+'\n')
        

    def setLoggerLevel(self):
        level = str(self.comboLogLevel.currentText())
        
        if level == 'Debug':
            logging.getLogger().setLevel(logging.DEBUG)

        elif level == 'Info':
            logging.getLogger().setLevel(logging.INFO)

        elif level == 'Warning':
            logging.getLogger().setLevel(logging.WARN)

        elif level == 'Error':
            logging.getLogger().setLevel(logging.ERROR)

        elif level == 'Critical':
            logging.getLogger().setLevel(logging.CRITICAL)


    def insertLinks(self):
        """
        Adds links to info menu
        """
        isis = QtGui.QAction(self.menuInfo)
        isis.setText('ISIS')
        isis.triggered.connect(
                functools.partial(self.openLink,
                    'https://www.aug.ipp.mpg.de/cgibin/sfread_only/isis'))
        self.menuInfo.insertAction(self.menuAbout,isis)

        shotf = QtGui.QAction(self.menuInfo)
        shotf.setText( 'Shotfile system documentation')
        shotf.triggered.connect(
                functools.partial(self.openLink,
                    'https://www.aug.ipp.mpg.de/wwwaug/guidelines/shotfiles.shtml'))
        self.menuInfo.insertAction(self.menuAbout,shotf)

        libddww = QtGui.QAction(self.menuInfo)
        libddww.setText( 'libddww documentation')
        libddww.triggered.connect(
                functools.partial(self.openLink,
                    'https://www.aug.ipp.mpg.de/aug/manuals/pylibs/'))
        self.menuInfo.insertAction(self.menuAbout,libddww)


    def openLink(self, link):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(link))

    def changePlayIncrement(self):
        incr, ok = QtGui.QInputDialog.getInt(self,
                        "Play mode increment",
                        "Insert integer by which to increment the slider "+\
                        "value at each step when playing:")
        if ok:
            self.playIncrement = int(incr)


    def showCoordinates(self, plot, event):
        """
        Callback function that shows mouse pointer coordinates in statusbar.
        """
        if event.inaxes:
            x = event.xdata
            y = event.ydata
            if plot.CELMAexists and not plot._CELMAnormalize:
                x *= 1000
            if plot.CELMAexists and plot._CELMAnormalize:
                x *= 100
            msg = 'x = {:.4f} | y = {:.2e}'.format(x, y)
            logging.critical(msg)
            self.statusbar.showMessage(msg)
        else:
            self.statusbar.clearMessage()
                        

    def actionToLabel(self, text):
        action = self.findActionByText(text)
        if action is None:
            print "Could not find action {}".format(text)
            logging.warn("Could not find action {}".format(text))
            return
        action.setEnabled(False)
        font = QtGui.QFont()
        font.setBold(True)
        action.setFont(font)


    def toggleMainSettings(self):
        visible = self.widgetMainSettings.isVisible()
        if not visible:
            self.btnToggleSettings.setText('Hide Settings')
        else:
            self.btnToggleSettings.setText('Show Settings')
        self.widgetMainSettings.setVisible(not visible)


    def addSegment(self, seg):
        ind = self.comboSegment.findText(seg)
        if ind > -1:
            self.comboSegment.setCurrentIndex(ind)
        else:
            self.comboSegment.addItem(seg)
            self.comboSegment.setCurrentIndex(self.comboSegment.count())


    def addRegion(self, reg):
        ind = self.comboRegion.findText(reg)
        if ind > -1:
            self.comboRegion.setCurrentIndex(ind)
        else:
            self.comboRegion.addItem(reg)
            self.comboRegion.setCurrentIndex(self.comboRegion.count())


    def toggleFit(self, arg):
        print "Toggling fit"
        logging.info("Toggling fit")
        if self.menuFit.isChecked():
            self.insertFit()
        else:
            type = arg
            self.removeFit(type)


    def removeFit(self, type):
        for plot in self.plots:
            if plot.type == type:
                try:
                    plot.fit.remove()
                except:
                    pass
                plot.fit = None
                plot.fitting = False
        plot.canvas.draw()


    def insertFit(self, method=None):
        # Apparently, the current slider position gets passed by valueChanged.
        # Try to convert passed method to int. If thats possible, it is the
        # slider position and the method is actually None
        try:
            int(method)
        except:
            pass
        else:
            method = None

        if method is not None:
            for plot in self.getSpatialPlots():
                plot.fitMethod = method
                
        # This is necessary since insertFit gets called when slider is moved
        if not self.menuFit.isChecked():
            return
        
        for plot in self.getSpatialPlots():
            plot.fitting = True
            plot.plotFit(method=method)


    def setFitPoints(self):
        """
        Starts dialog to enter number of evaluation points for the spatial
        fits. Triggers update of spatial fits with the entered data.
        """
        n, ok = QtGui.QInputDialog.getInt(self,
                                'Insert number of evaluation points',
                                'Number of evaluation points:',
                                self.fitNum)
        if ok:
            self.fitNum = int(n)
            for plot in self.getSpatialPlots():
                plot.fitNum = int(n)
                if self.menuFit.isChecked():
                    plot.plotFit()


    def changeAvgMethod(self):
        currMethod = next((p.avgMethod for p in self.getTemporalPlots()), None)
        
        method, ok = QtGui.QInputDialog.getText(self, 
                "Change averaging method",
                "Insert numpy method to be used for the temporal CELMA fit",
                text = currMethod)
        if ok:
            for plot in self.getTemporalPlots():
                plot.avgMethod = str(method)
            self.showCELMAupdateButton()


    def setFitColor(self):
        dialog = QtGui.QColorDialog()
        dialog.setWindowState(dialog.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive)
        dialog.activateWindow()
        color = dialog.getColor()

        if not QColor.isValid(color):
            logging.error('Picked color is not valid')
            return

        # Conversion to matplotlib-compatible rgb value
        red = color.red()/255.
        blue = color.blue()/255.
        green = color.green()/255.
        rgb = (red,green,blue)

        for plot in self.getSpatialPlots():
            plot.fitColor = rgb
            try:
                plot.fit.set_color(rgb)
            except AttributeError, e:
                print "Could not set fit color to existing fit because "+\
                        "it probably doesn't exist:\n" + str(e) +\
                        "\nIt was saved for future fits though"
                logging.warn("Could not set fit color to existing fit because "+\
                        "it probably doesn't exist:\n" + str(e) +\
                        "\nIt was saved for future fits though")
            else:
                plot.canvas.draw()


    def changeMarker(self):
        currMarker = next((p.marker for p in self.getTemporalPlots()),None)
        marker, ok = CheckAndEditDialog.getValue(
                self,
                'Change data point marker',
                'Specify matplotlib marker (e.g. *, +, ^, ...):',
                'Show markers',
                currMarker
                )
        if ok:
            for plot in self.getTemporalPlots():
                plot.marker = marker
            self.updatetPlots()


    def changeBinNumber(self):
        currBinNumber = next((p.CELMAbinNumber for p in self.getTemporalPlots()),None)
        
        bins, ok = QtGui.QInputDialog.getInt(
                self,
                'Change alpha value',
                'Transparency of CELMA data points:',
                value = currBinNumber,
                min = 2, max = 10000
                )
        if ok:
            for plot in self.getTemporalPlots():
                plot.CELMAbinNumber = int(bins)
            self.showCELMAupdateButton()


    def changeProbeColor(self, patch, probeName):
        # Choose new color
        dialog = QtGui.QColorDialog()
        dialog.setWindowState(dialog.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive)
        dialog.activateWindow()
        color = dialog.getColor()
        if not QColor.isValid(color):
            return

        # Conversion to matplotlib-compatible rgb value
        red = color.red()/255.
        blue = color.blue()/255.
        green = color.green()/255.
        rgb = (red,green,blue)

        patch.setColor(color)
        for plot in self.plots:
            probe = next((p for p in plot.probes if p.name == probeName),None)
            probe.setColor(rgb)
            plot.updateColors()

        
    def changeAlpha(self):
        currAlpha = next((p.CELMAalpha for p in self.getTemporalPlots()),None)
        alpha, ok = QtGui.QInputDialog.getDouble(
                self,
                'Change alpha value',
                'Transparency of CELMA data points:',
                value = currAlpha,
                min = 0, max = 1
                )
        if ok:
            try:
                alpha = float(alpha)
            except:
                self.statusbar.showMessage(
                        'Alpha value must be a float between 0 and 1')
            else:
                for plot in self.getSpatialPlots():
                    plot.CELMAalpha = alpha
                    self.createSpatialCELMA()


    def getTimeArray(self, shot):
        timeArrays = []
        for obj in shot.getSignalNames():
            isRightQuantity = obj.startswith(('te','ne'))
            isRightRegime = obj.split('-')[1][:2]==\
                    str(self.comboRegion.currentText())

            if isRightQuantity and isRightRegime:
                try:
                    timeArrays.append(shot.getTimeBase(obj))
                except:
                    print "Failed to retrieve time base for signal", obj
                    logging.error("Failed to retrieve time base for signal {}"\
                                    .format(obj))
        if len(timeArrays) == 0:
            print "Failed to find time array"
            logging.error( "Failed to find time array")

        equal = (np.diff(
                    np.vstack(timeArrays).reshape(len(timeArrays), -1),
                    axis=0) == 0).all()

        if not equal:
            print "Warning: time base arrays fetched from shotfile are not"+\
            " equal! Proceed with caution."
            logging.error("Time base arrays fetched from shotfile are not"+\
            " equal! Proceed with caution.")
        return timeArrays[0]


    def moveToNextPOI(self, ):
        """
        Moves xTimeSlider to the next POI of the current ELM. If the last POI
        of this ELM is reached, nothing will happen when invoking this
        function. It is therefore not intended to jump from ELM to ELM. Use
        moveToNextELM() for this.
        """
        self.POI_current_ind = min(self.POI_current_ind + 1, len(self.POIs) - 1)
        POI = self.POIs[self.POI_current_ind]
        POI_realtime_ind = Conversion.valtoind(POI, self.dtime)
        self.xTimeSlider.setValue(POI_realtime_ind)
        
        self.updatexPlotText()


    def moveToPrevPOI(self, ):
        """
        Moves xTimeSlider to the previous POI of the current ELM. If the first
        POI of this ELM is reached, nothing will happen when invoking this 
        function. It is therefore not intended to jump from ELM to ELM. Use
        moveToPrevELM() for this.
        """
        self.POI_current_ind = max(self.POI_current_ind - 1, 0)
        POI = self.POIs[self.POI_current_ind]
        POI_realtime_ind = Conversion.valtoind(POI, self.dtime)
        self.xTimeSlider.setValue(POI_realtime_ind)
        
        self.updatexPlotText()


    def moveToNextELM(self, ):
        """ Moves xTimeSlider to the first POI of the next ELM."""
        self.ELMstart_current_ind = min(self.ELMstart_current_ind + 1, len(self.ELMonsets) - 1)
        self.snapSlider(self.ELMstart_current_ind, POI='first')
        

    def moveToPrevELM(self, ):
        """ Moves xTimeSlider to the first POI of the previous ELM."""
        self.ELMstart_current_ind = max(self.ELMstart_current_ind - 1, 0)
        self.snapSlider(self.ELMstart_current_ind, POI='first')


    def snapSlider(self, ELMind=None, POI=None):
        """ Makes Slider snap to the closest POI relative to the closest ELM. """
        # - Make slider snap to ELM phases:
        #       * Convert slider position to realtime
        #       * Look for index i of ELM beginning closest to realtime
        #       * Calculate points of interest:
        #           1) tbeg_ELM[i] - dt_ELM[i-1]*.1
        #           2) tgeb_ELM[i] + dt_ELM[i]*.3
        #           3) tbeg_ELM[i] + dt_ELM[i]*.9
        #       * Determine POI closest to realtime
        #       * Get index of time in time array closest to POI
        #       * Set slider to this index
        # 
        # GUI setting of slider snapping will only affect behavior when
        # dragging the slider. Clicking the ELM control buttons will still work
        # as expected
        snapping = self.menuSliderSnapping.isChecked()
        if ELMind == None:
            pos = self.xTimeSlider.value()
            realtime = self.dtime[pos]
            self.ELMstart_current_ind = Conversion.valtoind(realtime, self.ELMonsets)
        else:
            self.ELMstart_current_ind = ELMind
            realtime = self.ELMonsets[self.ELMstart_current_ind]

        self.POIs = self.getPOItimes(realtime)

        if snapping or ELMind is not None:
            if POI is not None:
                if POI == 'first':
                    self.POI_current_ind = 0
                elif POI == 'last':
                    self.POI_current_ind = -1
                else:
                    try:
                        self.POI_current_ind = int(POI)
                    except IndexError:
                        print "Error: No POI number {} available. Using first POI instead".format(POI)
                        logging.warn("No POI number {} available. Using first POI instead".format(POI))
                        self.POI_current_ind = 0
                    except ValueError:
                        print "Error: POI {} seems to be invalid".format(POI)
                        logging.warn("POI {} seems to be invalid".format(POI))
                        return
                    except:
                        print "Error: Cannot snap to unknown POI", POI
                        logging.warn("Cannot snap to unknown POI {}".format(POI))
                        return
            else:
                self.POI_current_ind = np.abs((self.POIs - realtime)).argmin()

            POI_realtime = self.POIs[self.POI_current_ind]
            POI_realtime_ind = Conversion.valtoind(POI_realtime, self.dtime)
            self.xTimeSlider.setValue(POI_realtime_ind)
            
            self.drawELMmarkers()

            self.updatexPlotText()


    def drawELMmarkers(self):
        """
        Draws markers for the current ELM. Marks points of interest relative to
        this ELM and the ELM duration
        """
        for plot in self.getTemporalPlots():
            ELMstart = self.ELMonsets[self.ELMstart_current_ind]
            ELMstop = self.ELMends[self.ELMstart_current_ind]

            if len(plot.ELMmarkers) == 0:
                plot.ELMmarkers['spans'] = []
                plot.ELMmarkers['lines'] = []
                color = 'g'
                
                # Draw marker fill at ELM position
                span = plot.axes.axvspan( ELMstart, ELMstop, alpha=0.6,
                        color=color, label='ELM')
                plot.ELMmarkers['spans'].append(span)
                        
                # Draw marker line at every POI
                for i, t in enumerate(self.POIs):
                    line = plot.axes.axvline( t, color=color, lw=3, ls='--',
                                            alpha=0.6, label='POI {}'.format(i))
                    plot.ELMmarkers['lines'].append(line)

                plot.canvas.draw()
                
            else:
                plot.axes.draw_artist(plot.axes.patch)
                # Update marker fill
                for span in plot.ELMmarkers['spans']:
                    xy = span.get_xy()
                    xy = [
                            [ELMstart,xy[0][1]],
                            [ELMstart,xy[1][1]],
                            [ELMstop ,xy[2][1]],
                            [ELMstop ,xy[3][1]],
                            #[ELMstop ,xy[4][1]]
                        ]

                    span.set_xy(xy)

                # Update marker lines
                for line, POI in zip(plot.ELMmarkers['lines'],self.POIs):
                    line.set_xdata(POI)

                for line in plot.axes.lines:
                    if line.get_visible():
                        plot.axes.draw_artist(line)

                for patch in plot.axes.patches:
                    if patch.get_visible():
                        plot.axes.draw_artist(patch)

                plot.canvas.update()
                plot.canvas.flush_events()


    def toggleRescaling(self):
        rescaling = self.menuAutoscaling.isChecked()
        for plot in self.plots:
            if plot.type == 'temporal':
                plot.rescaling = rescaling


    def readPOIs(self, multiplePOIs=False):
        POIs = []
        slider = self.POISlider
        if multiplePOIs:
            POIs.append(slider.low()/100.)
            POIs.append(slider.middle()/100.)
            POIs.append(slider.high()/100.)

        else:
            POIs.append(slider.middle()/100.)
            
        return POIs


    def getPOItimes(self, time, multiplePOIs=True, unit=None):
        """
        Returns the three POIs around the current time.
        Used to draw markers around the indicator
        """
        i = Conversion.valtoind(self.ELMonsets, time)
        POIs = self.readPOIs(multiplePOIs)

        times= []
        for POIrelative in POIs:
            # unit is None in case of slider snapping. In this case, the
            # POIs are always percentages
            if unit =='%' or unit is None:
                # If this is the very first ELM, pre-ELM POI is not defined
                if POIrelative < 0 and i==0:
                    continue
                # POI in realtime
                if POIrelative < 0:
                    times.append(self.ELMonsets[i] + self.ELMtoELM[i-1] * POIrelative)
                else:
                    times.append(self.ELMonsets[i] + self.ELMtoELM[i] * POIrelative)

            elif unit == "0.1 ms":
                times.append(self.ELMonsets[i] + POIrelative/100)
            
            # This will not return POIs that are directly set off by the amount
            # of ms specified by the user. Instead, the input is converted to
            # ms by interpreting the input as a percentage of the minimum ELM
            # duration in the specified range
            #elif unit == '0.1 ms':
            #    # The shortest ELM-to-ELM duration determines the maximum
            #    # offset in ms. POI therefore ranges between 0 and
            #    # minimumELMduration
            #    durationsInCELMAwindow = []
            #    for ton,dt in zip(self.ELMonsets, self.ELMtoELM):
            #        if ton >= self.CELMAphaseOn and ton+dt <= self.CELMAphaseEnd:
            #            if j < ELMnum:
            #                durationsInCELMAwindow.append(dt)
            #                j += 1
            #            else: break

            #    durations = self.ELMtoELM
            #    onsets = self.ELMonsets
            #    ends = self.ELMends
            #    start = self.CELMAphaseOn
            #    stop = self.CELMAphaseEnd
            #    array = np.ma.where(durations, (onsets >= start) & (ends <= stop))
            #    minimumELMduration = min(durationsInCELMAwindow)
            #    if list(array) == durationsInCELMAwindow:
            #        print "SUCCESS - arrays are the same"
            #    else:
            #        print "Arrays are not the same :("

            #    # Convert from percent to ms
            #    POIrelative = POIrelative*minimumELMduration
            #    # Convert to absolute time
            #    times.append(self.ELMonsets[i] + POIrelative)

        return times
        

    def loadConfig(self, f, specf=None):
        self.config = ConfigObj(f, configspec=specf)

        # Validate/convert settings
        val = Validator()
        succeeded = self.config.validate(val)
        
        if not succeeded:
            print "Warning: Config file validation failed. Using default values"
            logging.warning("Config file validation failed. Using default values")
            self.config = self.defaultConfig


    def createConfig(self, f, specf=None):
        """ 
        Creates cofiguration file using default values
        """
        self.config = ConfigObj(f, configspec=specf, create_empty=True)

        # Copy default values to config and save it to file
        for key, value in self.defaultConfig.iteritems():
            self.config[key] = value
        self.config.write()


    def addUser(self, combo, ind):
        if ind == combo.count()-1:
            user, ok = QtGui.QInputDialog.getText(self,
                    "Add new user", "Insert new user name:")
            if ok:
                self.comboExpInt.insertItem(ind,user) 
                self.comboExpWmhd.insertItem(ind,user) 
                self.comboExpRaw.insertItem(ind,user)
                self.comboExpLSC.insertItem(ind,user)
                self.comboExpELM.insertItem(ind,user)
                self.comboExpEqu.insertItem(ind,user)

                combo.setCurrentIndex(ind)


    def changeIgnoreSpatialNaNs(self):
        ignoreNans = self.menuIgnoreNaNsSpatial.isChecked()
        for plot in self.getSpatialPlots():
            plot.ignoreNans = ignoreNans
            ind = self.xTimeSlider.value()
            time = self.dtime[ind]
            plot.update(time)


    def savePlot(self, plot):
        print "Saving plot"
        type = plot.type
        quantity = plot.quantity

        if plot.CELMAexists:
            start = '{:.4f}'.format(float(self.editCELMAstartTime))
            end = '{:.4f}'.format(float(self.editCELMAendTime))
        else:
            start, end = plot.axes.get_xlim()
            start = '{:.4f}'.format(start)
            end = '{:.4f}'.format(end)

        if plot.CELMAexists:
            CELMAprobes = [p.name for p in plot.probes if p.CELMA]
        else:
            CELMAprobes = [p.name for p in plot.probes 
                           if p.isVisible(plot.canvas)]
        if len(CELMAprobes) > 1:
            probeName = 'multiple'
        elif len(CELMAprobes) == 1:
            probeName = probes[0]
        else:
            probeName = 'None'

        if self.cbCELMAnormalize.isChecked():
            mode = 'normalized'
        else:
            mode = 'default'

        syncedBy = 'syncedBy' + str(self.comboELMcompare.currentText())
        extension = '.svg'

        if plot.CELMAexists:
            fileName = '_'.join([type, quantity, 'CELMA', start, end, probeName,
                                mode, syncedBy])
        else:
            fileName = '_'.join([type, quantity, start, end, probeName, mode,
                                syncedBy])
        fileName += extension

        print "Saving to file", fileName

        dialog = QtGui.QFileDialog()
        dialog.setDefaultSuffix('svg')
        filePath = dialog.getSaveFileName(
                                    parent=self,
                                    caption="Save figure as",
                                    directory=os.path.join(plot.saveDir,fileName),
                                    filter="Portable Network Graphics (PNG) (*.png);;"+\
                                           "Encapsulated PostScript (EPS) (*.eps);;"+\
                                           "Scalable Vector Graphics (SVG) (*.svg)",
                                    selectedFilter='SVG (*.svg)')
        if filePath:
            filePath = str(filePath)
            _, fmt = os.path.splitext(filePath)
            plot.fig.savefig(filePath, format=fmt[1:])
            plot.saveDir = os.path.dirname(fileName)
            logging.info("{} {} plot saved to {}".format(
                                plot.type, plot.quantity, filePath))


    def setTimeText(self):
        """ Updates GUI time edit field based on scrollbar value """
        # GUI scrollbar provides timestep (index of time array)
        time = self.xTimeSlider.value()
        # Convert to realtime
        realtime = self.dtime[time]
        # Update line edit text
        self.xTimeEdit.setText("{:.6f}".format(realtime))


    def setxTimeSlider(self):
        """ Updates time scrollbar based on text in GUI time edit field"""
        self.slider = self.xTimeSlider

        # GUI line edit expects a real time value
        realtime = float(self.xTimeEdit.text())

        # Convert to corresponding timestep
        time = int(Conversion.valtoind(realtime, self.dtime))

        # If new slider position is out of slider range, set slider range start
        # to new slider position while retaining range size as long as it's not
        # exceeding available time values
        if not self.slider.minimum() < time < self.slider.maximum():
            dt = self.slider.maximum() - self.slider.minimum()
            self.slider.setMinimum(max(0, time))
            self.slider.setMaximum(min(self.slider.minimum() + dt,
                                        len(self.dtime)))

        # Update slider position
        self.slider.setValue(time)

        # Update line edit text with the time corresponding to the found timestep
        self.xTimeEdit.setText("{:.10f}".format(self.dtime[time]))


    #def setDurationText(self):
    #    """ Updates the shot duration in the info bar. """
    #    self.dynDurationLabel.setText("{:.3f}".format(self.dtime[-1]))


    def attributeColorsToProbes(self):
        # Attribute colors to probes
        logging.info("\nAttributing colors to probes")
        probeNames = []
        for plot in self.plots:
            probeNames.extend([p.name for p in plot.probes 
                                        if p.name not in probeNames])
        
        cm = plt.get_cmap(self.colorScheme)
        colors = cm(np.linspace(0, 1, len(probeNames)))

        for plot in self.plots:
            for probeName, color in zip(probeNames, colors):
                # Find probe with this name
                probe = next((p for p in plot.probes
                                if p.name == probeName), None)
                if probe is None:
                    logging.info("Probe {} does not exist in "
                                 .format(probeName) +
                                 "{} {} plot."
                                 .format(plot.type, plot.quantity))
                    continue
                # Allow for default color
                if probeName in self.defaultProbeColors:
                    probe.color = self.defaultProbeColors[probeName]
                    continue
                color = tuple(color)[:-1]
                probe.color = color
            plot.updateColors()
                
        for probeName, color in zip(probeNames, colors):
            # Do not overwrite default colors. Otherwise they cannot be applied
            # next time the plots are reloaded (see switchxPlot or toggleLSC)
            if probeName not in self.defaultProbeColors:
                self.probeColors[probeName] = color


    def clearPlots(self):
        """ Removes all plots from their containers and deletes them """
        for plot in self.plots:
            if plot.pertinent:
                self.clearPlotContainer(plot.container)
            del plot


    def load(self, reloaded=False):
        """ 
            Loads specified shot, updates all plots on the GUI and implements
            interactivity 
        """
        logging.info('Loading shot')
        QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        self.btnShotUpdate.setVisible(False)
        self.clearCELMAs()
        self.CELMAexists = False
        self.patches = {}
        self.probeColors = self.config['Application']['probeColors']
        try:
            self.probeColors = eval(self.probeColors)
        except SyntaxError:
            logging.info("No or invalid probe colors specified in config file: {}"\
                            .format(self.probeColors))
            self.probeColors = {}
        else:
            for probe, color in self.probeColors.iteritems():
                self.probeColors[probe] = [el/255. for el in color]
            logging.info("Colors loaded from config file:")
            logging.info(self.probeColors)
        # Save as default colors so they are not overwritten when reloading
        # plots (see attributeProbeColors)
        self.defaultProbeColors = self.probeColors
            
        self.ignoreELMs = []
        self.clearPlots()

        self.progBar.setVisible(True)
        self.region = str(self.comboRegion.currentText())

        success = self.getShot()

        if success:
            logging.info("+++++++++Data retrieval was successful+++++++++")
            print("Data retrieval was successful")
            self.plots = []

            quantity = self.getSpatialPlotQuantity()
            ok = self.createPlot(self.PlotContainer11,'spatial',quantity)
            if not ok:
                return
            self.progBar.setValue(60)
            ok = self.createPlot(self.PlotContainer21,'temporal','te')
            if not ok:
                return
            self.progBar.setValue(70)
            ok = self.createPlot(self.PlotContainer22,'temporal','ne')
            if not ok:
                return
            self.progBar.setValue(80)
            ok = self.createPlot(self.PlotContainer23,'temporal','jsat')
            if not ok:
                return
            self.progBar.setValue(100)

            self.attributeColorsToProbes()
            self.populateProbeList()

            # Synchronize temporal plots
            Sync.sync(*self.getTemporalPlots())

            # Update GUI appearance with current values
            self.updateTWindowControls(self.avgNum)

            # Load data used for statistics
            self.loadStatData()

            #Implement GUI logic
            if not reloaded:
                self.activateXtimeSlider()
                self.comboSwitchxPlot.currentIndexChanged.connect(self.switchxPlot)
                self.xTimeEdit.returnPressed.connect(self.setxTimeSlider)
                self.xTimeEdit.returnPressed.connect(self.updatexPlot)
                self.xTimeEdit.returnPressed.connect(self.updatexPlotText)
                self.xTimeEdit.returnPressed.connect(self.updatetPlotXlims)
                self.POISlider.sliderReleased.connect(self.snapSlider)

                self.spinTWidth.editingFinished.connect(self.updateTWindow)
                self.btnReset.clicked.connect(self.resetPlots)
                self.btnCELMA.clicked.connect(self.toggleCELMAs)

                self.POISlider.valueChanged.connect(self.showCELMAupdateButton)
                self.comboPOIunit.currentIndexChanged.connect(self.showCELMAupdateButton)
                self.cbTemporalCELMAs.stateChanged.connect(self.showCELMAupdateButton)
                self.comboELMcompare.currentIndexChanged.connect(self.showCELMAupdateButton)
                #self.comboCELMAmode.currentIndexChanged.connect(self.showCELMAupdateButton)
                self.cbCELMAnormalize.stateChanged.connect(self.showCELMAupdateButton)
                self.editCELMAELMnum.textChanged.connect(self.showCELMAupdateButton)
                self.editCELMAstartTime.textChanged.connect(self.showCELMAupdateButton)
                self.editCELMAendTime.textChanged.connect(self.showCELMAupdateButton)
                self.btnCELMAupdate.clicked.connect(self.updateCELMAs)


                self.shotNumberEdit.textChanged.connect(self.showShotUpdateButton)
                self.comboSegment.currentIndexChanged.connect(self.showShotUpdateButton)
                self.comboRegion.currentIndexChanged.connect(self.showShotUpdateButton)
                self.comboExpInt.currentIndexChanged.connect(self.showShotUpdateButton)
                self.comboExpRaw.currentIndexChanged.connect(self.showShotUpdateButton)
                self.comboExpEqu.currentIndexChanged.connect(self.showShotUpdateButton)
                self.comboExpELM.currentIndexChanged.connect(self.showShotUpdateButton)
                self.comboExpLSC.currentIndexChanged.connect(self.showShotUpdateButton)
                self.btnShotUpdate.clicked.connect(self.reload)

                self.menuLiveIndicators.triggered.connect(self.toggleLiveIndicators)
                self.menuSpatialAvgNum.triggered.connect(self.setSpatialAvgNum)
                self.menuTemporalAvgNum.triggered.connect(self.setTemporalAvgNum)
                self.menuWindowWidth.triggered.connect(self.setWindowWidth)
                self.menuFixxPlotyLim.toggled.connect(self.changeFixxPlotyLim)
                self.menuIgnoreNaNsSpatial.toggled.connect(self.changeIgnoreSpatialNaNs)
                self.menuShowGaps.triggered.connect(self.updatetPlots)
                self.menuSetAvgMethod.triggered.connect(self.changeAvgMethod)

                self.menuSaveSpatialFigures.triggered.connect(self.savexPlot)
                self.menuSaveTemporalFigures.triggered.connect(
                        functools.partial(self.collectiveSave, 'temporal'))
                self.menuSaveAllFigures.triggered.connect(
                        functools.partial(self.collectiveSave, 'all'))
                self.menuSaveSpatialData.triggered.connect(self.saveSpatialData)

                self.menuSetTransparency.triggered.connect(self.changeAlpha)
                self.menuBinNumber.triggered.connect(self.changeBinNumber)
                self.menuChangeMarkers.triggered.connect(self.changeMarker)
                self.menuUseLSC.triggered.connect(self.toggleLSC)
                self.menuAutoscaling.triggered.connect(self.toggleRescaling)
                self.menuFitEvaluationPoints.triggered.connect(self.setFitPoints)
                self.menuFitColor.triggered.connect(self.setFitColor)
                self.menuDetachedFit.triggered.connect(self.changeFitDetachment)
                self.menuFit.triggered.connect(
                        functools.partial(self.toggleFit, 'spatial'))
                self.menuFitMethodEich.triggered.connect(
                        functools.partial(self.insertFit, 'Eich'))
                self.menuFitMethodLinear.triggered.connect(
                        functools.partial(self.insertFit, 'linear'))
                self.menuFitMethodSzero.triggered.connect(
                        functools.partial(self.insertFit, 'zero'))
                self.menuFitMethodNearest.triggered.connect(
                        functools.partial(self.insertFit, 'nearest'))
                self.menuFitMethodSlinear.triggered.connect(
                        functools.partial(self.insertFit, 'slinear'))
                self.menuFitMethodScubic.triggered.connect(
                        functools.partial(self.insertFit, 'cubic'))
                self.menuFitMethodSquadratic.triggered.connect(
                        functools.partial(self.insertFit, 'quadratic'))

                self.btnNextPOI.clicked.connect(self.moveToNextPOI)
                self.btnPrevPOI.clicked.connect(self.moveToPrevPOI)
                self.btnNextELM.clicked.connect(self.moveToNextELM)
                self.btnPrevELM.clicked.connect(self.moveToPrevELM)
                
                self.btnPlayCELMA.clicked.connect(self.playCELMA)
                self.btnPlay.clicked.connect(self.play)
                self.btnRecord.clicked.connect(self.record)
                self.btnRecordCELMA.clicked.connect(self.record)
                self.menuPlayStart.triggered.connect(self.play)
                self.menuStop.triggered.connect(self.stop)
                self.menuSetIncrement.triggered.connect(self.changePlayIncrement)
                
                self.menuShowAverages.triggered.connect(
                        functools.partial(self.changeCELMAsetting, 'spatial',
                            'showCELMAavg', self.menuShowAverages))
                self.menuMarkPOIsInTemporal.triggered.connect(self.showCELMAupdateButton)
                self.menuSimultaneousCELMAs.triggered.connect(self.showCELMAupdateButton)
                self.menuEnableBinning.triggered.connect(self.showCELMAupdateButton)

                self.btnPan.clicked.connect(self.activatePan)
                self.btnZoom.clicked.connect(self.activateZoom)

                self.btnFindMaximaDistances.clicked.connect(self.plotMaximaDistances)
                self.btnWmhd.clicked.connect(self.showWmhd)
                #self.btnTdivNbar.clicked.connect(self.createTNplot)

                self.btnFeatAddRow.clicked.connect(self.addFeatureRow)
                self.btnFeatAdd.clicked.connect(
                    self.featurePicker.addFeature)
                self.btnFeatClearTbl.clicked.connect(
                    self.featurePicker.clearTable)
                self.btnFeatSaveTbl.clicked.connect(
                    self.featurePicker.saveTable)
                self.btnFeatLoadTbl.clicked.connect(
                    self.featurePicker.loadTable)
                self.btnFeatRemoveRow.clicked.connect(
                    self.featurePicker.removeRow)
                self.btnFeatRemoveCol.clicked.connect(
                    self.featurePicker.removeColumn)
                self.btnFeatPlot.clicked.connect(
                    self.plotFeatures)

            self.statusbar.showMessage('Shot was fully loaded', 5000)
            logging.info( "\n\n+++++++++++++++++ ALL DONE! ++++++++++++++++++\n\n")
            print "\n\n+++++++++++++++++ ALL DONE! ++++++++++++++++++\n\n"

            self.toggleMainSettings()
            self.activateZoom()
            self.insertJournalLink()

        # If shot data was not loaded successfully, unbind actions and flush
        # afs cache to try and fix if something is broken
        else:
            self.checkAFSToken()
            logging.info('Flushing AFS cache')
            print('Flushing AFS cache')
            Tools.shellExecute(['fs', 'checkvolumes'])
            Tools.shellExecute(['fs', 'flush'])
            Tools.shellExecute(['fs', 'flushvolume', '-p', '/afs'])
            sys.exc_clear()
            gc.collect()
            try: 
                self.comboSwitchxPlot.disconnect()
                self.xTimeSlider.disconnect()
                self.xTimeEdit.disconnect()
            except Exception: pass

        QtGui.QApplication.restoreOverrideCursor()
        self.hideProgress()


    def addFeatureRow(self):
        settings = self.getCELMAsettings()
        if settings is None:
            return
        start, end, _ = settings
        picker = self.featurePicker
        picker.addRow()
        picker.setFeatureValue('Shot', self.shotnr)
        picker.setFeatureValue('CELMA start', start)
        picker.setFeatureValue('CELMA end', end)
        print(self.stats)
        for feat in self.stdFeatures:
            picker.setFeatureValue(feat, self.stats[feat])

    def plotFeatures(self):
        if self.plotter is None:
            self.plotter = Plotter(self.tblFeatures)
            self.plotter.delete.connect(self.removePlotter)
        self.plotter.plot()

    def removePlotter(self):
        self.plotter = None

    def checkAFSToken(self):
        res, err = Tools.shellExecute('tokens')
        token = False
        if err is not None:
            logging.error('Could not fetch AFS token list')
            return token

        if 'Tokens for afs' in res:
            logging.info('AFS token exists')
            token = True
        else:
            logging.critical('No AFS token')
            prompt = 'No AFS token found. Get one here:'
            pipe = subprocess.PIPE

            cmd = ('bash -c '
                   'read -p "Kerberos ID: " ID && kinit $ID;'
                   'aklog -noprdb;'
                   'LIST=$(klist);'
                   'case "$LIST" in'
                   '     *afs*) echo Token obtained!'
                   '     ;;'
                   '     *) echo Something went wrong. No token generated.'
                   '     ;;'
                   'esac;'
                   'read')

            program = ['xterm',
                       '-geometry', '100x30',
                       '-e', cmd]

            kinitProc = subprocess.Popen(program, stdout=pipe)
            token = True
        return token


    def insertJournalLink(self):
        if self.journalLink is not None:
            self.menuInfo.removeAction(self.journalLink)
            
        journal = QtGui.QAction(self.menuInfo)
        journal.setText('AUG journal entry for shot ' + str(self.shotnr))
        journal.triggered.connect(
                functools.partial(self.openLink,
                    'https://www.aug.ipp.mpg.de/cgibin/local_or_pass/journal.cgi?shot='+str(self.shotnr)))
        self.menuInfo.insertAction(self.menuAbout,journal)
        self.journalLink = journal


    def createTNplot(self):
        popout = FigureWindow()


    def changeFixxPlotyLim(self):
        fix = self.menuFixxPlotyLim.isChecked()
        for plot in self.getSpatialPlots():
            plot.fixyLim = fix
            

    def changeCELMAsetting(self, type, attr, cb):
        """
        Callback function for handling changes in toggleable CELMA settings.
        Sets the according plot attributes and shows the update button if there
        is a CELMA.
        """
        for plot in self.getPlotsByType(type):
            attr = getattr(plot,attr) 
            attr = cb.isChecked()
        self.showCELMAupdateButton()


    def reload(self):
        #_colors = self.probeColors
        _tmin = self.editCELMAstartTime.text()
        _tmax = self.editCELMAendTime.text()
        _celma= self.CELMAexists

        self.load(reload=True)

        #self.updateColors(_colors)

        self.editCELMAstartTime.setText(_tmin)
        self.editCELMAendTime.setText(_tmax)
        
        try:
            _tmin = float(_tmin)
            _tmax = float(_tmax)
        except ValueError:
            pass
        else:
            for plot in self.getTemporalPlots():
                plot.axes.set_xlim((_tmin,_tmax), emit=False)

        if _celma:
            self.toggleCELMAs()


    # Extremely slow and does not work nor fail
    #def updateColors(self, colors):
    #    print "Reinstating probe colors"
    #    for plot in self.plots:
    #        for probe in plot.probes:
    #            if probe.name in colors:
    #                print "Color for probe {}: {}"\
    #                        .format(probe.name, colors[probe.name])
    #                color = colors[probe.name]
    #                probe.color = color
    #                self.patches[probe.name].setColor(color,'mpl')
    #        
    #            plot.updateColors()


    def showShotUpdateButton(self):
        self.btnShotUpdate.setVisible(True)

    
    def getProbeVoltages(self):
        shot = self.LSFshot
        map = self.getVoltageMapping()
        data = {}
        time = {}
        for objName in shot.getObjectNames().values():
            if objName.startswith('CH'):
                for probe, (channel, ind) in map.iteritems():
                    if channel == objName:
                        try:
                            data[probe] = shot(channel).data[ind]
                            time[probe] = shot(channel).time
                        except TypeError, e:
                            print "Could not retrieve voltage data for probe {}".format(probe)+\
                                    " @channel {} ({}), {} ({}): {}".format(channel,
                                            type(channel), ind, type(ind),
                                            str(e))
                            logging.warn("Could not retrieve voltage data for probe {}".format(probe)+\
                                    " @channel {} ({}), {} ({}): {}".format(channel,
                                            type(channel), ind, type(ind),
                                            str(e)))
        return time, data


    def getVoltageMapping(self):
        shot = self.LSCshot
        map = []
        for vname,i in self.voltageNames.iteritems():
            signalName = 'ZSV' + i
            for obj in shot.getObjectNames().values():
                if obj.startswith(self.region):
                    probe = obj
                    data = shot(obj)[signalName].data 
                    info = ''.join([el for el in data if el.split() != []])
                    try:
                        channel, ind = info.split('_')
                    except:
                        logging.warn("Could not retrieve LSC data for probe {}".format(probe))
                    else:
                        # Actual LSC data starts with 'ch' while shotfile object
                        # names start with 'CH'.
                        channel = 'CH' + channel[2:]
                        # Indices are saved as numbers 1-6 but must serve as
                        # indexes 0-5
                        ind = int(ind) - 1
                        map[probe] = (channel, ind)
        return map



    def showCELMAupdateButton(self):
        if self.CELMAexists:
            self.btnCELMAupdate.setVisible(True)


    def activateXtimeSlider(self):
        self.xTimeSlider.valueChanged.connect(self.updatexPlot)
        self.xTimeSlider.valueChanged.connect(self.setTimeText)
        self.xTimeSlider.valueChanged.connect(self.insertFit)
        self.xTimeSlider.sliderReleased.connect(self.updatexPlotText)
        self.xTimeSlider.sliderReleased.connect(self.snapSlider)
        if self.menuLiveIndicators.isChecked():
            self.xTimeSlider.valueChanged.connect(self.updateIndicators)


    def deactivateXtimeSlider(self):
        try:
            self.xTimeSlider.valueChanged.disconnect()
            self.xTimeSlider.sliderReleased.disconnect()
        except TypeError:
            logging.error("Time slider could not be disconnected from slots")
            pass


    def getSpatialPlotQuantity(self):
        combo = self.comboSwitchxPlot
        quantity = combo.itemData(combo.currentIndex()).toPyObject()[0] 

        return quantity


    def switchxPlot(self):
        # If there is more than one spatial plot,
        # this will choose the container of the one first created
        container = next((p.container for p in self.getSpatialPlots()),None)
        quantity = self.getSpatialPlotQuantity()

        for plot in self.getSpatialPlots():
            #plot.reset()
            plot.clearCELMA()
            del plot

        self.createPlot(container, 'spatial', quantity)
        self.attributeColorsToProbes()
        self.populateProbeList()


    def toggleLSC(self):
        for plot in self.plots:
            if isinstance(plot, CurrentPlot):
                plot.calib = {}
                plot.map = {}
                #plot.reset()

                pos = self.xTimeSlider.value()
                realtime = self.dtime[pos]
                plot.fitting = self.menuFit.isChecked()
                plot.init(realtime, self.Dt)

        self.attributeColorsToProbes()
        self.populateProbeList()


    def createSpatialCELMA(self):
        settings = self.getCELMAsettings()
        if settings is None:
            logging.warn("Error getting CELMA settings")
            print "Error getting CELMA settings"
            return

        multiplePOIs = self.multiplePOIs
        createtCELMAs = self.cbTemporalCELMAs.isChecked()
        markPOIsInTemporal = self.menuMarkPOIsInTemporal.isChecked()
        unit = str(self.comboPOIunit.currentText())
        #mode = str(self.comboCELMAmode.currentText())
        normalize = self.cbCELMAnormalize.isChecked()
        fitting = self.menuFit.isChecked()

        markers = ['d','o','^']
        colors = ['r','b','g']

        POIsRel = self.readPOIs(multiplePOIs)
        if unit == '0.1 ms':
            POIsRel = [POI/100 for POI in POIsRel]

        handles = []
        labels = []
        for plot in self.getSpatialPlots():
            plot.hideArtists()
            i=0
            for POIrelative, marker, color in zip(POIsRel, markers, colors):
                result = plot.coherentELMaveraging(
                                 *settings,
                                 POIrelative = POIrelative,
                                 range = self.Dt,
                                 multiplePOIs = multiplePOIs,
                                 unit = unit,
                                 marker = marker,
                                 fitting = fitting,
                                 color = color,
                                 ignore = self.ignoreELMs)
                if result is None:
                    continue
                h, l, POIs, POIsShifted = result
                handles.append(h)
                labels.append(l)
                if markPOIsInTemporal:
                    if createtCELMAs:
                        if normalize:
                            self.markPOIsInTemporalPlots([POIrelative],color)
                        else:
                            self.markPOIsInTemporalPlots(POIsShifted,color)
                    else:
                        self.markPOIsInTemporalPlots(POIs,color)
                i+=1

            if i > 0:
                plot.CELMAexists = True
            else:
                print "WARNING: Could not create any CELMAs for spatial plot"
                logging.error("Could not create any CELMAs for spatial plot")


    def toggleIgnoreELM(self, time, cb):
        if cb.isChecked():
            self.removeIgnoreELM(time)
        else:
            self.addIgnoreELM(time)
        self.btnCELMAupdate.setVisible(True)


    def removeIgnoreELM(self, time):
        try:
            ind = self.ignoreELMs.index(time)
        except ValueError:
            return
        del self.ignoreELMs[ind]
            

    def addIgnoreELM(self, time):
        self.ignoreELMs.append(time)


    def populateELMtable(self, event=None):
        table = self.tblELMs
        labels = ('Show','Start','Duration [ms]', 
                  'Next ELM after [ms]', 'Frequency [kHz]')
        table.setRowCount(0)
        table.setColumnCount(len(labels))
        table.setSortingEnabled(False)

        table.setHorizontalHeaderLabels(labels)
        header = table.horizontalHeader()
        for i in range(len(labels) - 1):
            header.setResizeMode(i, QtGui.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)

        settings = self.getCELMAsettings()
        if settings is None:
            logging.warn("CELMA settings could not be read")
            print "Error: CELMA settings could not be read"
            return
        start, end, ELMnum = settings
        ind = np.where((start <= self.ELMonsets) & (self.ELMonsets <= end))
        if len(ind[0]) == 0:
            print "ERROR: No ELMs in specified range {}s-{}s".format(start,end)
            logging.critical("No ELMs in specified range {}s-{}s".format(start,end))
            return
        ind_select = np.where((start <= self.ELMonsets) & (self.ELMonsets <= end))
        ELMstarts= self.ELMonsets[ind][:ELMnum]
        ELMends = self.ELMends[ind][:ELMnum]
        ELMdt = ELMends - ELMstarts
        ELMtoELM = self.ELMtoELM[ind][:ELMnum]
        ELMfreqs = self.ELMfreqs[ind][:ELMnum]

        for i, (ton, dt, Dt, f) in enumerate(zip(ELMstarts, ELMdt, 
                                                 ELMtoELM, ELMfreqs)):
            rowPos = table.rowCount()
            table.insertRow(rowPos)
            item = QtGui.QTableWidgetItem('ELM {}'.format(i + 1))
            table.setVerticalHeaderItem(rowPos, item)

            cb = QtGui.QCheckBox()
            cb.setTristate(False)
            if ton not in self.ignoreELMs:
                cb.setChecked(True)
            cb.stateChanged.connect(
                    functools.partial(self.toggleIgnoreELM, ton, cb))
            cb.stateChanged.connect(self.showELMstatistics)
            table.setCellWidget(rowPos, 0, cb)

            item = QtGui.QTableWidgetItem()
            data = QtCore.QVariant('{:.5f}'.format(ton))
            item.setData(QtCore.Qt.EditRole, data)
            table.setItem(rowPos, 1, item)
            
            item = QtGui.QTableWidgetItem()
            data = QtCore.QVariant('{:.2f}'.format(dt * 1000))
            item.setData(QtCore.Qt.EditRole, data)
            table.setItem(rowPos, 2, item)

            item = QtGui.QTableWidgetItem()
            data = QtCore.QVariant('{:.2f}'.format(Dt * 1000))
            item.setData(QtCore.Qt.EditRole, data)
            table.setItem(rowPos, 3, item)

            item = QtGui.QTableWidgetItem()
            data = QtCore.QVariant('{:.2f}'.format(f))
            item.setData(QtCore.Qt.EditRole, data)
            table.setItem(rowPos, 4, item)

        table.setSortingEnabled(True)


    def loadStatData(self):
        # Heating
        shot = dd.shotfile('TOT', self.shotnr)
        heating = shot('P_TOT')

        # Line-averaged density
        shot = dd.shotfile('DCN', self.shotnr)
        lineDens = shot('H-1')

        # Tdiv
        shot = dd.shotfile('DDS', self.shotnr)
        Tdiv = shot('Tdiv')

        # N impurity density
        #shot = dd.shotfile('', self.shotnr)
        impN = 0

        # Ne impurity density
        #shot = dd.shotfile('', self.shotnr)
        impNe = 0

        # Ar impurity density
        #shot = dd.shotfile('', self.shotnr)
        impAr = 0

        self.statData = {self.lblStatN: [impN, 10**19, 'impN'],
                         self.lblStatNe: [impNe, 10**19, 'impNe'],
                         self.lblStatAr: [impAr, 10**19, 'impAr'],
                         self.lblStatTdiv: [Tdiv, 1, 'Tdiv'],
                         self.lblStatDens: [lineDens, 10**19, 'nbar'],
                         self.lblStatHeating: [heating, 10**6, 'Ptot']}


    def showStats(self, event=None):
        def getAverage(data, time, start, end):
            ind = np.where((start <= time) & (time <= end))
            avg = np.nanmean(data[ind])
            return avg
        
        try:
            start = float(self.editCELMAstartTime.text())
            end = float(self.editCELMAendTime.text())
        except ValueError:
            return

        for lbl, (obj, cal, name) in self.statData.items():
            try:
                data = obj.data
                time = obj.time
            except AttributeError:
                avg = 'N/A'
            else:
                avg = getAverage(data, time, start, end) / cal
                avg = '{:.2f}'.format(avg)
            lbl.setText(avg)
            self.stats[name] = avg


    def showELMstatistics(self, event=None):
        settings = self.getCELMAsettings()
        if settings is None:
            logging.warn("CELMA settings could not be read")
            print "Error: CELMA settings could not be read"
            return
        start, end, ELMnum = settings
 
        ind = np.where((start <= self.ELMonsets) & (self.ELMonsets <= end))
        ind_selected = np.where((start <= self.ELMonsets) &
                                (self.ELMonsets <= end) &
                                ~np.in1d(self.ELMonsets, self.ignoreELMs))
        if len(ind[0]) == 0:
            logging.debug("No ELMs in range")
            self.lblELMsInRange.setText('N/A')

        if len(ind_selected[0]) == 0:
            logging.debug("No ELMs selected")
            self.lblELMnum.setText('N/A')
            self.lblELMfreq.setText('N/A')
            self.lblELMdur.setText('N/A')
            self.lblELMdur_2.setText('N/A')
            self.lblELMmin.setText('N/A')
            self.lblELMmax.setText('N/A')
            self.lblELMENER.setText('N/A')
            self.lblELMelec.setText('N/A')
            return

        ELMstarts = self.ELMonsets[ind_selected][:ELMnum]
        ELMends = self.ELMends[ind_selected][:ELMnum]
        ELMdt = ELMends - ELMstarts
        ELMtoELM = self.ELMtoELM[ind_selected][:ELMnum]
        ELMfreqs = self.ELMfreqs[ind_selected][:ELMnum]
        ELMENER = self.ELMENER[ind_selected][:ELMnum]
        ELMELEC = self.ELMelec[ind_selected][:ELMnum]
        preELMWmhd = self.preELMWmhd[ind_selected][:ELMnum]
        preELMelec = self.preELMelec[ind_selected][:ELMnum]

        self.stats['DWmhd'] = np.mean(ELMENER)
        self.stats['ELMdt'] = np.mean(ELMdt)
        self.stats['EED'] = np.mean(ELMtoELM)

        self.lblELMsInRange.setText(str(len(ind[0])))
        self.lblELMnum.setText(str(len(ELMstarts)))
        self.lblELMfreq.setText(u'{:.2f} \u00B1 {:.2f}'
                                .format(np.mean(ELMfreqs),
                                        np.std(ELMfreqs)))
        self.lblELMdur_2.setText(u'{:.2f} \u00B1 {:.2f}'
                                 .format(np.mean(ELMdt) * 1000,
                                         np.std(ELMdt) * 1000))
        self.lblELMdur.setText(u'{:.2f} \u00B1 {:.2f}'
                               .format(np.mean(ELMtoELM) * 1000,
                                       np.std(ELMtoELM) * 1000))
        self.lblELMmin.setText('{:.2f}'.format(np.min(ELMtoELM) * 1000))
        self.lblELMmax.setText('{:.2f}'.format(np.max(ELMtoELM) * 1000))
        self.lblELMENER.setText('{:.2e} ({:.1f}%)'
                                .format(np.mean(ELMENER),
                                        np.mean(ELMENER / preELMWmhd) * 100))
        self.lblELMelec.setText('{:.2e} ({:.1f}%)'
                                .format(np.mean(ELMELEC),
                                        np.mean(ELMELEC / preELMelec) * 100))

    
    def markPOIsInTemporalPlots(self, POIs, color=None):
        """
        Marks all POIs in all temporal plots
        """
        # If not simultaneous, use color red for markers
        if color is None:
            color = 'r'

        unit = self.comboPOIunit.currentText()
        
        for _plot in self.getTemporalPlots():
            for i, POI in enumerate(POIs):
                j = i/3 + 1
                line = _plot.axes.axvline( POI, color=color, alpha=0.5, lw=3,
                        ls='-.', label='POI {} of ELM {}'.format(i,j),
                        picker=True)
                _plot.POImarkers.append(line)
            _plot.canvas.draw()
    

    def updateRange(self, axes):
        """
        Updates slider range and CELMA start and stop times as temporal plot
        axes limits change. If any temporal CELMA exists, the xlimits cannot
        necessarily be easily translated to realtimes anymore. The function
        checks for this condition and leaves slider and CELMA times alone if
        there is a spatial CELMA
        """
        tCELMAexists = any(p.CELMAexists for p in self.getTemporalPlots())
        if tCELMAexists:
            return
        limits = axes.get_xlim()

        self.setSliderRange(limits)

        self.editCELMAstartTime.setText("{:.6f}".format(limits[0]))
        self.editCELMAendTime.setText("{:.6f}".format(limits[1]))
        

    def setSliderRange(self, limits):
        """ Sets the time slider range corresponding to the time range in the temporal plot. """
        # Set time slider range to range shown in zoomed temporal plot
        minTime = limits[0]
        maxTime = limits[1]
        try:
            self.xTimeSlider.valueChanged.disconnect(self.updatexPlot)
        except:
            pass
        self.xTimeSlider.setMinimum(Conversion.valtoind(minTime, self.dtime))
        self.xTimeSlider.setMaximum(Conversion.valtoind(maxTime, self.dtime))
        self.xTimeSlider.valueChanged.connect(self.updatexPlot)


    def toggleLiveIndicators(self):
        enableLive = self.menuLiveIndicators.isChecked()
        if enableLive:
            self.xTimeSlider.valueChanged.connect(self.updateIndicators)
        else:
            try:
                self.xTimeSlider.valueChanged.disconnect(self.updateIndicators)
            except Exception, e:
                logging.error("Could not disable live indicator updates:")
                logging.error(str(e))


    def saveSpatialData(self):
        for p in self.plots:
            if p.type == 'spatial':
                p.saveData()


    def updatetPlots(self):
        """ Updates all temporal plots """
        for plot in self.plots:
            if plot.type == 'temporal':
                plot.showGaps = self.menuShowGaps.isChecked()
                plot.update()


    def updatetPlotXlims(self):
        """ Updates xlims of the temporal plots if the time value entered is
        not within the current xlims """
        time = float(self.xTimeEdit.text())

        # get current x-axis limits of any temporal plot
        # TO DO: MAKE INDEPENDENT OF TEMPORAL PLOTS
        # ONLY MAKES SENSE IF ALL PLOTS ARE SYNCHED
        for plot in self.plots:
            if plot.type == 'temporal':
                currxmin, currxmax = plot.axes.get_xlim()
                dt = currxmax - currxmin

                if not currxmin < time < currxmax:
                    newxmin = max(0, time)
                    newxmax = min(time + dt, self.dtime[-1])
                    plot.axes.set_xlim(newxmin, newxmax)


    def updatexPlotText(self):
        return
        for p in self.plots:
            if hasattr(p, 'updateText'):
                p.updateText()


    def setWindowWidth(self):
        width, ok = QtGui.QInputDialog.getInt(self, 
                'Set window width for spatial plot', 
                'Time window around current time from which ' + \
                'data is to be taken for the spatial plot:',
                value= self.Dt, min=0)

        if ok:
            self.Dt = width
            self.updateTWindowControls(self.avgNum)
            self.updateTWindow()
        else:
            self.statusbar.showMessage('Window width not valid', 3000)


    def setTemporalAvgNum(self):
        currAvgNum = next((p.avgNum for p in self.plots 
                                        if p.type=='temporal'),None)

        avgNum, ok = QtGui.QInputDialog.getInt(self, 
                'Averaging spatial plot', 
                'Number of data points to average to one ' +\
                    'scatter plot point:\n\navgNum = ', 
                value= currAvgNum, min=0)

        if ok:
            for p in self.plots:
                if p.type == 'temporal':
                    p.updateAveraging(avgNum)


    def setSpatialAvgNum(self):
        currAvgNum = next((p.avgNum for p in self.plots 
                                        if p.type=='spatial'),None)

        avgNum, ok = QtGui.QInputDialog.getInt(self, 
                'Averaging spatial plot', 
                'Number of data points to average to one ' +\
                    'scatter plot point:\n\navgNum = ', 
                value= currAvgNum, min=0)

        if ok and avgNum % 2 != 0:
            for p in self.plots:
                if p.type == 'spatial':
                    p.avgNum = avgNum
        else:
            msg = "avgNum must be an odd number. " +\
                  "Choosing {} instead.".format(avgNum+1)
            logging.warning(msg)
            self.statusbar.showMessage(msg, 4000)
            avgNum += 1

        self.updateTWindowControls(avgNum)
        self.updateTWindow(avgNum)


    def updateTWindowControls(self, avgNum):
        """ Updates time window controls with current value of avgNum (number of data point to average over). """
        # SpinBox
        self.spinTWidth.setRange(avgNum, avgNum + 100)
        self.spinTWidth.setSingleStep(avgNum)
        self.spinTWidth.setValue(self.Dt)

        # Real time label
        if not None in self.indicator_range:
            dt = abs(self.indicator_range[1] - self.indicator_range[0])
        else:
            dt = 0
        self.lblRealTWidth.setText("= {:.1f}us".format(dt*10**6))


    def updateIndicators(self, event=None):
        """ Updates all indicators. """
        # Block indicator update when panning to greatly enhance
        # performance. If this is not done, indicator.slide() will call
        # canvas.update() each time it hits the xlimits additionally to
        # the under-the-hood panning
        panning = next((True for p in self.plots if hasattr(p.axes,'_pan_start')), False)

        if hasattr(event, 'x'):
            pass
        
        for plot in self.plots:
            if plot.type == 'temporal':
                if not panning:
                    # See below
                    #try:
                    #    plot.canvas.mpl_disconnect(self._indicID)
                    #except: pass
                    pos = self.xTimeSlider.value()
                    range = self.indicator_range
                    time = self.dtime[pos]
                    plot.indicator.slide(time, range)
                # If this is really wished, it must be implemented for
                # updatexPlot to so the indicator position corresponds to the
                # spatial profile
                # Not doing this has the advantage of being able to browse the
                # time evolution without losing the current indicator position
                # and spatial profile
                #else:
                #    # Remember the indicators should be updated and fire the
                #    # update at mouse button release
                #    self._indicID = plot.canvas.mpl_connect('button_release_event',
                #            self.updateIndicators)


    def findCanvas(self, type, quantity):
        canvas = next((plt.canvas for plt in self.plots 
                        if plt.type == type and plt.quantity == quantity), None)
        if canvas is None:
            print "Warning: could not find canvas for {} {}".format(type, quantity)
            logging.error("could not find canvas for {} {}".format(type, quantity))

        return canvas
    
    
    def togglePlots(self, cb, probe, type, quantity):
        """ Toggles temporal plots based on checkbox selection. """
        plot = next((p for p in self.plots
                    if p.quantity == quantity and p.type == type), None)
        
        probe.setSelected(plot.canvas, cb.isChecked())

        if type == 'temporal':
            plot.update()
        if type == 'spatial':
            plot.toggleProbe(probe.name, cb.checkState())

        plot.canvas.draw()
        

    def resetPlots(self):
        for plot in self.plots:
            plot.viewAll()
            plot.canvas.draw()


    def changeCELMAmarker(self, type):
        """
        Triggers input dialog for entering a new marker style for CELMAs of
        type `type`. Updates any existing CELMA plots with the new setting."
        """

        marker, ok = QtGui.QInputDialog.getText(
                        self,
                        "Change {} CELMA marker style"\
                        .format(type),
                        "Marker to be used for {} coherent ELM averaging"\
                        .format(type))

        if ok:
            plots = [p for p in self.plots if p.type==type]
            for plot in plots:
                plot.CELMAmarker = str(marker)
                if len(plot.CELMAs) > 0:
                    if type=='temporal':
                        self.createTemporalCELMA(plot)
                    else:
                        self.createSpatialCELMA()


    def populateProbeList(self):
        """ Populates list of available probes with probe names and checkboxes. """
        table = self.probeTable
        # Clear table of previous contents
        table.setColumnCount(0)
        table.setRowCount(0)

        # Add row for color patches
        rowPos = table.rowCount()
        table.insertRow(rowPos)
        item = QtGui.QTableWidgetItem('Color')
        table.setVerticalHeaderItem(rowPos, item)

        print "\n\n++++++++++++++POPULATING PROBE TABLE++++++++++"
        logging.info("\n\n++++++++++++++POPULATING PROBE TABLE++++++++++")

        # Add available probes for each plot
        for i, plot in enumerate(self.plots):
            # Insert new row
            if plot.type == 'spatial':
                rowPos = 1
            else:
                rowPos = table.rowCount()
            table.insertRow(rowPos)
            item = QtGui.QTableWidgetItem(
                    plot.type.capitalize() + ' ' + plot.quantity.upper())
            table.setVerticalHeaderItem(rowPos, item)

            ## Add Tdiv, Nbar, V
            #for label,color in [('Tdiv','b'),('Nbar','r'),('V','g')]:
            #    # Insert new column and color patch only if probeName is not in
            #    # HorizontalHeaderLabel.
            #    inHeader = False
            #    for j in range(table.columnCount()):
            #        headerText = str(table.horizontalHeaderItem(j).text())
            #        if label == headerText:
            #            colPos = j
            #            inHeader = True
            #            break
            #    if not inHeader:
            #        colPos = table.columnCount()
            #        table.insertColumn(colPos)

            #        patch = ColorPatch(color) 
            #        patch.clicked.connect(
            #                functools.partial(self.changeCompareColor, patch, label))
            #        table.setCellWidget(0, colPos, patch)
            #        self.patches[label] = patch

            #    item = QtGui.QTableWidgetItem(label)
            #    table.setHorizontalHeaderItem(colPos, item)

            #    cb = QtGui.QCheckBox()
            #    cb.setTristate(False)
            #    cb.stateChanged.connect(
            #            functools.partial(self.toggleCompare, cb, label, plot.type, plot.quantity))
            #    table.setCellWidget(i+1, colPos, cb)

            # Add probes
            for probe in plot.probes:
                probeName = probe.name
                color = probe.color
                quantity = plot.quantity
                plotType = plot.type

                # Insert new column and color patch only if probeName is not in
                # HorizontalHeaderLabel.
                probeInHeader = False
                for j in range(table.columnCount()):
                    headerText = str(table.horizontalHeaderItem(j).text())
                    if probeName == headerText:
                        colPos = j
                        probeInHeader = True
                        break
                if not probeInHeader:
                    colPos = table.columnCount()
                    table.insertColumn(colPos)

                    # Color patch
                    patch = ColorPatch(color) 
                    patch.clicked.connect(
                        functools.partial(self.changeProbeColor, patch,
                                          probeName))
                    table.setCellWidget(0, colPos, patch)
                    self.patches[probeName] = patch

                # Set header label
                item = QtGui.QTableWidgetItem(probeName)
                table.setHorizontalHeaderItem(colPos, item)

                # Checkboxes
                cb = QtGui.QCheckBox()

                # Make checkboxes 0 or 1 only
                cb.setTristate(False)

                # Check selected probes
                if probe.isSelected(plot.canvas):
                    cb.setChecked(True)

                cb.stateChanged.connect(
                    functools.partial(self.togglePlots, cb, probe,
                                      plotType, quantity))

                table.setCellWidget(i + 1, colPos, cb)
        
        rowPos = table.rowCount()
        table.insertRow(rowPos)
        item = QtGui.QTableWidgetItem('Temporal CELMA')
        table.setVerticalHeaderItem(rowPos, item)

        # This will take the probes from the next best plot. Not all plots
        # necessarily have the same probes. This might provide too many/too
        # little probes
        probes = next((p.probes for p in self.getTemporalPlots()), None)
        for probe in probes:
            # It is pretty certain this probe is already somewhere in the
            # header. If not, something went wrong with populating the header
            for j in range(table.columnCount()):
                headerText = str(table.horizontalHeaderItem(j).text())
                if probe.name == headerText:
                    colPos = j
                    break
            cb = QtGui.QCheckBox()
            cb.setTristate(False)

            cb.stateChanged.connect(
                functools.partial(self.markProbeForCELMA, cb, probe.name))
            table.setCellWidget(rowPos, colPos, cb)

            # Check for CELMA if checked in any plot
            checkCB = any(probe.isSelected(plot.canvas) for plot in self.plots)
            if checkCB:
                cb.setChecked(True)


    #def toggleProbeVoltage(self, probe, vType):
    #    time, data = self.voltages[probe.name][vType]

    #    for plot in self.getTemporalPlots():
    #        if cb.isChecked():
    #            if probe.name + vType not in plot._showing:
    #                if plot.compareAx is not None:
    #                    plot.removeCompareAxes()
    #                plot.createCompareAxes()
    #            plot.addComparePlot(time,data,color)
    #            plot.showing[probe.name+vType] = True
    #        else:
    #            if probe.name + vType in plot._showing:
    #                plot.removeCompareAxes()
    #            del plot.showing[probe.name+vType]


    #def toggleCompare(self, cb, label, type, quantity):
    #    plot = next((p for p in self.getTemporalPlots() 
    #                        if p.type==type and p.quantity==quantity), None)
    #    if plot is not None:
    #        if cb.isChecked():
    #            color = self.comparePlotColors[label]
    #            time, data = self.compareData[label]
    #            plot.createCompareAxes(time, data, color)
    #        else:
    #            plot.removeCompareAxes()
    #            self.comparePlot.remove()
    #            self.compareAx.remove()
    #

    #def changeCompareColor(self, patch, label):
    #    # Choose new color
    #    dialog = QtGui.QColorDialog()
    #    dialog.setWindowState(dialog.windowState() & ~QtCore.Qt.WindowMinimized | QtCore.Qt.WindowActive)
    #    dialog.activateWindow()
    #    color = dialog.getColor()
    #    if not QColor.isValid(color):
    #        return

    #    # Conversion to matplotlib-compatible rgb value
    #    red = color.red()/255.
    #    blue = color.blue()/255.
    #    green = color.green()/255.
    #    rgb = (red,green,blue)

    #    patch.setColor(color)
    #    self.comparePlot.set_color(rgb)
    #    self.comparePlotColors[label] = rgb
                    

    def updatexPlot(self):
        """
        Updates spatial plots after changing GUI settings. Updates
        `indicator_range`.
        """
        # Block indicator update when panning to greatly enhance
        # performance. If this is not done, indicator.slide() will call
        # canvas.update() each time it hits the xlimits additionally to
        # the under-the-hood panning
        panning = next((True for p in self.plots if hasattr(p.axes,'_pan_start')), False)
        if panning:
            return

        pos = self.xTimeSlider.value()
        realtime = self.dtime[pos]
        for p in self.plots:
            if p.type == 'spatial':
                p.update(realtime)
                self.indicator_range = p.realdtrange


    def findTWindow(self, Dt, avgNum):
        """ 
        Finds the time window that is closest to the value `Dt` the user
        provided based on the number of data points to average over to create
        a plot point, `avgNum`.
        """
        if avgNum is None:
            print "ERROR: spatial avgNum is None!"+\
                    "Cannot find appropriate time window"
            logging.warn("ERROR: spatial avgNum is None!"+\
                    "Cannot find appropriate time window")
            return

        # Don't try anything fancy if no averaging is wanted anyway
        if avgNum == 0: return Dt

        # avgNum HAS to be odd or 0
        remAvg = Dt % avgNum 
        rem2 = Dt % 2

        # If Dt is divisible by avgNum but not by 2, accept it
        if remAvg == 0 and rem2 != 0:
            Dt = Dt

        # If Dt is divisible by avgNum and by 2, add avgNum
        if remAvg == 0 and rem2 == 0:
            Dt = Dt + avgNum

        # If Dt is not divisible by avgNum, subtract remainder and 
        # add avgNum if needed so that result is as close as possible to the
        # user input. Then check if that value is divisible by two. If so,
        # choose the other value anyway
        if remAvg != 0:
            if remAvg >= avgNum/2.:
                tempDt = Dt - remAvg + avgNum
                if tempDt % 2 == 0:
                    Dt = tempDt - avgNum
                else:
                    Dt = tempDt
            else:
                tempDt = Dt - remAvg
                if tempDt % 2 == 0:
                    Dt = tempDt + avgNum
                else:
                    Dt = tempDt
        return Dt
        

    def updateTWindow(self, avgNum=None):
        """ 
        Updates spatial plot and position indicators based on the choice of the
        time window from which data is to be included in the spatial plot.
        """
        if avgNum is None:
            avgNum = next((p.avgNum for p in self.plots
                            if p.type == 'spatial'), None)
            
        # Get new value for time window (Dt, see SpatialPlot.getShotData())
        Dt = self.spinTWidth.value()
        
        # Find time window that best matches user input and internal 
        # requirements
        Dt = self.findTWindow(Dt, avgNum)

        # Correct user input in GUI too
        self.spinTWidth.setValue(Dt)

        # Update xPlot with new time window
        self.Dt = Dt
        self.updatexPlot()

        # Update sliders with new time window
        self.updateIndicators()

        # Update label showing time window in realtime
        if not None in self.indicator_range:
            dt = abs(self.indicator_range[1] - self.indicator_range[0])
        else:
            dt = 0
        self.lblRealTWidth.setText("= {:.2f}us".format(dt*10**6))


    def createPlot(self, container, _type=None, quantity=None):
        """
        Creates a Plot object of the specified type and quantity at the
        specified location on the GUI.

        Expects:
            <string>    type:       'temporal' or 'spatial'
            <string>    quantity:   'te', 'ne', 'jsat'
            <QLayout>   container:  Layout to contain the plot
        
        Returns:
            None
        """
        if _type is not None and quantity is not None:
            ClassFinder = {
                    'spatial': {
                        'jsat': SpatialCurrentPlot,
                        'te':   SpatialPlot,
                        'ne':   SpatialPlot},
                    'temporal': {
                        'jsat': TemporalCurrentPlot,
                        'te':   TemporalPlot,
                        'ne':   TemporalPlot}
                    }

            try:
                PlotClass = ClassFinder[_type][quantity]
            except:
                print "Could not find PlotClass for '{} {}'"\
                        .format(_type, quantity)
                logging.critical("Could not find PlotClass for '{} {}'"\
                        .format(_type, quantity))
                return False

            self.statusbar.showMessage(
                    'Creating {} {} plot'.format(_type, quantity))
        else:
            if plot is None:
                print "ERROR: Either _type and quantity or plot have to be given"
                logging.critical( "ERROR: Either _type and quantity or plot have to be given")
                return False
            

        self.clearPlotContainer(container)

        plot = PlotClass(self,quantity)
        #plot.progressed.connect(self.onProgress)
        #plot.processEvent.connect(self.onProcessEvent)
        plot.container = container

        plot.fitting = self.menuFit.isChecked()
        
        currentTime = str(self.xTimeEdit.text())
        if currentTime == '':
            currentTime = 0
        else:
            currentTime = float(currentTime)
        
        plot.init(currentTime, self.Dt)

        container.addWidget(plot.canvas)
        
        ###################################################################
        # There must be a better way to do this
        # Also, App will not have attribute dtime or indicator_range, if no
        # SpatialPlot is instantiated
        if plot.type == 'spatial':
            self.dtime = plot.dtime
            self.indicator_range = plot.realdtrange
        elif plot.type == 'temporal':
            plot.pertinent = True
            plot._timeUpdtID = plot.axes.callbacks.connect(
                                        'xlim_changed', self.updateRange)
            plot._ELMtblUpdtID = plot.axes.callbacks.connect(
                                        'xlim_changed', self.populateELMtable)
            plot._ELMStatUpdtID = plot.axes.callbacks.connect(
                                        'xlim_changed', self.showELMstatistics)
            plot._StatUpdtID = plot.axes.callbacks.connect(
                                        'xlim_changed', self.showStats)

        self.plots.append(plot)

        plot.canvas.collectiveSaveClicked.connect(self.collectiveSave)
        plot.canvas.popupRequested.connect(
                functools.partial(self.createPopup, plot))

        self.featurePicker.addCanvas(plot.quantity, plot.canvas)

        # This does not work with FuncFormatter
        #plot.axes.get_xaxis().get_major_formatter().set_useOffset(False)

        return True


    def createPopup(self, plot=None):
        popup = FigureWindow(self, plot)
        popup.show()


    @pyqtSlot('PyQt_PyObject')
    def collectiveSave(self, toSave):
        if toSave == 'all':
            self.saveAllFigures()
        elif toSave == 'temporal':
            self.saveTemporalFigures()


    def clearPlotContainer(self, container):
        for i in reversed(range(container.count())): 
            container.itemAt(i).widget().setParent(None)


    def saveAllFigures(self):
        """
        Creates popup window with one figure showing all plots so they
        can be saved together using the toolbar functionality.
        """
        fig = Figure()
        canvas = FigureCanvas(fig)
        spatialPlots = self.getSpatialPlots()
        temporalPlots = self.getTemporalPlots()
        
        if len(temporalPlots) > 0:
            colNum = 2
        else:
            colNum = 1

        i = 1
        rowNum = len(spatialPlots)
        for plot in self.getSpatialPlots():
            ax = plot.axes
            ax.change_geometry(rowNum,colNum,i)
            fig.axes.append(ax)
            i += colNum

        i = 2
        rowNum = len(temporalPlots)
        for plot in self.getTemporalPlots():
            ax = plot.axes
            ax.change_geometry(rowNum,colNum,i)
            fig.axes.append(ax)
            i += colNum

        window = FigureWindow(self, fig)
        window.show()

    
    def saveTemporalFigures(self):
        """
        Creates popup window with one figure showing all temporal plots so they
        can be saved together using the toolbar functionality.
        """
        fig = Figure()
        canvas = FigureCanvas(fig)
        temporalPlots = self.getTemporalPlots()
        
        i = 1
        rowNum = len(temporalPlots)
        for plot in self.getTemporalPlots():
            print "Adding axes for temporal {} plot.".format(plot.quantity)
            ax = fig.add_subplot(rowNum,1,i)
            plot.update(fig,ax)
            i += 1

        print "Axes in figure:", fig.axes

        window = FigureWindow(self, fig)
        window.show()


    def changeCELMApad(self):
        curPad = next((p.CELMApad for p in self.getTemporalPlots()), None)
        pad, ok = QtGui.QInputDialog.getDouble(self,
                    "Change temporal CELMA padding",
                    "Insert padding in ms:",
                    value=curPad, min=0, max=100)
        if ok:
            pad = float(pad)
            for plot in self.getTemporalPlots():
                plot.CELMApad = pad
                if len(plot.CELMAs) > 0:
                    self.createTemporalCELMA(plot)


    def getTemporalPlots(self, quantity=None):
        if quantity is None:
            return [p for p in self.plots if p.type=='temporal']
        else:
            return next((p for p in self.plots if p.type=='temporal' and
                                                p.quantity==quantity), None)


    def getSpatialPlots(self, quantity=None):
        if quantity is None:
            return [p for p in self.plots if p.type=='spatial']
        else:
            return next((p for p in self.plots if p.type=='spatial' and
                                                p.quantity==quantity), None)


    def getPlotsByType(self, type, quantity=None):
        if type == 'temporal':
            return self.getTemporalPlots(quantity)
        if type == 'spatial':
            return self.getSpatialPlots(quantity)
        return


    def activateZoom(self):
        for plot in self.plots:
            if plot.toolbar._active == 'ZOOM':
                return
            plot.toolbar.zoom()


    def activatePan(self):
        for plot in self.plots:
            if plot.toolbar._active == 'PAN':
                return
            plot.toolbar.pan()


    # def createxPlot(self):
    #     """
    #         Updates spatial plot by trying to remove the previous plot and
    #         creating a new canvas. Creates a SpatialPlot object.
    #     """
    #     self.statusbar.showMessage('Creating spatial plot')
    #     # If canvas already exists, delete it
    #     self.clearxPlot()

    #     # create new canvas
    #     if self.getPlotOption() == "Saturation current density":
    #         self.xPlot = SpatialCurrentPlot(self)
    #     else:
    #         self.xPlot = SpatialPlot(self)

    #     self.xPlot.progressed.connect(self.onProgress)
    #     self.xPlot.processEvent.connect(self.onProcessEvent)

    #     self.xPlot.init()
    #     self.xPlotCanvas = self.xPlot.canvas
    #     self.xPlotLayout.addWidget(self.xPlotCanvas)
    #     self.dtime = self.xPlot.dtime

    #     self.plots.append(self.xPlot)
    #     self.indicator_range = self.xPlot.realdtrange
    #     
    #     self.probes = self.xPlot.probes

    #     self.xPlot.axes.get_xaxis().get_major_formatter().set_useOffset(False)


    # def createTPlot(self):
    #     self.statusbar.showMessage('Creating temporal temperature plot')
    #     try:
    #         self.TPlotLayout.removeWidget(self.TPlotCanvas)
    #         self.TPlotCanvas.close()
    #     except:
    #         pass

    #     TPlot = TemporalPlot(self,'te')

    #     self.TPlot.progressed.connect(self.onProgress)
    #     self.TPlot.processEvent.connect(self.onProcessEvent)

    #     TPlot.init()
    #     self.TPlotCanvas = TPlot.canvas
    #     self.TPlotLayout.addWidget(self.TPlotCanvas)
    #     TPlot.parent = self.TPlotLayout

    #     self.probes = self.TPlot.probes

    #     self.plots.append(TPlot)


    # def createnPlot(self):
    #     self.statusbar.showMessage('Creating temporal density plot')
    #     try:
    #         self.nPlotLayout.removeWidget(self.nPlotCanvas)
    #         self.nPlotCanvas.close()
    #     except:
    #         pass

    #     nPlot = TemporalPlot(self,'ne')

    #     self.nPlot.progressed.connect(self.onProgress)
    #     self.nPlot.processEvent.connect(self.onProcessEvent)

    #     nPlot.init()
    #     self.nPlotCanvas = nPlot.canvas
    #     self.nPlotLayout.addWidget(self.nPlotCanvas)
    #     nPlot.parent = self.nPlotLayout

    #     self.probes = self.nPlot.probes

    #     self.plots.append(nPlot)


    # def createjPlot(self):
    #     self.statusbar.showMessage('Creating temporal current density plot')
    #     try:
    #         self.jPlotLayout.removeWidget(self.jPlotCanvas)
    #         self.jPlotCanvas.close()
    #     except:
    #         pass

    #     self.jPlot = TemporalCurrentPlot(self)

    #     self.jPlot.progressed.connect(self.onProgress)
    #     self.jPlot.processEvent.connect(self.onProcessEvent)

    #     self.jPlot.init()
    #     self.jPlotCanvas = self.jPlot.canvas
    #     self.jPlotLayout.addWidget(self.jPlotCanvas)
    #     self.jPlot.parent = self.jPlotLayout

    #     self.probes = self.jPlot.probes

    #     self.plots.append(self.jPlot)
        

    @QtCore.pyqtSlot(int)
    def onProgress(self, prog):
        self.progBar.setValue(prog)


    @QtCore.pyqtSlot(str)
    def onProcessEvent(self, msg):
        if msg is None:
            self.statusbar.clearMessage()
        else:
            self.statusbar.showMessage(msg)


    def getLatestLSC(self, shotNumber):
        self.statusbar.showMessage("Getting LSC shotfile...")

        exp = str(self.comboExpLSC.currentText())
        try:
            shotNumberLSC = dd.getLastShotNumber('LSC', shotNumber, exp)
        except Exception, e:
            self.showShotWarning(
                "Shot could not be loaded",
                "Latest LSC shot file could not be found",
                "Please make sure you are connected to the internet" +
                " and have a valid Kerberos token",
                details=str(e))
            return False
        
        self.statusbar.showMessage("Most recent shot with LSC data before " +
                                   "this shot: {}"
                                   .format(shotNumberLSC), 3000)

        self.latestLSCshotnr = shotNumberLSC

        if shotNumberLSC == 0:
            self.showShotWarning(
                "Shot could not be loaded",
                "libddww method getLastShotNumber() returned 0 for the" +
                " LSC shot file belonging to this shot.",
                "Please make sure you are connected to the internet" +
                " and have a valid Kerberos token. You may have to " +
                "restart the applictaion after obtaining a token")
            return False

        return shotNumberLSC
        

    def getInterpretedLangmuirData(self):
        self.statusbar.showMessage('Fetching Langmuir data...')
        exp = str(self.comboExpInt.currentText())
        diag = self.langdiag
        try:
            shot = dd.shotfile( diag, self.shotnr, exp)
        except Exception, e:
            try:
                print "Could not find {} shotfile for user {}. Trying AUGD...".format(diag,exp)
                logging.critical("Could not find {} shotfile for user {}.  Trying AUGD...".format(diag,exp))
                shot = dd.shotfile(diag, self.shotnr)
            except Exception, e:
                self.showShotWarning(
                "Shotfile not found",
                "{} shotfile could not be loaded".format(diag),
                "No shotfile could be found at {}:{} for this shot.".format(diag,exp),
                details=str(e))
                return False
        self.LSDshot = shot
        self.shotfiles.append(shot)
            
        self.timeArray = self.getTimeArray(shot)
        return True


    def getStrikelineData(self):
        self.statusbar.showMessage('Fetching strikeline data...')
        
        exp = str(self.comboExpEqu.currentText())
        diag = self.sldiag
        try:
            shot = dd.shotfile( diag, self.shotnr, exp)
        except Exception, e:
            print "Could not find {} shotfile for user {}. Trying AUGD...".format(diag,exp)
            logging.critical("Could not find {} shotfile for user {}.  Trying AUGD...".format(diag,exp))
            try:
                shot = dd.shotfile(diag, self.shotnr)
            except Exception, e:
                self.showShotWarning(
                "Shotfile not found",
                "{} shotfile could not be loaded".format(diag),
                "No jsat shotfile could be found at {}:{} for this shot.".format(diag,exp),
                details=str(e))
                return False
        self.EQUshot = shot
        self.shotfiles.append(shot)

        # Strikeline coordinates
        self.ssl = {}
        self.Rsl = {}
        self.zsl = {}
        
        try:
            self.ssl['data'] = shot('Suna2b').data
            self.ssl['time'] = shot('Suna2b').time
            self.Rsl['data'] = shot('Runa2b').data
            self.Rsl['time'] = shot('Runa2b').time
            self.zsl['data'] = shot('Zuna2b').data
            self.zsl['time'] = shot('Zuna2b').time
        except Exception, e:
            self.showShotWarning(
            "Strikeline positions not readable",
            "Unable to read strikeline positions from {}".format(diag),
            "Invalid shotfile found at {}:{} for this shot.".format(diag,exp),
            details=str(e))
            self.hideProgress()
            return False
        return True

    
    def getELMdata(self):
        self.statusbar.showMessage('Fetching ELM times...')
        exp = str(self.comboExpELM.currentText())
        diag = self.ELMdiag
        try:
            shot = dd.shotfile( diag, self.shotnr, exp)
        except Exception, e:
            print "Could not find {} shotfile for user {}. Trying AUGD...".format(diag,exp)
            logging.critical("Could not find {} shotfile for user {}.  Trying AUGD...".format(diag,exp))
            try:
                shot = dd.shotfile(diag,self.shotnr)
            except:
                self.showShotWarning(
                "Shotfile not found",
                "{} shotfile could not be loaded".format(diag),
                "No jsat shotfile could be found at {}:{} for this shot."
                .format(diag,exp),
                details=str(e))
                self.hideProgress()
                return False
        self.ELMshot = shot
        self.shotfiles.append(shot)
         
        self.ELMonsets = shot('t_begELM')
        self.ELMends = shot('t_endELM').data
        self.ELMmaxima = shot('t_maxELM').data
        self.ELMfreqs = shot('freq_ELM').data
        self.ELMtoELM = np.append(np.diff(self.ELMonsets),0)
        return True


    def showShotWarning(self, title, msg, text, details=''):
        print msg
        logging.critical(msg)
        self.statusbar.showMessage(msg)
        msgBox = QMessageBox()
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.setText(msg +'\n\n' + text)
        msgBox.setDetailedText(details)
        msgBox.setWindowTitle(title)
        msgBox.setStandardButtons(QMessageBox.Ok)
        msgBox.setDefaultButton(QMessageBox.Ok)
        msgBox.setEscapeButton(QMessageBox.Ok)
        msgBox.exec_()
        self.hideProgress()


    def readShotNumber(self):
        token = self.checkAFSToken()
        if not token:
            return False
        try:
            self.shotnr = int(self.shotNumberEdit.text())
        except Exception, e:
            self.showShotWarning(
            "Shot number invalid",
            "Please make sure to enter an integer.",
            "Invalid shot number",
            details=str(e))
            return False

        # If shot number not five-digit, load default shot
        #if(len(str(self.shotnr)) != 5): 
        #    self.shotnr = 32273
        #    self.shotNumberEdit.setText(str(self.shotnr))
        print "Read shot number {} from GUI".format(self.shotnr)
        logging.info("Read shot number {} from GUI".format(self.shotnr))
        return True


    def getRawLangmuirData(self, diag=None):
        self.statusbar.showMessage('Fetching LSF shot...')
        diag = 'LSF'
        exp = str(self.comboExpRaw.currentText())
        try:
            shot = dd.shotfile(diag, self.shotnr, exp)
        except:
            print "Could not find {} shotfile for user {}. Trying AUGD...".format(diag,exp)
            logging.critical("Could not find {} shotfile for user {}.  Trying AUGD...".format(diag,exp))
            try:
                shot = dd.shotfile(diag, self.shotnr)
            except Exception, e:
                self.showShotWarning(
                "Shotfile not found",
                "{} shotfile could not be loaded".format(diag),
                "No jsat shotfile could be found at {}:{} for this shot."
                .format(diag,exp),
                details=str(e))
                return False
        self.LSFshot = shot
        self.shotfiles.append(shot)
        return True


    def getConfigurationData(self):
        self.statusbar.showMessage('Getting probe configuration from LSC...')
        diag = 'LSC'
        exp = str(self.comboExpLSC.currentText())
        print "Latest LSC shot number:", self.latestLSCshotnr
        logging.info("Latest LSC shot number: {}".format(self.latestLSCshotnr))
        try:
            shot = dd.shotfile(diag, self.latestLSCshotnr, exp)
        except Exception, e:
            self.showShotWarning(
            "Shotfile not found",
            "{} shotfile could not be loaded".format(diag),
            "No jsat shotfile could be found at {}:{} for this shot."
            .format(diag,exp),
            details=str(e))
            return False
        self.LSCshot = shot
        self.shotfiles.append(shot)
        return True


    def getWmhdData(self):
        self.statusbar.showMessage('Getting Wmhd data...')
        diag = 'FPG'
        exp = str(self.comboExpWmhd.currentText())
        logging.info("Getting Wmhd shot from {}:{}"
                     .format(exp, diag))
        try:
            shot = dd.shotfile(diag, self.shotnr, exp)
        except Exception, e:
            self.showShotWarning(
                "Shotfile not found",
                "{} shotfile could not be loaded".format(diag),
                "No shotfile could be found at {}:{} for this shot."
                .format(diag, exp),
                details=str(e))
            return False

        diag = 'ELM'
        WmhdELMshot = dd.shotfile(diag, self.shotnr, exp)
        self.WmhdELMonsets = WmhdELMshot('t_begELM')
        self.WmhdELMends = WmhdELMshot('t_endELM').data
        self.WmhdELMmaxima = WmhdELMshot('t_maxELM').data
        self.WmhdELMfreqs = WmhdELMshot('freq_ELM').data
        self.WmhdELMtoELM = np.append(np.diff(self.WmhdELMonsets), 0)
        self.ELMENER = WmhdELMshot('ELMENER').data
        self.preELMWmhd = WmhdELMshot('Wmhd').data
        self.ELMelec = WmhdELMshot('ELMPART').data
        self.preELMelec = WmhdELMshot('ELECTRNS').data

        self.WmhdShot = shot
        self.shotfiles.append(shot)
        self.shotfiles.append(WmhdELMshot)
        return True


    def getShot(self):
        """ Retrieves langmuir data and strikeline positions from AUG shotfiles. This is an expensive operation and should only be invoked when loading a new shotfile. """
        # Close any open shotfiles. Not doing this will prevent the program
        # from loading more shotfiles at some point
        for shotfile in self.shotfiles:
            shotfile.close()
        self.shotfiles = []

        if not self.readShotNumber():
            print "Could not read shotnumber"
            logging.critical( "Could not read shotnumber")
            return False

        logging.info("Getting last LSC shot number")
        ok = self.getLatestLSC(self.shotnr)
        if not ok:
            print "Failed to get latest LSC. Returned {}".format(ok)
            logging.critical( "Failed to get latest LSC. Returned {}".format(ok))
            return False
        self.progBar.setValue(5)

        # Get temperature and density data from langmuir diags
        logging.info("Getting LSD shot")
        ok = self.getInterpretedLangmuirData()
        if not ok:
            print "Failed to get interpreted langmuir data"
            logging.critical( "Failed to get interpreted langmuir data")
            return False

        # Get Wmhd data
        logging.info("Getting LSD shot")
        ok = self.getWmhdData()
        if not ok:
            print "Failed to get Wmhd data"
            logging.critical( "Failed to get Wmhd data")
            return False

        # Get strikeline positions from diagnostic
        logging.info("Getting FPG shot")
        ok = self.getStrikelineData()
        if not ok:
            print "Failed to get strikeline data"
            logging.critical( "Failed to get strikeline data")
            return False
        self.progBar.setValue(25)
        
        # Get ELM times
        logging.info("Getting ELM shot")
        ok = self.getELMdata()
        if not ok:
            print "Failed to get ELM data"
            logging.critical( "Failed to get ELM data")
            return False
        self.progBar.setValue(30)

        # Get raw langmuir data
        logging.info("Getting LSF shot")
        ok = self.getRawLangmuirData()
        if not ok:
            print "Failed to get raw langmuir data"
            logging.critical( "Failed to get raw langmuir data")
            return False
        self.progBar.setValue(40)

        # Get probe configuration data
        logging.info("Getting LSC shot")
        ok = self.getConfigurationData()
        if not ok:
            print "Failed to get configuration data"
            logging.critical( "Failed to get configuration data")
            return False
        self.progBar.setValue(50)

        # Set timeline scrollbar min and max values
        # timeArray comes from LSD data
        self.xTimeSlider.setRange(0, len(self.timeArray)-1)
        
        self.saveShotNumberToRecents()
        self.statusbar.clearMessage()

        return True


    def hideProgress(self):
        """ Removes progressbar widget from the statusbar and resets it to the value 0. """
        self.progBar.setVisible(False)
        self.progBar.setValue(0)


    def quit(self):
        """ Closes application """
        self.close()


    def showWmhd(self):
        QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        plot = WmhdPlot(self)
        plot.init()

        self.plots.append(plot)

        self.popout = FigureWindow(self, plot)

        QtGui.QApplication.restoreOverrideCursor()
        self.popout.update()
        self.popout.show()

            
    def about(self):
        """ Shows information about the application in a message box. """
        QtGui.QMessageBox.about(self, "About",
                "This program plots langmuir probe data from ASDEX Upgrade "+\
                "shotfiles using the pwwdd interface provided by Bernhard "+\
                "Sieglin.\n\n"+\

                "Written by: Amazigh Zerzour\n"+\
                "E-mail: amazigh.zerzour@gmail.com ")


    def changeFitDetachment(self):
        for plot in self.getSpatialPlots():
            plot.detachedFit = self.menuDetachedFit.isChecked()
            plot.plotFit()


    def savexPlot(self):
        """ Saves spatial plot figures. """
        for p in self.getSpatialPlots():
            t = p.realtime
            dt = str(self.lblRealTWidth.text()).split()[1]
            defaultName = 'Spatial_{}_{:.7f}s_{}{}'\
                    .format(p.quantity, t, dt, self.defaultExtension)

            dialog = QtGui.QFileDialog()
            dialog.setDefaultSuffix(self.defaultExtension)
            fileName = dialog.getSaveFileName(self,
                                    directory='./' + defaultName,
                                    caption = "Save figure as",
                                    filter="PNG (*.png);;EPS (*.eps);;SVG (*.svg)",
                                    selectedFilter=self.defaultFilter)
            fileName = str(fileName)
            ok = True
            if ok:
                if len(fileName.split('.')) < 2:
                    print "Extension missing. Figure not saved"
                    logging.error("Extension missing. Figure not saved")
                    return
                fmt = fileName.split('.')[-1]
                p.fig.savefig(fileName, format=fmt)
                self.statusbar.showMessage("Figure saves as {}".format(fileName))
    
    def saveSettings(self):
        """
        Saves application settings to ini file
        Not supported so far: SchizoSlider, ColorPatches
        """
        fileName = QtGui.QFileDialog.getOpenFileName(self,
                                "Configuration file to save current settings to")
        if os.path.isfile(fileName):
            settings = QtCore.QSettings(fileName,QtCore.QSettings.IniFormat)
        
            pyqtSaveAndLoad.savegui(self,settings)


    def restoreSettings(self):
        fileName = QtGui.QFileDialog.getOpenFileName(self,
                                "Configuration file to save current settings to")
        if os.path.isfile(fileName):
            settings = QtCore.QSettings(fileName,QtCore.QSettings.IniFormat)

            pyqtSaveAndLoad.restoregui(self,settings)


    def toggleMultiplePOIs(self):
        if self.menuSimultaneousCELMAs.isChecked():
            self.POISlider.setLow(-20)
            self.POISlider.setMiddle(20)
            self.POISlider.setHigh(50)
            self.multiplePOIs = True
        else:
            self.POISlider.setLow(self.POISlider.minimum())
            self.POISlider.setHigh(self.POISlider.maximum())
            self.multiplePOIs = False


    def findActionByText(self, text):
        result = self.menuBar().findChildren(QtGui.QAction)
        action = next((a for a in result if str(a.text())==text),None)
        return action


    def getCELMAsettings(self):
        try:
            ELMnum = int(self.editCELMAELMnum.text())
        except ValueError:
            ELMnum = None
        try:
            start = float(self.editCELMAstartTime.text())
        except ValueError:
            start = None
        try:
            stop = float(self.editCELMAendTime.text())
        except ValueError:
            stop = None

        if ELMnum is None:
            if start is None and stop is None:
                print "No values provided"
                logging.error( "No values provided")
                return
            elif start is None and stop is not None:
                if self.dtime[0] < stop:
                    start = self.dtime[0]
                else:
                    print "Stop time smaller than smallest time value"
                    logging.error( "Stop time smaller than smallest time value")
                    return
            elif start is not None and stop is None:
                if self.dtime[-1] > start:
                    stop = self.dtime[-1]
                else:
                    print "Start time bigger than greatest time value"
                    loggin.error( "Start time bigger than greatest time value")
                    return
            ELMnum = 10000#Show all ELMs in range
        else:
            if start is not None and stop is None:
                if self.dtime[-1] > start:
                    stop = self.dtime[-1]
                else:
                    print "Start value bigger than greatest time value"
                    loggin.error( "Start time bigger than greatest time value")
                    return
            elif start is not None and stop is not None:
                pass
            else:
                print "Unknown error"
                logging.error("Unknown error")
                return

        return [start, stop, ELMnum]


    def playCELMA(self):
        if self._playing:
            return
        self._playing = True
        self.btnPlayCELMA.setText('Stop')
        self.btnRecordCELMA.setVisible(True)
        self.btnPlayCELMA.clicked.disconnect(self.playCELMA)
        self.btnPlayCELMA.clicked.connect(self.stop)
        self.POISlider.valueChanged.connect(self.updateCELMAs)
        self.record()

        slider = self.POISlider
        minimum= slider.low()+1
        maximum= slider.high()-1
        incr = self.playIncrement
        size = (maximum-minimum)/incr
        for k, i in enumerate(range(minimum,maximum,incr)):
            k += 1
            print "Step {} of {}".format(k,size)
            slider.setMiddle(i)
            if self._record:
                tFileName = os.path.join('recordings',self._recDir,'jsat_T_CELMA'+str(k)+'.png')
                sFileName = os.path.join('recordings',self._recDir,'jsat_S_CELMA'+str(k)+'.png')
                self._tSavePlot.fig.savefig(tFileName, format='png')
                self._sSavePlot.fig.savefig(sFileName, format='png') 
            if self._stop or i == maximum-1:
                self.btnPlayCELMA.setText('Play')
                self.POISlider.valueChanged.disconnect(self.updateCELMAs)
                self.btnPlayCELMA.clicked.disconnect(self.stop)
                self.btnPlayCELMA.clicked.connect(self.playCELMA)
                self.btnRecordCELMA.setVisible(False)
                self._playing = False
                self._stop = False
                break

 
    def stop(self):
        self._stop = True


    def record(self):
        if self.CELMAexists:
            _start = float(self.editCELMAstartTime.text())
            _stop = float(self.editCELMAendTime.text())
        else:
            _start = self.dtime[self.xTimeSlider.value()]
            _stop = self.dtime[self.xTimeSlider.maximum()]
            
        self._recDir = ('{}_{:.0f}-{:.0f}'
                        .format(self.shotnr, _start*100, _stop*100))
        self._tSavePlot = self.getPlotsByType('temporal','jsat')
        self._sSavePlot = self.getPlotsByType('spatial','jsat')
        path = os.path.join('recordings',self._recDir)
        if not os.path.isdir(path):
            os.makedirs(path)
        # Make sure directory exists before starting to record
        if os.path.isdir(path):
            self._record = True
            self.btnRecord.setText('Stop recording')
            try:
                self.btnRecord.clicked.disconnect(self.record)
                self.btnRecordCELMA.clicked.disconnect(self.record)
            except TypeError: 
                pass
            self.btnRecord.clicked.connect(self.stopRecording)
            self.btnRecordCELMA.setText('Stop recording')
            self.btnRecordCELMA.clicked.connect(self.stopRecording)


    def stopRecording(self):
        self._record = False
        self.btnRecord.setText('Record')
        self.btnRecord.clicked.disconnect(self.stopRecording)
        self.btnRecord.clicked.connect(self.record)
        self.btnRecordCELMA.setText('Record')
        self.btnRecordCELMA.clicked.disconnect(self.stopRecording)
        self.btnRecordCELMA.clicked.connect(self.record)


    def play(self):
        if self._playing:
            return
        self._playing = True
        self.btnPlay.setText('Stop')
        self.btnRecord.setVisible(True)
        self.btnPlay.clicked.disconnect(self.play)
        self.btnPlay.clicked.connect(self.stop)

        slider = self.xTimeSlider
        minimum= slider.value()
        maximum= slider.maximum()
        incr = self.playIncrement
        for i in range(minimum,maximum,incr):
            slider.setValue(i)
            if self._record:
                time = self.dtime[slider.value()]
                tFileName = os.path.join('recordings',self._recDir,'jsat_T_'+str(time)+'.png')
                sFileName = os.path.join('recordings',self._recDir,'jsat_S_'+str(time)+'.png')
                self._tSavePlot.fig.savefig(tFileName, format='png')
                self._sSavePlot.fig.savefig(sFileName, format='png') 
            if self._stop or i == maximum-1:
                self.btnPlay.setText('Play')
                self.btnPlay.clicked.disconnect(self.stop)
                self.btnPlay.clicked.connect(self.play)
                self.btnRecord.setVisible(False)
                self._playing = False
                self._stop = False
                self._record = False
                break


    def updateCELMAs(self):
        QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        if not self.CELMAexists or not self.btnCELMAupdate.isVisible():
            return
        self.clearCELMAs()
        self.btnCELMA.setText('Return to profiles')
        self.createSpatialCELMA()

        _start = self.editCELMAstartTime.text()
        _end = self.editCELMAendTime.text()
        if self.cbTemporalCELMAs.isChecked():
            for plot in self.getTemporalPlots():
                xlim = plot.axes.get_xlim()
                modeHasChanged = plot._CELMAnormalize != self.cbCELMAnormalize.isChecked()
                self.createTemporalCELMA(plot)
                self.editCELMAstartTime.setText(_start)
                self.editCELMAendTime.setText(_end)
                
                # If normalization hasn't been toggled, reinstate axis limits
                if not modeHasChanged:
                    plot.axes.set_xlim(xlim)
        else:
            logging.info('Temporal CELMAs not selected (anymore)')
            logging.info('Resetting axes limits to [{},{}]'\
                         .format(str(_start),str(_end)))
            for plot in self.getTemporalPlots():
                try:
                    _start = float(str(_start))
                    _end = float(str(_end))
                except:
                    logging.warning("Could not convert axes limits")
                    pass
                else:
                    plot.axes.set_xlim((_start,_end),emit=False)
                    plot.draw()
        
        if not self.multiplePOIs:
            self.btnPlayCELMA.setVisible(True)

        self.btnCELMAupdate.setVisible(False)
        QtGui.QApplication.restoreOverrideCursor()

 
    def toggleCELMAs(self):
        """
        Toggles spatial and tempral CELMAs. Invoked by clicking GUI button
        """
        QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        if self.CELMAexists:
            self.clearCELMAs()
            for plot in self.plots:
                plot.reinstateView()
            self.CELMAexists = False
        else:
            self.statusbar.showMessage('Performing coherent ELM averaging on spatial plot')
            self.deactivateXtimeSlider()

            for plot in self.plots:
                plot.memorizeView()

            self.createSpatialCELMA()

            if self.cbTemporalCELMAs.isChecked():
                # Save CELMA start and end times to reinstate them after the CELMAs
                # have been created. This is necessary since changes of axes limits
                # sometime during what happens here cause the LineEdits to take
                # different values.
                _start = self.editCELMAstartTime.text()
                _end = self.editCELMAendTime.text()

                for plot in self.getTemporalPlots():
                    if plot.pertinent:
                        plot.canvas.callbacks.disconnect(plot._timeUpdtID)
                    self.statusbar.showMessage(
                        'Performing coherent ELM averaging on temporal plots')
                    if len(plot.probes) > 0:
                        self.createTemporalCELMA(plot)
                    else:
                        plot.coherentELMaveraging()
                    # Reinstate original times
                    # Each temporal plot will experience a change in xlim and
                    # therefore change the CELMA time range in the GUI that the
                    # next plot relies on. The disconnect above this does not
                    # seem to work
                    self.editCELMAstartTime.setText(_start)
                    self.editCELMAendTime.setText(_end)

            if not self.multiplePOIs:
                self.btnPlayCELMA.setVisible(True)

            self.btnCELMA.setText('Return to profiles')
            self.CELMAexists = True
            self.populateELMtable()
            self.showELMstatistics()

            self.statusbar.showMessage('Coherent ELM averaging finished successfully.')
        QtGui.QApplication.restoreOverrideCursor()


    def markProbeForCELMA(self, cb, probeName):
        """
        Callback function that sets probe attribute `CELMA` to True if the
        according checkbox has been clicked and checked. createTemporalCELMA()
        relies on this attribute.
        """
        for plot in self.plots:
            for probe in plot.probes:
                if probe.name == probeName:
                    if cb.isChecked():
                        print "Marking probe {} for CELMA".format(probeName)
                        probe.CELMA = True
                    else:
                        probe.CELMA = False


    def createTemporalCELMA(self, plot):
        logging.info("Creating temporal CELMA")
        settings = self.getCELMAsettings()
        if settings is None:
            print "Error getting CELMA settings"
            logging.error("Error getting CELMA settings")
            return

        plot.hideArtists(exceptFor=plot.POImarkers) 

        normalize = self.cbCELMAnormalize.isChecked()
        probes = [p for p in plot.probes if p.CELMA]
        compare = str(self.comboELMcompare.currentText())
        binning = self.menuEnableBinning.isChecked()

        if normalize:
           plot.changeTickLabels('percent')
           plot._CELMAnormalize = True
        else:
           plot.changeTickLabels('milliseconds')
           plot._CELMAnormalize = False

        logging.info("Creating CELMAs for these probes: {}".format(probes))
        for probe in probes:
            probeName = probe.name
            color = probe.color
            if probeName not in [p.name for p in plot.probes]:
                print "{} does not exist in {} {} plot"\
                        .format(probeName, plot.type, plot.quantity)
                logging.info("{} does not exist in {} {} plot"\
                        .format(probeName, plot.type, plot.quantity))
                return

            plot.coherentELMaveraging(
                    *settings, 
                    probe = probeName, 
                    normalize = normalize,
                    binning = binning, 
                    compare = compare,
                    color = color,
                    avgColor = color,
                    lw = 3,
                    alpha = 0.4,
                    ignore = self.ignoreELMs)
        
        plot.CELMAexists = True
        plot.indicator.hide()
        plot.axes.relim()
        plot.canvas.draw()


    def clearCELMAs(self):
        """ Ends CELMA mode and reinstates normal mode """
        for plot in self.plots:
            plot.clearCELMA()
            plot.canvas.draw()
            if plot.type=='temporal' and plot.pertinent:
                #plot.clearPOImarkers()
                plot._timeUpdtID = plot.canvas.callbacks.connect(
                                        'xlim_changed',self.updateRange)
        self.btnCELMAupdate.setVisible(False)
        self.btnPlayCELMA.setVisible(False)
        self.btnCELMA.setText('ELM-Average')
        self.activateXtimeSlider()


    def plotMaximaDistances(self):
        QtGui.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            plot = self.getSpatialPlots()[0]
        except IndexError:
            print "ERROR: to assess detachment quality, there has to be "+\
                    "a spatial plot initialized."
            logging.error("ERROR: to assess detachment quality, there has to be "+\
                    "a spatial plot initialized.")
            return

        settings = self.getCELMAsettings()
        if settings is None:
            print "Error getting settings"
            logging.error("Error getting CELMA settings")
            return
        start, end, ELMnum = settings

        timeData = next((plot.rawdata[key]['time'] for key in plot.rawdata),None)
        timeData = Conversion.removeNans(timeData)
        ind = np.where((start <= timeData) & (timeData <= end))
        times = timeData[ind]#[::self.Dt]
        
        ind = np.where((start <= self.ELMonsets) & (self.ELMonsets <= end) 
                                        & ~np.in1d(self.ELMonsets,self.ignoreELMs))
        ELMstarts= self.ELMonsets[ind][:ELMnum]
        ELMends = self.ELMends[ind][:ELMnum]
        ELMtoELM = self.ELMtoELM[ind][:ELMnum]

        size = float(len(times))
        #positionsRZ = plot.getProbePositions()
        means = self.radioDistancesMeans.isChecked()
        medians = self.radioDistancesMedians.isChecked()
        fitting = self.cbDistancesFitting.isChecked()
        #mode = self.comboCELMAmode.currentText()
        normalize = self.cbCELMAnormalize.isChecked()
        fitMethod = plot.fitMethod

        maximaTimes = []
        maximaValues = []
        profilesXdata = []
        profilesYdata = []

        for i, _time in enumerate(times):
            data, timeRange = plot.getDataInTimeWindow(plot.rawdata, _time, self.Dt)
            #positions = plot.rztods(positionsRZ, timeRange)
            positions = plot.getDeltaS(timeRange)
            data, positions = plot.averageData(data, positions)
            
            dataToFit = []
            possToFit = []
            for key in data:
                d = data[key]
                p = positions[key]
                if medians:
                    p = np.median(p[~np.isnan(d)])
                    d = np.median(d[~np.isnan(d)])
                    dataToFit.append(d)
                    possToFit.append(p)
                elif means:
                    p = np.mean(p[~np.isnan(d)])
                    d = np.mean(d[~np.isnan(d)])
                    dataToFit.append(d)
                    possToFit.append(p)
                else:
                    dataToFit.extend(d)
                    possToFit.extend(p)

            if fitting:
                scale = max(dataToFit)
                dataToFit = [el/scale for el in dataToFit]
                time = self.dtime[self.xTimeSlider.value()]
                fit = plot.findFit(time, dataToFit, possToFit, method=fitMethod)
                if fit is None:
                    print "Fitting failed for unknown reason: did not return any data"
                    logging.critical( "Fitting failed for unknown reason: did not return any data")
                    continue
                
                fitx, fity = fit
                fitx = fitx[~np.isnan(fity)]
                fity = fity[~np.isnan(fity)]*scale
                maxx = fitx[np.argmax(fity)]
                profilesXdata.append(fitx)
                profilesYdata.append(fity)
            else:
                maxx = possToFit[np.argmax(dataToFit)]
                profilesXdata.append(possToFit)
                profilesYdata.append(dataToFit)

            maximaValues.append(maxx)
            maximaTimes.append(_time)
            
        if len(maximaValues) == 0:
            print "ERROR: No maxima data to plot"
            loggin.critical("No maxima data to plot")
            return
        if len(maximaValues) != len(maximaTimes):
            print "ERROR: Maxima data and locations arrays have different sizes"
            loggin.critical("Maxima data and locations arrays have different sizes")
            return
        maximaTimes = np.array(maximaTimes)
        maximaValues = np.array(maximaValues)
        
        ### Plotting
        self.popout = FigureWindow(self)

        # Time evolution of maximum distance from strikeline
        xlabel = 'Time [s]'
        ylabel = 'Distance from strikeline'
        axes = self.popout.currentAxes()
        axes.set_ylabel(ylabel)
        axes.set_xlabel(xlabel)
        axes.plot(maximaTimes,maximaValues,
                    marker='+',label = 'Maximum distance from strikeline')
        axes.axhline(0,0,1,ls='--',color='black', label = 'Strikeline')
        # Mark ELM durations in time evolution
        for i, (ton, tend) in enumerate(zip(ELMstarts,ELMends)):
            axes.axvspan(ton,tend,0,1,color='grey',alpha=0.2,
                        label = 'ELM {} @{:.4}s)'.format(i,ton))

        # CELMA of temporal maximum-distance-from-strikeline evolution
        newAx = self.popout.addSubplot()
        for ton, dt in zip(ELMstarts,ELMtoELM):
            ind = np.where((ton <= maximaTimes) & (maximaTimes < ton+dt))
            if normalize:
                xlabel = 'ELM duration [%]'
                t = (maximaTimes[ind] - ton)/dt
            else:
                xlabel = 'Time [s]'
                t = maximaTimes[ind] - ton
            y = maximaValues[ind]
            newAx.scatter(t,y, label='ELM {} @{:.4}s)'.format(i,ton))
        ylabel = 'Distance from strikeline (CELMA)'
        newAx.set_ylabel(ylabel)
        newAx.set_xlabel(xlabel)

        # Spatial profiles
        newAx = self.popout.addSubplot()
        xlabel = 'Distance along target [m]'
        ylabel = plot.quantity.capitalize()
        newAx.set_ylabel(ylabel)
        newAx.set_xlabel(xlabel)
        if fitting:
            for x, y in zip(profilesXdata, profilesYdata):
                newAx.plot(x,y)
        else:
            for x, y in zip(profilesXdata, profilesYdata):
                newAx.scatter(x,y)

        QtGui.QApplication.restoreOverrideCursor()
        self.popout.update()
        self.popout.show()


class LogPipe(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = False
        self.fdRead, self.fdWrite = os.pipe()
        self.pipeReader = os.fdopen(self.fdRead)
        self.start()


    def fileno(self):
        """Return the write file descriptor of the pipe
        """
        return self.fdWrite


    def run(self):
        for line in iter(self.pipeReader.readline, ''):
            sys.stdout(line.strip('\n'))

        self.pipeReader.close()


    def close(self):
        os.close(self.fdWrite)



class EmbeddedTerminal(QtGui.QWidget):
    def __init__(self):
        super(EmbeddedTerminal, self).__init__()
        self.resize(400, 200)
        #pipe = LogPipe()
        pipe = subprocess.PIPE
        self.terminal = QtGui.QWidget(self)
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(self.terminal)


class QPlainTextEditLogger(logging.Handler):
    def __init__(self, parent):
        super(QPlainTextEditLogger,self).__init__()
        self.widget = QtGui.QPlainTextEdit(parent)
        self.widget.setReadOnly(True)    

    def emit(self, record):
        msg = self.format(record)
        self.widget.appendPlainText(msg)    



class ToolFigureCanvas(FigureCanvas):
    saveClicked = pyqtSignal()
    collectiveSaveClicked = pyqtSignal('PyQt_PyObject')
    editClicked = pyqtSignal()
    optionsClicked = pyqtSignal()
    popupRequested = pyqtSignal()

    def __init__(self, fig):
        super(ToolFigureCanvas, self).__init__(fig)
        
        self.toolButton = QtGui.QToolButton(self)
        menu = QtGui.QMenu()

        menu.addAction('Save plot', self.saveClicked.emit)
        menu.addAction('Edit line and axes properties', self.editClicked.emit)
        menu.addAction('Edit plot properties', self.optionsClicked.emit)
        menu.addSeparator()
        menu.addAction('Open in popup window', self.popupRequested.emit)

        self.toolButton.setMenu(menu)
        self.toolButton.setAutoRaise(True)
        self.toolButton.setPopupMode(QtGui.QToolButton.InstantPopup)


    def paintEvent(self,event):
        super(ToolFigureCanvas,self).paintEvent(event)
        cw = self.geometry().width()
        ch = self.geometry().height()
        cx = self.geometry().x()
        cy = self.geometry().y()
        tw = self.toolButton.width()
        th = self.toolButton.height()
        # QGeometry(x,y,w,h)
        self.toolButton.setGeometry(cx+cw-2*tw,cy,tw,th)


class LimitsDialog(QtGui.QDialog):
    def __init__(self, parent=None):
        super(LimitsDialog,self).__init__(parent)

        layout = QtGui.QFormLayout()
        self.lblStart = QtGui.QLabel('Start time:')
        self.lblEnd = QtGui.QLabel('End time:')
        self.editStart = QtGui.QLineEdit()
        self.editEnd = QtGui.QLineEdit()

        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok
                | QtGui.QDialogButtonBox.Cancel, QtCore.Qt.Horizontal)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        layout.addRow(self.lblStart, self.editStart)
        layout.addRow(self.lblEnd, self.editEnd)
        layout.addRow(buttonBox)

        self.setLayout(layout)
        self.setWindowTitle('Start and end times')

    def limits(self):
        start = float(self.editStart.text())
        end = float(self.editEnd.text())
        return start, end

    @staticmethod
    def getLimits(parent = None):
        dialog = LimitsDialog(parent)
        result = dialog.exec_()
        start, end = dialog.limits()
        return (start, end, result == QtGui.QDialog.Accepted)



class ColorPatch(QtGui.QWidget):
    clicked = QtCore.pyqtSignal()
    
    def __init__(self, color):
        super(ColorPatch, self).__init__()
        self.color = QColor(mpl.colors.rgb2hex(color))


    def mousePressEvent(self, event):
        self.clicked.emit()


    def paintEvent(self,event):
        qp = QPainter()
        qp.begin(self)
        self.drawPatch(qp)
        qp.end()


    def drawPatch(self, qp):
        qp.setBrush(self.color)
        qp.drawRect(10, 10, 50, 10)


    def setColor(self, color, type=None):
        if type=='rgb':
            rgb = color
            color = QtGui.QColor()
            color.setRgb(*rgb)

        if type=='mpl':
            color = QColor(mpl.colors.rgb2hex(color))

        self.color = color
        self.update()


    def rgb(self):
        r = self.color.red()
        g = self.color.green()
        b = self.color.blue()
        return (r,g,b)



class Tools():
    @staticmethod
    def shellExecute(string):
        cmd = subprocess.Popen(string, stdout=subprocess.PIPE)
        result = cmd.communicate()
        return result

    @staticmethod
    def find_between(s, first, last ):
        try:
            start = s.index( first ) + len( first )
            end = s.index( last, start )
            return s[start:end]
        except ValueError:
            return ""
    
    @staticmethod
    def padToFit(array, n, dummy=np.NAN):
        array = np.array(array)

        rest = array.size % n
        if rest != 0:
            array = np.lib.pad(array, (0,n-rest),
                                'constant', constant_values=dummy)

        return array



#class MenuLabel(QtGui.QAction):
#    def __init__(self, parent):
#        super(MenuLabel, self).__init__(parent)
#        self.setEnabled(False)
#
#        font = QtGui.QFont()
#        font.setBold(True)
#        self.setFont(font)



class Indicator():
    """ Class for creating an indicator on a temporal plot to show the time that is displayed in the spatial plot. """
    def __init__(self, parent, color=None):
        self.parent = parent

        if color is None:
            self.color = 'b'
        else:
            self.color = color 

        attrs = self.getParentAttributes(parent)
        self.parentCanvas = attrs[0]
        self.parentAxes = attrs[1]
        self.time = 0
        self.tminus = 0
        self.tplus = 0

        self.slide(self.time)

    
    def getParentAttributes(self, parent):
        canvas = None
        axes = None

        for attr in dir(parent):
            try:
                attr = getattr(parent, attr)
            except RuntimeError:
                continue
            
            if isinstance(attr,FigureCanvas):
                canvas = attr
            elif isinstance(attr,mpl.axes.Axes):
                axes = attr

        return canvas, axes


    def hide(self):
        self.indic.set_visible(False)
        self.indic_fill.set_visible(False)
        

    def show(self):
        self.indic.set_visible(True)
        self.indic_fill.set_visible(True)


    def slide(self, time, range=None):
        """ 
        Positions indicator at `time` and gives it a width that corresponds to
        `range`.
        """
        if self.parentAxes is None or self.parentCanvas is None:
            print "Error: invalid parent axes or canvas"
            logging.critical("Invalid parent axes or canvas")
            return

        self.time = time
        if range is not None and not None in range:
            self.tminus = self.time - range[0]
            self.tplus = self.time + range[1]
        else:
            self.tminus = self.time
            self.tplus = self.time

        # Update previous indicator if there already is one
        if hasattr(self, "indic"):
            self.indic.set_xdata(self.time)
            xy = self.indic_fill.get_xy()
            xy = [
                    [self.tminus,xy[0][1]],
                    [self.tminus,xy[1][1]],
                    [self.tplus,xy[2][1]],
                    [self.tplus,xy[3][1]],
                    #[self.tminus,xy[4][1]]
                ]

            self.indic_fill.set_xy(xy)

            self.parentAxes.draw_artist(self.parentAxes.patch)
            for plot in self.parentAxes.lines:
                if plot.get_visible():
                    self.parentAxes.draw_artist(plot)
            for plot in self.parentAxes.patches:
                if plot.get_visible():
                    self.parentAxes.draw_artist(plot)

            self.parentAxes.draw_artist(self.indic)
            self.parentAxes.draw_artist(self.indic_fill)
            self.parentCanvas.update()
            self.parentCanvas.flush_events()

        #Plot new indicator if there is none
        else:
            self.indic = self.parentAxes.axvline(x=self.time,
                                color=self.color, label='Current position')
            self.indic_fill = self.parentAxes.axvspan(self.tminus, self.tplus,
                                    alpha=0.5, color=self.color,
                                    label='Time window used\nfor averaging spatial plot')
            self.parentCanvas.draw()



class Conversion():
    @staticmethod
    def valtoind(realtime, timearray):
        """ 
        Converts a real time value to an index in a given array with time
        values. This is achieved by comparing the real time value to the array
        elements and returning the index of the closest one.
        """
        return np.abs((timearray - realtime)).argmin()

    @staticmethod
    def removeNans(array, refarray=None):
        """ 
        Removes values from array based on the indices of NaN values in
        refarray. If refarray is not specified, NaN values are removed from
        array. Returns a numpy array. 
        """ 
        # If refarray was passed, comparing it to None would be deprecated
        if refarray is None:
            refarray = array

        # Convert to numpy arrays
        array = np.array(array)
        refarray = np.array(refarray)

        # Arrays must have same dimensions
        if array.size != refarray.size:
            raise ValueError('Arrays must be the same size. Array with size {}'
            'cannot be filtered based on array with size {}'.format(array.size,
            refarray.size))
            return array

        return array[~np.isnan(refarray)]



class Plot(QObject):
    progressed = QtCore.pyqtSignal(int)
    processEvent = QtCore.pyqtSignal(str)

    def __init__(self, gui, quantity, type):
        self.gui = gui

        # Config
        config = gui.config['Plots']
        self.dpi = config['dpi']
        # If this value is 1 then averaged values are
        # no nans if one or more of the values used to calculate it is a nan
        # This setting is ignored if all values to be averaged over are nans
        self.ignoreNans = config['ignoreNans']
        self.defaultProbes = config[type.capitalize()]['defaultProbes']

        # Attributes
        self.region = str(gui.comboRegion.currentText())
        self.segment = str(gui.comboSegment.currentText())
        self.quantity = quantity
        self.ELMonsets = gui.ELMonsets
        self.ELMends = gui.ELMends
        self.ELMmaxima = gui.ELMmaxima
        self.ELMtoELM = gui.ELMtoELM
        self.data = {}
        self.times = {}
        self.rawdata = {}
        self.plots = {}
        self.scatters = {}
        self.probeNames = []
        self.CELMAs = []
        self.realtime = 0
        self.realdtrange = [0,0]
        self.dtime = []
        self.fit = None
        self.fitColor = 'black'
        self.fitNum = 1000
        self.probes = []
        self.CELMAexists = False
        self.fits = []
        self.LSCshot = gui.LSCshot
        self.saveDir = '.'
        self._CELMAnormalize = False
        self.pertinent = False

        self.fig = Figure(dpi=self.dpi)
        self.axes = self.fig.add_subplot(111)
        self.canvas = ToolFigureCanvas(self.fig)

        self.toolbar = NavigationToolbar(self.canvas, gui)
        self.toolbar.hide()

        # This does not work when using self.save. Weird!
        self.canvas.saveClicked.connect(
                functools.partial(self.gui.savePlot, self))
        self.canvas.editClicked.connect(self.toolbar.edit_parameters)
        self.canvas.optionsClicked.connect(self.toolbar.configure_subplots)

        self.axes.get_xaxis().get_major_formatter().set_useOffset(False)
        self.canvas.mpl_connect('motion_notify_event',
                                functools.partial(self.gui.showCoordinates,
                                                  self))

    #def saveMe(self):
    #    print "Saving plot"
    #    type = self.type
    #    quantity = self.quantity

    #    if self.CELMAexists:
    #        start = '{:.4f}'.format(float(self.gui.editCELMAstartTime))
    #        end = '{:.4f}'.format(float(self.gui.editCELMAendTime))
    #    else:
    #        start, end = self.axes.get_xlim()
    #        start = '{:.4f}'.format(start)
    #        end = '{:.4f}'.format(end)

    #    if self.CELMAexists:
    #        CELMAprobes = [p.name for p in self.probes if p.CELMA]
    #    else:
    #        CELMAprobes = [p.name for p in self.probes 
    #                       if p.isVisible(self.canvas)]
    #    if len(CELMAprobes) > 1:
    #        probeName = 'multiple'
    #    elif len(CELMAprobes) == 1:
    #        probeName = probes[0]
    #    else:
    #        probeName = 'None'

    #    if self.gui.cbCELMAnormalize.isChecked():
    #        mode = 'normalized'
    #    else:
    #        mode = 'default'

    #    syncedBy = '_syncedBy' + str(self.gui.comboELMcompare.currentText())
    #    extension = '.svg'

    #    if self.CELMAexists:
    #        fileName = '_'.join([type, quantity, 'CELMA', start, end, probeName,
    #                            mode, syncedBy])
    #    else:
    #        fileName = '_'.join([type, quantity, start, end, probeName, mode,
    #                            syncedBy])
    #    fileName += extension

    #    print "Saving to file", fileName

    #    filePath = QtGui.QFileDialog.getSaveFileName(
    #                                parent=self.gui,
    #                                caption="Save figure as",
    #                                directory=os.path.join(self.saveDir,fileName),
    #                                filter="PNG (*.png);;EPS (*.eps);;SVG (*.svg)",
    #                                selectedFilter='{SVG} (*.{svg})')
    #    if os.path.isfile(filePath):
    #        _, fmt = os.path.splitext(filePath)
    #        self.fig.savefig(filePath, format=fmt)
    #        self.saveDir = os.path.dirname(fileName)
    #        logging.info("{} {} plot saved to {}".format(
    #                            self.type, self.quantity, filePath))


    def attributeProbePositions(self):
        for probe in self.probes:
            probeName = probe.name
            pos = self.LSCshot(probeName)['Ort'].data/1000.
            logging.info("\nProbe {} has position s = {}".format(probeName, pos))
            probe.position = pos
        

    def memorizeView(self):
        _xlim = self.axes.get_xlim()
        _ylim = self.axes.get_ylim()
        self._view = (_xlim,_ylim)


    def reinstateView(self):
        try:
            _xlim, _ylim = self._view
        except (AttributeError, RuntimeError):
            print "ERROR: View has to be memorized before it can be reinstated"
            logging.critical("ERROR: View has to be memorized before it can be reinstated")
            return

        self.axes.set_xlim(_xlim)
        self.axes.set_ylim(_ylim)

        # Delete view to be sure it doesn't linger around and causes unexpected
        # behavior. It's better to get an error message
        del self._view


    def shareWisdom(self, fromAx, toFig, toAx):
        """
        Populates `fig` and `ax` with what is currently visible in the figure.
        This is necessary because the matplotlib community actively combats any
        way to share an existing axes object with another figure.
        """
        for line in fromAx.lines():
            xdata = line.get_xdata()
            ydata = line.get_ydata()
            newLine = toAx.plot(xdata, ydata)
            for attr in dir(line):
                try:
                    mpl.artist.getp(line,attr)
                except:
                    continue
                else:
                    mpl.artist.setp(newline,attr=value)
                

    def viewAll(self):
        """ Sets view so that all visible plots and scatter plots are fully
        displayed. 
        """
        xmax = -float('inf')
        xmin = float('inf')
        ymax = -float('inf')
        ymin = float('inf')
        for line in self.axes.lines:
            if line.get_visible():
                if not self.isVline(line):
                    x = line.get_xdata()
                    y = line.get_ydata()
                    xmax = max(xmax, max(x))
                    xmin = min(xmin, min(x))
                    ymax = max(ymax, max(y))
                    ymin = min(ymin, min(y))

        for scatter in self.axes.collections:
            if scatter.get_visible():
                offsets = scatter.get_offsets()
                x = [_x for _x, _y in offsets]
                y = [_y for _x, _y in offsets]
                xmax = max(xmax, max(x))
                xmin = min(xmin, min(x))
                ymax = max(ymax, max(y))
                ymin = min(ymin, min(y))
            
        self.axes.set_xlim((xmin,xmax))
        self.axes.set_ylim((ymin,ymax))


    def isVline(self, line):
        x = line.get_xdata()
        try:
            float(x)
        except TypeError:
            pass
        else:
            return True
        # np.ndarrays have len() too
        #try:
        #    x.size
        #except AttributeError:
        #    pass
        #else:
        #    if x.size == 2 and x[0]==x[1]:
        #        return True
        #    else:
        #        return False
        try:
            len(x)
        except TypeError:
            pass
        else:
            if len(x) == 2 and x[0]==x[1]:
                return True
            else:
                return False
        # If type could not be specified, ignore this thing
        return True


    def clearCELMA(self):
        for CELMA in self.CELMAs:
            try: CELMA.remove()
            except ValueError,e:
                print "Could not remove CELMA {} in {} plot"\
                        .format(CELMA,self.type)
                logging.error("Could not remove CELMA {} in {} plot"\
                        .format(CELMA,self.type))
            except AttributeError:
                pass
        self.CELMAexists = False
        self.CELMAs = []

        for fit in self.fits:
            try:
                fit.remove()
            except AttributeError:
                pass
        self.fits = []

        self.showArtists()
        if self.type=='temporal':
            self.changeTickLabels('seconds')
            self.clearPOImarkers()

    
    def updateColors(self):
        """
        This function should be invoked after the probes were attributed new
        colors so that already plotted graphs adopt the new setting.
        """
        if self.type == 'spatial':
            for probeName, scatter in self.scatters.iteritems():
                color = next((p.color for p in self.probes if p.name == probeName), None)
                mpl.artist.setp(scatter,color=color)
        elif self.type == 'temporal':
            for probeName, line in self.plots.iteritems():
                color = next((p.color for p in self.probes if p.name == probeName), None)
                mpl.artist.setp(line,color=color)
        self.canvas.draw()


    def hideArtists(self, exceptFor=[]):
        """
        Sets all lines and collections to not visible
        """
        # Never hide fits or strikline marker
        if hasattr(self, 'fit') and self.fit is not None:
            exceptFor.append(self.fit)
        if hasattr(self, 'strikeline'):
            exceptFor.append(self.strikeline)
        if hasattr(self, 'fits'):
            exceptFor.extend(self.fits)

        for line in self.axes.lines:
            if line not in exceptFor:
                line.set_visible(False)
        for scatter in self.axes.collections:
            if scatter not in exceptFor:
                scatter.set_visible(False)


    def showArtists(self):
        """
        Sets all lines and collections to visible
        """
        for line in self.axes.lines:
            line.set_visible(True)
        for scatter in self.axes.collections:
            scatter.set_visible(True)


    def averagesInBins(self, n, x, y, avgMethod=None, noZeros=False):
        """
        Creates `n` bins in which the averages of `x`and `y` are respectively
        calculated. If noZeros is true, averages evaluating to zero will be
        filtered. Expects arrays to be ordered by x
        """
        if avgMethod is None:
            avgMethod = self.avgMethod

        try:
            _avgfunc = getattr(np, avgMethod)
        except AttributeError:
            logging.error("Invalid average method. Use a numpy method."+\
                            " Continuing with np.median")
            _avgFunc = np.median
            
        x = Conversion.removeNans(x,y)
        y = Conversion.removeNans(y)

        bins = np.linspace(min(x),max(x),n+1)
        avgs = np.zeros(len(bins)-1)
        t = np.zeros(len(bins)-1)
        
        for i, (left, right) in enumerate(zip(bins[:-1],bins[1:])):
            t[i] = (left + right)/2
            ind = np.where((left <= x) & (x <=right))[0]
            if len(y[ind]) == 0:
                logging.warn("{} {} plot: No data points in bin {} [{},{}]"
                             .format(self.type, self.quantity, i+1, left, right))
                avgs[i] = 0
            else:
                avgs[i] = _avgfunc(y[ind])

        avgs = avgs[t.argsort()]
        t = t[t.argsort()]

        if len(avgs) == 0:
            logging.error("No averages found")
            return

        if noZeros:
            t = t[avgs!=0]
            avgs = avgs[avgs!=0]

        return t, avgs


    def clear(self):
        """
            Removes all graphs and legends from the plot. Less intrusive than
            reset() since no data is discarded. Axes limits are not retained,
            however.
        """
        self.axes.clear()
        for legend in self.fig.legends:
            try:
                legend.remove()
            except ValueError: pass

    
    def reset(self):
        """ 
            Resets all data-related plot attributes so the plot looks like it
            was just initialized. The plot 'forgets' all its data and drawn lines.
            The plot axes are cleared but the axes limits are retained. reset()
            should always be called before init() is called if it is not the
            first init call
        """ 
        self.data = {}
        self.times = {}
        self.rawdata = {}
        self.plots = {}
        self.scatters = {}
        self.probes = []
        self.probeNames = []
        # For some utterly elusive reason, when using this solution five of the
        # old 11 plots pop up again when the plot is updated (e.g. when the
        # slider is moved). Quite upsetting -.-
        #for l in self.axes.lines:
        #        l.remove()
        #for s in self.axes.collections:
        #        s.remove()
        #self.axes.draw_artist(self.axes.patch)
        #self.canvas.update()

        xlim = self.axes.get_xlim()
        self.axes.clear()
        self.axes.set_xlim(xlim)


    def getShotData(self):
        """
        Reads data and timestamps from shotfile and outputs a congregated
        rawdata array of the format rawdata[probeName]['data'/'time']
        """
        #self.processEvent.emit(
        #        'Fetching interpreted {} data'.format(self.quantity))

        signalNames = self.shot.getSignalNames()

        # Count number of signals to be loaded to accurately show progress in widget
        probes = [s.split('-')[-1] for s in signalNames 
                                    if s.startswith(self.quantity) 
                                    and s.split('-')[-1][:2] == self.region]
        signalNum = len(probes)

        # Load signals into array
        initProg = self.gui.progBar.value()
        progress = initProg
        rawdata = {}
        for probe in probes:
            signal = self.quantity + '-' + probe
            try:
                data = self.shot(signal).data
                time = self.shot(signal).time
            except Exception, e:
                print "Signal {} cannot be read and is skipped. Message: "\
                        .format(signal) + str(e)
                logging.info("Signal {} cannot be read and is skipped. Message: "\
                        .format(signal) + str(e))
            else:
                if probe not in rawdata:
                    rawdata[probe] = {}
                rawdata[probe]['data'] = data
                rawdata[probe]['time'] = time

                self.createProbe(probe)
                print "Successfully read signal", signal
                logging.info("Successfully read signal {}".format(signal))
                progress += (30-initProg)/signalNum
                #self.progressed.emit(progress)

        self.probes.sort(key = lambda x: x.name)

        return rawdata


    def createProbe(self, probeName):
        """
        Checks if the probe object with the specified probe name already
        exists and if it's supposed to be selected. Creates probe object if it
        doesn't exist yet and selects it if it's supposed to.
        
        Expects:
            <string>    probe:  name of probe to be checked

        Returns:
            None
        """
        isDefault = probeName[-1] in self.defaultProbes \
                    or self.defaultProbes[0] == 'all'

        # See if probe already exists and select it if it's supposed to be
        for p in self.probes:
            if p.name == probeName:
                if isDefault:
                    p.setSelected(self.canvas, True)
                return

        # If probe does not exist yet, create it and select it if it's supposed
        # to be
        p = LangmuirProbe(probeName)
        if isDefault:
            p.setSelected(self.canvas, True)
        self.probes.append(p)
        self.probeNames.append(p.name)


    def getTimeArray(self, shot=None, timeArrays=None):
        if shot is None and timeArrays is None:
            print "Either shot or an array of time arrays must be provided"
            logging.critical( "Either shot or an array of time arrays must be provided")
            return
        if timeArrays is None or len(timeArrays) == 0:
            # This will NOT work for LSF since getSignalNames returns an empty
            # list -.-  --> provide array of time arrays in this case
            timeArrays = []
            for obj in shot.getSignalNames():
                isRightQuantity = obj.startswith(self.quantity)
                isRightRegion = obj.split('-')[1][:2] == self.region

                if isRightQuantity and isRightRegion:
                    try:
                        timeArrays.append(shot.getTimeBase(obj))
                    except:
                        print "Failed to retrieve time base for signal", obj
                        logging.warn("Failed to retrieve time base for signal", obj)
            if len(timeArrays) == 0:
                print "Failed to find any time arrays for these signals"
                logging.critical( "Failed to find any time arrays for these signals")
                return

        equal = (np.diff(
                    np.vstack(timeArrays).reshape(len(timeArrays), -1),
                    axis = 0) == 0).all()

        if not equal:
            print "Warning: time base arrays fetched from shotfile are not"+\
                    " equal! Proceed with caution."
            logging.error("Warning: time base arrays fetched from shotfile are not"+\
                    " equal! Proceed with caution.")
        return timeArrays[0]



class SpatialPlot(Plot):
    """ Class for spatial temperature and density plots. Subclass of Plot. Needs the application object as an argument to be able to manipulate GUI elements. """
    ### TO DO
    #
    # - rztods should save relative positions with timestamps to rule out
    #   mismatches when plotting
    # - In update(), proper scaling of the scatter is achieved by adding
    #   a plot, rescaling, and removing that plot. A more elegant solution is
    #   desirable
    #
    progressed = QtCore.pyqtSignal(int)
    processEvent = QtCore.pyqtSignal(str)


    def __init__(self, gui, quantity):
        super(SpatialPlot, self).__init__(gui, quantity, 'spatial')

        config = gui.config['Plots']['Spatial']
        self.coloring = config['coloring']
        self.defaultColor = config['defaultColor']
        self.posFile = config['positionsFile']
        self.fixyLim = config['fixyLim']
        self.fitMethod = config['fitMethod']
        self.avgNum = config['avgNum']
        self.CELMAfacecolor = config['CELMA']['facecolor']
        self.showCELMAAvg = config['CELMA']['showAverages']
        self.CELMAalpha = config['CELMA']['alpha']
        self.detachedFit = config['detachedFit']

        self.scatters = {}
        self.quantities = {
                'te': 'Temperature',
                'ne': 'Density',
                'jsat' : 'Saturation current density'
                }
        self.axLabels = {
                'te': 'T$_{e,t}$ [eV]',
                'ne': 'n$_{e,t}$ [1/m$^3$]',
                'jsat': 'j$_{sat}$ [kA/m$^2$]'
                }

        self.type = 'spatial'
        self.timeRange = []
        self.fits = []

        self.Rsl = self.gui.Rsl
        self.ssl = self.gui.ssl
        self.zsl = self.gui.zsl

        self.strikeline = self.axes.axvline(
                            0,0,1,ls='--',lw='4',color='grey', alpha=.7,
                            label = 'Strikeline')
        
        self.quantity = quantity
        self.timeArray = self.gui.timeArray
        quantName = self.quantities[quantity]

        # Set axes labels
        self.axes.set_title("{} distribution on the outer lower target plate".format(quantName))
        self.axes.set_ylabel(self.axLabels[quantity])
        self.axes.set_xlabel("$\Delta$s [cm]")

        # Hide axes offsets
        self.axes.yaxis.get_offset_text().set_visible(False)
        self.axes.xaxis.get_offset_text().set_visible(False)

        def centimeter(val, pos):
            return "{}".format(val*100)
        fmt = mpl.ticker.FuncFormatter(centimeter)
        self.axes.xaxis.set_major_formatter(fmt)
        
        if not isinstance(self, CurrentPlot):
            self.shot = gui.LSDshot


    def init(self, time, range):
        """
        If this is a CurrentPlot, data is calibrated once when it is loaded and
        saved to self.rawdata.
        """
        self.rawdata = self.getShotData()
        self.attributeProbePositions()
        if isinstance(self, CurrentPlot):
            self.rawdata= self.calibrateData(self.rawdata)
        data, timeRange = self.getDataInTimeWindow(self.rawdata, time, range)
        self.timeRange = timeRange
        #positions = self.getProbePositions()
        #positions = self.rztods(positions, timeRange)
        positions = self.getDeltaS(timeRange)
        data, positions = self.averageData(data, positions)

        self.initPlot(data, positions)

        if self.fitting:
            self.plotFit()


    def createCompareAxes(self):
        self.compareAx = plot.axes.twinx()
        self.comparePlots = {}


    def removeCompareAxes(self):
        self.compareAx.remove()
        self.compareAx = None
        self.comparePlots = {}


    def addComparePlot(self, time, data, color):
        p, = self.compareAx.plot(time, data, alpha=0.3, lw=2, ls='--', color=color)
        plot.comparePlots[probe] = p


    def coherentELMaveraging(self, start, end, ELMnumber, POIrelative, range,
            unit, marker=None, color=None, multiplePOIs=False, fitting=True,
            facecolor=None, ignore=[]):
        """
        Performs an average over a specified amount of ELMs at a point of
        interest relative to the ELM start time
        """
        oldLimits = self.axes.get_ylim()
        handles = []
        labels = []
        data_tot = {}
        positions_tot = {}
        showLegend = self.gui.menuShowLegend.isChecked()
        average = self.showCELMAAvg
        alpha = self.CELMAalpha

        if facecolor is None:
            facecolor = self.CELMAfacecolor

        ### Finding ELM times in range
        # Filter arrays according to passed values start, end, ELMnum
        # Pad the index array for ELMtoELM so that the (i-1)th element is
        # included in case POIrelative is negative. np.where returns tuple.
        ind = np.where((self.ELMonsets >= start) & (self.ELMonsets <= end) &
                       ~np.in1d(self.ELMonsets,ignore))
        if len(ind[0]) == 0:
            print "ERROR: No ELMs in specified range {}s-{}s".format(start,end)
            logging.critical("No ELMs in specified range {}s-{}s".format(start,end))
            return
        durInd = np.pad(ind[0], (1,0), 'constant', constant_values = ind[0][0]-1)
        ELMonsets = self.ELMonsets[ind][:ELMnumber]
        ELMtoELM = self.ELMtoELM[durInd][:ELMnumber+1] 
        ELMends = self.ELMends[ind][:ELMnumber]

        # POIs at one relative location for each ELM in range [start,end]
        # If POIrelative is negative, the ELMtoELM element at index i-1
        # must be subtracted from the ELMonset element at index i
        # POIsShifted can be used in a CELMA temporal plot
        if unit == '%':
            if POIrelative > 0:
                POIs = ELMonsets + ELMtoELM[1:]*POIrelative
                POIsShifted = ELMtoELM[1:]*POIrelative
            else:
                POIs = ELMonsets + ELMtoELM[:-1]*POIrelative
                POIsShifted = ELMtoELM[:-1]*POIrelative
        elif unit == '0.1 ms':
                POIs = ELMonsets + POIrelative
                POIsShifted = np.array([POIrelative])
        POIs.sort()
        POIsShifted.sort()

        ### Data retrieval
        for POIreal in POIs:
            if POIreal not in data_tot:
                data_tot[POIreal] = {}
            if POIreal not in positions_tot:
                positions_tot[POIreal] = {}

            data, timeRange = self.getDataInTimeWindow(self.rawdata, POIreal, range)
            #positions = self.getProbePositions()
            #positions = self.rztods(positions, timeRange)
            positions = self.getDeltaS(timeRange)
            data, positions = self.averageData(data, positions)

            for probe, vals in data.iteritems():
                locs = positions[probe]
                if len(vals) != len(locs):
                    print "Number of values is not the same as number of locations."
                    logging.critical("Number of values is not the same as number of locations.")
                data_tot[POIreal][probe] = vals
                positions_tot[POIreal][probe] = locs
        
        #### Averaging
        #if average:
        #    for POI in POIs:
        #        y = np.nanmean(data_tot[POI])
        #        x = np.nanmean(data_tot[POI])
        #        scatter = self.axes.scatter(x,y, marker='*', color='black')
        #        self.CELMAs.append(scatter)

        #### Plotting
        if color is None:
            colors = cm.rainbow(np.linspace(0,1,POIs.size))
        else:
            colors = [color]*POIs.size

        for color, POI in zip(colors, POIs):
            for probe in self.probes:
                probeName = probe.name
                if not multiplePOIs:
                    probeColor = probe.color
                else:
                    probeColor = color
                
                vals = data_tot[POI][probeName]
                locs = positions_tot[POI][probeName]
                scatter = self.axes.scatter(locs, vals, color=probeColor,
                                            alpha=alpha, marker=marker,
                                            facecolor=facecolor,
                                            label='POI @{:.4f}s'.format(POI))
                self.CELMAs.append(scatter)

        #### Fitting
        if fitting:
            xdata = []
            ydata = []
            for POI, probeData in data_tot.iteritems():
                for probe, data in probeData.iteritems():
                    locs = positions_tot[POI][probe]
                    ydata.extend(list(data))
                    xdata.extend(list(locs))

            fit = self.plotFit(xdata,ydata,color=color,update=False)
            self.fits.append(fit)

        if not self.fixyLim:
            self.axes.set_xlim(-0.07,0.3)
        else:
            self.axes.set_ylim(oldLimits)

        self.canvas.draw()
        self.CELMAexists = True

        return handles, labels, POIs, POIsShifted

        ## Get data
        #j = 0
        #for i, (ton,dt) in enumerate(zip(ELMonsets, ELMtoELM)):
        #    if j < ELMnumber:
        #        if ton >= start and ton+dt <= end:
        #            if POIrelative < 0:
        #                POI = ton + ELMtoELM[i-1]*POIrelative
        #            else:
        #                POI = ton + dt*POIrelative

        #            if POI not in data_tot:
        #                data_tot[POI] = {}
        #            if POI not in positions_tot:
        #                positions_tot[POI] = {}

        #            # Data retrieval
        #            data, timeRange = self.getDataInTimeWindow(self.rawdata, POI, range)
        #            positions = self.getProbePositions(timeRange)
        #            data, positions = self.averageData(data, positions)

        #            for (probe,vals), poss in zip(data.iteritems(), positions.values()):
        #                if probe not in data_tot:
        #                    data_tot[POI][probe] = list(vals)
        #                else:
        #                    data_tot[POI][probe].extend(list(vals))
        #                if probe not in positions_tot:
        #                    positions_tot[POI][probe] = list(poss)
        #                else:
        #                    positions_tot[POI][probe].extend(list(poss))
        #            j += 1

        # Average points per probe to one data point if desired
        #if average:
        #    dataAccu = {}
        #    possAccu = {}
        #    for POI in POIs:
        #        for probe, data in data_tot[POI].iteritems():
        #            if probe not in dataAccu:
        #                dataAccu[probe] = data
        #            else:
        #                dataAccu[probe].extend(data)
        #        for probe, poss in positions_tot[POI].iteritems():
        #            if probe not in possAccu:
        #                possAccu[probe] = poss
        #            else:
        #                possAccu[probe].extend(poss)
        #    for probe, data in dataAccu.iteritems():
        #        if 'Averaged' not in data_tot:
        #            data_tot['Averaged'] = {}
        #        data_tot['Averaged'][probe] = np.nanmean(data)
        #    for probe, poss in possAccu.iteritems():
        #        if 'Averaged' not in positions_tot:
        #            positions_tot['Averaged'] = {}
        #        positions_tot['Averaged'][probe] = np.nanmean(poss)
        #    POIs.append('Averaged')

        #if color is None:
        #    colors = cm.rainbow(np.linspace(0,1,len(data_tot)))
        #else:
        #    colors = [color]*len(data_tot)
        #for color, POI in zip(colors, POIs):
        #    if POI == 'Averaged':
        #        for probe in data_tot['Averaged']:
        #            x = positions_tot['Averaged'][probe]
        #            y = data_tot['Averaged'][probe]
        #            self.CELMAs.append( self.axes.scatter(x,y, marker='*',
        #                color='black') )
        #    else:
        #        # Draw the CELMA for each POI
        #        for probe, vals in data_tot[POI].iteritems():
        #            poss = positions_tot[POI][probe]
        #            scatter = self.axes.scatter(poss, vals, color=color,
        #                alpha=alpha, marker=marker)
        #            self.CELMAs.append(scatter)
        #    if not multiplePOIs:
        #        handles.append(self.CELMAs[-1])
        #        labels.append(POI)

        #if multiplePOIs:
        #    proxy = mpl.patches.Patch(color=color)
        #    handles.append(proxy)
        #    labels.append('CELMA @{}%'.format(int(POIrelative)))

        #if fitting:
        #    xdata = []
        #    ydata = []
        #    for POI, data in data_tot.iteritems():
        #        if POI != 'Averaged':
        #            for probe, probeData in data.iteritems():
        #                ydata.extend(probeData)
        #                xdata.extend(positions_tot[POI][probe])

        #    print "Creating CELMA fit"
        #    self.fit = self.plotFit(xdata,ydata,color=color)
        #    self.CELMAs.append(self.fit)

        #if showLegend and not multiplePOIs:
        #    self.fig.legend(labels=labels,handles=handles)

        #if not self.fixyLim:
        #    self.axes.set_xlim(-0.07,0.3)
        #else:
        #    self.axes.set_ylim(oldLimits)

        #self.canvas.draw()

        #return handles, labels


    def plotFit(self, xdata=None, ydata=None, color=None, method=None,
                        update=True):
        """ Plots a fit function to the shown data based on the Eich function

        Parameters:
        
        shiftToStrikeline: if True, the current time at which the plot is to 
              be drawn influences the fit. Then, the fit is shifted by the
              separatrix position.
        """
        if method is None:
            method = self.fitMethod
        if method == 'none':
            return
        if color is None:
            color = self.fitColor
        fit = self.fit
        detached = self.detachedFit

        result = self.findFit(xdata, ydata, method, detached=detached)
        if result is None:
            print "ERROR: Fit could not be determined"
            logging.error("Fit could not be determined")
            return

        xft, yft = result

        if not update:
            try:
                self.fit.remove()
            except: pass
            self.fit = None
            
        if hasattr(self, 'fit') and self.fit is not None:
            self.fit.set_xdata(xft)
            self.fit.set_ydata(yft)
            fit = self.fit
        else:
            fit, = self.axes.plot(xft, yft, color,
                                    label=method.capitalize()+' fit')
            # This is needed only for when the fit is first initialized: Then
            # self.fit is None and the fit must be attributed to it
            if update:
                self.fit = fit

        fit.set_visible(True)

       #     self.canvas.draw()
       # else:
       #     self.axes.draw_artist(self.axes.patch)
       #     self.axes.draw_artist(self.fit)
       #     self.canvas.update()
       #     for scatter in self.scatters.values():
       #         self.axes.draw_artist(scatter)
       #     self.canvas.update()
       #     self.canvas.flush_events()

        return fit


    def findFit(self, xdata=None, ydata=None, method=None, detached=False):
        """
        Finds fit x and y data based on passed data and method
        If no data was passed, the plots currently shown on the plot canvas
        will be used to fit.
        """
        if xdata is None or ydata is None:
            # Get currently visible data
            offsets = []
            for scatter in self.scatters.values():
                if scatter.get_visible():
                    offsets.extend(scatter.get_offsets())
            locs = np.array([el[0] for el in offsets])
            data = np.array([el[1] for el in offsets])
        else:
            xdata, ydata = zip(*sorted(zip(xdata, ydata)))
            locs = np.array(xdata)
            data = np.array(ydata)

        if data.size == 0:
            print "No data to fit"
            logging.error( "No data to fit")
            return
        
        # Sort data from "left to right"
        data = data[locs.argsort()]
        locs = locs[locs.argsort()]

        # This is necessary for scipy curve_fit to work
        locs = Conversion.removeNans(locs,data)
        data = Conversion.removeNans(data)
        
        xmin, xmax = (np.min(locs),np.max(locs))
        xft = np.arange(xmin, xmax, 1/float(self.fitNum))

        if method in ('eich','Eich'):
            # Normalize y values so curve_fit will not break because of too
            # large/small values
            scal = np.max(data)
            y = data/scal
            try:
                ft = FitFunctions.fit(locs, y, detachment=detached)
            except RuntimeError:
                logging.error("Could not find fit parameters")
                return
            else:
                if detached:
                    yft = FitFunctions.eich_model_detached(xft, *ft)
                else:
                    yft = FitFunctions.eich_model(xft, *ft)
            yft *= scal
           
        #elif method == 'Linear':
        #    n = 100
        #    xmin, xmax = self.axes.xaxis.get_view_intervall()
        #    ind = np.ma.where((locs >= xmin) & (locs <= xmax))
        #    xdata = locs[ind]
        #    ydata = data[ind]
        #    xft, yft = self.averagesInBins(n, xdata, ydata, noZeros=True)
                
        elif method in ('linear','nearest','zero','slinear','cubic','quadratic'):
            fit = interpolate.interp1d(locs, data, kind=method)
            yft = fit(xft)

        else:
            print "Unrecognized fit method", method
            logging.error("Unrecognized fit method", method)
            return
        return xft, yft


    def getDataInTimeWindow(self, rawdata, time, range):
        """ 
        Extracts data in `range` around `time` from `data`
        """
        # Let the number of data points to be averaged to one value be n and the number of averaged values to show per probe be m.
        # The time offset dt is the number of timesteps to go left and right from the current time to define the time range Dt over which to average.
        # Then the data points filtered symmetrically around the current time will be Dt = dt*2+1 in number, which should equal n*m
        #          dt   t   dt
        #       <====== | ======>
        #       * * * * * * * * *  time steps
        #       <===============>
        #              Dt
        # The time offset corresponding to n and m is then dt = k(n*m-1)/2, where k is a natural number.
        # Since Dt will always be an odd number and n and m are natural numbers, n and m both have to be odd too.

        # Convert supplied time to index
        time = Conversion.valtoind(time, self.timeArray)

        # Time range expressed by indices in shotfile
        self.dt = (range - 1)/2 

        # Min and max time expressed by indices in shotfile
        # Prevent tmin to take negative values so getting value by index
        # won't cause problems
        tmin = max(time - self.dt, 0)
        tmax = time + self.dt

        timeRange = {}
        data = {}
        for probe, probeData in rawdata.iteritems():
            # filter for specified probes
            if probe.startswith(self.region):
                
                if len(probe.split('-')) == 2:
                    probe = probe.split('-')[-1]

                dtime = probeData['time']
                _data = probeData['data']

                # Time converted to actual time values
                # If there is an index error, take the global minimum or maximum
                self.realtmin = dtime[tmin]
                try:
                    self.realtmax = dtime[tmax]
                except Exception:
                    self.realtmax = dtime[-1]
                    print("Maximum value of time range to evaluate is out " +\
                            "of range. Using maximum of available time range.")
                    logging.warning("Maximum value of time range to evaluate is out " +\
                            "of range. Using maximum of available time range.")
                try:
                    self.realtime = dtime[time]
                except IndexError:
                    print "Could not determine realtime from time array"
                    logging.warning( "Could not determine realtime from time array")
                    if time >= dtime.size: 
                        self.realtime = dtime[-1]
                    elif time < dtime.size: 
                        self.realtime = dtime[0]
                    else: 
                        print("FATAL: Realtime could not be determined.")
                        logging.critical("Realtime could not be determined!")
                
                # Filter for time range. 
                ind = np.ma.where((dtime >= self.realtmin) & (dtime <= self.realtmax))
                data[probe] = _data[ind]
                timeRange[probe] = dtime[ind]

                # Save the time data of the last probe as the global time data.
                # This assumes that all time arrays of the probes are identical
                self.dtime = dtime
                realdtminus = abs(self.realtime - self.realtmin)
                realdtplus = abs(self.realtime - self.realtmax)
                self.realdtrange = (realdtminus, realdtplus)

        return data, timeRange


    def averageData(self, data, positions):
        """ Averages data points over specified number of points. """
        # If no averaging wished, use the data as received from shotfile
        if self.avgNum == 0:
            return

        n = self.avgNum
        for probeName, probeData in data.iteritems():
            probePositions = positions[probeName]
            # Ignore nans if wished. Ignoring will ensure plot points to be
            # plotted even if one or more of its data points are NaNs
            if self.ignoreNans:
                # NaN filtering must occur before averaging instead of using
                # nanmean or location will not know which values got filtered
                # by nanmean
                probePositions = Conversion.removeNans(probePositions, probeData)
                probeData = Conversion.removeNans(probeData)
            else:
                probePositions = np.array(probePositions)
                probeData = np.array(probeData)

            probePositions = Tools.padToFit(probePositions, n, np.NAN)
            probeData = Tools.padToFit(probeData, n, np.NAN)
            
            data[probeName] = probeData.reshape(-1,n).mean(axis=1)
            positions[probeName] = probePositions.reshape(-1,n).mean(axis=1)
            
        ## Averaging
        #for probe, data in data.iteritems():
        #    locs = plotPositions[probe]
        #   
        #    # If this probe didn't record any values at this point in time, continue with the next one
        #    if data.size == 0: 
        #        continue

        #    i=0
        #    # Take values in the range 0 to avgNum-1 and average them
        #    # valcount is used to calculate average value because of the possibility of nans
        #    data_avgs = []
        #    loc_avgs = []
        #    while True:
        #        xsum=0
        #        locsum=0
        #        valcount=0

        #        for x in np.arange(self.avgNum):
        #            # Ignore nans if wished. Ignoring will ensure plot points
        #            # to be plotted even if one or more of its data points are
        #            # NaNs
        #            if self.ignoreNans and np.isnan(data[i]):
        #                pass
        #            else:
        #                xsum += data[i]
        #                locsum += locs[i]
        #                valcount += 1 
        #            i += 1

        #        # If all values were nans, ignore the result no matter what the value of ignoreNans is
        #        if valcount == 0:
        #            avg = np.NAN
        #            locavg = np.NAN
        #        else:
        #            avg = xsum/float(valcount)
        #            locavg = locsum/float(valcount)

        #        # Save averages to new array
        #        data_avgs.append(avg)
        #        loc_avgs.append(locavg)

        #        # End loop if end of data array will be reached next time
        #        if i + self.avgNum > data.size: 
        #            break
        #    
        #    self.data[probe] = np.array(data_avgs)
        #    self.plotPositions[probe] = np.array(loc_avgs)
        return data, positions


    def getDeltaS(self, timeRange):
        """
        Reads the s coodrinates of probes directly from LSC and the
        s-coordinate of the strikeline from FPG. Calculates ds for each probe
        and returns it in a dictionary.
        """
        ds = {}
        for probe in self.probes:
            probeName = probe.name
            ds[probeName] = []
            for time in timeRange[probeName]:
                ind = np.abs((self.ssl['time'] - time)).argmin()
                ssl = self.ssl['data'][ind]
                _ds = probe.position - ssl

                ds[probeName].append(_ds)
        return ds


    def getProbePositions(self):
        """ 
        Gets positions of probes in the specified region in terms of R,z
        coordinates. Saves the coordinates as tuples in a class parameter array
        "probePositions" with the probe names as keys. 
        """
        # Read probe name and R and z coordinates of each probe
        probePositions = {}
        with open(self.posFile) as f:
            lines = f.readlines()
            for line in lines:
                probeName = line.split()[0][1:]                 # Probe name
                R = float(line.split()[1].replace(",","."))     # R
                z = float(line.split()[2].replace(",","."))     # z
                 
                probePositions[probeName] = (R,z)

        self.probePositions = probePositions

        logging.info("Probe positions:")
        for probe, position in probePositions.iteritems():
            logging.info("{}: {}".format(probe, position))

        return probePositions


    def rztods(self, positions=None, timeRange=None):
        """ 
        Converts probe positions from (R,z) coordinates to delta-s coordinate
        based on current strikeline position. This enables plots in units of
        delta-s along the x-axis. It is implicitly assumed that the divertor
        tile is flat.
        """
        if positions is None:
            positions = self.probePositions
        if timeRange is None:
            timeRange = self.timeRange

        plotPositions = {}
        for probe in self.probes:
            probeName = probe.name
            plotPositions[probeName] = []

            # Get R and z coordinates of probe
            R_p = positions[probeName][0]
            z_p = positions[probeName][1]

            for time in timeRange[probeName]:
                # Get R and z coordinates of strikeline at this point in time
                # Finding the index of the time value closest to the current
                # time is less prone to errors than trying to find the exact
                # value
                ind_R = np.abs((self.Rsl['time'] - time)).argmin()
                R_sl = self.Rsl['data'][ind_R]
                ind_z = np.abs((self.zsl['time'] - time)).argmin()
                z_sl = self.zsl['data'][ind_z]

                # Throw error if timestamps don't match
                if self.zsl['time'][ind_z] != self.Rsl['time'][ind_R]:
                    print('++++CRITICAL++++\n\nTried to find timestamps of\
                            strikeline R and z measurements at times closest\
                            to {} in the respective shot file data but the\
                            found values for R and z don\'t match! Data\
                            evaluation will not be reliable.')
                    logging.critical('\n\nTried to find timestamps of\
                            strikeline R and z measurements at times closest\
                            to {} in the respective shot file data but the\
                            found values for R and z don\'t match! Data\
                            evaluation will not be reliable.')

                # Calculate delta-s
                # Assumption: divertor tile is flat
                ds = np.sqrt( (R_sl-R_p)**2 + (z_sl-z_p)**2 ) 
                # If the z coordinate of the probe is smaller than that of the
                # strikeline, 
                # then the delta-s associated with this probe at this time is
                # negative
                if z_p < z_sl: ds = -ds

                plotPositions[probeName].append(ds)

        self.plotPositions = plotPositions

        return plotPositions


    def initPlot(self, data, positions):
        """ Populates canvas with initial plot. Creates PathCollection objects that will be updated when plot has to change based on GUI interaction."""
        if data is None:
            data = self.data
        if positions is None:
            positions = self.positions
            
        for probeName in data:
            x = []
            y = []
            for value, position in zip(data[probeName], positions[probeName]):
                x.append(position)
                y.append(value)

            # Use different color for each probe if wished
            if self.coloring:
                color = next((p.color for p in self.probes if p.name == probeName), None)
            else:
                color = self.defaultColor

            # Plot
            self.scatters[probeName] = self.axes.scatter(x, y, color=color,
                                                            label=probeName)

            probe = next((p for p in self.probes if p.name == probeName), None)
            probe.setPlotted(self.canvas, True)

        # Add text box showing the current time
        #self.updateText()
        self.updateAxesLabels()
        
        self.axes.set_xlim(-0.07,0.3)

    
    def saveData(self):
        data = []
        for s in self.scatters.values():
            data.extend(s.get_offsets())

        with open('spatialData.p','wb') as f:
            pickle.dump(data, f)
        self.gui.statusbar.showMessage("Spatial data saved to spatialData.p", 3000)


    def updateText(self):
        """ Updates the figure text and its position according to the current
        time"""
        t = self.realtime
        dt = (self.realdtrange[0] * 10**6, 
              self.realdtrange[1] * 10**6)

        text = r"$@{0:.7f}s^{{+{1:.1f}\mu s}}_{{-{2:.1f}\mu s}}$".format(t,
                dt[0], dt[1])
     
        if not len(self.axes.texts):
            self.axes.text(0.7, 0.9, text, 
                            ha='left', va='center',
                            transform=self.axes.transAxes)
        else:
            self.axes.texts[0].set_text(text)
        
        if self.fixyLim:
            try:
                self.axes.draw_artist(self.axes.texts[0])
            except:
                pass
            else:
                self.canvas.update()
                self.canvas.flush_events()
        else:
            self.canvas.draw()
    

    def updateAxesLabels(self):
        """ Updates axes labels with current offsets. """
        oldyLabel = self.axes.get_ylabel()
        yOffsetText = self.axes.yaxis.get_offset_text().get_text()

        # Make offset text pretty
        if 'e' in yOffsetText:
            yOffsetText = yOffsetText.replace('e','0$^{') + '}$'

        # Add unit to label
        if len(oldyLabel.split()) > 1: 
            newyLabel = oldyLabel.split()[0] + ' ' \
                        + yOffsetText + ' ' + oldyLabel.split()[-1]
        else:
            newyLabel = oldyLabel
        self.axes.set_ylabel(newyLabel)


    def update(self, time):
        """ Updates scatter plots based on the current time. If y-axis is
        fixed, only the background and the scatter plots are updated with
        a succeding call of ax.update() which considerably improves
        performance. If the y-axis is not fixed, the whole canvas is
        re-drawn."""
        range = self.gui.Dt
        data, timeRange = self.getDataInTimeWindow(self.rawdata, time, range)
        self.timeRange = timeRange
        #pos = self.rztods(self.probePositions, timeRange)
        pos = self.getDeltaS(timeRange)
        data, pos = self.averageData(data, pos)
        self.data = data
        self.pos = pos
        #if isinstance(self, CurrentPlot):
        #    data = self.calibrateData(data)

        xtot = []
        ytot = []
        for probeName, scatter in self.scatters.iteritems():
            x = []
            y = []
            for value,position in zip(data[probeName], pos[probeName]):
                x.append(position)
                y.append(value)
                xtot.append(position)
                ytot.append(value)
             
            newdata = [list(t) for t in zip(x,y)]
            scatter.set_offsets(newdata)

        # Only update changing artists if axes are fixed
        if self.fixyLim:
            # Background
            self.axes.draw_artist(self.axes.patch)
            # Fit
            if self.fit is not None:
                self.axes.draw_artist(self.fit)
            # Strikeline
            self.axes.draw_artist(self.strikeline)
            # Scatter plots
            for scatter in self.scatters.values():
                self.axes.draw_artist(scatter)
            self.canvas.update()
            self.canvas.flush_events()

        # Re-draw everything if axes are not fixed
        else:
            plot, = self.axes.plot(xtot,ytot, label='Dummy for rescaling')
            self.axes.relim()
            self.axes.autoscale()
            self.axes.set_xlim(-0.07,0.3)
            plot.remove()
            self.updateAxesLabels()
            self.canvas.draw()
            

    def toggleProbe(self, probe, vis):
        """ Toggle probes to show in scatter plot. """
        print "Toggling probe", probe
        for p in self.probes:
            if p.name == probe:
                p.setSelected(self.canvas, vis)
                p.setVisible(self.canvas, vis)
                break
        scatter = self.scatters[probe]
        scatter.set_visible(vis)



class TemporalPlot(Plot):
    """ Class for temporal temperature and density plots. Subclass of Plot.
    Needs the application object as an argument to be able to manipulate GUI
    elements and the quantity that is to be plotted. """
    #######
    # To do:
    #
    # - Original axes limits are overwritten when zoomed in and updating plot by (un)checking a probe. When zoomed in, zoom level should be retained but the new maximum/minimum values should be saved for "resetting"
    #
    progressed = QtCore.pyqtSignal(int)
    processEvent = QtCore.pyqtSignal(str)


    def __init__(self, gui, quantity):
        Plot.__init__(self, gui, quantity, 'temporal')

        config = gui.config['Plots']['Temporal']
        self.axTitles = config['axTitles']
        self.showGaps = config['showGaps']
        self.rescaling = config['rescale-y']
        self.avgNum = config['avgNum']
        self.marker = config['marker']
        self.CELMApad = config['CELMA']['padding']
        self.CELMAalpha = config['CELMA']['alpha']
        self.CELMAbinNumber = config['CELMA']['binNumber']
        self.CELMAcolor = config['CELMA']['color']
        self.CELMAavgColor = config['CELMA']['averagedCurveColor']
        self.CELMAmarker = config['CELMA']['marker']
        self.avgMethod = config['CELMA']['avgMethod']
        self.CELMAnormalize = False
        self.type = 'temporal'
        self.ELMmarkers = {}
        self.shot = gui.LSDshot
        self.POImarkers = []
        self._CELMAnormalize = False

        # Set axes labels
        self.axes.set_ylabel(self.axTitles[self.quantity])

        self.changeTickLabels('seconds')
        #self.fig.canvas.mpl_connect('pick_event', self.showAnnotation)


    #def showAnnotation(self, event):
    #    artist = event.artist
    #    for marker in self.POImarkers:
    #        if marker.contains(event)[0]:
    #            label = artist.get_label()
    #            x = event.xdata
    #            y = event.ydata

    #            self.axes.annotate(label, xy=(x,y), xytext=(10,10),
    #                                textcoords='offset points')



    def init(self, time, range):
        # time, range, and fitting are only passed to keep consistency with
        # SpatialPlot
        rawdata = self.getShotData()
        if isinstance(self, CurrentPlot):
            rawdata = self.calibrateData(rawdata)
        data, times = self.splitRawData(rawdata)
        self.dataCalib = data
        self.timesCalib = times
        data, times = self.averageData(data, times)
        self.data = data
        self.times = times
        self.update()
        
        color = self.gui.config['Indicators']['color']
        self.indicator = Indicator(self, color)

        #self.axes.callbacks.connect('xlim_changed', self.setSliderRange)
        self.axes.callbacks.connect('ylim_changed', self.rescaleyAxis)


    def clearPOImarkers(self):
        for marker in self.POImarkers:
            marker.remove()
        self.POImarkers = []


    def splitRawData(self, rawdata):
        """
        Splits rawdata into two arrays, the one holding the data and the other
        holding the times.

        Receives:
            list    rawdata     Two-dimensional array of the format
                                data[probe]['data'/'time']

        Returns:
            list    data        1D array holding data
            list    times       1D array holding time
            
        TemporalPlot uses the same getShotData functions to get the rawdata as
        SpatialPlot instances. Those feed the rawdata into getDataInTimeWindow,
        which does, amongst other things, the job of this function: splitting
        the rawdata format 'data[probe]['time'/'data'] into two seperate arrays
        with the form data[probe] and times[probe]. This is necessary since
        other functions, such as calibrateData() need the data in this
        format"""
        data = {}
        times = {}
        for probe, probeData in rawdata.iteritems():
            data[probe] = probeData['data']
            times[probe] = probeData['time']
        
        return data, times


    def rescaleyAxis(self, event):
        """
        Rescales yaxis to better resolve data and keep all lines completely
        visible in y-direction if TemporalPlot.rescaling is True.
        """
        if self.rescaling:
            xmin, xmax = self.axes.xaxis.get_view_interval()
            data = []
            for line in self.axes.lines:
                if self.isVline(line):
                    continue
                if line.get_visible():
                    xdata = line.get_xdata()
                    ydata = line.get_ydata()
                    # This is necessary in case self.showGaps is true since
                    # then there will be NaNs in the data causing problems with
                    # comparison operations
                    xdata = Conversion.removeNans(xdata,ydata)
                    ydata = Conversion.removeNans(ydata)
                    ind = np.where( (xmin <= xdata) & (xdata <= xmax))[0]
                    data.extend(list(ydata[ind]))

            if len(data) == 0:
                return
            miny, maxy = [min(data), max(data)]

            if miny > 0:
                miny *= 0.95
            else:
                miny *= 1.05
            if maxy > 0:
                maxy *= 1.05
            else:
                maxy *= 0.95

            ylimits = (miny, maxy)
                
            self.axes.set_ylim(ylimits, emit=False)


    def averageData(self, data=None, time=None):
        """ Averages data for selected probes if average data does not exist for them yet. """
        if data is None:
            data = self.dataCalib
        if time is None:
            time = self.timesCalib

        n = self.avgNum
        print "Averaging temporal data over {} adjacent values".format(n)
        logging.info("Averaging temporal data over {} adjacent values".format(n))
        for probeName in data:
            #########################################
            # Add ignoreNans check
            data[probeName] = Tools.padToFit(data[probeName], n, np.NAN)
            time[probeName] = Tools.padToFit(time[probeName], n, np.NAN)
            data[probeName] = data[probeName].reshape(-1,n).mean(axis=1)
            time[probeName] = time[probeName].reshape(-1,n).mean(axis=1)

        return data, time


    def changeTickLabels(self, unit):
        if unit == 'seconds':
            def seconds(val, loc):
                return "{}s".format(val)
            fmt = mpl.ticker.FuncFormatter(seconds)
            self.axes.xaxis.set_major_formatter(fmt)

        elif unit == 'milliseconds':
            def milliseconds(val, loc):
                return "{}ms".format(val*1000)
            fmt = mpl.ticker.FuncFormatter(milliseconds)
            self.axes.xaxis.set_major_formatter(fmt)

        elif unit == 'percent':
            def percent(val, loc):
                return "{}%".format(val*100)
            fmt = mpl.ticker.FuncFormatter(percent)
            self.axes.xaxis.set_major_formatter(fmt)


    def updateAveraging(self, avgNum):
        self.avgNum = avgNum
        self.data, self.times = self.averageData()
        self.update()


    def update(self, showGaps=None, marker=None):
        """ Plots temporal data if it hasn't been plotted yet. If it has been plotted, it is set to visible. """
        if marker is None:
            marker = self.marker
        if showGaps is None:
            showGaps = self.showGaps
        if len(self.data) == 0:
            print "Error: No data to update"
            logging.critical( "Error: No data to update")
            return
        if len(self.probes) == 0:
            print "Error: No probes to update"
            logging.critical( "Error: No probes to update")
            return

        visible = False
        plotted = False
        selected = False
        draw = False
        # Update plots
        for probeName in self.data: 
            probe = next((p for p in self.probes if p.name == probeName), None)
            selected = probe.isSelected(self.canvas)
            plotted = probe.isPlotted(self.canvas)
        
            if plotted:
                line = self.plots[probeName]
                visible = line.get_visible()
                if marker != mpl.artist.getp(line,'marker'):
                    mpl.artist.setp(line, marker=marker)
                    draw = True
            
            # If probe hasn't been plotted yet, is selected, plot it
            if not plotted and selected:
                #print("{} hasn't been plotted yet".format(probeName))
                y = self.data[probeName]
                x = self.times[probeName]

                # Filter NaNs if wished
                if showGaps == False:
                   x = Conversion.removeNans(x,y) 
                   y = Conversion.removeNans(y) 

                # Plot data
                color = probe.color
                plot, = self.axes.plot(x,y, color=color, marker=marker,
                                        label=probeName)
                
                probe.setPlotted(self.canvas, True)
                probe.setVisible(self.canvas, True)

                # Save artist for future reference
                self.plots[probeName] = plot
                draw = True

            # If probe has been plotted, is not selected, and is visible, hide it
            elif plotted and not selected and visible:
                #print("Setting probe {} invisible".format(probeName))
                self.plots[probeName].set_visible(False)
                probe.setVisible(self.canvas, False)
                draw = True

            # If probe has been plotted, is selected, and is hidden, show it
            elif plotted and selected and not visible:
                #print("Setting probe {} visible".format(probeName))
                self.plots[probeName].set_visible(True)
                probe.setVisible(self.canvas, True)
                draw = True

        if draw:
            self.canvas.draw()

        # Get current axes limits
        xlim = self.axes.get_xlim()
        ylim = self.axes.get_ylim()


    def coherentELMaveraging(self, start, end, ELMnum, probe, normalize=None, color=None,
                            avgColor=None, alpha=None, binning=False,
                            binNumber=None, compare=None, marker=None,
                            pad=None, ignore=[], avgMethod=None, lw=1):
        logging.info("\nELM-synchronizing temporal {} signal".format(self.quantity))
        logging.info("From {}s to {}s".format(start,end))
        logging.info("Taking at most {} ELMs into account".format(ELMnum))

        if pad is None:
            pad = self.CELMApad
        pad /= 1000 #pad is given in ms
        if alpha is None:
            alpha = self.CELMAalpha
        if binNumber is None:
            binNumber = self.CELMAbinNumber
        if color is None:
            color = self.CELMAcolor
        if marker is None:
            marker = self.CELMAmarker
        if avgColor is None:
            avgColor = self.CELMAavgColor
        if normalize is None:
            normalize = self.CELMAnormalize

        time = np.array(self.times[probe])
        data = np.array(self.data[probe])

        # Not doing this will result in problems during numpy comparisons
        time = Conversion.removeNans(time, data)
        data = Conversion.removeNans(data)

        ### Finding ELM times in range
        # Filter arrays according to passed values start, end, ELMnum
        ind = np.where((self.ELMonsets >= start) & (self.ELMonsets <= end) &
                       ~np.in1d(self.ELMonsets,ignore))[0][:ELMnum]
        if len(ind) == 0:
            print "ERROR: No ELMs in specified range {}s-{}s".format(start,end)
            logging.critical("No ELMs in specified range {}s-{}s".format(start,end))
            return
        ELMonsets = self.ELMonsets[ind]
        ELMtoELM = self.ELMtoELM[ind]
        ELMends = self.ELMends[ind]
        ELMmaxima = self.ELMmaxima[ind]
        ELMdurations = ELMends - ELMonsets

        if compare == 'Start':
            shiftArray = ELMonsets
            durationHandle = max(ELMdurations)
        elif compare == 'End':
            shiftArray = ELMends
            durationHandle = -max(ELMdurations)
        elif compare == 'Maximum':
            shiftArray = ELMmaxima
            durationHandle = None
        else:
            print "Unknown compare mode {}. Synchronizing by ELM start".format(compare)
            logging.warning("Unknown compare mode {}. Synchronizing by ELM start".format(compare))
            shiftArray = ELMonsets

        dataTotal = []
        timeTotal = []
        i = 0
        logging.debug("Found ELM starts: {}".format(ELMonsets))
        for i, (ton, dt, shift) in enumerate(zip(ELMonsets, ELMtoELM, shiftArray)):
            ind = np.where((ton-dt - pad <= time) & (time <= ton+dt + pad))[0]
            if normalize:
                timeELM = (time[ind] - shift)/dt
            else:
                timeELM = time[ind] - shift
            dataELM = data[ind]
            scatter = self.axes.scatter(timeELM,dataELM, marker=marker, 
                                        color=color, alpha=alpha, linewidth=0,
                                        label='ELM {} @{:.4f}s'.format(i,ton))
            self.CELMAs.append(scatter)

            dataTotal.extend(list(dataELM))
            timeTotal.extend(list(timeELM))
            i += 1

        if durationHandle is not None and not normalize:
            durationSpan = self.axes.axvspan(durationHandle, 0,
                                             color='grey', alpha=.3)
            self.CELMAs.append(durationSpan)
        else:
            syncMarker = self.axes.axvline(
                                0,0,1,ls='--',lw='4',color='grey', alpha=.3,
                                label = 'ELM start')
            self.CELMAs.append(syncMarker)


        if len(timeTotal) == 0 and len(dataTotal) == 0:
            print "ERROR: Retreived ELM data or time arrays contain no data"
            logging.critical("ERROR: Retreived ELM data or time arrays contain no data")
            return
        
        timeTotal, dataTotal = zip(*sorted(zip(timeTotal,dataTotal)))

        if binning:
            result = self.averagesInBins(binNumber, timeTotal, dataTotal,
                                         avgMethod)
            if result is not None:
                t, avgs = result

                self.CELMAs.append(
                        self.axes.plot(t,avgs,
                                        color=avgColor,
                                        lw=lw,
                                        label='Linear regression')[0])

        self.axes.set_xlim(min(timeTotal), max(timeTotal))
        self.axes.set_ylim(min(dataTotal), max(dataTotal))

        self.CELMAexists = True



class WmhdPlot(TemporalPlot):
    def __init__(self, gui):
        quantity = 'wmhd'
        super(WmhdPlot, self).__init__(gui, quantity)
        self.shot = gui.WmhdShot
        self.gui = gui
        self.container = None
        self.annots = {}


    def init(self):
        data, times = self.getShotData()
        self.data = data
        self.times = times
        
        color = self.gui.config['Indicators']['color']
        self.indicator = Indicator(self, color)

        self.axes.plot(self.times, self.data, marker='+')
        self._lossID = self.axes.callbacks.connect('xlim_changed',
                                                   self.showWmhdLoss)


    def showWmhdLoss(self, event):
        if not self.CELMAexists:
            self.axes.callbacks.disconnect(self._lossID)
            tmin, tmax = self.axes.get_xlim()
            ind = np.where((self.gui.WmhdELMonsets > tmin) &
                           (self.gui.WmhdELMends < tmax))
            if len(ind[0]) == 0:
                logging.info('Wmhd: No ELMs in this range')
                return
            ELMstarts = self.gui.WmhdELMonsets[ind]
            ELMends = self.gui.WmhdELMends[ind]
            preELMWmhd = self.gui.preELMWmhd[ind]
            ELMENER = self.gui.ELMENER[ind]

            for ID, annot in self.annots.iteritems():
                if ID not in ind[0]:
                    for artist in annot:
                        artist.remove()

            self.annots = {ID: val for ID, val in self.annots.items()
                           if ID in ind[0]}

            for ID, ELMbeg, ELMend, _preELMWmhd, _ELMENER in zip(ind[0],
                                                                 ELMstarts,
                                                                 ELMends,
                                                                 preELMWmhd,
                                                                 ELMENER):
                if ID not in self.annots:
                    ELMdt = ELMend - ELMbeg
                    postELMWmhd = _preELMWmhd - _ELMENER
                    beg = self.axes.scatter(ELMbeg, _preELMWmhd, marker='x')
                    end = self.axes.scatter(ELMend, postELMWmhd, marker='x')
                    loss = self.axes.annotate('', 
                                              xytext=(ELMbeg, _preELMWmhd),
                                              xy=(ELMbeg, postELMWmhd),
                                              xycoords='data',
                                              textcoords='data',
                                              arrowprops=dict(arrowstyle='simple',
                                                              facecolor='r')
                                              )
                    postELMlevel = self.axes.hlines(postELMWmhd,
                                                    ELMbeg, ELMend,
                                                    linestyles='-.')
                    self.annots[ID] = [beg, end, loss, postELMlevel]

            self._lossID = self.axes.callbacks.connect('xlim_changed',
                                                       self.showWmhdLoss)


    def getShotData(self):
        """ Loads wmhd data from shotfile. """
        shot = self.shot
        data = shot('Wmhd').data
        times = shot('Wmhd').time
        return data, times


    def clearCELMA(self):
        super(WmhdPlot, self).clearCELMA()
        self._lossID = self.axes.callbacks.connect('xlim_changed',
                                                   self.showWmhdLoss)


    def averageData(self, data=None, time=None):
        """ Averages data for selected probes if average data does not exist for them yet. """
        n = self.avgNum
        data = Tools.padToFit(data, n, np.NAN)
        time = Tools.padToFit(time, n, np.NAN)
        data = data.reshape(-1,n).mean(axis=1)
        time = time.reshape(-1,n).mean(axis=1)

        return data, time


    def __del__(self):
        for i, plot in enumerate(self.gui.plots):
            if plot == self:
                del self.gui.plots[i]
                break
        super(WmhdPlot, self).__del__()


    def coherentELMaveraging(self):
        self.axes.callbacks.disconnect(self._lossID)
        settings = self.gui.getCELMAsettings()
        if settings is None:
            print "Error getting settings"
            logging.error("Error getting CELMA settings")
            return
        start, end, ELMnum = settings

        times = self.times
        data = self.data

        # If Wmhd and ELM experiments differ, ignoreELMs will most certainly
        # not work
        ind = np.where((start <= self.gui.WmhdELMonsets) &
                       (self.gui.WmhdELMonsets <= end) &
                       ~np.in1d(self.gui.WmhdELMonsets, self.gui.ignoreELMs))

        ELMstarts = self.gui.WmhdELMonsets[ind][:ELMnum]
        ELMends = self.gui.WmhdELMends[ind][:ELMnum]
        ELMtoELM = self.gui.WmhdELMtoELM[ind][:ELMnum]
        normalize = self.gui.cbCELMAnormalize.isChecked()
        binning = self.gui.menuEnableBinning.isChecked()
        binNumber = self.CELMAbinNumber

        timeTotal = []
        dataTotal = []
        for ton, dt in zip(ELMstarts, ELMtoELM):
            ind = np.where((ton - dt/2. <= times) & (times < ton + dt/2.))
            if normalize:
                xlabel = 'ELM duration [%]'
                t = (times[ind] - ton) / dt
            else:
                xlabel = 'Time [s]'
                t = times[ind] - ton
            y = data[ind]
            timeTotal.extend(list(t))
            dataTotal.extend(list(y))
            self.CELMAs.append(self.axes.scatter(t, y))

        if binning:
            avgColor = self.CELMAavgColor
            result = self.averagesInBins(binNumber, timeTotal, dataTotal)
            if result is not None:
                t, avgs = result

                self.CELMAs.append(
                        self.axes.plot(t,avgs,
                                        color=avgColor,
                                        label='Linear regression')[0])
                maxInd = np.argmax(avgs)
                minInd = np.argmin(avgs)
                maximum = [t[maxInd], avgs[maxInd]]
                minimum = [t[minInd], avgs[minInd]]
            
                maxPoint = self.axes.scatter(maximum[0], maximum[1], marker='x')
                minPoint = self.axes.scatter(minimum[0], minimum[1], marker='x')
                self.CELMAs.append(maxPoint)
                self.CELMAs.append(minPoint)

                loss = self.axes.annotate('', 
                                          xytext=(maximum[0], maximum[1]),
                                          xy=(maximum[0], minimum[1]),
                                          xycoords='data',
                                          textcoords='data',
                                          arrowprops=dict(arrowstyle='simple',
                                                          facecolor='r')
                                          )
                postELMlevel = self.axes.hlines(minimum[1],
                                                maximum[0], minimum[0],
                                                linestyles='-.')
                self.CELMAs.append(loss)
                self.CELMAs.append(postELMlevel)
            
        self.axes.set_xlim([min(timeTotal), max(timeTotal)])
        self.axes.set_ylim([min(dataTotal), max(dataTotal)])
        self.axes.set_xlabel(xlabel)
        self.CELMAexists = True
        self.canvas.draw()



class CurrentPlot(Plot):
    """ 
    Abstract plot class providing functions to create current density plots
    """
    # Get mapping between probes and channels from files at
    # /afs/ipp/home/d/dacar/divertor/ If no file present, try to get the
    # mapping from LSC Calibrate the measurements with probe surfaces to obtain
    # current densities Plot results
    progressed = QtCore.pyqtSignal(int)
    processEvent = QtCore.pyqtSignal(str)


    def __init__(self, gui, quantity):

        # Configuration
        config = gui.config['Plots']['Temporal']['Current']
        self.mapDir = config['mapDir']
        self.mapDiag = config['mapDiag']
        self.diag = config['diag']
        self.calibFile = config['calibFile']
        self.mapFilePath = config['mapFile']
        self.showGaps = gui.config['Plots']['Temporal']['showGaps']
        self.rescaling = gui.config['Plots']['Temporal']['rescale-y']

        # Attributes
        self.shotnr = gui.shotnr
        self.hasMapping = False
        self.calib = {}
        self.map = {}
        self.shot = gui.LSFshot
        self.gui = gui

        self.axes.set_ylabel('Current density [kA/m$^2$]')

        def formatTicks(val, loc):
            return '{:.1f}'.format(val*1e-3)
        fmt = mpl.ticker.FuncFormatter(formatTicks)
        self.axes.yaxis.set_major_formatter(fmt)


    def getShotData(self):
        """ Loads jsat data from shotfile. """
        if len(self.map) < 1:
            hasMapping = self.getMapping()
        
        if not hasMapping:
            print "No mapping found"
            logging.critical("No mapping found")
            return

        shot = self.shot
        timeArrays = []
        rawdata = {}
        for key, objName in shot.getObjectNames().iteritems():
            if objName.startswith('CH'):
                for probe, (channel, ind) in self.map.iteritems():
                    if channel == objName:
                        try:
                            if probe not in rawdata:
                                rawdata[probe] = {}
                            rawdata[probe]['data'] = shot(channel).data[ind]
                            rawdata[probe]['time'] = shot(channel).time
                        except TypeError, e:
                            print "Could not retrieve LSF data for probe {}".format(probe)+\
                                    " @channel {} ({}), {} ({}): {}".format(channel,
                                            type(channel), ind, type(ind),
                                            str(e))
                            logging.warn("Could not retrieve LSF data for probe {}".format(probe)+\
                                    " @channel {} ({}), {} ({}): {}".format(channel,
                                            type(channel), ind, type(ind),
                                            str(e)))

                        self.createProbe(probe)
                        timeArrays.append(shot(channel).time)

        self.probes.sort(key = lambda x: x.name)
        self.timeArray = self.getTimeArray(timeArrays=timeArrays)
        return rawdata


    def getMappingFromShotfile(self):
        self.gui.statusbar.showMessage("Trying to get probe-channel mapping from LSC")
        shot = self.LSCshot

        map = {}
        signalName = 'ZSI' + self.segment

        for obj in shot.getObjectNames().values():
            if obj.startswith(self.region):
                probe = obj
                data = shot(obj)[signalName].data 
                info = ''.join([el for el in data if el.split() != []])
                try:
                    channel, ind = info.split('_')
                except:
                    print "Could not retrieve LSC data for probe", probe
                    logging.warn("Could not retrieve LSC data for probe {}".format(probe))
                else:
                    # Actual LSC data starts with 'ch' while shotfile object
                    # names start with 'CH'.
                    channel = 'CH' + channel[2:]
                    # Indices are saved as numbers 1-6 but must serve as
                    # indexes 0-5
                    ind = int(ind) - 1
                    map[probe] = (channel, ind)
                        
        return map


    def getMapping(self):
        """ 
        Loads probe-channel mapping from file. Tries to load from LSC if
        file not available. 
        """
        print "\n++++++++++++++++ Getting mappings +++++++++++++++++++++++++\n"
        logging.info("\n++++++++++++++++ Getting mappings +++++++++++++++++++++++++\n")

        # Try to get mapping from LSC shotfile
        if self.gui.menuUseLSC.isChecked():
            self.map = self.getMappingFromShotfile()

        if len(self.map) == 0:
            print "Trying to get mapping from text file"
            logging.info("Getting mapping from text file {}"\
                        .format(self.mapFilePath))
            # File load dialog if mapFilePath was set to None during runtime
            specified = self.mapFilePath != ''
            exists = os.path.isfile(self.mapFilePath)
            if self.mapFilePath is None or not specified or not exists:
                while True:
                    self.mapFilePath = \
                        QtGui.QFileDialog.getOpenFileName(
                            self.gui,
                            directory=self.mapDir,
                            caption='Load mapping file'
                        )
                    # If cancelled, abort
                    if self.mapFilePath == '':
                        return False
                    # If filename valid, leave loop
                    elif not os.path.isfile(self.mapFilePath):
                        self.gui.statusbar.showMessage('Could not find mapping file', 3000)
                        continue
                    else:
                        break
            
            with open(self.mapFilePath) as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    try:
                        probe, quantity, channel, ind = line.split()
                    except:
                        print "Failed to read probe-channel mapping file" +\
                                " {} at line {}: {}".format(self.mapFilePath, i, line)
                        logging.error("Failed to read probe-channel mapping file" +\
                                " {} at line {}: {}".format(self.mapFilePath, i, line))
                        break
            
                    # If channel doesn't start with "CH", add the prefix so LSF
                    # shotfile can be read with it
                    if not channel.startswith('CH'): channel = 'CH' + channel
            
                    # ind is saved as str from 1-6 but must serve as an index
                    # from 0-5
                    ind = int(ind) - 1
            
                    # Only care about probes in this segment and region and the
                    # saturation current
                    if probe.startswith(self.segment + self.region) and quantity == 'Isat':
                        # Cut off probe segment
                        probe = probe[1:].lower()
                        print "Found Isat for probe {} on channel {}-{}"\
                                .format(probe,channel, ind)
                        logging.info("Found Isat for probe {} on channel {}-{}"\
                            .format(probe,channel, ind))
                        self.map[probe] = (channel, ind)
        
        if len(self.map) > 0:
            #print "\n\nProbe mappings:"
            #for probe in self.map:
            #    print "Probe: {:5s}Channel: {}".format(probe,self.map[probe])
            logging.info( "\n\nProbe mappings:")
            for probe in self.map:
                logging.info("Probe: {:5s}Channel: {}".format(probe,self.map[probe]))
            return True
        else:
            print "Failed to get probe-channel mapping. jsat will not be plotted"
            logging.critical( "Failed to get probe-channel mapping. jsat will not be plotted")
            return False


    def calibrateData(self, rawdata):
        """ Converts current to current density. """
        calibrate = self.gui.menuCalibrateJsat.isChecked()
        if not calibrate:
            #print "\n++++ JSAT NOT CALIBRATED ++++\n --> Activate calibration in GUI"
            logging.warning("\n++++ JSAT NOT CALIBRATED ++++\n")
            return

        print "\nCalibrating data"
        logging.info( "\nCalibrating data")
        if len(self.calib) == 0:
            self.getCalibrations()

        for probe, probeData in rawdata.iteritems():
            data = probeData['data']
            l, w = self.calib[probe]
            if l*w == 0:
                print "Caution! Invalid dimensions for probe {}.".format(probe)+\
                        " No calibration possible."
                logging.error("Caution! Invalid dimensions for probe {}.".format(probe)+\
                        " No calibration possible.")
                continue
            rawdata[probe]['data'] = data/(l*w)
        
        return rawdata


    def getCalibrationsFromShotfile(self):
        print "Getting calibrations from shotfile..."
        logging.info( "Getting calibrations from shotfile...")
        shot = self.LSCshot
        for obj in shot.getObjectNames().values():
            probeInLSF = obj in [p.name for p in self.probes]
            if obj.startswith(self.region) and probeInLSF:
                probe = obj
                data = shot(obj)['Geom'].data 
                try:
                    l, w = data[:2]
                except:
                    print "Could not retrieve geometry of probe {} from LSC".format(probe)
                    print "Aborting"
                    logging.critical("Could not retrieve geometry of probe {} from LSC".format(probe))
                    return False

                self.calib[probe] = (float(l), float(w))

        return self.calib
    

    def getCalibrations(self, path=None):
        """ Loads probe dimensions from file so current can be converted to current density. """
        if self.gui.menuUseLSC.isChecked():
            self.getCalibrationsFromShotfile()
        else:
            if path is None:
                path = self.calibFile

            with open(path) as f:
                lines = f.readlines()[1:]
                for line in lines:
                    probe, l, w = line.split()
                    self.calib[probe] = (float(l), float(w))
                
        #print "\n\nProbe dimensions:"
        #for probe in self.calib:
        #    print "Probe: {:5s} Geometry: {}".format(probe,self.calib[probe])
        logging.info("\n\nProbe dimensions:")
        for probe in self.calib:
            logging.info("Probe: {:5s} Geometry: {}".format(probe,self.calib[probe]))

        return self.calib



class SpatialCurrentPlot(CurrentPlot, SpatialPlot):
    progressed = QtCore.pyqtSignal(int)
    processEvent = QtCore.pyqtSignal(str)

    def __init__(self, gui, quantity):
        Plot.__init__(self, gui, quantity, 'spatial')
        # This order is essential since self.shot and self.getShotData must
        # correspond to CurrentPlot atrributes
        SpatialPlot.__init__(self, gui, quantity)
        CurrentPlot.__init__(self, gui, quantity)



class TemporalCurrentPlot(CurrentPlot, TemporalPlot):
    def __init__(self, gui, quantity):
        TemporalPlot.__init__(self, gui, 'jsat')
        super(TemporalCurrentPlot, self).__init__(gui, quantity)

    def getShotData(self):
        # This is necessary due to TemporalPlot being initialized first
        # I guess. Otherwise getShotData() of TemporalPlot would get called.
        # Initializing TemporalPlot is necessary since CurrentPlot does not
        # call Plot.__init__() since that messes with fit plotting in
        # SpatialCurrentPlot -.-
        rawdata = CurrentPlot.getShotData(self)
        return rawdata



# Main
if __name__ == '__main__':

    app = QtGui.QApplication(sys.argv)

    main = ApplicationWindow()
    main.show()

    sys.exit(app.exec_())
