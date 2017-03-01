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
# - Data evaluation will be unreliable if the time data arrays vary from probe to probe
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
#       * SpatialPlot.region
#       * SpatialPlot.ignoreNans
#       * TemporalPlot.axTitles
#       * TemporalPlot.showgaps
#       * Plot.region
#       * Plot.domain
#       * CurrentPlot.mapDir
#       * CurrentPlot.mapDiag
#       * CurrentPlot.diag
#       * Path to calibrations
#       * Path to probe positions
#       * Path to mappings
#   from within the GUI and store them in a config file
#
# - Implement getting mappings for CurrentPlot from LSC
# 
# - Make Indicator update time window when moving away from t=0
#
# - Implement option to automatically zoom temporal plots to their value limits
# 
# - Implement ELM synchronized plots
#       * ELM length: maximum ELM length
#       * modes:
#           + stretch: all ELM durations are normalized wrt longest ELM
#           + original: ELMs are plotted with their original length
#       * Set slider range to [0,ELM lenght] if mode=original
#         Set slider range to [0,1] if mode=stretch
#         
##############################################################################


import matplotlib as mpl
mpl.use('Qt5Agg')
from matplotlib import cm
from matplotlib import pyplot as plt
from matplotlib import patches
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.widgets import SpanSelector

from PyQt5 import QtWidgets
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QWidget, QMessageBox)
from PyQt5.QtGui import (QPainter, QColor)
from PyQt5.uic import loadUiType

# Either use network libraries or local ones depending on internet access
# Local ones might be outdated but don't require internet access
#import dd
import ddlocal
import numpy as np
import sys
import os
from copy import copy

# This is needed for passing arguments to callback functions
import functools

from configobj import ConfigObj
from validate import Validator

# Set recursion limit high so using the slider won't crash the app
sys.setrecursionlimit(10000)

# Don't cut off axes labels or ticks
#mpl.rcParams.update({'figure.autolayout': True})

# Load UI
Ui_MainWindow, QMainWindow = loadUiType('GUI.ui')

# Uncomment the following line if using ddlocal
dd = ddlocal


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
                'domain': '8',
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
        self.xTimeSlider.setTickPosition(QtWidgets.QSlider.NoTicks)
        #self.btnELMplot.hide()

        # Set GUI options to what was read from config.ini
        self.menuFixxPlotyLim.setChecked(self.config['Plots']['Spatial']['fixyLim'])
        self.menuIgnoreNaNsSpatial.setChecked(self.config['Plots']['ignoreNans'])

        # Prepare probe table
        columnNames = ['Probe','Color','Style','T/n(x)','T(t)','n(t)','jsat(t)']
        self.probeTable.setColumnCount(len(columnNames))
        self.probeTable.setHorizontalHeaderLabels(columnNames)
        
        # Resize columns to fit table width
        header = self.probeTable.horizontalHeader()
        for i in range(header.count()):
            header.setSectionResizeMode(i, QtWidgets.QHeaderView.Stretch)
        self.probeTable.resizeColumnsToContents()

        # Hide vertical header
        self.probeTable.verticalHeader().setVisible(False)

        # Set general behavior of GUI
        self.shotNumberEdit.returnPressed.connect(self.load)
        self.xTimeEdit.setMaxLength(7)
        self.shotNumberEdit.setMaxLength(5)
        self.shotNumberEdit.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)


    def loadConfig(self, f, specf=None):
        self.config = ConfigObj(f, configspec=specf)

        # Validate/convert settings
        val = Validator()
        succeeded = self.config.validate(val)
        
        if not succeeded:
            print "Config file validation failed. Using default values"
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
        self.getShot()

        # getShot sets the attribute succeeded at the very end of the function if all went well
        if hasattr(self, "succeeded"):
            print("Data retrieval was successful")
            
            self.getPlotOption()
            self.populateProbeList()
            self.selectedProbes = {'x': [], 't': ['te-ua1','ne-ua1','j-ua1']}
            self.ELMphase = (0,0)

            # Update plots
            self.createxPlot()
            self.dtime = self.xPlot.dtime
            self.indicator_range = self.xPlot.realdtrange
            self.createnPlot()
            self.createTPlot()
            self.createjPlot()

            # Add matplotlib toolbar functionality
            self.nToolbar = NavigationToolbar(self.nPlot.canvas, self)
            self.TToolbar = NavigationToolbar(self.TPlot.canvas, self)
            self.jToolbar = NavigationToolbar(self.jPlot.canvas, self)
            self.xToolbar = NavigationToolbar(self.xPlot.canvas, self)
            self.nToolbar.hide()
            self.TToolbar.hide()
            self.jToolbar.hide()
            self.xToolbar.hide()

            # Synchronize temporal plots
            Sync.sync(self.nPlot, self.TPlot, self.jPlot)

            # Update GUI appearance with current values
            self.xPlot.setTimeText()
            self.xPlot.setDurationText()
            self.updateTWindowControls()
        
            # Instantiate child windows to host plot matrices
            self.matricesVisible = False
            self.jMatrixWindow = MatrixWindow(self)
            #self.nMatrixWindow = MatrixWindow(self)
            #self.TMatrixWindow = MatrixWindow(self)


            # Implement GUI logic
            # This has to be done after updating the plots because the plot objects are referenced
            self.switchxPlot.activated.connect(self.createxPlot)

            self.xTimeEdit.returnPressed.connect(self.updateSlider)
            self.xTimeEdit.returnPressed.connect(self.updatexPlot)
            self.xTimeEdit.returnPressed.connect(self.updatexPlotText)
            self.xTimeEdit.returnPressed.connect(self.updatetPlots)

            self.xTimeSlider.valueChanged.connect(self.updatexPlot)
            self.xTimeSlider.valueChanged.connect(self.updateTimeText)
            self.xTimeSlider.valueChanged.connect(self.updateIndicators)
            self.xTimeSlider.sliderReleased.connect(self.updatexPlotText)
            self.xTimeSlider.sliderReleased.connect(self.updatexPlotText)
        
            self.spinTWidth.editingFinished.connect(self.updateTWindow)

            self.btnPan.clicked.connect(self.nToolbar.pan)
            self.btnZoom.clicked.connect(self.nToolbar.zoom)
            self.btnPan.clicked.connect(self.TToolbar.pan)
            self.btnZoom.clicked.connect(self.TToolbar.zoom)
            self.btnPan.clicked.connect(self.jToolbar.pan)
            self.btnZoom.clicked.connect(self.jToolbar.zoom)
            self.btnReset.clicked.connect(self.resettPlots)
            self.btnPan.clicked.connect(self.xToolbar.pan)
            self.btnZoom.clicked.connect(self.xToolbar.zoom)
            self.btnReset.clicked.connect(self.xToolbar.home)
            
            self.btnAddToMatrices.clicked.connect(self.addToMatrices)

            self.btnCohELMavg.clicked.connect(self.createCohELMPlot)

            self.menuAvgSpatial.triggered.connect(self.setAvgNum)
            self.menuFixxPlotyLim.toggled.connect(self.updatexPlot)
            self.menuIgnoreNaNsSpatial.toggled.connect(self.updatexPlot)
            self.menuSaveSpatialPlot.triggered.connect(self.savexPlot)
            self.menuSaveCurrentPlot.triggered.connect(self.savejPlot)

        # If shot data was not loaded successfully, unbind actions
        else:
            try: 
                del self.succeeded
                self.switchxPlot.disconnect()
                self.xTimeSlider.disconnect()
                self.xTimeEdit.disconnect()
            except Exception: pass
            print("No valid shot number has been entered yet.")


    def addToMatrices(self):
        self.jMatrixWindow.addAxes(self.jPlot.axes)
        #self.nMatrixWindow.addAxes(self.nPlot.axes)
        #self.TMatrixWindow.addAxes(self.TPlot.axes)
        if not self.matricesVisible:
            self.showMatrices()


    def showMatrices(self):
        self.jMatrixWindow.show()
        #self.nMatrixWindow.show()
        #self.TMatrixWindow.show()

        self.matricesVisible = True


    def updatetPlots(self):
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
        avgNum, ok = QtWidgets.QInputDialog.getInt(self, 'Averaging spatial plot', 'Number of data points to average to one scatter plot point:\n\navgNum = ', value= self.avgNum, min=0)

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

        #print "Selected probes after the update:", self.selectedProbes
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
            print "axType is x"
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
        self.option = self.switchxPlot.currentText()
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
            label = QtWidgets.QLabel()
            label.setText(probe)

            # Checkboxes
            mapper = QtCore.QSignalMapper(self)
            for i, cbType in enumerate(('te-x','te-t','ne-t','j-t')):
                cb = QtWidgets.QCheckBox()
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


    def changeColor(self, row, col):
        print "Cell was clicked! Row {}, Col {}".format(row,col)


    def updatexPlot(self):
        self.xPlot.fixyLim = self.menuFixxPlotyLim.isChecked()
        self.xPlot.ignoreNans = self.menuIgnoreNaNsSpatial.isChecked()
        self.xPlot.update()


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
            print "Dt is divisible by avgNum but not by 2, accepting it"
            Dt = Dt

        # If Dt is divisible by 3 and by 2, add 3
        if remAvg == 0 and rem2 == 0:
            print "Dt is divisible by avgNum and 2, adding avgNum"
            Dt = Dt + avgNum

        # If Dt is not divisible by 3, subtract remainder and 
        # add 3 if needed so that result is as close as possible to the
        # user input. Then check if that value is divisible by two. If so,
        # choose the other value anyway
        if remAvg != 0:
            print "Dt is not divisible by avgNum"
            if remAvg >= avgNum/2.:
                print "Dt is closer to the next higher multiple of avgNum"
                tempDt = Dt - remAvg + avgNum
                if tempDt % 2 == 0:
                    print "That value is divisible by 2, though, so choosing the lower multiple of avgNum anyway"
                    Dt = tempDt - avgNum
                else:
                    Dt = tempDt
            else:
                print "Dt is closer to the next lower multiple of avgNum"
                tempDt = Dt - remAvg
                if tempDt % 2 == 0:
                    print "That value is divisible by 2, though, so choosing the higher multiple of avgNum anyway"
                    Dt = tempDt + avgNum
                else:
                    Dt = tempDt

        print "Found best Dt:", Dt
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
            print("Deleting old canvas")
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
        self.xPlot = SpatialPlot(self)
        self.xPlotCanvas = self.xPlot.canvas
        self.xPlotLayout.addWidget(self.xPlotCanvas)


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
    

    def createjPlot(self):
        try:
            self.jPlotLayout.removeWidget(self.jPlotCanvas)
            self.jPlotCanvas.close()
        except:
            pass

        self.jPlot = CurrentPlot(self)
        self.jPlotCanvas = self.jPlot.canvas
        self.jPlotLayout.addWidget(self.jPlotCanvas)
        self.jPlot.parent = self.jPlotLayout
        

    def onPanZoom(self,event):
        self.updatexPlot()


    def getShot(self):
        """ Retrieves langmuir data and strikeline positions from AUG shotfiles. This is an expensive operation and should only be invoked when loading a new shotfile. """
        # Try to read langmuir data. If shot number not valid, prompt user and abort
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
            return

        if(len(str(self.shotnr)) != 5): self.shotnr = 32273
        self.shotNumberEdit.setText(str(self.shotnr))

        # Add progress bar to the status bar
        try:
            self.statusbar.removeWidget(self.progBar)
        except Exception:
            pass
        self.progBar = QtWidgets.QProgressBar()
        self.statusbar.addPermanentWidget(self.progBar)
        self.progBar.setMinimum(0)
        self.progBar.setMaximum(100)

        # Get temperature and density data from langmuir diags
        self.statusbar.showMessage('Fetching Langmuir data...')
        try:
            self.langShot = dd.shotfile(self.langdiag,self.shotnr)
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
            return
            
        self.progBar.setValue(20)
        self.signalNames = self.langShot.getSignalNames()

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
                    test = self.langShot(probe).data
                    test = self.langShot(probe).time
                except Exception:
                    print "Signal {} cannot be read and is skipped. Probably its status does not permit access".format(probe)
                else:
                    if probe[3:] not in self.uniqueProbes:
                        self.uniqueProbes.append(probe[3:])
                    self.probes.append(probe)
                    if probe not in self.langData.keys():
                        self.langData[probe] = {}
                    self.langData[probe]['data'] = self.langShot(probe).data
                    self.langData[probe]['time'] = self.langShot(probe).time
                    print "Successfully read signal", probe

                    progress += (70-20)/signalNum
                    self.progBar.setValue(progress)

        self.progBar.setValue(70)

        # Set timeline scrollbar min and max values
        # Here the absolute maximum value of all time data arrays is used. Data evaluation will be unreliable if the time data arrays vary from probe to probe
        maxDataPoints = max(self.langData[key]['time'].size for key in self.langData.keys())
        self.xTimeSlider.setRange(0, maxDataPoints-1)
        
        # Get strikeline positions from diagnostic
        self.statusbar.showMessage('Fetching strikeline data...')
        try:
            self.slShot = dd.shotfile(self.sldiag,self.shotnr)
        except Exception:
            msg = QMessageBox()
            msg.setText("The Langmuir probe data for the shot with the specified number could not be loaded. Please make sure you entered an existing shot number. It could also be that your connection to the AFS is not set up correctly or your internet connection is not working.")
            msg.setWindowTitle("Shot could not be loaded")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setDefaultButton(QMessageBox.Ok)
            msg.setEscapeButton(QMessageBox.Ok)
            self.hideProgress()
            return

        self.progBar.setValue(90)

        # Strikeline coordinates
        self.ssl = {}
        self.Rsl = {}
        self.zsl = {}

        try:
            self.ssl['data'] = self.slShot('Suna2b').data
            self.ssl['time'] = self.slShot('Suna2b').time
            self.Rsl['data'] = self.slShot('Runa2b').data
            self.Rsl['time'] = self.slShot('Runa2b').time
            self.zsl['data'] = self.slShot('Zuna2b').data
            self.zsl['time'] = self.slShot('Zuna2b').time
        except Exception:
            print "Strikeline positions could not be read!"
            self.hideProgress()
            return
        else:
            print "Successfully read strikeline positions"


        # Get jsat
        try:
            self.jshot = dd.shotfile(self.jdiag, self.shotnr)
        except:
            msg = QMessageBox()
            msg.setText("The shot file with the probe current data could not be loaded. It might have not been written for this shot.")
            msg.setWindowTitle("Shotfile could not be loaded")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setDefaultButton(QMessageBox.Ok)
            msg.setEscapeButton(QMessageBox.Ok)
            self.hideProgress()
            #return


        # Get ELM times
        shot = dd.shotfile(self.ELMdiag,self.shotnr)
        self.ELMonsets = shot('t_begELM')
        self.ELMends   = shot('t_endELM').data
        self.ELMmaxima = shot('t_maxELM').data


        # Flag denoting successful shotfile load
        self.succeeded = 1

        self.progBar.setValue(100)
        self.hideProgress()


    def hideProgress(self):
        """ Removes progressbar widget from the statusbar and resets it to the value 0. """
        self.statusbar.removeWidget(self.progBar)
        self.progBar.setValue(0)


    def quit(self):
        """ Closes application """
        self.close()


    def about(self):
        """ Shows information about the application in a message box. """
        QtWidgets.QMessageBox.about(self, "About",
                """This program plots langmuir probe data from ASDEX Upgrade shotfiles using the pwwdd interface provided by Bernhard Sieglin.

                Version: December 2016
                Written by: Amazigh Zerzour
                """)


    def savexPlot(self):
        """ Saves spatial plot figure. """
        t  = self.xPlot.realtime
        dt = self.lblRealTWidth.text().split()[1]
        defaultName = 'Spatial_{}_{:.7f}s_{}{}'.format(self.xPlot.quantity, t,
                                                        dt, self.defaultExtension)

        print "Default filter: ", self.defaultFilter
        dialog = QtWidgets.QFileDialog()
        dialog.setDefaultSuffix(self.defaultExtension)
        fileName, ok = dialog\
                        .getSaveFileName(self,
                                        directory='./' + defaultName,
                                        caption = "Save figure as",
                                        filter="PNG (*.png);;EPS (*.eps);;SVG (*.svg)",
                                        initialFilter=self.defaultFilter)
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
        dialog = QtWidgets.QFileDialog()
        dialog.setDefaultSuffix(self.defaultExtension)
        fileName, ok = dialog\
                        .getSaveFileName(self,
                                        directory='./' + defaultName,
                                        caption = "Save figure as",
                                        filter="PNG (*.png);;EPS (*.eps);;SVG (*.svg)",
                                        initialFilter=self.defaultFilter)
        if ok:
            if len(fileName.split('.')) < 2:
                print "Extension missing. Figure not saved"
                return
            fmt = fileName.split('.')[-1]
            plot.fig.savefig(fileName, format=fmt)


    def createCohELMPlot(self):
        self.jPlot.coherentELMaveraging()



class ColorPatch(QtWidgets.QWidget):
    def __init__(self, color):
        super(ColorPatch, self).__init__()
        self.color = mpl.colors.rgb2hex(color)


    def paintEvent(self,event):
            qp = QPainter()
            qp.begin(self)
            self.drawPatch(qp)
            qp.end()


    def drawPatch(self, qp):
        #print "Drawing color", self.color
        qp.setBrush(QColor(self.color))
        qp.drawRect(10, 10, 10, 10)



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
        """ Removes values from array based on the indices of NaN values in refarray. If refarray is not specified, NaN values are removed from array. Expects numpy arrays """ 
        # If refarray was passed, comparing it to None would be deprecated
        if type(refarray).__name__ == 'NoneType':
            refarray = array

        array = np.array(array)
        refarray = np.array(refarray)

        return array[~np.isnan(refarray)]



class Plot(object):
    def __init__(self, gui):
        self.gui = gui
        config = gui.config['Plots']
        self.region = config['region']
        self.domain = config['domain']
        self.dpi    = config['dpi']
        self.ignoreNans    = config['ignoreNans']

        self.ELMonsets = gui.ELMonsets
        self.ELMends   = gui.ELMends


        self.parents = {
                'te': 'TPlotLayout',
                'ne': 'nPlotLayout',
                'j': 'jPlotLayout',
                }

        self.fig = Figure(dpi=self.dpi)
        self.axes = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)



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
                'Saturation current density': 'j$_sat$ [A/m$^2$]'
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
        
        self.getShotData()
        self.averageData()
        self.getProbePositions()
        self.rztods()
        self.initPlot()


    def getShotData(self):
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

        # Get current time index from GUI slider
        self.time = self.gui.xTimeSlider.value()

        # Time range expressed by indices in shotfile
        self.dt = (self.gui.Dt - 1)/2 

        # Min and max time expressed by indices in shotfile
        # Prevent tmin to take negative values so getting value by index
        # won't cause problems
        tmin = max(self.time - self.dt, 0)
        tmax = self.time + self.dt

        probeNamePrefix = self.quantity + '-' + self.region

        self.data = {}
        self.realtime_arr = {}
        for probe in self.gui.langData.keys():
            # filter for specified probes
            if probe.startswith(probeNamePrefix):
                dtime = self.gui.langData[probe]['time']
                data = self.gui.langData[probe]['data']

                # Time converted to actual time values
                # If there is an index error, take the global minimum or maximum
                self.realtmin = dtime[tmin]
                try:
                    self.realtmax = dtime[tmax]
                except Exception:
                    self.realtmax = dtime[-1]
                    print("Maximum value of time range to evaluate is out of range. Using maximum of available time range.")
                try:
                    self.realtime = dtime[self.time]
                except Exception:
                    print "Could not determine realtime from time array"
                    if self.time >= dtime.size: self.realtime = dtime[-1]
                    elif self.time < dtime.size: self.realtime = dtime[0]
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


    def averageData(self):
        """ Averages data points over specified number of points. """
        self.avgData = {}

        # If no averaging wished, use the data as received from shotfile
        if self.avgNum == 0:
            self.avgData = self.data 
            return

        # Averaging
        for probe in self.data.keys():
            data = self.data[probe]
            self.avgData[probe] = []
           
            # If this probe didn't record any values at this point in time, continue with the next one
            if data.size == 0: continue

            i=0
            # Take values in the range 0 to avgNum-1 and average them
            # valcount is used to calculate average value because of the possibility of nans
            while True:
                xsum=0
                valcount=0

                for x in np.arange(self.avgNum):
                    # Ignore nans if wished. Ignoring will ensure plot points
                    # to be plotted even if one or more of its data points are
                    # NaNs
                    if self.ignoreNans and np.isnan(data[i]):
                        pass
                    else:
                        xsum += data[i]
                        valcount += 1 
                    i += 1

                # If all values were nans, ignore the result no matter what the value of ignoreNans is
                if valcount == 0:
                    avg = np.NAN
                else:
                    avg = xsum/float(valcount)

                # Save averages to new array
                self.avgData[probe].append(avg)

                # End loop if end of data array will be reached next time
                if i + self.avgNum > data.size: break
            
            self.avgData[probe] = np.array(self.avgData[probe])


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


    def rztods(self):
        """ Converts probe positions from (R,z) coordinates to delta-s
        coordinate based on current strikeline position. This enables plots in
        units of delta-s along the x-axis. It is implicitly assumed that the
        divertor tile is flat."""
        self.plotPositions = {}
        
        for probe in self.data.keys():
            self.plotPositions[probe] = []

            # Get R and z coordinates of probe
            R_p = self.probePositions[probe[3:]][0]
            z_p = self.probePositions[probe[3:]][1]

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

                #print('Position of strikeline at time {}: R = {}, z = {} resulting in ds = {}'.format(self.zsl['time'][ind_z],R_sl,z_sl,ds))
                self.plotPositions[probe].append(ds)


    def initPlot(self, ):
        """ Populates canvas with initial plot. Creates PathCollection objects that will be updated when plot has to change based on GUI interaction."""
        print("Populating canvas with spatial plot")
        for probe in self.avgData.keys():
            x = []
            y = []
            for value,position in zip(self.avgData[probe], self.plotPositions[probe]):
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
        
        self.fig.tight_layout()


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
        self.getShotData()
        self.averageData()

        xtot = []
        ytot = []
        for probe in self.avgData.keys():
            scatter = self.scatters[probe.split('-')[1]]
            x = []
            y = []
            for value,position in zip(self.avgData[probe], self.plotPositions[probe]):
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

        # Enable span selector for ELM evaluation
        self.spanSelector = SpanSelector(self.axes, self.onSpanSelect,
                                        'horizontal', span_stays=True,
                                        useblit=True, button=1)

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


    #def coherentELMaveraging(self):
    #    self.axes.clear()

    #    self.phaseOn  = 6.0
    #    self.phaseEnd = 6.5
    #    ttot = []
    #    ytot = []
    #    for ton, tend in zip(self.ELMonsets, self.ELMends):
    #        if ton >= self.phaseOn and tend <= self.phaseEnd:
    #            tonInd  = Conversion.valtoind(ton, self.time)
    #            tendInd = Conversion.valtoind(tend, self.time)
    #            t = self.time[tonInd:tendInd]
    #            y = self.data[tonInd:tendInd]
    #            ttot.append(t)
    #            ytot.append(y)
    #            self.axes.plot(t,y,color='b') 

    #    self.axes.set_xlim(min(ttot), max(ttot))
    #    self.axes.set_ylim(min(ytot), max(ytot))
    #    self.canvas.draw()


    def averageData(self):
        """ Averages data for selected probes if average data does not exist for them yet. """
        #print "Data before averaging:", self.data
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
        print "\nplotting", self.quantity
        # Get currently selected probes from GUI
        self.selectedProbes = self.gui.selectedProbes['t']
        print "Selected probes:", self.selectedProbes

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
                if self.showGaps == 0:
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



class CurrentPlot(TemporalPlot):
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

        self.getShotData()
        #self.calibrateData()
        self.averageData()
        self.update()


    def getShotData(self, diag=None):
        """ Loads jsat data from shotfile (default: LSF). """
        # If no mapping available yet, get it
        if len(self.map) < 1:
            hasMapping = self.getMapping()
        
        if not hasMapping:
            return

        if diag != None:
            self.diag = diag
        try:
            shot = dd.shotfile(self.diag, self.shotnr)
        except Exception:
            print "Shotfile not found"
            self.statusbar.showMessage("Shotfile could not be loaded")
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("No jsat shotfile could be found at {} for this shot.".format(self.diag))
            msg.setWindowTitle("Shotfile not found")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setDefaultButton(QMessageBox.Ok)
            msg.setEscapeButton(QMessageBox.Ok)
            msg.exec_()
            return
        
        for key, objName in shot.getObjectNames().iteritems():
            if objName.startswith('CH'):
                for probe, (channel, ind) in self.map.iteritems():
                    if channel == objName:
                        #print "Getting data for probe {} from channel {}-{}".format(probe,channel,ind)
                        self.data[probe] = shot.getObjectData(channel)[ind]
                        self.time[probe] = shot.getTimeBase(channel)


    def getMapping(self):
        """ Loads probe-channel mapping from file. Tries to load from LSC if file not available. """
        ok = True
        # File load dialog if mapFilePath was set to None during runtime
        if self.mapFilePath == None:
            self.mapFilePath, ok = \
                    QtWidgets.QFileDialog.getOpenFileName(
                        self.gui,
                        directory=self.mapDir,
                        caption='Load mapping file'
                    )
        if not ok:
            return False
        else:
            with open(self.mapFilePath) as f:
                lines = f.readlines()
                for line in lines:
                    try:
                        probe, quantity, channel, ind = line.split()
                    except:
                        print "Failed to read probe-channel mapping file", filePath
                        break

                    # If channel doesn't start with "CH", add the prefix so LSF shotfile can be read with it
                    if not channel.startswith('CH'): channel = 'CH' + channel

                    # ind is saved as str from 1-6 but must serve as an index from 0-5
                    ind = int(ind) - 1

                    # Only care about probes in this domain and region and the saturation current
                    if probe.startswith(self.domain + self.region) and quantity == 'Isat':
                        # Cut off probe domain and add quantity identifier
                        # Identifier is needed for using the TemporalPlot.update() method
                        probe = 'j-' + probe[1:].lower()
                        print "Found Isat for probe {} on channel {}-{}".format(probe,channel, ind)
                        self.map[probe] = (channel, ind)

            # Exit if this worked
            if len(self.map) > 0:
                "+++++++++++++Found mappings :)"
                return True

        # If that failed, try to get mapping from LSC
        self.statusbar.showMessage("Trying to get probe-channel mapping from LSC")
        try:
            shot = dd.getshot(self.mapDiag, self.shotnr)
        except Exception:
            print "LSC not available"
            self.statusbar.showMessage("LSC not available for this shot")
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("No LSC shotfile could be found for this shot. jsat will not be plotted.")
            msg.setWindowTitle("LSC shotfile not found")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.setDefaultButton(QMessageBox.Ok)
            msg.setEscapeButton(QMessageBox.Ok)
            msg.exec_()
            return False
        print 'LSC not impemented yet. Aborting'
        return False


        # If that failed, abort plotting current
        print "Failed to get probe-channel mapping. jsat will not be plotted"
        return False


    def calibrateData(self, cal=None):
        """ Converts current to current density. """
        print "Calibrating data"
        if cal != None:
            self.calib = cal
        else:
            self.getCalibrations()

        for probe in self.data.keys():
            l, w = self.calib[probe[2:]]
            self.data[probe] = np.array([val/(l*w) for val in self.data[probe]])


    def getCalibrations(self, path=None):
        """ Loads probe dimensions from file so current can be converted to current density. """
        if path == None:
            path = self.calibFile

        with open(path) as f:
            lines = f.readlines()[1:]
            for line in lines:
                probe, l, w = line.split()
                self.calib[probe] = (float(l), float(w))


    def coherentELMaveraging(self):
        self.axes.clear()
        probe = 'j-ua3'
        time = self.time[probe]
        data = self.data[probe]

        self.phaseOn  = 5.8
        self.phaseEnd = 6.5
        ttot = []
        ytot = []
        for ton, tend in zip(self.ELMonsets, self.ELMends):
            if ton >= self.phaseOn and tend <= self.phaseEnd:
                tonInd  = Conversion.valtoind(ton, time)
                tendInd = Conversion.valtoind(tend, time)
                t = time[tonInd:tendInd] - ton
                y = data[tonInd:tendInd]
                ttot.extend(t)
                ytot.extend(y)

                if self.ignoreNans:
                    t = Conversion.removeNans(t,y)
                    y = Conversion.removeNans(y)

                self.axes.plot(t,y,color='b') 

        self.axes.set_xlim(min(ttot), max(ttot))
        self.axes.set_ylim(min(ytot), max(ytot))
        self.canvas.draw()


class MatrixWindow(QtWidgets.QWidget):
    def __init__(self, parent):
        QtWidgets.QWidget.__init__(self)
        self.gui = parent

        # Initialize figure
        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)

        print "Canvas:", type(self.canvas)

        self.rows = 1
        self.cols = 1
        self.currentRow = 1
        self.currentCol = 1
        self.prevRow = 0
        self.prevCol = 0
        self.axNum = 1
        self.newRow = False
        self.defaultExtension = '.svg'
        self.defaultFilter = 'SVG (*.svg)'

        self.btnAddRow = QtWidgets.QPushButton("Next phase")
        self.btnSave   = QtWidgets.QPushButton("Save matrix")

        self.layout = QtWidgets.QHBoxLayout()
        self.layout.addWidget(self.canvas)
        self.layout.addWidget(self.btnAddRow)
        self.layout.addWidget(self.btnSave)

        self.setLayout(self.layout)

        self.resize(500,300)

        self.btnAddRow.clicked.connect(self.addRow)
        self.btnSave.clicked.connect(self.saveMatrix)

        # Config from Plot
        config = self.gui.config['Plots']
        self.region = config['region']
        self.domain = config['domain']
        self.dpi    = config['dpi']

        self.parents = {
                'te': 'TPlotLayout',
                'ne': 'nPlotLayout',
                'j': 'jPlotLayout',
                }

        # Config from SpatialPlot
        config = self.gui.config['Plots']['Spatial']
        self.coloring = config['coloring']
        self.defaultColor = config['defaultColor']
        self.posFile = config['positionsFile']
        self.fixyLim = config['fixyLim']
        # If this value is 1 then averaged values are not nans if one or more
        # of the values used to calculate it is a nan
        # This setting is ignored if all values to be averaged over are nans
        self.ignoreNans = config['ignoreNans']

        self.scatters = {}
        self.quantities = {
                'Temperature': 'te',
                'Density': 'ne',
                'Saturation current density': 'j'
                }
        self.axLabels = {
                'Temperature': 'T$_{e,t}$ [eV]',
                'Density': 'n$_{e,t}$ [1/m$^3$]',
                'Saturation current density': 'j$_sat$ [A/m$^2$]'
                }

        # Number of timesteps around the current time to include in the plot (see getShotData())
        self.Dt = self.gui.Dt
        # Number of data points over which to average
        self.avgNum = self.gui.avgNum

        self.Rsl = self.gui.Rsl
        self.ssl = self.gui.ssl
        self.zsl = self.gui.zsl
        
        self.option = self.gui.getPlotOption()
        self.quantity = self.quantities[self.option]

        # Hide axes offsets
        if hasattr(self, 'axes'):
            self.axes.yaxis.get_offset_text().set_visible(False)
            self.axes.xaxis.get_offset_text().set_visible(False)


    def addRow(self):
        """ Adds another row to the figure and selects it. """
        print "Adding row"
        self.newRow  = True
        self.prevRow = self.currentRow
        self.prevCol = self.currentCol
        self.rows += 1
        self.currentRow += 1
        if self.cols >= self.currentCol:
            self.cols -= 1
        self.currentCol = 0


    def addAxes(self, axes):
        #axesInRow = [ax for ax in self.fig.axes 
        #                          if ax.get_geometry()[0] == self.currentRow]
        #n = len(axesInRow)
        print "\nAdding axes"
        print "Current row:", self.currentRow
        print "Total rows:", self.rows
        print "Current col:", self.currentCol
        print "Total cols:", self.cols
        print "Current axNum:", self.axNum


        n = self.axNum

        neighbor = None
        neighborLoc = None
        hasNeighborAbove = False
        for ax in self.fig.axes:
            k, l, m = ax.get_geometry()
            print "Changing geometry from ({},{},{}) to ({},{},{})".format(k,l,m,self.rows,self.cols,m)
            ax.change_geometry(self.rows, self.cols , m)

            # Find neighbor to share axes with
            # Neighbor to the left
            if self.currentCol != 0 and m == n - 1:
                neighborLoc = 'left'
                neighbor = ax
            # No neighbor
            elif self.currentCol == 0 and self.currentRow == 0:
                neighborLoc = None
                neighbor = None
            # Neighbor above
            elif self.currentCol == 0 \
                and k == self.currentRow - 1 \
                and m == n - self.prevCol:
                    neighborLoc = 'above'
                    neighbor = ax
            # If this axes has a neighbor above, remove its neighbor's xticklabels
            if self.currentCol != 0 \
                and self.currentRow != 0 \
                and l == n - self.cols:
                    for lbl in ax.get_xticklabels():
                        lbl.set_visible(False)

        print "Inserting axes at ({},{},{})".format(self.rows,self.cols,n)
        if neighbor != None:
            print "Neighbor at", neighbor.get_geometry()
        else:
            print "No neighbor"
        if neighborLoc == None:
            self.axes = self.fig.add_subplot(self.rows, self.cols, n)
        elif neighborLoc == 'left':
            self.axes = self.fig.add_subplot(self.rows, self.cols, n,
                    sharey=neighbor)
            # Set tick labels invisible
            for lbl in self.axes.get_yticklabels():
                lbl.set_visible(False)
        elif neighborLoc == 'above':
            self.axes = self.fig.add_subplot(self.rows, self.cols, n,
                    sharex=neighbor)
            # Set tick labels invisible
            for lbl in neighbor.get_xticklabels():
                lbl.set_visible(False)

        self.getShotData()
        self.averageData()
        self.getProbePositions()
        self.rztods()
        self.initPlot()

        self.axNum += 1
        self.currentCol += 1
        # If this column is smaller than the maximum number of columns, don't
        # add another column
        if self.currentCol >= self.cols:
            self.cols += 1
            self.newRow = False

        self.canvas.draw()


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
            yOffsetText = yOffsetText.replace('e','$^{') + '}$'

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
        self.getShotData()
        self.averageData()

        xtot = []
        ytot = []
        for probe in self.avgData.keys():
            scatter = self.scatters[probe.split('-')[1]]
            x = []
            y = []
            for value,position in zip(self.avgData[probe], self.plotPositions[probe]):
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


    def getShotData(self):
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

        # Get current time index from GUI slider
        self.time = self.gui.xTimeSlider.value()

        # Time range expressed by indices in shotfile
        self.dt = (self.gui.Dt - 1)/2 

        # Min and max time expressed by indices in shotfile
        # Prevent tmin to take negative values so getting value by index
        # won't cause problems
        tmin = max(self.time - self.dt, 0)
        tmax = self.time + self.dt

        probeNamePrefix = self.quantity + '-' + self.region

        self.data = {}
        self.realtime_arr = {}
        for probe in self.gui.langData.keys():
            # filter for specified probes
            if probe.startswith(probeNamePrefix):
                dtime = self.gui.langData[probe]['time']
                data = self.gui.langData[probe]['data']

                # Time converted to actual time values
                # If there is an index error, take the global minimum or maximum
                self.realtmin = dtime[tmin]
                try:
                    self.realtmax = dtime[tmax]
                except Exception:
                    self.realtmax = dtime[-1]
                    print("Maximum value of time range to evaluate is out of range. Using maximum of available time range.")
                try:
                    self.realtime = dtime[self.time]
                except Exception:
                    print "Could not determine realtime from time array"
                    if self.time >= dtime.size: self.realtime = dtime[-1]
                    elif self.time < dtime.size: self.realtime = dtime[0]
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


    def averageData(self):
        """ Averages data points over specified number of points. """
        self.avgData = {}

        # If no averaging wished, use the data as received from shotfile
        if self.avgNum == 0:
            self.avgData = self.data 
            return

        # Averaging
        for probe in self.data.keys():
            data = self.data[probe]
            self.avgData[probe] = []
           
            # If this probe didn't record any values at this point in time, continue with the next one
            if data.size == 0: continue

            i=0
            # Take values in the range 0 to avgNum-1 and average them
            # valcount is used to calculate average value because of the possibility of nans
            while True:
                xsum=0
                valcount=0

                for x in np.arange(self.avgNum):
                    # Ignore nans if wished. Ignoring will ensure plot points
                    # to be plotted even if one or more of its data points are
                    # NaNs
                    if self.ignoreNans and np.isnan(data[i]):
                        pass
                    else:
                        xsum += data[i]
                        valcount += 1 
                    i += 1

                # If all values were nans, ignore the result no matter what the value of ignoreNans is
                if valcount == 0:
                    avg = np.NAN
                else:
                    avg = xsum/float(valcount)

                # Save averages to new array
                self.avgData[probe].append(avg)

                # End loop if end of data array will be reached next time
                if i + self.avgNum > data.size: break
            
            self.avgData[probe] = np.array(self.avgData[probe])


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


    def rztods(self):
        """ Converts probe positions from (R,z) coordinates to delta-s
        coordinate based on current strikeline position. This enables plots in
        units of delta-s along the x-axis. It is implicitly assumed that the
        divertor tile is flat."""
        self.plotPositions = {}
        
        for probe in self.data.keys():
            self.plotPositions[probe] = []

            # Get R and z coordinates of probe
            R_p = self.probePositions[probe[3:]][0]
            z_p = self.probePositions[probe[3:]][1]

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

                #print('Position of strikeline at time {}: R = {}, z = {} resulting in ds = {}'.format(self.zsl['time'][ind_z],R_sl,z_sl,ds))
                self.plotPositions[probe].append(ds)


    def initPlot(self, ):
        """ Populates canvas with initial plot. Creates PathCollection objects that will be updated when plot has to change based on GUI interaction."""
        print("Populating canvas with spatial plot")
        for probe in self.avgData.keys():
            x = []
            y = []
            for value,position in zip(self.avgData[probe], self.plotPositions[probe]):
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
    
    
    def saveMatrix(self):
        """ Saves current density plot figure. """
        defaultName = "Matrix" 
        dialog = QtWidgets.QFileDialog()
        dialog.setDefaultSuffix(self.defaultExtension)
        fileName, ok = dialog\
                        .getSaveFileName(self,
                                        directory='./' + defaultName,
                                        caption = "Save figure as",
                                        filter="PNG (*.png);;EPS (*.eps);;SVG (*.svg)",
                                        initialFilter=self.defaultFilter)
        if ok:
            if len(fileName.split('.')) < 2:
                print "Extension missing. Figure not saved"
                return
            fmt = fileName.split('.')[-1]
            self.fig.savefig(fileName, format=fmt)



# Main
if __name__ == '__main__':

    app = QtWidgets.QApplication(sys.argv)
    main = ApplicationWindow()
    main.show()

    sys.exit(app.exec_())
