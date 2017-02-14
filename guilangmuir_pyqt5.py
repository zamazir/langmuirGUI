##############################################################################
#
# guilangmuir.py -  A graphical user interface for langmuir data evaluation of 
#                   ASDEX Upgrade shotfiles
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
# - Crashes if xTimeSlider is set to the maximum value
# - On xPlotSwitch, the indicator jumps to the start of the time window
#
# To do:
# - Set constant color for each probe
# - Increase speed when moving the indicator
# 
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

from PyQt5 import QtWidgets
from PyQt5 import QtCore
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtGui import (QPainter, QColor)
from PyQt5.uic import loadUiType

# Either use network libraries or local ones depending on internet access
# Local ones might be outdated but don't require internet access
#import dd
import ddlocal
import numpy as np
import sys

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

        # Set up UI
        self.setupUi(self)
        self.xTimeSlider.setTickPosition(QtWidgets.QSlider.NoTicks)

        # Prepare probe table
        columnNames = ['Probe','Color','Style','T(x)','n(x)','T(t)','n(t)','jsat(t)']
        self.probeTable.setColumnCount(len(columnNames))
        self.probeTable.setHorizontalHeaderLabels(columnNames)
        
        # Resize columns to fit table width
        header = self.probeTable.horizontalHeader()
        for i in range(header.count()):
            header.setSectionResizeMode(i, QtWidgets.QHeaderView.Stretch)
        self.probeTable.resizeColumnsToContents()

        # Hide vertical header
        self.probeTable.verticalHeader().setVisible(False)

        # Parameters for averaging spatial plot
        self.avgNum = 3
        self.Dt = 15

        # Set general behavior of GUI
        self.shotNumberEdit.returnPressed.connect(self.load)
        self.xTimeEdit.setMaxLength(7)
        self.shotNumberEdit.setMaxLength(5)
        self.shotNumberEdit.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)


    def load(self, ):
        """ Loads specified shot, updates all plots on the GUI and implements interactivity """
        # Try to load shotfiles
        self.getShot()

        # getShot sets the attribute succeeded at the very end of the function if all went well
        if hasattr(self, "succeeded"):
            print("Data retrieval was successful")
            
            self.getPlotOption()
            self.populateProbeList()
            self.selectedProbes = {'x': [], 't': []}

            # Update plots
            self.createxPlot()
            self.dtime = self.xPlot.dtime
            self.indicator_range = self.xPlot.realdtrange
            self.createnPlot()
            self.createTPlot()

            # Select default probe
            for cb in self.checkBoxes['ua1'].values():
                cb.setCheckState(True)

            # Add matplotlib toolbar functionality
            self.nToolbar = NavigationToolbar(self.nPlot.canvas, self)
            self.TToolbar = NavigationToolbar(self.TPlot.canvas, self)
            self.nToolbar.hide()
            self.TToolbar.hide()

            # Synchronize temporal plots
            Sync.sync(self.nPlot,self.TPlot)

            # Update GUI appearance with current values
            self.xPlot.setTimeText()
            self.xPlot.setDurationText()
            self.updateTWindowControls()

            # Make some menu elements checkable
            self.menuFixxPlotyLim.setCheckable(True)

            # Implement GUI logic
            # This has to be done after updating the plots because the plot objects are referenced
            self.switchxPlot.activated.connect(self.createxPlot)

            self.xTimeEdit.returnPressed.connect(self.updateSlider)
            self.xTimeEdit.returnPressed.connect(self.updatexPlot)

            self.xTimeSlider.sliderMoved.connect(self.updatexPlot)
            self.xTimeSlider.valueChanged.connect(self.updateTimeText)
            self.xTimeSlider.valueChanged.connect(self.updateIndicators)
        
            self.spinTWidth.editingFinished.connect(self.updateTWindow)

            self.btnPan.clicked.connect(self.nToolbar.pan)
            self.btnZoom.clicked.connect(self.nToolbar.zoom)
            self.btnPan.clicked.connect(self.TToolbar.pan)
            self.btnZoom.clicked.connect(self.TToolbar.zoom)
            self.btnReset.clicked.connect(self.resettPlots)

            self.menuAvgSpatial.triggered.connect(self.setAvgNum)
            
            self.menuFixxPlotyLim.toggled.connect(self.updatexPlot)

        # If shot data was not loaded successfully, unbind actions
        else:
            try: 
                del self.succeeded
                self.switchxPlot.disconnect()
                self.xTimeSlider.disconnect()
                self.xTimeEdit.disconnect()
            except Exception: pass
            print("No valid shot number has been entered yet.")


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
        # Save old value
        self.spinTWidth.setRange(self.avgNum, self.avgNum + 100)
        self.spinTWidth.setSingleStep(self.avgNum)
        self.spinTWidth.setValue(self.Dt)

        # Real time label
        dt = self.xPlot.realtmax - self.xPlot.realtmin
        self.lblRealTWidth.setText("= {:.2f}us".format(dt*10**6))


    def updateIndicators(self):
        """ Updates all indicators. """
        self.nPlot.indicator.slide()
        self.TPlot.indicator.slide()
    
    
    def togglePlots(self, cbID):
        """ Toggles temporal plots based on checkbox selection. """
        #print "\n\nCheckbox clicked:", cbID
        # Mapper returns unicode string. Must be converted to standard string
        probe, quantity, axType = str(cbID).split('-')
        pnq = quantity + '-' + probe 
        cbType = quantity + '-' + axType
        cb = self.checkBoxes[probe][cbType]

        # If probe is checked, add it to selectedProbes
        # If not, make sure it's not in selectedProbes
        if cb.checkState() and pnq not in self.selectedProbes[axType]:
            #print("Adding {} to selectedProbes".format(pnq))
            self.selectedProbes[axType].append(pnq)
        elif not cb.checkState() and pnq in self.selectedProbes[axType]:
            while pnq in self.selectedProbes[axType]:
                self.selectedProbes[axType].remove(pnq)
                #print("Removing {} from selectedProbes".format(pnq))

        #print "Selected probes after the update:", self.selectedProbes
        self.nPlot.averageData()
        self.nPlot.update()
        self.nPlot.canvas.draw()
        self.TPlot.averageData()
        self.TPlot.update()
        self.TPlot.canvas.draw()
        

    def resettPlots(self):
        self.nPlot.reset()
        self.nPlotCanvas.draw()


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
        cm = plt.get_cmap('gist_rainbow')
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
            for i, cbType in enumerate(('te-x','ne-x','te-t','ne-t','j-t')):
                cb = QtWidgets.QCheckBox()
                cbID = probe + '-' + cbType
                mapper.setMapping(cb, cbID) 
                cb.stateChanged.connect(mapper.map)
                table.setCellWidget(rowPos, i+3, cb)
                self.checkBoxes[probe][cbType] = cb

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
        #self.xPlot.fixyLim = self.menuFixxPlotyLim.checkState()
        self.xPlot.update()
        self.xPlotCanvas.draw()


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
        self.nPlot.indicator.slide()
        self.TPlot.indicator.slide()

        dt = self.xPlot.realtmax - self.xPlot.realtmin
        self.lblRealTWidth.setText("= {:.2f}us".format(dt*10**6))


    def createxPlot(self):
        """ Updates spatial plot by trying to remove the previous plot and creating a new canvas. Creates a SpatialPlot object. """
        # If canvas already exists, delete it
        try:
            print("Deleting old canvas")
            self.xPlotLayout.removeWidget(self.xPlotCanvas)
            self.xPlotCanvas.close()
        except:
            print("Old canvas could not be deleted")
            pass

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


    def createnPlot(self):
        try:
            self.nPlotLayout.removeWidget(self.nPlotCanvas)
            self.nPlotCanvas.close()
        except:
            pass

        self.nPlot = TemporalPlot(self,'ne')
        self.nPlotCanvas = self.nPlot.canvas
        self.nPlotLayout.addWidget(self.nPlotCanvas)
        

    def onPanZoom(self,event):
        self.updatexPlot()


    def getShot(self):
        """ Retrieves langmuir data and strikeline positions from AUG shotfiles. This is an expensive operation and should only be invoked when loading a new shotfile. """
        self.langdiag = 'LSD'
        self.sldiag = 'FPG'
        self.elmdiag = 'ELM'
        self.jdiag = 'LSC'

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
            return


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
    def __init__(self, plot):
        self.plot = plot
        self.gui = plot.gui
        self.color = 'b'
        self.gui.xTimeSlider = self.gui.xTimeSlider

        self.slide()

    def slide(self):
        """ Repositions indicator according to time slider value. """
        # Get current time from time slider and convert it
        pos = self.gui.xTimeSlider.value()
        time= self.gui.dtime[pos]
        tminus = time - self.gui.indicator_range[0]
        tplus = time + self.gui.indicator_range[1]
        print('tminus: {}, tplus: {}'.format(tminus, tplus))

        # Update previous indicator if there already is one
        if hasattr(self, "indic"):
            self.indic.set_xdata(time)
            self.indic_fill.remove()
            self.indic_fill = self.plot.axes.axvspan(tminus, tplus, alpha=0.5, color=self.color)

        else:
            #Plot new indicator
            self.indic = self.plot.axes.axvline(x=time, color=self.color)
            self.indic_fill = self.plot.axes.axvspan(tminus, tplus, alpha=0.5, color=self.color)

        # Re-draw canvas
        self.plot.canvas.draw()



class Conversion():
    @staticmethod
    def valtoind(realtime, timearray):
        """ Converts a real time value to an index in a given array with time values. This is achieved by comparing the real time value to the array elements and returning the index of the closest one. """
        return np.abs((timearray - realtime)).argmin()

    @staticmethod
    def removeNans(array, refarray=None):
        """ Removes values from array based on the indices of NaN values in refarray. If refarray is not specified, NaN values are removed from array. Expects numpy arrays """ 
        if refarray == None:
            refarray = array

        return array[~np.isnan(refarray)]



class SpatialPlot():
    """ Class for spatial temperature and density plots. Subclass of Plot. Needs the application object as an argument to be able to manipulate GUI elements. """
    ### TO DO
    #
    # - rztods depends on realtime_arr
    # - rztods should save relative positions with timestamps to rule out mismatches when plotting
    # - In update(), proper scaling of the scatter is achieved by adding a plot, rescaling, and removing that plot. A more elegant solution is desirable
    #
    def __init__(self, gui):
        print("Initiating spatial plot")
        self.gui = gui
        # Number of timesteps around the current time to include in the plot (see getShotData())
        self.Dt = gui.Dt
        # Number of data points over which to average
        self.avgNum = gui.avgNum

        # If this value is 1 then averaged values are not nans if one or more of the values used to calculate it is a nan
        # This setting is ignored if all values to be averaged over are nans
        self.ignoreNans = 1

        self.fixyLim = False

        fig = Figure()
        self.axes = fig.add_subplot(111)
        self.canvas = FigureCanvas(fig)

        self.Rsl = self.gui.Rsl
        self.ssl = self.gui.ssl
        self.zsl = self.gui.zsl
        
        self.region = 'ua' 
        self.option = self.gui.getPlotOption()
        if self.option == 'Temperature':
            self.quantity = 'te'
        if self.option == 'Density':
            self.quantity = 'ne'


        self.gui.xTimeSlider.setValue(10000)
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

        print "Getting shot data for {} time steps".format(self.gui.Dt)
        # Min and max time expressed by indices in shotfile
        tmin = self.time - self.dt
        tmax = self.time + self.dt

        probeNamePrefix = self.quantity + '-' + self.region

        print "Filtering array for time range", self.dt
        self.data = {}
        self.realtime_arr = {}
        for probe in self.gui.langData.keys():
            # filter for specified probes
            if probe.startswith(probeNamePrefix):
                dtime = self.gui.langData[probe]['time']
                data = self.gui.langData[probe]['data']

                # Time converted to actual time values
                # If there is an index error, take the global minimum or maximum
                try:
                    self.realtmin = dtime[tmin]
                except Exception:
                    self.realtmin = dtime[0]
                    print("Minimum value of time range to evaluate is smaller than available time range. Using minimum of available time range.")
                try:
                    self.realtmax = dtime[tmax]
                except Exception:
                    self.realtmax = dtime[-1]
                    print("Maximum value of time range to evaluate is greater than available time range. Using maximum of available time range.")
                try:
                    self.realtime = dtime[self.time]
                except Exception:
                    if self.time >= dtime.size: self.realtime = dtime[-1]
                    elif self.time <= dtime.size: self.realtime = dtime[0]
                    else: print("FATAL: Realtime could not be determined.")
                
                # Filter for time range. The prefixes determining the quantity have to be removed from the data array keys for successful comparison to probe location data in SpatialPlot().updatePlot()
                ##### SAVE DATA TO ARRAY #####
                ind = np.ma.where((dtime >= self.realtmin) & (dtime <= self.realtmax))
                self.data[probe] = data[ind]
                self.realtime_arr[probe] = dtime[ind]

                # Save the time data of the last probe as the global time data. This assumes that all time arrays of the probes are identical
                self.dtime = dtime
                realdtminus = self.realtime - self.realtmin
                realdtplus = -(self.realtime - self.realtmax)
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
            
            print "Probe {} - Data points: {}".format(probe, data.size)

            # If this probe didn't record any values at this point in time, continue with the next one
            if data.size == 0: continue

            i=0
            # Take values in the range 0 to avgNum-1 and average them
            # valcount is used to calculate average value because of the possibility of nans
            while True:
                xsum=0
                valcount=0

                print "Averaging {} data points".format(data.size)    
                print "Taking {} values to average over".format(self.avgNum)
                for x in np.arange(self.avgNum):
                    # Ignore nans if wished
                    if self.ignoreNans == 1 and np.isnan(data[i]):
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

                # End loop if end of data array is reached
                if i == data.size: break
            
            self.avgData[probe] = np.array(self.avgData[probe])


    def getProbePositions(self):
        """ Gets positions of probes in the specified region in terms of R,z coordinates. Saves the coordinates as tuples in a class parameter array "probePositions" with the probe names as keys. """
        self.probePositions = {}

        posFile = open("Position_pins_08-2015.txt")

        # Read probe name and R and z coordinates of each probe
        for line in posFile:
            probeName = line.split()[0][1:]                 # Probe name
            R = float(line.split()[1].replace(",","."))     # R
            z = float(line.split()[2].replace(",","."))     # z
        
            self.probePositions[probeName] = (R,z)
        posFile.close()


    def rztods(self):
        """ Converts probe positions from (R,z) coordinates to delta-s coordinate based on current strikeline position. This enables plots in units of delta-s along the x-axis. It is implicitly assumed that the divertor tile is flat."""
        self.plotPositions = {}
        
        for probe in self.data.keys():
            self.plotPositions[probe] = []

            # Get R and z coordinates of probe
            R_p = self.probePositions[probe[3:]][0]
            z_p = self.probePositions[probe[3:]][1]

            for time in self.realtime_arr[probe]:
                # Get R and z coordinates of strikeline at this point in time
                # Finding the index of the time value closest to the current time is less prone to errors than trying to find the exact value
                ind_R = np.abs((self.Rsl['time'] - time)).argmin()
                R_sl = self.Rsl['data'][ind_R]
                ind_z = np.abs((self.zsl['time'] - time)).argmin()
                z_sl = self.zsl['data'][ind_z]

                # Throw error if timestamps don't match
                if self.zsl['time'][ind_z] != self.Rsl['time'][ind_R]:
                    print('++++CRITICAL++++\n\nTried to find timestamps of strikeline R and z measurements at times closest to {} in the respective shot file data but the found values for R and z don\'t match! Data evaluation will not be reliable.')

                # Calculate delta-s
                # Assumption: divertor tile is flat
                ds = np.sqrt( (R_sl-R_p)**2 + (z_sl-z_p)**2 ) 
                # If the z coordinate of the probe is smaller than that of the strikeline, 
                # then the delta-s associated with this probe at this time is negative
                if z_p < z_sl: ds = -ds

                #print('Position of strikeline at time {}: R = {}, z = {} resulting in ds = {}'.format(self.zsl['time'][ind_z],R_sl,z_sl,ds))
                self.plotPositions[probe].append(ds)


    def initPlot(self, ):
        """ Populates canvas with initial plot. Creates Line2D object that will be updated when plot has to change based on GUI interaction."""
        #print("Populating canvas with spatial plot")
        x = []
        y = []
        for probe in self.avgData.keys():
            for value,position in zip(self.avgData[probe], self.plotPositions[probe]):
                x.append(position)
                y.append(value)
        self.scatter = self.axes.scatter(x, y)

        self.axes.set_title("{} distribution on the outer lower target plate in AUG @{:.4f}s".format(self.option,self.realtime))
        self.axes.set_ylabel(self.option)
        self.axes.set_xlabel("$\Delta$s")

    
    def update(self, ):
        self.avgNum = self.gui.avgNum
        print "updating spatial plot"
        print "avgNum:", self.avgNum
        self.getShotData()
        self.averageData()

        x = []
        y = []
        for probe in self.avgData.keys():
            for value,position in zip(self.avgData[probe], self.plotPositions[probe]):
                x.append(position)
                y.append(value)

        # Insert dummy plot for proper scaling
        plot, = self.axes.plot(x,y)

        # If scatter exists, update data
        if "scatter" in [str(el) for el in dir(self)]:
            newdata = [list(t) for t in zip(x,y)]
            self.scatter.set_offsets(newdata)
        else:
            print("Critical: Scatter plot has not been initialized!")

        # Scale the canvas and remove the dummy plot
        self.axes.relim()
        self.axes.autoscale()
        plot.remove()

        # Update title based on new time
        self.axes.set_title("{} distribution on the outer lower target plate in AUG @{:.4f}s".format(self.option,self.realtime))


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
        # GUI line edit expects a real time value
        realtime = float(self.gui.xTimeEdit.text())
        # Convert to corresponding timestep
        time = Conversion.valtoind(realtime, self.dtime)
        # Update slider position
        self.gui.xTimeSlider.setValue(float(time))
        # Update line edit text with the time corresponding to the found timestep
        self.gui.xTimeEdit.setText("{:.10f}".format(self.dtime[time]))


    def setDurationText(self):
        """ Updates the shot duration in the info bar. """
        self.gui.dynDurationLabel.setText("{:.3f}".format(self.dtime[-1]))



class TemporalPlot():
    #######
    # To do:
    #
    # - Original axes limits are overwritten when zoomed in and updating plot by (un)checking a probe. When zoomed in, zoom level should be retained but the new maximum/minimum values should be saved for "resetting"
    # - Rename reset to View all
    #
    def __init__(self, gui, quantity):

        self.gui = gui
        self.quantity = quantity
        self.region = 'ua'
        self.selectedProbes = self.gui.selectedProbes['t']

        self.data = {}
        self.time = {}
        self.avgData = {}
        self.avgTime = {}
        self.plots = {}
        self.xlim_orig = [9999999999999, -999999999999]
        self.ylim_orig = [9999999999999, -999999999999]

        self.showGaps = 0

        fig = Figure()
        self.axes = fig.add_subplot(111)
        self.canvas = FigureCanvas(fig)

        self.axes.autoscale()

        self.getShotData()
        self.averageData()
        self.update()

        self.indicator = Indicator(self)

        # Implement interactive behavior: Event handling when zoomed or dragged
        # Zoom with mouse wheel
        #self.enableMouseZoom()
        self.axes.callbacks.connect('xlim_changed', self.setSliderRange)


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

        #print "Selected probes when averaging:", self.selectedProbes
        #print "Prefix:", self.probeNamePrefix

        for probe in self.selectedProbes:
            #print "Averaging probe:", probe
            if probe.startswith(self.probeNamePrefix) and probe not in self.avgData.keys():
                #print("Averaging temporal data")
                self.avgData[probe] = []
                self.avgTime[probe] = []
                self.maxDataPoints = 0

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
                 
                # Save maximum data array length
                if len(self.avgData[probe]) > self.maxDataPoints:
                    self.maxDataPoints = self.avgData[probe]

                self.avgData[probe] = np.array(self.avgData[probe])
                self.avgTime[probe] = np.array(self.avgTime[probe])


    def reset(self):
        """ Resets the plot to its original state. """
        # Reset axes limits
        self.axes.set_xlim(self.xlim_orig)
        self.axes.set_ylim(self.ylim_orig)

        self.axes.relim()
        self.axes.autoscale_view()


    def update(self):
        """ Plots temporal data if it hasn't been plotted yet. If it has been plotted, it is set to visible. """
        # Get currently selected probes from GUI
        self.selectedProbes = self.gui.selectedProbes['t']

        # Update plots
        for probe in self.avgData.keys(): 
            # If probe hasn't been plotted yet, is selected, and belongs to this canvas, plot it
            if probe not in self.plots.keys() \
                    and probe in self.selectedProbes \
                    and probe.startswith(self.probeNamePrefix):
                #print("{} hasn't been plotted yet".format(probe))
                y = self.avgData[probe]
                x = self.avgTime[probe]

                # Filter NaNs if wished
                if self.showGaps == 0:
                   x = Conversion.removeNans(x,y) 
                   y = Conversion.removeNans(y) 

                # Plot data
                color = self.gui.probeColors[probe[3:]]
                self.plot, = self.axes.plot(x,y, color=color)

                # Save artist for future reference
                self.plots[probe] = self.plot

            # If probe has been plotted, is not selected, and is visible, hide it
            elif probe in self.plots.keys() \
                    and probe not in self.selectedProbes \
                    and self.plots[probe].get_visible():
                #print("Setting probe {} invisible".format(probe))
                self.plots[probe].set_visible(False)
                self.canvas.draw()

            # If probe has been plotted, is selected, and is hidden, show it
            elif probe in self.plots.keys() \
                    and probe in self.selectedProbes \
                    and not self.plots[probe].get_visible():
                #print("Setting probe {} visible".format(probe))
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


    def enableMouseZoom(self, base_scale = .5):
        """ Enables zooming with the scroll wheel if called on a matplotlib canvas. """
        def zoom_fun(event):
            """ Zooms plot using mouse wheel motion. """
            # Original axes limits
            xlim_orig = self.xlim_orig
            ylim_orig = self.ylim_orig

            # get the current x and y limits
            cur_xlim = self.axes.get_xlim()
            cur_ylim = self.axes.get_ylim()
            cur_xrange = (cur_xlim[1] - cur_xlim[0])*.5
            cur_yrange = (cur_ylim[1] - cur_ylim[0])*.5
             
            # Get event location
            xdata = event.xdata
            ydata = event.ydata

            # Handle zoom events
            if event.button == 'down':
                # deal with zoom in
                scale_factor = 1/base_scale
            elif event.button == 'up':
                # deal with zoom out
                scale_factor = base_scale
            else:
                # deal with something that should never happen
                scale_factor = 1
                #print event.button

            # New axes limits. Don't allow zooming out beyond original boundaries
            xlim = [max(xlim_orig[0], xdata - cur_xrange*scale_factor), min(xlim_orig[1], xdata + cur_xrange*scale_factor)]
            #ylim = [max(ylim_orig[0], ydata - cur_yrange*scale_factor), min(ylim_orig[1], ydata + cur_yrange*scale_factor)]

            # set new limits
            self.axes.set_xlim(xlim)
            #self.axes.set_ylim(ylim)
            
            # Re-draw canvas
            self.canvas.draw()

        #return the function
        return zoom_fun



# Main
if __name__ == '__main__':

    app = QtWidgets.QApplication(sys.argv)
    main = ApplicationWindow()
    main.show()

    sys.exit(app.exec_())
