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
# Issues:
# - Data evaluation will fail if the time data arrays vary from probe to probe
#
# - At application start, jPlot is not synced with the others
#
# To do:
# - Increase speed when calibrating current
#
# - Add options to change all parameters like
#       * Indicator.color
#       * SpatialPlot.coloring = 1
#       * SpatialPlot.defaultColor = 'b'
#       * TemporalPlot.axTitles
#       * Plot.region
#       * Plot.segment
#       * CurrentPlot.mapDir
#       * CurrentPlot.mapDiag
#       * CurrentPlot.diag
#       * Path to calibrations
#       * Path to probe positions
#   from within the GUI and store them in a config file
#
# - Make Indicator update time window when moving away from t=0
#
# - Implement option to automatically zoom temporal plots to their value limits
# 
#
##############################################################################

import matplotlib as mpl
mpl.use('Qt4Agg')
from matplotlib import cm
from matplotlib import pyplot as plt
from matplotlib import patches
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt4agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.widgets import SpanSelector

from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4.QtGui import (QWidget, QMessageBox)
from PyQt4.QtGui import (QPainter, QColor)
from PyQt4.uic import loadUiType

from fitting import FitFunctions

# Either use network libraries or local ones depending on internet access
# Local ones might be outdated but don't require internet access
#import dd
import ddlocal as dd
import numpy as np
import sys
import os
from copy import copy
import pickle

# This is needed for passing arguments to callback functions
import functools

from configobj import ConfigObj
from validate import Validator

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
        if len(args) < 2:
            pass
        else:
            for triggerPlot in args:
                for receiverPlot in args:
                    if triggerPlot != receiverPlot:
                        triggerPlot.axes._shared_x_axes.join(triggerPlot.axes, receiverPlot.axes)



class LoadingAllThread(QtCore.QThread):
    def __init__(self,gui):
        super(LoadingAllThread, self).__init__()
        print "Thread is being instantiated"
        self.gui = gui


    def __del__(self):
        self.wait()


    def run(self):
        print "Running thread"
        self.gui.load()



class ApplicationWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, ):
        super(ApplicationWindow, self).__init__()

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
        validFile  = 'validation.ini'
        
        if not os.path.isfile(validFile):
            validFile = None
        if os.path.isfile(configFile):
            self.loadConfig(configFile, validFile)
        else:
            self.createConfig(configFile, validFile)

        # Reference configuration for this class
        config = self.config['Application']

        # Configuration
        self.avgNum     = config['avgNum']
        self.Dt         = config['Dt']
        self.langdiag   = config['langmuirDiag']
        self.sldiag     = config['strikelineDiag']
        self.ELMdiag    = config['ELMDiag']
        self.colorScheme= config['colorScheme']
        self.defaultExtension = config['defaultExtension'] 
        self.defaultFilter = '{} (*.{})'.format(self.defaultExtension[1:].upper(),
                                                self.defaultExtension[1:].lower())

        # Set up UI
        self.setupUi(self)
        self.xTimeSlider.setTickPosition(QtGui.QSlider.NoTicks)
        #self.btnELMplot.hide()

        self.POIs = [0]
        self.POI_current_ind = 0
        self.POIsPlots = []
        self.ELMstart_current_ind = 0
        self.POImarkers = []
        
        self.editPOIbefore.setText('20')
        self.editPOIafter.setText('20')
        self.editPOIfarafter.setText('50')

        # Set GUI options to what was read from config.ini
        self.menuFixxPlotyLim.setChecked(self.config['Plots']['Spatial']['fixyLim'])
        self.menuShowGaps.setChecked(self.config['Plots']['Temporal']['showGaps'])
        self.menuIgnoreNaNsSpatial.setChecked(self.config['Plots']['ignoreNans'])

        # Prepare probe table
        columnNames = ['Probe','Color','Style','T/n(x)','T(t)','n(t)','jsat(t)']
        self.probeTable.setColumnCount(len(columnNames))
        self.probeTable.setHorizontalHeaderLabels(columnNames)
        
        # Resize columns to fit table width
        header = self.probeTable.horizontalHeader()
        for i in range(header.count()):
            header.setResizeMode(i, QtGui.QHeaderView.Stretch)
        self.probeTable.resizeColumnsToContents()

        # Hide vertical header
        self.probeTable.verticalHeader().setVisible(False)

        # Set up CELMA slider
        self.slideCELMAPOI.setMinimum(0)
        self.slideCELMAPOI.setMaximum(100)

        # Add progress bar to the status bar
        try:
            self.statusbar.removeWidget(self.progBar)
        except Exception:
            pass
        self.progBar = QtGui.QProgressBar()
        self.statusbar.addPermanentWidget(self.progBar)
        self.progBar.setMinimum(0)
        self.progBar.setMaximum(100)

        # Set general behavior of GUI
        #self.shotNumberEdit.returnPressed.connect(self.triggerThread)
        self.shotNumberEdit.returnPressed.connect(self.load)
        self.xTimeEdit.setMaxLength(7)
        self.shotNumberEdit.setMaxLength(5)
        self.shotNumberEdit.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)


    def triggerThread(self):
        print "triggered"
        loadAll = LoadingAllThread(self)
        loadAll.start()


    def getTimeArray(self, shot):
        timeArrays = []
        for obj in shot.getSignalNames():
            isRightQuantity = obj.startswith(('te','ne'))
            isRightRegime = obj.split('-')[1][:2]=='ua'

            if isRightQuantity and isRightRegime:
                try:
                    timeArrays.append(shot.getTimeBase(obj))
                except:
                    print "Failed to retrieve time base for signal", obj

        equal = (np.diff(
                    np.vstack(timeArrays).reshape(len(timeArrays),-1),axis=0)\
                    ==0).all()

        if not equal:
            print """Warning: time base arrays fetched from shotfile are not
            equal! Proceed with caution."""
        return timeArrays[0]


    def moveToNextPOI(self, ):
        self.POI_current_ind = min(self.POI_current_ind + 1, len(self.POIs) - 1)
        POI = self.POIs[self.POI_current_ind]
        POI_realtime_ind = Conversion.valtoind(POI, self.dtime)
        self.xTimeSlider.setValue(POI_realtime_ind)
        
        self.updatexPlotText()


    def moveToPrevPOI(self, ):
        self.POI_current_ind = max(self.POI_current_ind - 1, 0)
        POI = self.POIs[self.POI_current_ind]
        POI_realtime_ind = Conversion.valtoind(POI, self.dtime)
        self.xTimeSlider.setValue(POI_realtime_ind)
        
        self.updatexPlotText()


    def moveToNextELM(self, ):
        self.ELMstart_current_ind = min(self.ELMstart_current_ind + 1, len(self.ELMonsets) - 1)
        self.snapSlider(self.ELMstart_current_ind)
        

    def moveToPrevELM(self, ):
        self.ELMstart_current_ind = max(self.ELMstart_current_ind - 1, 0)
        self.snapSlider(self.ELMstart_current_ind)


    def snapSlider(self, ELMind=None):
        """ Makes Slider snap to ELM-related points of interest. """
        # - Make slider snap to ELM phases. onValueChange:
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

        if snapping or ELMind is not None:
            for plot in self.POIsPlots:
                try: plot.remove()
                except: pass
            self.POIsPlots.append(self.jPlot.axes.axvline(self.ELMonsets[self.ELMstart_current_ind], color='g', lw=3,
                    alpha=0.3))
            self.POIs= self.elmPhases(self.ELMstart_current_ind)
            for t in self.POIs:
                self.POIsPlots.append(self.jPlot.axes.axvline(t, color='g', lw=3,
                        ls='--', alpha=0.3))
            self.POI_current_ind = np.abs((self.POIs - realtime)).argmin()
            POI = self.POIs[self.POI_current_ind]
            POI_realtime_ind = Conversion.valtoind(POI, self.dtime)
            self.xTimeSlider.setValue(POI_realtime_ind)
            
            self.updatexPlotText()
        

    def elmPhases(self, i):
        justBefore = float(self.editPOIbefore.text())/100.
        justAfter  = float(self.editPOIafter.text())/100.
        farAfter   = float(self.editPOIfarafter.text())/100.
        t1 = self.ELMonsets[i] - self.ELMtotalDurations[i-1] * justBefore
        t2 = self.ELMonsets[i] + self.ELMtotalDurations[i] * justAfter
        t3 = self.ELMonsets[i] + self.ELMtotalDurations[i] * farAfter
        
        return t1, t2, t3
        

    def loadConfig(self, f, specf=None):
        self.config = ConfigObj(f, configspec=specf)

        # Validate/convert settings
        val = Validator()
        succeeded = self.config.validate(val)
        
        if not succeeded:
            print "Warning: Config file validation failed. Using default values"
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


    def load(self, ):
        """ Loads specified shot, updates all plots on the GUI and implements interactivity """
        # Try to load shotfiles
        success = self.getShot()

        # getShot sets the attribute succeeded at the very end of the function if all went well
        if success:
            print("Data retrieval was successful")
            
            self.getPlotOption()
            self.populateProbeList()
            self.populateCELMAprobeCombo()
            self.selectedProbes = {'x': [], 't':
                        ['te-ua2','ne-ua2','j-ua2',
                         'te-ua3','ne-ua3','j-ua3',
                         'te-ua4','ne-ua4','j-ua4']}
            self.ELMphase = (0,0)
            self.CELMAactive = False
            self.CELMAexists = False

            # Update plots
            self.createxPlot()
            self.indicator_range = self.xPlot.realdtrange
            self.createnPlot()
            self.createTPlot()
            self.createjPlot()

            # Add matplotlib toolbar functionality
            self.nToolbar = NavigationToolbar(self.nPlot.canvas, self)
            self.TToolbar = NavigationToolbar(self.TPlot.canvas, self)
            self.nToolbar.hide()
            self.TToolbar.hide()

            # Synchronize temporal plots
            Sync.sync(self.nPlot, self.TPlot, self.jPlot)

            # Update GUI appearance with current values
            self.xPlot.setTimeText()
            self.xPlot.setDurationText()
            self.updateTWindowControls()
        

            # Implement GUI logic
            # This has to be done after updating the plots because the plot objects are referenced
            self.switchxPlot.activated.connect(self.createxPlot)

            self.xTimeEdit.returnPressed.connect(self.updateSlider)
            self.xTimeEdit.returnPressed.connect(self.updatexPlot)
            self.xTimeEdit.returnPressed.connect(self.updatexPlotText)
            self.xTimeEdit.returnPressed.connect(self.updatetPlotXlims)

            self.xTimeSlider.valueChanged.connect(self.updatexPlot)
            self.xTimeSlider.valueChanged.connect(self.updateTimeText)
            self.xTimeSlider.valueChanged.connect(self.updateIndicators)
            self.xTimeSlider.sliderReleased.connect(self.updatexPlotText)
            self.xTimeSlider.valueChanged.connect(self.updatexFit)
            self.xTimeSlider.sliderReleased.connect(self.snapSlider)
        
            self.spinTWidth.editingFinished.connect(self.updateTWindow)

            self.btnPan.clicked.connect(self.nToolbar.pan)
            self.btnZoom.clicked.connect(self.nToolbar.zoom)
            self.btnPan.clicked.connect(self.TToolbar.pan)
            self.btnZoom.clicked.connect(self.TToolbar.zoom)
            self.btnReset.clicked.connect(self.resettPlots)
            
            self.btnCELMA.clicked.connect(self.toggleCELMAs)
            self.comboCELMAmode.currentIndexChanged.connect(self.clearCELMAs)
            self.comboCELMAprobe.currentIndexChanged.connect(self.clearCELMAs)
            self.cbCELMAbinning.stateChanged.connect(self.clearCELMAs)
            self.editCELMAbins.textChanged.connect(self.clearCELMAs)
            self.editCELMAELMnum.textChanged.connect(self.clearCELMAs)
            self.editCELMAstartTime.textChanged.connect(self.clearCELMAs)
            self.editCELMAendTime.textChanged.connect(self.clearCELMAs)

            self.menuAvgSpatial.triggered.connect(self.setAvgNum)
            self.menuFixxPlotyLim.toggled.connect(self.updatexPlot)
            self.menuIgnoreNaNsSpatial.toggled.connect(self.updatexPlot)
            self.menuSaveSpatialPlot.triggered.connect(self.savexPlot)
            self.menuSaveCurrentPlot.triggered.connect(self.savejPlot)
            self.menuShowGaps.toggled.connect(self.updatetPlots)
            self.menuSaveSpatialData.triggered.connect(self.saveSpatialData)

            self.btnNextPOI.clicked.connect(self.moveToNextPOI)
            self.btnPrevPOI.clicked.connect(self.moveToPrevPOI)
            self.btnNextELM.clicked.connect(self.moveToNextELM)
            self.btnPrevELM.clicked.connect(self.moveToPrevELM)

            self.btnCELMAspatial.clicked.connect(self.createSpatialCELMA)

        # If shot data was not loaded successfully, unbind actions
        else:
            try: 
                del self.succeeded
                self.switchxPlot.disconnect()
                self.xTimeSlider.disconnect()
                self.xTimeEdit.disconnect()
            except Exception: pass
            print("No valid shot number has been entered yet.")


    def createSpatialCELMA(self):
        self.xPlot.axes.clear()
        # Remove existing legends
        for legend in self.xPlot.fig.legends:
            try:
                legend.remove()
            except ValueError: pass
        # Remove existing markers
        for marker in self.POImarkers:
            try:
                marker.remove()
            except ValueError: pass


        POIs = []
        simultaneous = self.cbSimultaneousCELMAs.isChecked()
        if simultaneous:
            markers = ['D','o','^']
            colors  = ['r','b','g']

            # Make sure pre-ELM value is negative and post-ELM values are
            # positive
            POI_pre   = float(self.editPOIbefore.text())/100.
            POI_post  = float(self.editPOIafter.text())/100.
            POI_inter = float(self.editPOIfarafter.text())/100.
            POIs.append( POI_pre if POI_pre <= 0 else -POI_pre )
            POIs.append( POI_post if POI_post >= 0 else -POI_post )
            POIs.append( POI_inter if POI_inter >= 0 else -POI_inter )
        else:
            markers = ['o']
            colors = [None]
            POIs.append(float(self.slideCELMAPOI.value())/100.)

        # COPIED FROM SpatialPlot.coherentELMaveraging AND MODIFIED
        try:
            self.CELMAphaseOn = float(self.editCELMAstartTime.text())
        except ValueError:
            print "Invalid starting time for ELM averaging"
            self.CELMAphaseOn = 6.0
        try:
            self.CELMAphaseEnd = float(self.editCELMAendTime.text())
        except ValueError:
            print "Invalid end time for ELM averaging"
            self.CELMAphaseOn = 6.2
        # END OF COPY

        for POI, marker, color in zip(POIs, markers, colors):
            # THE FOLLOWING IS VERY SIMILAR TO WHAT HAPPENS IN
            # SpatialPlot.coherentELMaveraging. Create function for it or so
            ELMtotalDurationsHere = []
            j = 0
            try:
                ELMnum = int(self.editCELMAELMnum.text())
            except:
                print "Invalid number of ELMs. Using 5 ELMs for ELM averaging"
                ELMnum = 5
            if self.comboPOIunit.currentText() == 'ms' and not simultaneous:
                # If a single POI is plotted, the shortest ELM-to-ELM duration
                # determines the maximum offset in ms. POI therefore ranges
                # between 0 and minimumELMduration
                for ton,dt in zip(self.ELMonsets, self.ELMtotalDurations):
                    if ton >= self.CELMAphaseOn and ton+dt <= self.CELMAphaseEnd:
                        if j < ELMnum:
                            print "ELM", j
                            ELMtotalDurationsHere.append(dt)
                            j += 1
                        else: break
                minimumELMduration = min(ELMtotalDurationsHere)
                POI = POI*minimumELMduration
                print "Relative POI in ms:", POI
            if self.comboPOIunit.currentText() == 'ms' and simultaneous:
                # If value was entered by user - as it is required for
                # simultaneous plot - it is assumed that the values are
                # sensible without any extra checking
                POI = POI/10 # Convert to milliseconds

            POIs = self.xPlot.coherentELMaveraging(POI, marker=marker,
                    color=color)

            markPOIsInTemporal = self.menuMarkPOIsInTemporal.isChecked()
            if markPOIsInTemporal:
                # If not simultaneous, use color red for markers
                if color is None:
                    color = 'r'
                # Plot new markers
                unit = self.comboPOIunit.currentText()
                if self.jPlot.CELMAactive and unit == 'ms':
                    self.POImarkers.append(self.jPlot.axes.axvline(POI,
                        color=color, alpha=0.5))
                elif not self.jPlot.CELMAactive:
                    for POI in POIs:
                        self.POImarkers.append(self.jPlot.axes.axvline(POI,
                            color=color, alpha=0.5))
                self.jPlot.canvas.draw()
    

    def saveSpatialData(self):
        self.xPlot.saveData()


    def updatetPlots(self):
        """ Updates all temporal plots """
        self.nPlot.update()
        self.TPlot.update()
        self.jPlot.update()


    def updatetPlotXlims(self):
        """ Updates xlims of the temporal plots if the time value entered is
        not within the current xlims """
        time = float(self.xTimeEdit.text())

        # get current x-axis limits of any temporal plot
        # TO DO: MAKE INDEPENDENT OF TEMPORAL PLOTS
        # ONLY MAKES SENSE IF ALL PLOTS ARE SYNCHED
        currxmin, currxmax = self.jPlot.axes.get_xlim()
        dt = currxmax - currxmin

        if not currxmin < time < currxmax:
            newxmin = max(0, time)
            newxmax = min(time + dt, self.xPlot.dtime[-1])
            self.jPlot.axes.set_xlim(newxmin, newxmax)
            self.nPlot.axes.set_xlim(newxmin, newxmax)
            self.TPlot.axes.set_xlim(newxmin, newxmax)


    def updatexPlotText(self):
        self.xPlot.updateText()


    def setAvgNum(self):
        avgNum, ok = QtGui.QInputDialog.getInt(self, 'Averaging spatial plot', 'Number of data points to average to one scatter plot point:\n\navgNum = ', value= self.avgNum, min=0)

        if ok and avgNum % 2 != 0:
            self.avgNum = avgNum
            self.updateTWindowControls()
            self.updateTWindow()
        else:
            print "ERROR: avgNum must be an odd number"


    def updateTWindowControls(self):
        """ Updates time window controls with current value of avgNum (number of data point to average over). """
        # SpinBox
        self.spinTWidth.setRange(self.avgNum, self.avgNum + 100)
        self.spinTWidth.setSingleStep(self.avgNum)
        self.spinTWidth.setValue(self.Dt)

        # Real time label
        dt = self.xPlot.realtmax - self.xPlot.realtmin
        self.lblRealTWidth.setText("= {:.1f}us".format(dt*10**6))


    def updateIndicators(self):
        """ Updates all indicators. """
        self.nPlot.indicator.slide()
        self.TPlot.indicator.slide()
        self.jPlot.indicator.slide()
    
    
    def togglePlots(self, cbID):
        """ Toggles temporal plots based on checkbox selection. """
        print "\n\nCheckbox clicked:", cbID
        # Mapper returns unicode string. Must be converted to standard string
        probe, quantity, axType = str(cbID).split('-')
        pnq = quantity + '-' + probe 
        cbType = quantity + '-' + axType
        cb = self.checkBoxes[probe][cbType]

        # If probe is checked, add it to selectedProbes
        # If not, make sure it's not in selectedProbes
        if cb.checkState() and pnq not in self.selectedProbes[axType]:
            print("Adding {} to selectedProbes".format(pnq))
            self.selectedProbes[axType].append(pnq)
        elif not cb.checkState() and pnq in self.selectedProbes[axType]:
            while pnq in self.selectedProbes[axType]:
                self.selectedProbes[axType].remove(pnq)
                print("Removing {} from selectedProbes".format(pnq))

        if axType == 't':
            if quantity == 'ne':
                self.nPlot.averageData()
                self.nPlot.update()
                self.nPlot.canvas.draw()
            elif quantity == 'te':
                self.TPlot.averageData()
                self.TPlot.update()
                self.TPlot.canvas.draw()
            elif quantity == 'j':
                self.jPlot.averageData()
                self.jPlot.update()
                self.jPlot.canvas.draw()
        if axType == 'x':
            self.xPlot.toggleProbe(probe, cb.checkState())
            self.xPlot.canvas.draw()
        

    def resettPlots(self):
        self.nPlot.reset()
        self.TPlot.reset()
        self.jPlot.reset()
        self.nPlotCanvas.draw()
        self.TPlotCanvas.draw()
        self.jPlotCanvas.draw()


    def getPlotOption(self):
        """ Creates class attribute and returns option chosen for the spatial plot as a string. """
        self.option = str(self.switchxPlot.currentText())
        return self.option 
    

    def optionProbes(self):
        """ Creates class list containing probes associated with the chosen plot option. """
        self.optProbes = []
        if not hasattr(self, 'probes'):
            print("CRITICAL: {} has no attribute {}.\n \
                  optionProbes() needs to be called after shot file has been loaded. ".format(self, "probes"))
        else:
            for probe in self.probes:
                if probe.startswith(self.option):
                    self.optProbes.append(probe)

  
    def populateProbeList(self):
        """ Populates list of available probes with probe names and checkboxes. """
        table = self.probeTable
        # Clear table of previous contents
        table.setRowCount(0)

        # Set color scheme for currently available probes
        cm = plt.get_cmap(self.colorScheme)
        colors = cm(np.linspace(0, 1, len(self.uniqueProbes)))

        self.probeColors = {}
        for probe, color in zip(self.uniqueProbes, colors):
            color = tuple(color)[:-1]
            self.probeColors[probe] = color

        # Add currently available probes
        self.checkBoxes = {}
        for probe in self.uniqueProbes:
            self.checkBoxes[probe] = {}
            color = self.probeColors[probe]

            # Insert new row
            rowPos = table.rowCount()
            self.probeTable.insertRow(rowPos)

            # Label
            label = QtGui.QLabel()
            label.setText(probe)

            # Checkboxes
            mapper = QtCore.QSignalMapper(self)
            for i, cbType in enumerate(('te-x','te-t','ne-t','j-t')):
                cb = QtGui.QCheckBox()
                cbID = probe + '-' + cbType
                mapper.setMapping(cb, cbID) 
                cb.stateChanged.connect(mapper.map)
                table.setCellWidget(rowPos, i+3, cb)
                self.checkBoxes[probe][cbType] = cb

                # Make checkboxes 0 or 1 only
                cb.setTristate(False)

                # Check ua1 plots
                if probe == 'ua1':
                    cb.setChecked(True)
                # Check all spatial plots
                elif cbType[-1] == 'x':
                    cb.setChecked(True)

            mapper.mapped['QString'].connect(self.togglePlots)

            # Color patch
            patch = ColorPatch(color) 
            style = ColorPatch(color) 

            # Add widgets to row
            table.setCellWidget(rowPos, 0, label)
            table.setCellWidget(rowPos, 1, patch)
            table.setCellWidget(rowPos, 2, style)

            # Make cells clickable
            table.cellClicked.connect(self.changeColor)
        self.probeTable.resizeColumnsToContents()


    def populateCELMAprobeCombo(self):
        combo = self.comboCELMAprobe

        for probe in self.uniqueProbes:
            combo.addItem(QtCore.QString(probe))


    def changeColor(self, row, col):
        print "Cell was clicked! Row {}, Col {}".format(row,col)


    def updatexPlot(self):
        self.xPlot.fixyLim = self.menuFixxPlotyLim.isChecked()
        self.xPlot.ignoreNans = self.menuIgnoreNaNsSpatial.isChecked()
        self.xPlot.update()


    def updatexFit(self):
        pass
        #self.xPlot.plotFit()


    def updateSlider(self):
        self.xPlot.setxTimeSlider()


    def updateTimeText(self):
        self.xPlot.setTimeText()


    def findTWindow(self, Dt, avgNum=None):
        """ Finds the time window that is closest to the value the user provided based on the number of data points to average over to create a plot point. """
        if avgNum != None:
            self.avgNum = avgNum
        elif not hasattr(self, 'avgNum'):
            print("WARNING! Number of points to average about is unknown. No averaging will take place")
            self.avgNum = 0
        else:
            avgNum = self.avgNum

        # Don't try anything fancy if no averaging is wanted anyway
        if avgNum == 0: return Dt

        # avgNum HAS to be odd or 0
        remAvg = Dt % avgNum 
        rem2   = Dt % 2

        # If Dt is divisible by 3 but not by 2, accept it
        if remAvg == 0 and rem2 != 0:
            Dt = Dt

        # If Dt is divisible by 3 and by 2, add 3
        if remAvg == 0 and rem2 == 0:
            Dt = Dt + avgNum

        # If Dt is not divisible by 3, subtract remainder and 
        # add 3 if needed so that result is as close as possible to the
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
        

    def updateTWindow(self):
        """ Updates spatial plot and position indicators based on the choice of the time window from which data is to be included in the spatial plot. """
        # Get new value for timesteps (Dt, see SpatialPlot.getShotData())
        Dt = self.spinTWidth.value()
        
        # Find time window that best matches user input and internal 
        # requirements
        Dt = self.findTWindow(Dt)

        # Correct user input in GUI too
        self.spinTWidth.setValue(Dt)

        # Update xPlot with new time window
        self.Dt = Dt
        self.updatexPlot()

        # Update sliders with new time window
        self.indicator_range = self.xPlot.realdtrange
        self.updateIndicators()

        # Update label showing time window in realtime
        dt = self.xPlot.realtmax - self.xPlot.realtmin
        self.lblRealTWidth.setText("= {:.2f}us".format(dt*10**6))


    def createOverlayPlot(self):
        self.clearxPlot()
        # create new canvas
        self.xPlot = SpatialPlot(self)
        self.xPlotCanvas = self.xPlot.canvas
        self.xPlotLayout.addWidget(self.xPlotCanvas)


    def clearxPlot(self):
        try:
            self.xPlotLayout.removeWidget(self.xPlotCanvas)
            self.xPlotCanvas.close()
        except:
            print("Old canvas could not be deleted")
            pass


    def createxPlot(self):
        """ Updates spatial plot by trying to remove the previous plot and creating a new canvas. Creates a SpatialPlot object. """
        # If canvas already exists, delete it
        self.clearxPlot()

        # create new canvas
        if self.getPlotOption() == "Saturation current density":
            self.xPlot = SpatialCurrentPlot(self)
        else:
            self.xPlot = SpatialPlot(self)
        self.xPlotCanvas = self.xPlot.canvas
        self.xPlotLayout.addWidget(self.xPlotCanvas)
        self.dtime = self.xPlot.dtime

        self.xPlot.axes.get_xaxis().get_major_formatter().set_useOffset(False)

        self.xToolbar = NavigationToolbar(self.xPlot.canvas, self)
        self.xToolbar.hide()

        self.btnPan.clicked.connect(self.xToolbar.pan)
        self.btnZoom.clicked.connect(self.xToolbar.zoom)
        self.btnReset.clicked.connect(self.xToolbar.home)


    def createTPlot(self):
        try:
            self.TPlotLayout.removeWidget(self.TPlotCanvas)
            self.TPlotCanvas.close()
        except:
            pass

        self.TPlot = TemporalPlot(self,'te')
        self.TPlotCanvas = self.TPlot.canvas
        self.TPlotLayout.addWidget(self.TPlotCanvas)
        self.TPlot.parent = self.TPlotLayout

        self.TPlot.axes.get_xaxis().get_major_formatter().set_useOffset(False)


    def createnPlot(self):
        try:
            self.nPlotLayout.removeWidget(self.nPlotCanvas)
            self.nPlotCanvas.close()
        except:
            pass

        self.nPlot = TemporalPlot(self,'ne')
        self.nPlotCanvas = self.nPlot.canvas
        self.nPlotLayout.addWidget(self.nPlotCanvas)
        self.nPlot.parent = self.nPlotLayout
         
        self.nPlot.axes.get_xaxis().get_major_formatter().set_useOffset(False)


    def createjPlot(self):
        try:
            self.jPlotLayout.removeWidget(self.jPlotCanvas)
            self.jPlotCanvas.close()
        except:
            pass

        self.jPlot = TemporalCurrentPlot(self)
        self.jPlotCanvas = self.jPlot.canvas
        self.jPlotLayout.addWidget(self.jPlotCanvas)
        self.jPlot.parent = self.jPlotLayout
            
        self.jPlot.axes.get_xaxis().get_major_formatter().set_useOffset(False)
        
        self.jToolbar = NavigationToolbar(self.jPlot.canvas, self)
        self.jToolbar.hide()
        self.btnPan.clicked.connect(self.jToolbar.pan)
        self.btnZoom.clicked.connect(self.jToolbar.zoom)
        

    def onPanZoom(self,event):
        self.updatexPlot()


    def getInterpretedLangmuirData(self):
        self.statusbar.showMessage('Fetching Langmuir data...')
        exp = str(self.comboDiagInt.currentText())
        try:
            self.shot = dd.shotfile(
                                self.langdiag,
                                self.shotnr,
                                experiment=exp)
        except:
            try:
                print "Could not find {} shotfile for user {}. Trying AUGD...".format(self.langdiag,exp)
                self.shot = dd.shotfile(self.langdiag, self.shotnr)
            except Exception:
                print "Shot number could not be read"
                self.statusbar.showMessage("Shot number could not be read.")
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("The Langmuir probe data for this shot could not be loaded.")
                msg.setInformativeText("Please make sure you entered an existing shot number. It could also be that your connection to the AFS is not set up correctly or your internet connection is not working.")
                msg.setWindowTitle("Shot could not be loaded")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.setDefaultButton(QMessageBox.Ok)
                msg.setEscapeButton(QMessageBox.Ok)
                msg.exec_()
                self.hideProgress()
                return False
            
        self.timeArray = self.getTimeArray(self.shot)
        self.progBar.setValue(20)
        self.signalNames = self.shot.getSignalNames()

        # Count number of signals to be loaded to accurately show progress in widget
        signalNum = 0.0
        for probe in self.signalNames:
            if probe.startswith('ne-ua') or probe.startswith('te-ua'):
                signalNum +=1

        # Load signals into array
        progress = self.progBar.value()
        self.langData = {}
        self.probes = []
        self.uniqueProbes = []
        for probe in self.signalNames:
            if probe.startswith('ne-ua') or probe.startswith('te-ua'):
                try:
                    test = self.shot(probe).data
                    test = self.shot(probe).time
                except Exception:
                    print "Signal {} cannot be read and is skipped. Probably its status does not permit access".format(probe)
                else:
                    if probe[3:] not in self.uniqueProbes:
                        self.uniqueProbes.append(probe[3:])
                    self.probes.append(probe)
                    if probe not in self.langData.keys():
                        self.langData[probe] = {}
                    self.langData[probe]['data'] = self.shot(probe).data
                    self.langData[probe]['time'] = self.shot(probe).time
                    print "Successfully read signal", probe

                    progress += (70-20)/signalNum
                    self.progBar.setValue(progress)

        self.progBar.setValue(70)


    def getStrikelineData(self):
        self.statusbar.showMessage('Fetching strikeline data...')
        exp = str(self.comboDiagEqu.currentText())
        try:
            self.shot = dd.shotfile(
                                self.sldiag,
                                self.shotnr,
                                experiment=exp)
        except:
            print "Could not find {} shotfile for user {}. Trying AUGD...".format(self.sldiag,exp)
            try:
                self.shot = dd.shotfile(self.sldiag, self.shotnr)
            except Exception:
                msg = QMessageBox()
                msg.setText("The Langmuir probe data for the shot with the specified number could not be loaded. Please make sure you entered an existing shot number. It could also be that your connection to the AFS is not set up correctly or your internet connection is not working.")
                msg.setWindowTitle("Shot could not be loaded")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.setDefaultButton(QMessageBox.Ok)
                msg.setEscapeButton(QMessageBox.Ok)
                self.hideProgress()
                return False

        self.progBar.setValue(90)

        # Strikeline coordinates
        self.ssl = {}
        self.Rsl = {}
        self.zsl = {}
        
        try:
            self.ssl['data'] = self.shot('Suna2b').data
            self.ssl['time'] = self.shot('Suna2b').time
            self.Rsl['data'] = self.shot('Runa2b').data
            self.Rsl['time'] = self.shot('Runa2b').time
            self.zsl['data'] = self.shot('Zuna2b').data
            self.zsl['time'] = self.shot('Zuna2b').time
        except Exception:
            print "Strikeline positions could not be read!"
            self.hideProgress()
            return False
        else:
            print "Successfully read strikeline positions"

    
    def getELMdata(self):
        self.statusbar.showMessage('Fetching ELM times...')
        exp = str(self.comboDiagELM.currentText())
        try:
            shot = dd.shotfile(
                        self.ELMdiag,
                        self.shotnr,
                        experiment=exp)
        except:
            print "Could not find {} shotfile for user {}. Trying AUGD...".format(self.ELMdiag,exp)
            try:
                shot = dd.shotfile(self.ELMdiag,self.shotnr)
            except:
                print "No ELM shotfile could be found. Aborting..."
                self.hideProgress()
                return False
    
        self.ELMonsets = shot('t_begELM')
        self.ELMends   = shot('t_endELM').data
        self.ELMmaxima = shot('t_maxELM').data
        ELMtotalDurations = []
        i=0
        while i < self.ELMonsets.size:
            if i+1 < self.ELMonsets.size:
                dt = self.ELMonsets[i+1] - self.ELMonsets[i]
            else:
                dt = 0
            ELMtotalDurations.append(dt) 
            i += 1
        self.ELMtotalDurations = np.array(ELMtotalDurations)


    def getShot(self):
        """ Retrieves langmuir data and strikeline positions from AUG shotfiles. This is an expensive operation and should only be invoked when loading a new shotfile. """
        # If shot number not valid, prompt user and abort
        try:
            self.shotnr = int(self.shotNumberEdit.text())
        except Exception:
            print "Shot number invalid"
            self.statusbar.showMessage("Shot number invalid")
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Please make sure to enter an integer.")
            msg.setWindowTitle("Invalid shot number")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setDefaultButton(QMessageBox.Ok)
            msg.setEscapeButton(QMessageBox.Ok)
            msg.exec_()
            return False

        # If shot number not five-digit, load default shot
        if(len(str(self.shotnr)) != 5): 
            self.shotnr = 32273
            self.shotNumberEdit.setText(str(self.shotnr))

        # Get temperature and density data from langmuir diags
        self.getInterpretedLangmuirData()

        # Set timeline scrollbar min and max values
        # Here the absolute maximum value of all time data arrays is used. Data evaluation will be unreliable if the time data arrays vary from probe to probe
        maxDataPoints = max(self.langData[key]['time'].size for key in self.langData.keys())
        self.xTimeSlider.setRange(0, maxDataPoints-1)
        
        # Get strikeline positions from diagnostic
        self.getStrikelineData()
        
        # Get ELM times
        self.getELMdata()

        # Reset status messages and progress bar
        self.statusbar.showMessage('')
        self.progBar.setValue(100)
        self.hideProgress()

        return True


    def hideProgress(self):
        """ Removes progressbar widget from the statusbar and resets it to the value 0. """
        self.statusbar.removeWidget(self.progBar)
        self.progBar.setValue(0)


    def quit(self):
        """ Closes application """
        self.close()


    def about(self):
        """ Shows information about the application in a message box. """
        QtGui.QMessageBox.about(self, "About",
                """This program plots langmuir probe data from ASDEX Upgrade shotfiles using the pwwdd interface provided by Bernhard Sieglin.

                Version: December 2016
                Written by: Amazigh Zerzour
                """)


    def savexPlot(self):
        """ Saves spatial plot figure. """
        t  = self.xPlot.realtime
        dt = str(self.lblRealTWidth.text()).split()[1]
        defaultName = 'Spatial_{}_{:.7f}s_{}{}'.format(self.xPlot.quantity, t,
                                                        dt, self.defaultExtension)

        dialog = QtGui.QFileDialog()
        dialog.setDefaultSuffix(self.defaultExtension)
        fileName = dialog\
                        .getSaveFileName(self,
                                        directory='./' + defaultName,
                                        caption = "Save figure as",
                                        filter="PNG (*.png);;EPS (*.eps);;SVG (*.svg)",
                                        selectedFilter=self.defaultFilter)
        fileName = str(fileName)
        ok = True
        if ok:
            if len(fileName.split('.')) < 2:
                print "Extension missing. Figure not saved"
                return
            fmt = fileName.split('.')[-1]
            self.xPlot.fig.savefig(fileName, format=fmt)


    def savejPlot(self):
        """ Saves current density plot figure. """
        plot = self.jPlot
        defaultName = 'Temporal_{}_{:.7f}s_{:.0f}us{}'.format(plot.quantity,
                                                        plot.indicator.time,
                                                        plot.indicator.dt*10**6,
                                                        self.defaultExtension)
        dialog = QtGui.QFileDialog()
        dialog.setDefaultSuffix(self.defaultExtension)
        fileName = dialog\
                        .getSaveFileName(self,
                                        directory='./' + defaultName,
                                        caption = "Save figure as",
                                        filter="PNG (*.png);;EPS (*.eps);;SVG (*.svg)",
                                        selectedFilter=self.defaultFilter)
        fileName = str(fileName)
        ok = True
        if ok:
            if len(fileName.split('.')) < 2:
                print "Extension missing. Figure not saved"
                return
            fmt = fileName.split('.')[-1]
            plot.fig.savefig(fileName, format=fmt)


    def toggleCELMAs(self):
        self.jPlot.toggleCELMA()
        self.TPlot.toggleCELMA()
        self.nPlot.toggleCELMA()


    def clearCELMAs(self):
        self.jPlot.clearCELMA()
        self.TPlot.clearCELMA()
        self.nPlot.clearCELMA()
        self.jPlotCanvas.draw()
        self.TPlotCanvas.draw()
        self.nPlotCanvas.draw()



class ColorPatch(QtGui.QWidget):
    def __init__(self, color):
        super(ColorPatch, self).__init__()
        self.color = mpl.colors.rgb2hex(color)


    def paintEvent(self,event):
            qp = QPainter()
            qp.begin(self)
            self.drawPatch(qp)
            qp.end()


    def drawPatch(self, qp):
        qp.setBrush(QColor(self.color))
        qp.drawRect(10, 10, 10, 10)


class Tools():
    @staticmethod
    def find_between( s, first, last ):
        try:
            start = s.index( first ) + len( first )
            end = s.index( last, start )
            return s[start:end]
        except ValueError:
            return ""


class Indicator():
    """ Class for creating an indicator on a temporal plot to show the time that is displayed in the spatial plot. """
    def __init__(self, parent):
        self.parent = parent
        self.gui    = parent.gui
        self.color  = self.gui.config['Indicators']['color']

        self.pos    = 0
        self.time   = 0
        self.tminus = 0
        self.tplus  = 0
        self.dt     = 0

        self.slide()


    def slide(self):
        """ Repositions indicator according to time slider value. """
        # Get current time from time slider and convert it
        self.pos    = self.gui.xTimeSlider.value()
        self.time   = self.gui.dtime[self.pos]
        self.tminus = self.time - self.gui.indicator_range[0]
        self.tplus  = self.time + self.gui.indicator_range[1]
        self.dt     = self.tplus - self.tminus

        # Update previous indicator if there already is one
        if hasattr(self, "indic"):
            self.indic.set_xdata(self.time)
            xy = self.indic_fill.get_xy()
            xy = [
                    [self.tminus,xy[0][1]],
                    [self.tminus,xy[1][1]],
                    [self.tplus,xy[2][1]],
                    [self.tplus,xy[3][1]],
                    [self.tminus,xy[4][1]]
                ]

            self.indic_fill.set_xy(xy)

            self.parent.axes.draw_artist(self.parent.axes.patch)
            for plot in self.parent.plots.values():
                if plot.get_visible():
                    self.parent.axes.draw_artist(plot)
            self.parent.axes.draw_artist(self.indic)
            self.parent.axes.draw_artist(self.indic_fill)
            self.parent.canvas.update()
            self.parent.canvas.flush_events()

        #Plot new indicator if there is none
        else:
            self.indic      = self.parent.axes.axvline(x=self.time, color=self.color)
            self.indic_fill = self.parent.axes.axvspan(self.tminus, self.tplus,
                                                        alpha=0.5, color=self.color)
            self.parent.canvas.draw()



class Conversion():
    @staticmethod
    def valtoind(realtime, timearray):
        """ Converts a real time value to an index in a given array with time values. This is achieved by comparing the real time value to the array elements and returning the index of the closest one. """
        return np.abs((timearray - realtime)).argmin()

    @staticmethod
    def removeNans(array, refarray=None):
        """ Removes values from array based on the indices of NaN values in
        refarray. If refarray is not specified, NaN values are removed from
        array. Returns a numpy array. """ 
        # If refarray was passed, comparing it to None would be deprecated
        if type(refarray).__name__ == 'NoneType':
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



class Plot(object):
    def __init__(self, gui):
        self.gui = gui
        config = gui.config['Plots']
        self.region = config['region']
        self.segment = config['segment']
        self.dpi    = config['dpi']
        self.ignoreNans    = config['ignoreNans']

        self.ELMonsets = gui.ELMonsets
        self.ELMends   = gui.ELMends
        self.ELMtotalDurations   = gui.ELMtotalDurations


        self.parents = {
                'te': 'TPlotLayout',
                'ne': 'nPlotLayout',
                'j': 'jPlotLayout',
                }

        self.fig = Figure(dpi=self.dpi)
        self.axes = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)


    def getTimeArray(self, shot=None, timeArrays=None):
        if shot is None and timeArrays is None:
            print "Either shot or an array of time arrays must be provided"
            return
        if timeArrays is None:
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
            if len(timeArrays) == 0:
                print "Failed to find any time arrays for these signals"
                return

        equal = (np.diff(
                    np.vstack(timeArrays).reshape(len(timeArrays),-1),axis=0)\
                    ==0).all()

        if not equal:
            print """Warning: time base arrays fetched from shotfile are not
            equal! Proceed with caution."""
        return timeArrays[0]


class SpatialPlot(Plot):
    """ Class for spatial temperature and density plots. Subclass of Plot. Needs the application object as an argument to be able to manipulate GUI elements. """
    ### TO DO
    #
    # - rztods depends on realtime_arr
    # - rztods should save relative positions with timestamps to rule out mismatches when plotting
    # - In update(), proper scaling of the scatter is achieved by adding a plot, rescaling, and removing that plot. A more elegant solution is desirable
    #
    def __init__(self, gui):
        super(SpatialPlot, self).__init__(gui)

        config = gui.config['Plots']['Spatial']
        self.coloring = config['coloring']
        self.defaultColor = config['defaultColor']
        self.posFile = config['positionsFile']
        self.fixyLim = config['fixyLim']
        # If this value is 1 then averaged values are nohttp://thecodeship.com/patterns/guide-to-python-function-decorators/t nans if one or more
        # of the values used to calculate it is a nan
        # This setting is ignored if all values to be averaged over are nans
        self.ignoreNans = self.ignoreNans

        self.scatters = {}
        self.quantities = {
                'Temperature': 'te',
                'Density': 'ne',
                'Saturation current density': 'j'
                }
        self.axLabels = {
                'Temperature': 'T$_{e,t}$ [eV]',
                'Density': 'n$_{e,t}$ [1/m$^3$]',
                'Saturation current density': 'j$_{sat}$ [kA/m$^2$]'
                }

        # Number of timesteps around the current time to include in the plot (see getShotData())
        self.Dt = gui.Dt
        # Number of data points over which to average
        self.avgNum = gui.avgNum
        self.rawdata = gui.langData # Needed for method <coherentELMaveraging> shared with class <SpatialCurrentPlot>

        self.Rsl = self.gui.Rsl
        self.ssl = self.gui.ssl
        self.zsl = self.gui.zsl
        
        self.option = self.gui.getPlotOption()
        self.quantity = self.quantities[self.option]
        self.timeArray = self.gui.timeArray

        # Set axes labels
        self.axes.set_title("{} distribution on the outer lower target plate".format(self.option))
        self.axes.set_ylabel(self.axLabels[self.option])
        self.axes.set_xlabel("$\Delta$s [m]")

        # Hide axes offsets
        #self.axes.yaxis.get_offset_text().set_visible(False)
        #self.axes.xaxis.get_offset_text().set_visible(False)
        #
        self.getShotData(self.gui.langData)
        self.getProbePositions()
        self.rztods()
        self.averageData()
        self.initPlot()
        #self.plotFit()

    
    def coherentELMaveraging(self, POIrelative, marker=None, color=None):
        """
        Performs an average over a specified amount of ELMs at a point of
        interest (POI) relative to the ELM beginning

        - Within certain time range OR for certain amount of ELMs
        - Iterate over ELMs
        - Take data at ELM times (within intervall, as previously)
        - Plot all points OR average them for each probe
        """
        print "\n ----- CELMA -----\n"
        oldLimits = self.axes.get_ylim()

        # Get ELM range from GUI
        try:
            self.CELMAELMnum = int(self.gui.editCELMAELMnum.text())
        except ValueError:
            print "Invalid number of ELMs while averaging"
            self.CELMAELMnum = 5
        try:
            self.CELMAphaseOn = float(self.gui.editCELMAstartTime.text())
        except ValueError:
            print "Invalid starting time for ELM averaging"
            self.CELMAphaseOn = 4.7
        try:
            self.CELMAphaseEnd = float(self.gui.editCELMAendTime.text())
        except ValueError:
            print "Invalid end time for ELM averaging"
            self.CELMAphaseEnd = 5 

        self.CELMAs = []
        handles = []
        labels = []
        data_tot = {}
        positions_tot = {}
        unit = self.gui.comboPOIunit.currentText()

        # Get data
        j = 0
        for i, (ton,dt) in enumerate(zip(self.gui.ELMonsets, self.gui.ELMtotalDurations)):
            if j < self.CELMAELMnum:
                if ton >= self.CELMAphaseOn and ton+dt <= self.CELMAphaseEnd:
                    # Use duration of previous ELM to determine pre-ELM POI
                    if POIrelative < 0:
                        # If this is the very first ELM, pre-ELM POI is not
                        # defined
                        if i==0:
                            return
                        dt = self.gui.ELMtotalDurations[i-1]
                    print "\nELM", j
                    # POI in realtime
                    if unit == '%':
                        POI = ton + dt * POIrelative
                    if unit == 'ms':
                        POI = ton + POIrelative
                    print "Position:", POI

                    if POI not in data_tot.keys():
                        data_tot[POI] = {}
                    if POI not in positions_tot.keys():
                        positions_tot[POI] = {}

                    # Data retrieval
                    data = self.getShotData(self.rawdata, POI)
                    positions = self.getProbePositions()
                    positions = self.rztods(positions)
                    data, positions = self.averageData(data, positions)
                    if self.quantity == 'j':
                        data = self.calibrateData(data)

                    for (probe,vals), poss in zip(data.iteritems(), positions.values()):
                        if probe not in data_tot.keys():
                            data_tot[POI][probe] = list(vals)
                        else:
                            data_tot[POI][probe].extend(list(vals))
                        if probe not in positions_tot.keys():
                            positions_tot[POI][probe] = list(poss)
                        else:
                            positions_tot[POI][probe].extend(list(poss))
                    j += 1

        POIs = sorted(data_tot.keys())

        showLegend = self.gui.menuShowLegend.isChecked()
        average = self.gui.menuShowAverages.isChecked()
        try:
            alpha = float(self.gui.transparency.text())
        except ValueError:
            alpha = 1

        # Average points per probe to one data point if desired
        if average:
            dataAccu = {}
            possAccu = {}
            for POI in POIs:
                for probe, data in data_tot[POI].iteritems():
                    if probe not in dataAccu:
                        dataAccu[probe] = data
                    else:
                        dataAccu[probe].extend(data)
                for probe, poss in positions_tot[POI].iteritems():
                    if probe not in possAccu:
                        possAccu[probe] = poss
                    else:
                        possAccu[probe].extend(poss)
            for probe, data in dataAccu.iteritems():
                if 'Averaged' not in data_tot:
                    data_tot['Averaged'] = {}
                data_tot['Averaged'][probe] = np.nanmean(data)
            for probe, poss in possAccu.iteritems():
                if 'Averaged' not in positions_tot:
                    positions_tot['Averaged'] = {}
                positions_tot['Averaged'][probe] = np.nanmean(poss)
            POIs.append('Averaged')


        # PLOT PER ELM SO PLOTS CAN BE DISTIGUISHED IN LEGEND
        if color is None:
            colors = cm.rainbow(np.linspace(0,1,len(data_tot)))
        else:
            colors = [color]*len(data_tot)
        for color, POI in zip(colors, POIs):
            if POI == 'Averaged':
                for probe in data_tot['Averaged'].keys():
                    x = positions_tot['Averaged'][probe]
                    y = data_tot['Averaged'][probe]
                    self.CELMAs.append( self.axes.scatter(x,y, marker='*', color=color) )
            for probe, vals in data_tot[POI].iteritems():
                poss = positions_tot[POI][probe]
                self.CELMAs.append( self.axes.scatter(poss, vals, color=color,
                    alpha=alpha, marker=marker) )
            # Use last plot of this ELM as legend handle
            handles.append(self.CELMAs[-1])
            labels.append(POI)

        if showLegend:
            self.fig.legend(labels=labels,handles=handles)

        if not self.fixyLim:
            self.axes.set_xlim(-0.07,0.3)
        else:
            self.axes.set_ylim(oldLimits)

        self.canvas.draw()

        return [POI for POI in POIs if POI != 'Averaged']


    def plotFit(self):
        """ Plots a fit function to the shown data based on the Eich function
        """
        # Get currently visible data
        offsets = []
        for scatter in self.scatters.values():
            if scatter.get_visible():
                offsets.extend(scatter.get_offsets())
        locs = np.array([el[0] for el in offsets])
        data = np.array([el[1] for el in offsets])

        if data.size == 0:
            return
        
        # Sort data from "left to right"
        data = data[locs.argsort()]
        locs = locs[locs.argsort()]
        
        # Normalize y values so curve_fit will not break because of too
        # large/small values
        scal = np.max(data)
        y = data/scal
        x = np.arange(np.min(locs), np.max(locs), 0.001)
        
        ft = FitFunctions.fit(locs, y)
        yft= FitFunctions.eich_model(x, *ft)
       
        if hasattr(self, 'fit'):
            self.fit.remove()
        #    self.fit.set_xdata(x)
        #    self.fit.set_ydata(yft*scal)
        #    self.axes.draw_artist(self.fit)
        #    self.canvas.update()
        #else:
        self.fit, = self.axes.plot(x, yft*scal)
        self.canvas.draw()


    def getShotData(self, data, time=None):
        """ Gets data specified by class variables "quantity" and "region" from shotfile for times in range dt. Saves this data and associated timestamps in class arrays "data" and "realtime_arr", respectively """
        ##############
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
        input = data

        if time == None:
            # Get current time index from GUI slider
            time = self.gui.xTimeSlider.value()
        else:
            # Convert supplied times to indices
            time = Conversion.valtoind(time, self.timeArray)

        # Time range expressed by indices in shotfile
        self.dt = (self.gui.Dt - 1)/2 

        # Min and max time expressed by indices in shotfile
        # Prevent tmin to take negative values so getting value by index
        # won't cause problems
        tmin = max(time - self.dt, 0)
        tmax = time + self.dt

        probeNamePrefix = self.quantity + '-' + self.region

        self.data = {}
        self.realtime_arr = {}
        for probe in input.keys():
            # filter for specified probes
            if probe.startswith(probeNamePrefix):
                dtime = input[probe]['time']
                data = input[probe]['data']

                # Time converted to actual time values
                # If there is an index error, take the global minimum or maximum
                self.realtmin = dtime[tmin]
                try:
                    self.realtmax = dtime[tmax]
                except Exception:
                    self.realtmax = dtime[-1]
                    print("Maximum value of time range to evaluate is out of range. Using maximum of available time range.")
                try:
                    self.realtime = dtime[time]
                except Exception:
                    print "Could not determine realtime from time array"
                    if time >= dtime.size: self.realtime = dtime[-1]
                    elif time < dtime.size: self.realtime = dtime[0]
                    else: print("FATAL: Realtime could not be determined.")
                
                # Filter for time range. 
                ##### SAVE DATA TO ARRAY #####
                ind = np.ma.where((dtime >= self.realtmin) & (dtime <= self.realtmax))
                self.data[probe] = data[ind]
                self.realtime_arr[probe] = dtime[ind]

                # Save the time data of the last probe as the global time data. This assumes that all time arrays of the probes are identical
                self.dtime  = dtime
                realdtminus = abs(self.realtime - self.realtmin)
                realdtplus  = abs(self.realtime - self.realtmax)
                self.realdtrange = (realdtminus, realdtplus)

        return self.data


    def averageData(self, data=None, locs=None):
        """ Averages data points over specified number of points. """
        if data is not None:
            self.data = data
        if locs is not None:
            self.plotPositions = locs

        # If no averaging wished, use the data as received from shotfile
        if self.avgNum == 0:
            return

        # Averaging
        for probe, data in self.data.iteritems():
            locs = self.plotPositions[probe]
           
            # If this probe didn't record any values at this point in time, continue with the next one
            if data.size == 0: 
                continue

            i=0
            # Take values in the range 0 to avgNum-1 and average them
            # valcount is used to calculate average value because of the possibility of nans
            data_avgs = []
            loc_avgs = []
            while True:
                xsum=0
                locsum=0
                valcount=0

                for x in np.arange(self.avgNum):
                    # Ignore nans if wished. Ignoring will ensure plot points
                    # to be plotted even if one or more of its data points are
                    # NaNs
                    if self.ignoreNans and np.isnan(data[i]):
                        pass
                    else:
                        xsum += data[i]
                        locsum += locs[i]
                        valcount += 1 
                    i += 1

                # If all values were nans, ignore the result no matter what the value of ignoreNans is
                if valcount == 0:
                    avg = np.NAN
                    locavg = np.NAN
                else:
                    avg = xsum/float(valcount)
                    locavg = locsum/float(valcount)

                # Save averages to new array
                data_avgs.append(avg)
                loc_avgs.append(locavg)

                # End loop if end of data array will be reached next time
                if i + self.avgNum > data.size: 
                    break
            
            self.data[probe] = np.array(data_avgs)
            self.plotPositions[probe] = np.array(loc_avgs)
        return self.data, self.plotPositions


    def getProbePositions(self):
        """ 
        Gets positions of probes in the specified region in terms of R,z
        coordinates. Saves the coordinates as tuples in a class parameter array
        "probePositions" with the probe names as keys. 
        """
        self.probePositions = {}

        # Read probe name and R and z coordinates of each probe
        with open(self.posFile) as f:
            lines = f.readlines()
            for line in lines:
                probeName = line.split()[0][1:]                 # Probe name
                R = float(line.split()[1].replace(",","."))     # R
                z = float(line.split()[2].replace(",","."))     # z
                 
                self.probePositions[probeName] = (R,z)
        return self.probePositions


    def rztods(self, positions=None):
        """ Converts probe positions from (R,z) coordinates to delta-s
        coordinate based on current strikeline position. This enables plots in
        units of delta-s along the x-axis. It is implicitly assumed that the
        divertor tile is flat."""
        if positions is not None:
            self.probePositions = positions

        self.plotPositions = {}
        
        for probe in self.data.keys():
            self.plotPositions[probe] = []

            # Get R and z coordinates of probe
            probeName = probe.split('-')[-1]
            R_p = self.probePositions[probeName][0]
            z_p = self.probePositions[probeName][1]

            for time in self.realtime_arr[probe]:
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

                # Calculate delta-s
                # Assumption: divertor tile is flat
                ds = np.sqrt( (R_sl-R_p)**2 + (z_sl-z_p)**2 ) 
                # If the z coordinate of the probe is smaller than that of the
                # strikeline, 
                # then the delta-s associated with this probe at this time is
                # negative
                if z_p < z_sl: ds = -ds

                self.plotPositions[probe].append(ds)
        return self.plotPositions


    def initPlot(self, ):
        """ Populates canvas with initial plot. Creates PathCollection objects that will be updated when plot has to change based on GUI interaction."""
        for probe in self.data.keys():
            x = []
            y = []
            for value,position in zip(self.data[probe], self.plotPositions[probe]):
                x.append(position)
                y.append(value)

            # Use different color for each probe if wished
            if self.coloring:
                color = self.gui.probeColors[probe.split('-')[1]]
            else:
                color = self.defaultColor

            # Plot
            self.scatters[probe.split('-')[1]] = self.axes.scatter(x, y, color=color)

        # Add text box showing the current time
        self.updateText()
        
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
        t    = self.realtime
        dt   = (self.realdtrange[0]*10**6, 
                self.realdtrange[1]*10**6)

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
        oldyLabel   = self.axes.get_ylabel()
        yOffsetText = self.axes.yaxis.get_offset_text().get_text()

        # Make offset text pretty
        if 'e' in yOffsetText:
            yOffsetText = yOffsetText.replace('e','0$^{') + '}$'

        # Add offset to label

        # Add unit to label
        if len(oldyLabel.split()) > 1: 
            newyLabel = oldyLabel.split()[0] + ' ' \
                        + yOffsetText + ' ' + oldyLabel.split()[-1]
        else:
            newyLabel = oldyLabel
        self.axes.set_ylabel(newyLabel)


    def update(self, ):
        """ Updates scatter plots based on the current time. If y-axis is
        fixed, only the background and the scatter plots are updated with
        a succeding call of ax.update() which considerably improves
        performance. If the y-axis is not fixed, the whole canvas is
        re-drawn."""
        self.avgNum = self.gui.avgNum
        self.getShotData(self.rawdata)
        self.rztods()
        self.averageData()

        xtot = []
        ytot = []
        for probe in self.data.keys():
            scatter = self.scatters[probe.split('-')[1]]
            x = []
            y = []
            for value,position in zip(self.data[probe], self.plotPositions[probe]):
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
            # Scatter plots
            for scatter in self.scatters.values():
                self.axes.draw_artist(scatter)
            # Spines
            #for spine in self.axes.spines.values():
            #    self.axes.draw_artist(spine)
            self.canvas.update()
            self.canvas.flush_events()

        # Re-draw everything if axes are not fixed
        else:
            plot, = self.axes.plot(xtot,ytot)
            self.axes.relim()
            self.axes.autoscale()
            self.axes.set_xlim(-0.07,0.3)
            plot.remove()
            #if min(ytot) > 0:
            #    self.axes.set_ylim(min(ytot)*0.9, max(ytot)*1.2)
            #if min(ytot) == 0:
            #    self.axes.set_ylim(-1, max(ytot)*1.2)
            #else:
            #    self.axes.set_ylim(min(ytot)*1.2, max(ytot)*1.2)
            ## This creates too much space on the right
            ##self.axes.set_xlim(min(xtot)*0.9, max(xtot)*1.1)
            #self.axes.set_xlim(-0.1, 0.35)
            self.updateAxesLabels()
            self.axes.set_xlim(-0.07,0.3)
            self.canvas.draw()
            

    def toggleProbe(self, probe, vis):
        """ Toggle probes to show in scatter plot. """
        print "Toggling probe", probe
        scatter = self.scatters[probe]
        scatter.set_visible(vis)


    def setTimeText(self):
        """ Updates GUI time edit field based on scrollbar value """
        # GUI scrollbar provides timestep (index of time array)
        time = self.gui.xTimeSlider.value()
        # Convert to realtime
        realtime = self.dtime[time]
        # Update line edit text
        self.gui.xTimeEdit.setText("{:.4f}".format(realtime))


    def setxTimeSlider(self):
        """ Updates time scrollbar based on text in GUI time edit field"""
        self.slider = self.gui.xTimeSlider

        # GUI line edit expects a real time value
        realtime = float(self.gui.xTimeEdit.text())

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
        self.gui.xTimeEdit.setText("{:.10f}".format(self.dtime[time]))


    def setDurationText(self):
        """ Updates the shot duration in the info bar. """
        self.gui.dynDurationLabel.setText("{:.3f}".format(self.dtime[-1]))



class TemporalPlot(Plot):
    """ Class for temporal temperature and density plots. Subclass of Plot. Needs the application object as an argument to be able to manipulate GUI elements and the quantity that is to be plotted. """
    #######
    # To do:
    #
    # - Original axes limits are overwritten when zoomed in and updating plot by (un)checking a probe. When zoomed in, zoom level should be retained but the new maximum/minimum values should be saved for "resetting"
    # - Rename reset to View all
    #
    def __init__(self, gui, quantity):
        super(TemporalPlot, self).__init__(gui)

        config = gui.config['Plots']['Temporal']
        self.axTitles = config['axTitles']
        self.showGaps = config['showGaps']
        self.rescaling = config['rescale-y']

        self.quantity = quantity
        self.selectedProbes = self.gui.selectedProbes['t']
        self.parent = getattr(gui, self.parents[quantity])

        self.data = {}
        self.time = {}
        self.avgData = {}
        self.avgTime = {}
        self.plots = {}
        self.xlim_orig = [9999999999999, -999999999999]
        self.ylim_orig = [9999999999999, -999999999999]

        self.CELMAs = []
        self.CELMAactive = False
        self.CELMAexists = False

        # Enable span selector for ELM evaluation
        self.spanSelector = SpanSelector(self.axes, self.onSpanSelect,
                                        'horizontal', span_stays=True,
                                        useblit=True)

        # Set axes labels
        self.axes.set_ylabel(self.axTitles[self.quantity])
        self.axes.set_xlabel('Time [s]')
        self.axes.autoscale()
        self.fig.tight_layout()

        # Initial plot
        self.getShotData()
        self.averageData()
        self.update()
        self.indicator = Indicator(self)

        self.axes.callbacks.connect('xlim_changed', self.setSliderRange)
        self.axes.callbacks.connect('xlim_changed', self.rescaleyAxis)


    def clearCELMA(self):
        self.gui.btnCELMA.setText('Average')
        for scat in self.CELMAs:
            try: scat.remove()
            except ValueError: pass
        self.CELMAactive = False
        self.CELMAexists = False
        for line in self.axes.lines:
            line.set_visible(True)


    def toggleCELMA(self):
        self.CELMAmode = str(self.gui.comboCELMAmode.currentText())
        self.CELMAprobe = self.quantity + \
                            '-' + \
                            str(self.gui.comboCELMAprobe.currentText())

        if self.CELMAactive:
            self.gui.btnCELMA.setText('Average')
            for CELMA in self.CELMAs:
                CELMA.set_visible(False)
            for line in self.axes.lines:
                line.set_visible(True)
            self.CELMAactive = False

        else:
            self.gui.btnCELMA.setText('Temporal plots')
            for line in self.axes.lines:
                line.set_visible(False)
            if not self.CELMAexists:
                self.coherentELMaveraging()
                self.CELMAexists = True
            else:
                for CELMA in self.CELMAs:
                    CELMA.set_visible(True)
            self.CELMAactive = True
        self.axes.relim()
        self.canvas.draw()


    def onSpanSelect(self, xmin, xmax):
        self.gui.ELMphase = (xmin, xmax)
        #self.gui.btnELMplot.show()


    def rescaleyAxis(self, event):
        """
        Rescales yaxis to better resolve data in y-direction if
        TemporalPlot.rescaling is True. This function is triggered when zooming
        in x-direction.
        """
        pass
        #print dir(event)
        #print "RESCALE TRIGGERED"
        #if self.rescaling:
        #    print "Rescaling axes"
        #    # Get currently visible ydata based on current xdata
        #    yvis = []
        #    xlims= self.axes.get_xlim()
        #    for plot in self.plots.values():
        #        xdata = plot.get_xdata()
        #        ydata = plot.get_ydata()

        #        for x, y in zip(xdata, ydata):
        #            if xlims[0] < x < xlims[1]:
        #                yvis.append(y)

        #    # Rescale yaxis based on visible ydata
        #    if len(yvis) > 0:
        #        self.axes.set_ylim(min(yvis), max(yvis))


    def getShotData(self):
        #print("Getting temporal shot data")
        self.probeNamePrefix = self.quantity + '-' + self.region
        for probe in self.gui.langData.keys():
            if probe.startswith(self.probeNamePrefix):
                self.time[probe] = self.gui.langData[probe]['time']
                self.data[probe] = self.gui.langData[probe]['data']


    def averageData(self):
        """ Averages data for selected probes if average data does not exist for them yet. """
        self.selectedProbes = self.gui.selectedProbes['t']

        for probe in self.selectedProbes:
            if probe.startswith(self.probeNamePrefix) and probe not in self.avgData.keys():
                self.avgData[probe] = []
                self.avgTime[probe] = []

                i=0
                while True:
                    avgData = (self.data[probe][i] + self.data[probe][i+1])/2
                    avgTime = (self.time[probe][i] + self.time[probe][i+1])/2
                    
                    self.avgData[probe].append(avgData)
                    self.avgTime[probe].append(avgTime)
                    
                    i += 2
                    
                    # Exit loop when end of data array is reached
                    if i+1 == self.data[probe].size:
                        self.avgData[probe].append(self.data[probe][i])
                        self.avgTime[probe].append(self.time[probe][i])
                        break
                    if i == self.data[probe].size: break
                 
                self.data[probe] = np.array(self.avgData[probe])
                self.time[probe] = np.array(self.avgTime[probe])


    def reset(self):
        """ Resets the plot to its original state. """
        # Reset axes limits
        self.axes.set_xlim(self.xlim_orig)
        self.axes.set_ylim(self.ylim_orig)

        self.axes.relim()
        self.axes.autoscale_view()


    def update(self):
        """ Plots temporal data if it hasn't been plotted yet. If it has been plotted, it is set to visible. """
        print "\nPlotting", self.quantity
        # Get currently selected probes from GUI
        self.selectedProbes = self.gui.selectedProbes['t']
        print "Selected probes:", self.selectedProbes
        self.showGaps = self.gui.menuShowGaps.isChecked()

        # Update plots
        for probe in self.data.keys(): 
            # If probe hasn't been plotted yet, is selected, and belongs to this canvas, plot it
            if probe not in self.plots.keys() \
                    and probe in self.selectedProbes \
                    and probe.startswith(self.probeNamePrefix):
                print("{} hasn't been plotted yet".format(probe))
                y = self.data[probe]
                x = self.time[probe]

                # Filter NaNs if wished
                if self.showGaps == False:
                   x = Conversion.removeNans(x,y) 
                   y = Conversion.removeNans(y) 

                # Plot data
                uniqueProbe = probe.split('-')[1]
                color = self.gui.probeColors[uniqueProbe]
                plot, = self.axes.plot(x,y, color=color, zorder=50)

                # Save artist for future reference
                self.plots[probe] = plot

            # If probe has been plotted, is not selected, and is visible, hide it
            elif probe in self.plots.keys() \
                    and probe not in self.selectedProbes \
                    and self.plots[probe].get_visible():
                print("Setting probe {} invisible".format(probe))
                self.plots[probe].set_visible(False)
                self.canvas.draw()

            # If probe has been plotted, is selected, and is hidden, show it
            elif probe in self.plots.keys() \
                    and probe in self.selectedProbes \
                    and not self.plots[probe].get_visible():
                print("Setting probe {} visible".format(probe))
                self.plots[probe].set_visible(True)
                self.canvas.draw()

        # Get current axes limits
        xlim = self.axes.get_xlim()
        ylim = self.axes.get_ylim()
        
        # Compare current axes limits with current maximum and minimum values
        # If the minimum/maximum limits are surpassed, save the new limits 
        # so they will be adopted when resetting the plot and all plots will show fully
        self.xlim_orig = [min(self.xlim_orig[0], xlim[0]), max(self.xlim_orig[1], xlim[1])] 
        self.ylim_orig = [min(self.ylim_orig[0], ylim[0]), max(self.ylim_orig[1], ylim[1])] 


    def setSliderRange(self, axes):
        """ Sets the time slider range corresponding to the time range in the temporal plot. """
        minTime = axes.get_xlim()[0]
        maxTime = axes.get_xlim()[1]

        # Set time slider range to range shown in zoomed temporal plot
        self.gui.xTimeSlider.setMinimum(Conversion.valtoind(minTime, self.gui.dtime))
        self.gui.xTimeSlider.setMaximum(Conversion.valtoind(maxTime, self.gui.dtime))


    def coherentELMaveraging(self):
        print "Temporal CELMA"
        time = self.time[self.CELMAprobe]
        data = self.data[self.CELMAprobe]

        self.CELMAbinning = self.gui.cbCELMAbinning.checkState()
        self.CELMAcolor = 'b'
        try:
            self.CELMAELMnum = int(self.gui.editCELMAELMnum.text())
        except ValueError:
            print "Invalid number of ELMs while averaging"
            self.CELMAELMnum = 10

        try:
            self.CELMAphaseOn = float(self.gui.editCELMAstartTime.text())
        except ValueError:
            print "Invalid starting time for ELM averaging"
            self.CELMAphaseOn = 6.0
        try:
            self.CELMAphaseEnd = float(self.gui.editCELMAendTime.text())
        except ValueError:
            print "Invalid end time for ELM averaging"
            self.CELMAphaseOn = 6.2

        ttot = []
        ytot = []
        j = 0
        for ton, dt in zip(self.ELMonsets, self.ELMtotalDurations):
            if j < self.CELMAELMnum:
                if ton >= self.CELMAphaseOn and ton+dt <= self.CELMAphaseEnd:
                    print "\nELM", j
                    tonInd  = Conversion.valtoind(ton, time)
                    tendInd = Conversion.valtoind(ton + dt, time)

                    if self.CELMAmode == 'Default':
                        t = time[tonInd:tendInd] - ton
                        y = data[tonInd:tendInd]
                    elif self.CELMAmode == 'Normalize':
                        t = (time[tonInd:tendInd] - ton) / dt 
                        y = data[tonInd:tendInd]

                    if self.ignoreNans:
                        t = Conversion.removeNans(t,y)
                        y = Conversion.removeNans(y)
                    
                    ttot.extend(t)
                    ytot.extend(y)
                    
                    if not self.CELMAbinning:
                        self.CELMAs.append( self.axes.scatter(t,y,color=self.CELMAcolor) )
                    j += 1
            else:
                break
        
        if self.CELMAbinning:
            print "Binning CELMA"
            ytot = Conversion.removeNans(ytot)
            t    = []
            avgs = []

            try:
                n = int(self.gui.editCELMAbins.text())
            except ValueError:
                print("Bin number input not valid. Using default value.")
                n = 100

            bins = np.linspace(min(ttot),max(ttot),n)

            for left, right in zip(bins[:-1],bins[1:]):
                t.append((left + right)/2)
                to_avg = []
                for val, _t in zip(ytot,ttot):
                    if left <= _t < right:
                        to_avg.append(val)
                avgs.append(np.mean(to_avg))

            t, avgs = zip(*sorted(zip(t,avgs)))
            self.CELMAs.append(
                    self.axes.plot(t,avgs,color=self.CELMAcolor)[0])

        if len(ttot) > 0 and len(ytot) > 0:
            self.axes.set_xlim(min(ttot), max(ttot))
            self.axes.set_ylim(min(ytot), max(ytot))
        else:
            print "Warning: No data found for CELMA. Check start and end times"



class CurrentPlot(Plot):
    """ Temporal current density plot """
    # Get mapping between probes and channels from files at
    # /afs/ipp/home/d/dacar/divertor/ If no file present, try to get the
    # mapping from LSC Calibrate the measurements with probe surfaces to obtain
    # current densities Plot results
    def __init__(self, gui):
        Plot.__init__(self, gui)

        # Configuration
        config = gui.config['Plots']['Temporal']['Current']
        self.mapDir      = config['mapDir']
        self.mapDiag     = config['mapDiag']
        self.diag        = config['diag']
        self.calibFile   = config['calibFile']
        self.mapFilePath = config['mapFile']
        self.showGaps    = gui.config['Plots']['Temporal']['showGaps']
        self.rescaling   = gui.config['Plots']['Temporal']['rescale-y']

        # Attributes
        self.quantity    = 'j'
        self.shotnr      = gui.shotnr
        self.probeNamePrefix = self.quantity + '-' + self.region
        self.selectedProbes  = self.gui.selectedProbes['t']
        self.hasMapping  = False
        self.calib       = {}
        self.map         = {}
        self.rawdata     = {}
        self.data        = {}
        self.avgData     = {}
        self.avgTime     = {}
        self.time        = {}
        self.plots       = {}
        self.xlim_orig   = [9999999999999, -999999999999]
        self.ylim_orig   = [9999999999999, -999999999999]
        self.parent      = getattr(gui, self.parents[self.quantity])

        self.axes.set_ylabel('Current density [A/m$^2$]')
        self.axes.set_xlabel('Time [s]')
        self.axes.autoscale()
        self.fig.tight_layout()

        self.indicator = Indicator(self)

        self.axes.callbacks.connect('xlim_changed', self.setSliderRange)
        self.axes.callbacks.connect('xlim_changed', self.rescaleyAxis)

        self.getShot()
        self.calibrateData()
        self.averageData()
        self.update()


    def getShot(self, diag=None):
        """ Loads jsat data from shotfile. """
        # If no mapping available yet, get it
        if len(self.map) < 1:
            hasMapping = self.getMapping()
        
        if not hasMapping:
            return

        if diag != None:
            self.diag = diag
        self.gui.statusbar.showMessage("Fetching jsat signals...")
        print "\n+++++++++++++++++++++ Getting jsat signals +++++++++++++++++++++++++++"
        exp = str(self.gui.comboDiagRaw.currentText())
        try:
            shot = dd.shotfile(
                            self.diag, 
                            self.shotnr,
                            experiment=exp)
        except:
            print "Could not find {} shotfile for user {}. Trying AUGD...".format(self.diag,exp)
            try:
                shot = dd.shotfile(self.diag, self.shotnr)
            except Exception:
                print "Shotfile not found"
                self.gui.statusbar.showMessage("Shotfile could not be loaded")
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("No jsat shotfile could be found at {} for this shot.".format(self.diag))
                msg.setWindowTitle("Shotfile not found")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.setDefaultButton(QMessageBox.Ok)
                msg.setEscapeButton(QMessageBox.Ok)
                msg.exec_()
                return

        timeArrays = []
        for key, objName in shot.getObjectNames().iteritems():
            if objName.startswith('CH'):
                for probe, (channel, ind) in self.map.iteritems():
                    if channel == objName:
                        self.data[probe] = shot(channel).data[ind]
                        self.time[probe] = shot(channel).time
                        if probe not in self.rawdata:
                            self.rawdata[probe] = {}
                        self.rawdata[probe]['data'] = shot(channel).data[ind]
                        self.rawdata[probe]['time'] = shot(channel).time
                        timeArrays.append(shot(channel).time)

        self.timeArray = self.getTimeArray(timeArrays=timeArrays)
        self.gui.statusbar.showMessage("")
        return self.rawdata


    def getMappingFromShotfile(self):
        self.gui.statusbar.showMessage("Trying to get probe-channel mapping from LSC")
        try:
            shot = dd.shotfile(self.mapDiag, self.shotnr)
        except Exception, e:
            print "LSC not available"
            self.gui.statusbar.showMessage(
                    "Probe mapping could not be read from LSC")
            return False

        signalName = 'ZSI' + self.segment
        print """LSC shotfile found! Retrieving mapping for probes in segment
                    {}...""".format(self.segment)

        for obj in shot.getObjectNames().values():
            probeInLSF = obj in self.gui.uniqueProbes
            if obj.startswith(self.region) and probeInLSF:
                probe = obj
                data = shot(obj)[signalName].data 
                info = ''.join([el for el in data if el.split() != []])
                try:
                    channel, ind = info.split('_')
                except:
                    print "Could not retrieve LSC data for probe", probe
                    print "Aborting..."
                    return False

                self.map[probe] = (channel, ind)

        return self.map


    def getMapping(self):
        """ 
        Loads probe-channel mapping from file. Tries to load from LSC if
        file not available. 
        """
        print "\n++++++++++++++++ Getting mappings +++++++++++++++++++++++++\n"
        success = False

        # Try to get mapping from LSC shotfile
        if self.gui.menuUseLSC.isChecked():
            success = self.getMappingFromShotfile()

        if success:
            return True

        # If that failed, get it from handwritten file
        print "Trying to get mapping from alternative file"
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
                    continue
                else:
                    break
        
        with open(self.mapFilePath) as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
        	try:
        	    probe, quantity, channel, ind = line.split()
        	except:
        	    print """Failed to read probe-channel mapping file {} at
        	    line {}""".format(i,filePath)
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
        	    # Cut off probe segment and add quantity identifier
        	    # Identifier is needed for using the
        	    # TemporalPlot.update() method
        	    probe = 'j-' + probe[1:].lower()
        	    print "Found Isat for probe {} on channel {}-{}"\
        		    .format(probe,channel, ind)
        	    self.map[probe] = (channel, ind)
        
            # Exit if this worked
            if len(self.map) > 0:
                "+++++++++++++Found mappings :)"
                return True
        
        # If that failed, abort plotting current
        print "Failed to get probe-channel mapping. jsat will not be plotted"
        return False


    def calibrateData(self, data=None, cal=None):
        """ Converts current to current density. """
        if data == None:
            data = self.data
        print "Calibrating data"
        calibrate = self.gui.menuCalibrateJsat.isChecked()
        if not calibrate:
            print "\n++++ JSAT NOT CALIBRATED ++++\n --> Activate calibration in GUI"
            return

        if cal != None:
            self.calib = cal
        else:
            self.getCalibrations()

        for probe, data in self.data.iteritems():
            probeName = probe.split('-')[-1]
            l, w = self.calib[probeName]
            self.data[probe] = np.array([val/(l*w) for val in data])
        print "Data was calibrated"
        return self.data


    def getCalibrationsFromShotfile(self):
        print "Getting calibrations from LSC"
        try:
            shot = dd.shotfile(self.mapDiag,self.shotnr)
        except:
            print "Could not load probe geometry from LSC. Proceeding to load "
            "geometry from standard file. You should verify the sensibility of "
            "the jsat data."
            return False

        for obj in shot.getObjectNames().values():
            probeInLSF = obj in self.gui.uniqueProbes
            if obj.startswith(self.region) and probeInLSF:
                probe = obj
                data = shot(obj)['Geom'].data 
                try:
                    l, w = data[:2]
                except:
                    print "Could not retrieve geometry of probe {} from LSC".format(probe)
                    print "Aborting"
                    return False

                self.map[probe] = (float(l), float(w))
        return self.calib
    

    def getCalibrations(self, path=None):
        """ Loads probe dimensions from file so current can be converted to current density. """
        print "Getting calibrations..."
        result = False

        if self.gui.menuUseLSC.isChecked():
            result = self.getCalibrationsFromShotfile()

        if result:
            return result

        if path == None:
            path = self.calibFile

        with open(path) as f:
            lines = f.readlines()[1:]
            for line in lines:
                probe, l, w = line.split()
                self.calib[probe] = (float(l), float(w))
        return self.calib



class SpatialCurrentPlot(SpatialPlot, CurrentPlot):
    def __init__(self, gui):
        Plot.__init__(self, gui)

        # config from SpatialPlot
        config = gui.config['Plots']['Spatial']
        self.coloring = config['coloring']
        self.defaultColor = config['defaultColor']
        self.posFile = config['positionsFile']
        self.fixyLim = config['fixyLim']
        # If this value is 1 then averaged values are not nans if one or more
        # of the values used to calculate it is a nan
        # This setting is ignored if all values to be averaged over are nans
        self.ignoreNans = self.ignoreNans

        self.scatters = {}
        self.quantities = {
                'Temperature': 'te',
                'Density': 'ne',
                'Saturation current density': 'j'
                }
        self.axLabels = {
                'Temperature': 'T$_{e,t}$ [eV]',
                'Density': 'n$_{e,t}$ [1/m$^3$]',
                'Saturation current density': 'j$_{sat}$ [A/m$^2$]'
                }

        # Number of timesteps around the current time to include in the plot (see getShotData())
        self.Dt = gui.Dt
        # Number of data points over which to average
        self.avgNum = gui.avgNum

        self.Rsl = self.gui.Rsl
        self.ssl = self.gui.ssl
        self.zsl = self.gui.zsl
        
        self.option = self.gui.getPlotOption()
        self.quantity = self.quantities[self.option]

        # Set axes labels
        self.axes.set_title("{} distribution on the outer lower target plate".format(self.option))
        self.axes.set_ylabel(self.axLabels[self.option])
        self.axes.set_xlabel("$\Delta$s [m]")

        # Hide axes offsets
        self.axes.yaxis.get_offset_text().set_visible(False)
        self.axes.xaxis.get_offset_text().set_visible(False)

        # config from Current plot
        # Configuration
        config = gui.config['Plots']['Temporal']['Current']
        self.mapDir      = config['mapDir']
        self.mapDiag     = config['mapDiag']
        self.diag        = config['diag']
        self.calibFile   = config['calibFile']
        self.mapFilePath = config['mapFile']
        self.showGaps    = gui.config['Plots']['Temporal']['showGaps']
        self.rescaling   = gui.config['Plots']['Temporal']['rescale-y']

        # Attributes
        self.quantity    = 'j'
        self.shotnr      = self.gui.shotnr
        self.selectedProbes  = self.gui.selectedProbes['t']
        self.hasMapping  = False
        self.calib       = {}
        self.map         = {}
        self.data        = {}
        self.time        = {}
        self.rawdata     = {}
        self.avgData     = {}
        self.avgTime     = {}
        self.rawtime        = {}
        self.plots       = {}
        self.xlim_orig   = [9999999999999, -999999999999]
        self.ylim_orig   = [9999999999999, -999999999999]
         
        self.probeNamePrefix = self.quantity + '-' + self.region
         
        self.rawdata = self.getShot()
        self.getShotData(self.rawdata)
        self.getProbePositions()
        self.rztods()
        self.averageData()
        self.calibrateData()
        self.initPlot()
        #self.plotFit()


    def update(self, ):
        """ Updates scatter plots based on the current time. If y-axis is
        fixed, only the background and the scatter plots are updated with
        a succeding call of ax.update() which considerably improves
        performance. If the y-axis is not fixed, the whole canvas is
        re-drawn."""
        self.avgNum = self.gui.avgNum
        self.getShotData(self.rawdata)
        self.rztods()
        self.averageData()
        self.calibrateData()

        xtot = []
        ytot = []
        for probe in self.data.keys():
            scatter = self.scatters[probe.split('-')[1]]
            x = []
            y = []
            for value,position in zip(self.data[probe], self.plotPositions[probe]):
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
            # Scatter plots
            for scatter in self.scatters.values():
                self.axes.draw_artist(scatter)
            # Spines
            #for spine in self.axes.spines.values():
            #    self.axes.draw_artist(spine)
            self.canvas.update()
            self.canvas.flush_events()

        # Re-draw everything if axes are not fixed
        else:
            plot, = self.axes.plot(xtot,ytot)
            self.axes.relim()
            self.axes.autoscale()
            plot.remove()
            #if min(ytot) > 0:
            #    self.axes.set_ylim(min(ytot)*0.9, max(ytot)*1.2)
            #if min(ytot) == 0:
            #    self.axes.set_ylim(-1, max(ytot)*1.2)
            #else:
            #    self.axes.set_ylim(min(ytot)*1.2, max(ytot)*1.2)
            ## This creates too much space on the right
            ##self.axes.set_xlim(min(xtot)*0.9, max(xtot)*1.1)
            #self.axes.set_xlim(-0.1, 0.35)
            self.updateAxesLabels()
            self.axes.set_xlim(-0.07,0.3)
            self.canvas.draw()


    def initPlot(self, ):
        """ Populates canvas with initial plot. Creates PathCollection objects that will be updated when plot has to change based on GUI interaction."""
        print("Populating canvas with spatial plot")
        for probe in self.data.keys():
            x = []
            y = []
            for value,position in zip(self.data[probe], self.plotPositions[probe]):
                x.append(position)
                y.append(value)

            # Use different color for each probe if wished
            if self.coloring:
                color = self.gui.probeColors[probe.split('-')[1]]
            else:
                color = self.defaultColor

            # Plot
            self.scatters[probe.split('-')[1]] = self.axes.scatter(x, y, color=color)

        # Add text box showing the current time
        #self.updateText()
        
        self.updateAxesLabels()
        
        self.axes.set_xlim(-0.07,0.3)
        self.fig.tight_layout()



class TemporalCurrentPlot(CurrentPlot, TemporalPlot):
    def __init__(self, gui):
        super(TemporalCurrentPlot, self).__init__(gui)
        self.CELMAactive = False
        self.CELMAexists = False
        self.CELMAs = []



# Main
if __name__ == '__main__':

    app = QtGui.QApplication(sys.argv)
    main = ApplicationWindow()
    main.show()

    sys.exit(app.exec_())
