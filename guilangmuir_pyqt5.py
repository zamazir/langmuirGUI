test
###############################################################
#
# guilangmuir.py - A graphical user unterface for langmuir data evaluation of ASDEX Upgrade shotfiles
#
# This program was written as part of the master's thesis of Amazigh Zerzour. It's aim is to provide a visual and interactive way of recognizing and classifying detachment regimes using langmuir data from the outer divertor probes
#
# Author: Amazigh Zerzour
# E-Mail: amazigh.zerzour@gmail.com
#
# Version: Jan. 2017
#
# Issues:
# - Data evaluation will be unreliable if the time data arrays vary from probe to probe
# - Crashes if xTimeSlider is set to the maximum value
#
# To do:
# 
###############################################################

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib import cm

from PyQt5 import QtWidgets
from PyQt5 import QtCore
from PyQt5.QtWidgets import QMessageBox
from PyQt5.uic import loadUiType
from qrangeslider import QRangeSlider
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# Either use network libraries or local ones depending on internet access
# Local ones might be outdated but don't require internet access
#import dd
import ddlocal
import numpy as np
import sys

Ui_MainWindow, QMainWindow = loadUiType('GUI.ui')

# Uncomment the following line if using ddlocal
dd = ddlocal

class ApplicationWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, ):
        super(ApplicationWindow, self).__init__()

        # Set up UI
        self.setupUi(self)

        # Add range slider
        self.rangeSlider = QRangeSlider()
        #self.plotLayout.addWidget(self.rangeSlider)
        self.xTimeSlider.setTickPosition(QtWidgets.QSlider.NoTicks)

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
            # Update plots
            self.updatexPlot()
            self.createnPlot()
            #self.updateTPlot()
            
            self.dtime = self.xPlotObject.dtime

            # Update GUI appearance with current values
            self.xPlotObject.setTimeText()
            self.xPlotObject.setDurationText()
            self.setRangeSliderLimits()

            # Implement GUI logic
            # This has to be done after updating the plots because the plot objects are referenced
            self.switchxPlot.activated.connect(self.updatexPlot)
            self.xTimeSlider.sliderReleased.connect(self.updatexPlot)

            self.xTimeEdit.returnPressed.connect(self.updateSlider)
            self.xTimeEdit.returnPressed.connect(self.updatexPlot)
            self.xTimeSlider.valueChanged.connect(self.updateTimeText)

            self.rangeSlider.startValueChanged.connect(self.updatetPlots)
            self.rangeSlider.endValueChanged.connect(self.updatetPlots)

        # If shot data was not loaded successfully, unbind actions
        else:
            try: 
                del self.succeeded
                self.switchxPlot.disconnect()
                self.xTimeSlider.disconnect()
                self.xTimeEdit.disconnect()
            except Exception: pass
            print("No valid shot number has been entered yet.")


    def updatetPlots(self):
        """ Calls update methods of temporal plot objects. """
        self.nPlotObject.update()
        #self.TPlotObject.update()

        self.nPlotCanvas.draw()
        #self.TPlotCanvas.draw_idle()


    def updateSlider(self):
        self.xPlotObject.setxTimeSlider()


    def updateTimeText(self):
        self.xPlotObject.setTimeText()


    def updatexPlot(self):
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
        self.xPlotObject = SpatialPlot(self)
        self.xPlotCanvas = self.xPlotObject.canvas
        self.xPlotLayout.addWidget(self.xPlotCanvas)


    def updateTPlot(self):
        try:
            self.TPlotLayout.removeWidget(self.TPlotCanvas)
            self.TPlotCanvas.close()
        except:
            pass

        self.TPlotObject = TemporalPlot(self,'te')
        self.TPlotCanvas = self.TPlotObject.canvas
        self.TPlotLayout.addWidget(self.TPlotCanvas)


    def createnPlot(self):
        try:
            self.nPlotLayout.removeWidget(self.nPlotCanvas)
            self.nPlotCanvas.close()
        except:
            pass

        self.nPlotObject = TemporalPlot(self,'ne')
        self.nPlotCanvas = self.nPlotObject.canvas
        self.nPlotLayout.addWidget(self.nPlotCanvas)
        
        self.nPlotObject.initPlot()


    def setRangeSliderLimits(self):
        """ Updates range slider maximum and minimum values with minimum and maximum data array indices. """
        maxDataPoints = len(self.nPlotObject.maxDataPoints)
        self.rangeSlider.setMin(0)
        self.rangeSlider.setMax(maxDataPoints-1)
        self.rangeSlider.setStart(0)
        self.rangeSlider.setEnd(maxDataPoints-1)



    def getShot(self):
        """ Retrieves langmuir data and strikeline positions from AUG shotfiles. This is an expensive operation and should only be invoked when loading a new shotfile. """
        self.langdiag = 'LSD'
        self.sldiag = 'FPG'

        # Try to read shot number. If it's not valid, prompt user and abort
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

        self.shotnr = 32273
        self.shotNumberEdit.setText("32273")

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
        for probe in self.signalNames:
            if probe.startswith('ne-ua') or probe.startswith('te-ua'):
                try:
                    test = self.langShot(probe).data
                    test = self.langShot(probe).time
                except Exception:
                    print "Signal {} cannot be read and is skipped. Probably its status does not permit access".format(probe)
                else:
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




class Plot(QMainWindow, Ui_MainWindow, FigureCanvas):
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

        # Number of data points over which to average
        self.avgNum = 3
        # Number of averaged data points to be shown per probe
        self.datNum = 5
        # If this value is 1 then averaged values are not nans if one or more of the values used to calculate it is a nan
        # This setting is ignored if all values to be averaged over are nans
        self.ignoreNans = 1

        # Time range expressed by indices in shotfile
        self.dt = (self.avgNum * self.datNum - 1)/2 

        # Min and max time expressed by indices in shotfile
        tmin = self.time - self.dt
        tmax = self.time + self.dt

        probeNamePrefix = self.quantity + '-' + self.region

        print "Filtering array for specified probes and time range"
        self.data = {}
        self.realtime_arr = {}
        for probe in self.parent.langData.keys():
            # filter for specified probes
            if probe.startswith(probeNamePrefix):
                dtime = self.parent.langData[probe]['time']
                data = self.parent.langData[probe]['data']

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
                self.data[probe[3:]] = data[ind]
                self.realtime_arr[probe[3:]] = dtime[ind]

                # Save the time data of the last probe as the global time data. This assumes that all time arrays of the probes are identical
                self.dtime = dtime
        



    def convRealToIndex(self, realtime, timearray):
        """ Converts a real time value to an index in a given array with time values. This is achieved by comparing the real time value to the array elements and returning the index of the closest one. """
        return np.abs((timearray - realtime)).argmin()




class SpatialPlot(Plot):
    """ Class for spatial temperature and density plots. Subclass of Plot. Needs the application object as an argument to be able to manipulate GUI elements. """
    def __init__(self, parent):
        self.parent = parent

        fig = Figure()
        self.axes = fig.add_subplot(111)
        self.canvas = FigureCanvas(fig)

        self.Rsl = self.parent.Rsl
        self.ssl = self.parent.ssl
        self.zsl = self.parent.zsl
        
        self.region = 'ua' 

        self.time = self.parent.xTimeSlider.value()
        self.option = self.parent.switchxPlot.currentText()

        if self.option == 'Temperature':
            self.quantity = 'te'
        if self.option == 'Density':
            self.quantity = 'ne'


        self.getShotData()
        self.averageData()
        self.getProbePositions()
        self.convProbePosToX()
        self.updatePlot()


    def averageData(self):
        """ Averages data points over specified number of points. """
        self.avgdata = {}

        # If no averaging wished, use the data as received from shotfile
        if self.avgNum == 0:
            self.avgdata = self.data 
            return

        # Averaging
        for probe in self.data.keys():
            data = self.data[probe]
            self.avgdata[probe] = []

            # If this probe didn't record any values at this point in time, continue with the next one
            if len(data) == 0: continue

            i=0
            # Take values in the range 0 to avgNum and average them
            # valcount is used to calculate average value because of the possibility of nans
            while True:
                xsum=0
                valcount=0

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
                self.avgdata[probe].append(avg)

                # End loop if end of data array is reached
                if i == data.size: break


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


    def convProbePosToX(self):
        """ Converts probe positions from (R,z) coordinates to delta-s coordinate based on current strikeline position. This enables plots in units of delta-s along the x-axis. It is implicitly assumed that the divertor tile is flat."""
        self.plotPositions = {}
	
	for probe in self.data.keys():
            self.plotPositions[probe] = []

            # Get R and z coordinates of probe
            R_p = self.probePositions[probe][0]
            z_p = self.probePositions[probe][1]

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


    def updatePlot(self, ):
        """ Populates canvas with plot. """
        colors = iter(cm.rainbow(np.linspace(0,1,len(self.data.keys()))))

        for probe in self.avgdata.keys():
            color = next(colors)
            for value,position in zip(self.avgdata[probe], self.plotPositions[probe]):
                self.axes.scatter(position, value, color=color)

        self.axes.set_title("{} distribution on the outer lower target plate in AUG @{:.4f}s".format(self.option,self.realtime))
        self.axes.set_ylabel(self.option)
        self.axes.set_xlabel("$\Delta$s")
        #self.axes.legend()
    

    def setTimeText(self):
        """ Updates GUI time edit field based on scrollbar value """
        # GUI scrollbar provides timestep (index of time array)
        time = self.parent.xTimeSlider.value()
        # Convert to realtime
        realtime = self.dtime[time]
        # Update line edit text
        self.parent.xTimeEdit.setText("{:.4f}".format(realtime))


    def setxTimeSlider(self):
        """ Updates time scrollbar based on text in GUI time edit field"""
        # GUI line edit expects a real time value
        realtime = float(self.parent.xTimeEdit.text())
        # Convert to corresponding timestep
        time = self.convRealToIndex(realtime, self.dtime)
        # Update slider position
        self.parent.xTimeSlider.setValue(float(time))
        # Update line edit text with the time corresponding to the found timestep
        self.parent.xTimeEdit.setText("{:.10f}".format(self.dtime[time]))

    def setDurationText(self):
        """ Updates the shot duration in the info bar. """
        self.parent.dynDurationLabel.setText("{:.3f}".format(self.dtime[-1]))



class TemporalPlot(Plot):
    def __init__(self, parent, quantity):

        self.parent = parent
        self.quantity = quantity
        self.region = 'ua'

        fig = Figure()
        self.axes = fig.add_subplot(111)
        self.canvas = FigureCanvas(fig)

        self.getShotData()
        self.averageData()


    def getShotData(self):
        print("Getting temporal shot data")
        probeNamePrefix = self.quantity + '-' + self.region
        self.data = {}
        self.time = {}
        for probe in self.parent.langData.keys():
            if probe == 'ne-ua1':#probe.startswith(probeNamePrefix):
                self.time[probe] = self.parent.langData[probe]['time']
                self.data[probe] = self.parent.langData[probe]['data']

    def averageData(self):
        """ Averages data for temporal plots. """
        print("Averaging temporal data")
        self.avgData = {}
        self.avgTime = {}
        for probe in self.data.keys():
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

    def initPlot(self):
        """ Creates temporal plot at application start. """
        print("Initiating temporal plot")
        for probe in self.data.keys(): 
            y = self.avgData[probe]
            x = self.avgTime[probe]

            self.scatter, = self.axes.plot(x,y)

        # Implement interactive behavior: Event handling when zoomed or dragged
        # Zoom with mouse wheel
        self.xlim_orig = self.axes.get_xlim()
        self.ylim_orig = self.axes.get_ylim()
        print("Original axes limits - x: {}, y: {}".format(self.xlim_orig, self.ylim_orig))
        self.enableMouseZoom()
        self.axes.callbacks.connect('xlim_changed', self.onXlimChange)

    def onXlimChange(self, axes):
        print "updated xlims: ", axes.get_xlim()

        minTime = axes.get_xlim()[0]
        maxTime = axes.get_xlim()[1]

        # Set time slider range to range shown in zoomed temporal plot
        self.parent.xTimeSlider.setMinimum(self.convRealToIndex(minTime, self.parent.dtime))
        self.parent.xTimeSlider.setMaximum(self.convRealToIndex(maxTime, self.parent.dtime))

        """
        # If the slider is out of range now, set it to the beginning or end of the range
        # depending on where it was before
        if  self.parent.xTimeSlider.value() < minTime:
            self.parent.xTimeSlider.setValue(minTime)
        elif  self.parent.xTimeSlider.value() > maxTime:
            self.parent.xTimeSlider.setValue(maxTime)"""

    def enableMouseZoom(self, base_scale = .5):
        def zoom_fun(event):
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
                print event.button

            # New axes limits. Don't allow zooming out beyond original boundaries
            xlim = [max(xlim_orig[0], xdata - cur_xrange*scale_factor), min(xlim_orig[1], xdata + cur_xrange*scale_factor)]
            ylim = [max(ylim_orig[0], ydata - cur_yrange*scale_factor), min(ylim_orig[1], ydata + cur_yrange*scale_factor)]

            # set new limits
            self.axes.set_xlim(xlim)
            self.axes.set_ylim(ylim)
            
            # Re-draw canvas
            self.canvas.draw()

        fig = self.axes.get_figure() # get the figure of interest
        # attach the call back
        fig.canvas.mpl_connect('scroll_event',zoom_fun)

        #return the function
        return zoom_fun


    def update(self):
        """ Updates temporal plot range based on range slider values. """
        # Minimum and maximum time to display data for in timesteps
        tmin = self.parent.rangeSlider.start()
        tmax = self.parent.rangeSlider.end()

        # Adopt new data
        for probe in self.data.keys(): 
            y = self.avgData[probe][tmin:tmax]
            x = self.avgTime[probe][tmin:tmax]

            self.scatter.set_xdata(x)
            self.scatter.set_ydata(y)

        # Rescale axes
        self.axes.relim()
        self.axes.autoscale_view()


# Main
if __name__ == '__main__':

    app = QtWidgets.QApplication(sys.argv)
    main = ApplicationWindow()
    main.show()

    sys.exit(app.exec_())
