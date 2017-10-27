from __future__ import print_function
import csv
import functools
import operator

import numpy as np
import pandas as pd
from PyQt4 import QtGui, QtCore

from windows import FigureWindow
from conversion import Conversion

class FeaturePicker(object):
    def __init__(self, table):
        self.table = table
        table.cellDoubleClicked.connect(self.selectFeature)
        table.horizontalHeader().setMovable(True)
        table.verticalHeader().setMovable(True)

        self.currentFeatureCell = None
        self.currentCanvas = None
        self.features = []
        self._cbids = {}
        self.canvases = {}

        self.table.cellChanged.connect(self.disable)

    def addCanvas(self, quantity, canvas):
        self.canvases[quantity] = canvas

    def addFeature(self, featName=None, meta=False):
        table = self.table
        if featName is None or not featName:
            featName, ok = QtGui.QInputDialog.getText(table,
                                                      'Add feature',
                                                      'Feature name:')
            if not ok:
                return
            featName = str(featName)

        colPos = table.columnCount()
        table.insertColumn(colPos)

        item = QtGui.QTableWidgetItem(featName)
        table.setHorizontalHeaderItem(colPos, item)

        feature = Feature(featName, colPos, not meta)
        self.features.append(feature)

    def setFeatureValue(self, featName, value):
        table = self.table
        feature = next((feat for feat in self.features
                        if feat.name == featName), None)
        if feature is None:
            print('No feature {} found'.format(featName))
            return

        row = table.rowCount() - 1
        col = feature.column

        try:
            table.removeCellWidget(row, col)
        except:
            pass
        item = QtGui.QTableWidgetItem()
        item.setText(str(value))
        table.setItem(row, col, item)

    def selectFeature(self, row, col):
        table = self.table
        feature = next((feat for feat in self.features
                        if feat.column == col), None)
        if feature is None:
            print("Could not select unregistered feature in column {}"
                  .format(col))
            return
        if feature.isSelectable:
            self.currentFeatureCell = [row, col]
            try:
                table.removeCellWidget(row, col)
            except:
                pass
            self.enable()

    def addRow(self):
        table = self.table
        rowPos = table.rowCount()
        table.insertRow(rowPos)

    def removeRow(self):
        ok = ConfirmDialog.getConfirmation(self.table,
                                           'delete the current row')
        if ok:
            rowPos = self.table.currentRow()
            self.table.removeRow(rowPos)

    def removeColumn(self):
        ok = ConfirmDialog.getConfirmation(self.table,
                                           'delete the current column')
        if ok:
            colPos = self.table.currentColumn()
            self.table.removeColumn(colPos)

    def clearTable(self):
        ok = ConfirmDialog.getConfirmation(self.table)
        if ok:
            self.table.setRowCount(0)

    def saveTable(self):
        table = self.table
        path = QtGui.QFileDialog.getSaveFileName(self.table,
                                                 'Save File',
                                                 '', 'CSV (*.csv)')
        if not path.isEmpty():
            with open(unicode(path), 'w') as stream:
                writer = csv.writer(stream)
                headerLabels = []
                for col in range(table.columnCount()):
                    label = table.horizontalHeaderItem(col).text()
                    headerLabels.append(str(label))
                writer.writerow(headerLabels)
                for row in range(table.rowCount()):
                    rowdata = []
                    for column in range(table.columnCount()):
                        item = table.item(row, column)
                        if item is not None:
                            rowdata.append(
                                unicode(item.text()).encode('utf8'))
                        else:
                            rowdata.append('')
                    writer.writerow(rowdata)

    def loadTable(self):
        path = QtGui.QFileDialog.getOpenFileName(self.table,
                                                 'Open File',
                                                 '',
                                                 'CSV (*.csv)')
        if not path.isEmpty():
            self.features = []
            self.disable()
            with open(unicode(path), 'r') as stream:
                self.table.setRowCount(0)
                self.table.setColumnCount(0)
                for i, rowdata in enumerate(csv.reader(stream)):
                    if i == 0:
                        self.table.setColumnCount(len(rowdata))
                        self.table.setHorizontalHeaderLabels(rowdata)
                        for col, lbl in enumerate(rowdata):
                            feature = Feature(lbl, col, True)
                            self.features.append(feature)
                        continue
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    for column, data in enumerate(rowdata):
                        item = QtGui.QTableWidgetItem(data.decode('utf8'))
                        self.table.setItem(row, column, item)

    def enable(self):
        if len(self.canvases) == 0:
            print('You have to connect at least one canvas to the picker ' +
                  'using addCanvas(quantity, canvas)')
            return
        self._cbids = {}
        for quantity, canvas in self.canvases.items():
            _id = canvas.mpl_connect('button_press_event',
                                     functools.partial(self.pick,
                                                       quantity))
            self._cbids[canvas] = _id

    def disable(self, exceptFor=None):
        for canvas, _id in self._cbids.items():
            if exceptFor == canvas:
                continue
            canvas.mpl_disconnect(_id)
            del self._cbids[canvas]
        self.currentFeatureCell = None
        self.currentCanvas = None

    def pick(self, quantity, event):
        table = self.table
        if event.inaxes:
            if self.currentFeatureCell is None:
                print('No cell selected')
                return
            row, col = self.currentFeatureCell

            quantCol = None
            for _col in range(table.columnCount()):
                headerItem = table.horizontalHeaderItem(_col)
                if str(headerItem.text()) == 'quantity':
                    quantCol = _col
                    break
            if quantCol is None:
                print('Column specifying quantity could not be found. ' +
                      'Aborting')

            quantItem = table.item(row, quantCol)
            if quantItem is not None:
                label = str(quantItem.text())
                if label != '' and quantity != label:
                    print('Quantity conflict! Please pick {} coordinates '
                          .format(label) +
                          '(picked {} instead)'.format(quantity))
                    return

            self.disable(exceptFor=event.canvas)

            x = event.xdata
            y = event.ydata

            self.setFeatureValue('quantity', quantity)

            table.removeCellWidget(row, col)
            item = QtGui.QTableWidgetItem('{} | {}'.format(x, y))
            table.setItem(row, col, item)

            self.disable()


class Feature(object):
    def __init__(self, name, column, selectable=False):
        self.name = name
        self.column = column
        self.isSelectable = selectable


class ConfirmDialog(QtGui.QDialog):
    def __init__(self, parent=None, action=None):
        super(ConfirmDialog, self).__init__(parent)
        if action is None:
            self.setWindowTitle('Are you sure?')
        else:
            self.setWindowTitle('Are you sure you want to {}?'
                                .format(action))

        layout = QtGui.QFormLayout()
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok |
                                           QtGui.QDialogButtonBox.Cancel,
                                           QtCore.Qt.Horizontal)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        layout.addRow(buttonBox)

        self.setLayout(layout)

    @staticmethod
    def getConfirmation(parent=None, action=None):
        dialog = ConfirmDialog(parent, action)
        result = dialog.exec_()
        return result == QtGui.QDialog.Accepted


class PlottingDialog(QtGui.QDialog):
    updated = QtCore.pyqtSignal('PyQt_PyObject')

    def __init__(self, quantities, parent=None):
        super(PlottingDialog, self).__init__(parent)
        self.quantities = quantities
        self.rows = {'x': None, 'y': None}
        self.combos = {'x': [], 'y': []}
        self.operators = {'x': [], 'y': []}
        self.operatorMappings = {'-': operator.sub,
                                 '+': operator.add,
                                 '*': operator.mul,
                                 '/': operator.div}
        self.probes = []

        layout = QtGui.QVBoxLayout()

        # figure title
        row = QtGui.QHBoxLayout()
        xlbl = QtGui.QLabel('Figure title:')
        self.editTitle = QtGui.QLineEdit()
        row.addWidget(xlbl)
        row.addWidget(self.editTitle)
        layout.addLayout(row)

        # quantity
        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('Quantity:')
        self.comboQuantity = QtGui.QComboBox()
        self.comboQuantity.addItems(['all', 'te', 'ne', 'jsat'])
        row.addWidget(lbl)
        row.addWidget(self.comboQuantity)

        # probes
        probeLbl = QtGui.QLabel('Probes:')
        row.addWidget(probeLbl)
        self.cbEmptyProbe = QtGui.QCheckBox('None')
        self.cbEmptyProbe.setTristate(False)
        self.cbEmptyProbe.setChecked(True)
        row.addWidget(self.cbEmptyProbe)
        probes = ['ua1', 'ua2', 'ua3', 'ua4', 'ua5', 'ua6', 'ua7', 'ua8', 'ua9']
        for probe in probes:
            cbProbe = QtGui.QCheckBox(probe)
            cbProbe.setTristate(False)
            cbProbe.setChecked(True)
            row.addWidget(cbProbe)
            self.probes.append(cbProbe)
        self.cbSplitProbes = QtGui.QCheckBox('Split probes')
        self.cbSplitProbes.setTristate(False)
        row.addWidget(self.cbSplitProbes)
        layout.addLayout(row)

        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('Only show values for xth probe from separatrix:')
        self.comboProbeIndex = QtGui.QComboBox()
        self.comboProbeIndex.addItem('Show all')
        inds = [str(el) for el in range(-2, len(probes))]
        self.comboProbeIndex.addItems(inds)
        row.addWidget(lbl)
        row.addWidget(self.comboProbeIndex)
        layout.addLayout(row)

        # x-axis
        row = QtGui.QHBoxLayout()
        self.rows['x'] = row
        xlbl = QtGui.QLabel('x-axis')
        row.addWidget(xlbl)
        self.addCombo('x')

        self.xRadioGroup = QtGui.QButtonGroup()
        self.xxradio = QtGui.QRadioButton('x')
        self.xyradio = QtGui.QRadioButton('y')
        self.xRadioGroup.addButton(self.xxradio, 0)
        self.xRadioGroup.addButton(self.xyradio, 1)
        self.xxradio.setChecked(True)
        row.addWidget(self.xxradio)
        row.addWidget(self.xyradio)

        btnAdd = QtGui.QPushButton('Add')
        btnRemove = QtGui.QPushButton('Remove')
        btnAdd.clicked.connect(functools.partial(self.addCombo, 'x'))
        btnRemove.clicked.connect(functools.partial(self.removeCombo, 'x'))
        row.addWidget(btnAdd)
        row.addWidget(btnRemove)
        layout.addLayout(row)
        
        row = QtGui.QHBoxLayout()
        self.editxlabel = QtGui.QLineEdit()
        lbl = QtGui.QLabel('x-axis label:')
        row.addWidget(lbl)
        row.addWidget(self.editxlabel)
        layout.addLayout(row)

        # y-axis
        row = QtGui.QHBoxLayout()
        self.rows['y'] = row
        ylbl = QtGui.QLabel('y-axis')
        row.addWidget(ylbl)
        self.addCombo('y')

        self.yRadioGroup = QtGui.QButtonGroup()
        self.yxradio = QtGui.QRadioButton('x')
        self.yyradio = QtGui.QRadioButton('y')
        self.yRadioGroup.addButton(self.yxradio, 0)
        self.yRadioGroup.addButton(self.yyradio, 1)
        self.yxradio.setChecked(True)
        row.addWidget(self.yxradio)
        row.addWidget(self.yyradio)

        btnAdd = QtGui.QPushButton('Add')
        btnRemove = QtGui.QPushButton('Remove')
        btnAdd.clicked.connect(functools.partial(self.addCombo, 'y'))
        btnRemove.clicked.connect(functools.partial(self.removeCombo, 'y'))
        row.addWidget(btnAdd)
        row.addWidget(btnRemove)
        layout.addLayout(row)

        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('y-axis label:')
        self.editylabel = QtGui.QLineEdit()
        row.addWidget(lbl)
        row.addWidget(self.editylabel)
        layout.addLayout(row)
        
        # confirmation
        buttonLayout = QtGui.QHBoxLayout()
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok |
                                           QtGui.QDialogButtonBox.Cancel,
                                           QtCore.Qt.Horizontal)
        #buttonBox.accepted.connect(self.accept)
        buttonBox.accepted.connect(self.broadcastUpdate)
        buttonBox.rejected.connect(self.reject)
        buttonLayout.addWidget(buttonBox)
        layout.addLayout(buttonLayout)

        self.setLayout(layout)

    def addCombo(self, axis):
        # Add after last combo at index 1 + #combos + #operators =
        # 1 + #combos + #combos - 1 = 2 * #combos
        # row.count() - 5 should yield the same result
        ind = max(1, 2 * len(self.combos[axis]))
        row = self.rows[axis]
        if len(self.combos[axis]) > 0:
            operatorCombo = QtGui.QComboBox()
            operatorCombo.addItems(self.operatorMappings.keys())
            self.operators[axis].append(operatorCombo)
            row.insertWidget(ind, operatorCombo)

        combo = QtGui.QComboBox()
        combo.addItems(self.quantities)
        self.combos[axis].append(combo)
        row.insertWidget(ind + 1, combo)

    def removeCombo(self, axis):
        if len(self.combos[axis]) < 2:
            return
        row = self.rows[axis]
        ind = row.count() - 6
        row.itemAt(ind).widget().setParent(None)
        self.combos[axis].pop()
        if len(self.operators) > 0:
            row.itemAt(ind).widget().setParent(None)
            self.operators[axis].pop()

    def broadcastUpdate(self):
        pars = self.parameters()
        self.updated.emit(pars)

    def parameters(self):
        axisx = str(self.xRadioGroup.checkedButton().text())
        axisy = str(self.yRadioGroup.checkedButton().text())
        opx = self.operators['x']
        opy = self.operators['y']

        x = []
        y = []
        for combo in self.combos['x']:
            x.append(str(combo.currentText()))
        for combo in self.combos['y']:
            y.append(str(combo.currentText()))

        xlabel = str(self.editxlabel.text())
        ylabel = str(self.editylabel.text())
        title = str(self.editTitle.text())

        plot = str(self.comboQuantity.currentText())
        probes = [str(cb.text()) for cb in self.probes
                  if cb.isChecked()]
        if self.cbEmptyProbe.isChecked():
            probes.append('')

        condense = not self.cbSplitProbes.isChecked()

        try:
            index = int(self.comboProbeIndex.currentText())
        except ValueError:
            index = False

        return ([x, y], [opx, opy], [axisx, axisy],
                [xlabel, ylabel, title], plot, probes, condense, index)

    @staticmethod
    def getQuantities(quantities, parent=None):
        dialog = PlottingDialog(quantities, parent)
        result = dialog.exec_()
        quants, ops, axes, labels, plot, probes, condense, index = dialog.parameters()
        return (quants, ops, axes, labels,
                plot, probes, condense, index, result == QtGui.QDialog.Accepted)


class Plotter(QtCore.QObject):
    delete = QtCore.pyqtSignal()

    def __init__(self, table):
        super(Plotter, self).__init__(table)
        self.table = table
        self.window = FigureWindow()
        self.window.close.connect(self.__del__)
        self.operatorMappings = {'-': operator.sub,
                                 '+': operator.add,
                                 '*': operator.mul,
                                 '/': operator.div}
        self.choice = self.chooseQuantities()

    def chooseQuantities(self):
        quantities = []
        for col in range(self.table.columnCount()):
            lbl = self.table.horizontalHeaderItem(col).text()
            quantities.append(str(lbl))

        #result = PlottingDialog.getQuantities(quantities, self.table)
        dialog = PlottingDialog(quantities, self.table)
        dialog.updated.connect(self.update)
        dialog.show()
        #quants, ops, axes, lbls, plot, probes, condense, index, ok = result
        #if not ok:
        #    return
        #return quants, ops, axes, lbls, plot, probes, condense, index

    def __del__(self):
        self.delete.emit()

    def update(self, pars):
        print("Updating with", pars)
        self.choice = pars
        self.plot()

    def getHeaderLabels(self, table):
        headerLabels = []
        for col in range(table.columnCount()):
            lbl = table.horizontalHeaderItem(col).text()
            headerLabels.append(lbl)
        return headerLabels

    def getTableData(self, quants, ops, axes, labels,
                     plot, probes, condense, index):
        xquants, yquants = quants
        xops, yops = ops
        xaxisAx, yaxisAx = axes
        self.xlabel, self.ylabel, self.title = labels

        headerLabels = self.getHeaderLabels(self.table)

        def getColumns(quantities, headerLabels):
            cols = []
            for lbl in quantities:
                try:
                    col = headerLabels.index(lbl)
                except ValueError:
                    print('Did not find quantity "{}" in header. '
                          .format(lbl) +
                          'Cannot proceed')
                    return
                else:
                    cols.append(col)
            return cols

        def getItemValue(item, axis):
            if not item:
                val = np.nan
            else:
                cont = str(item.text()).split('|')
                if len(cont) > 1:
                    axis = (0 if axis == 'x' else 1)
                    cont = cont[axis]
                else:
                    cont = cont[0]
                try:
                    val = float(cont)
                except ValueError:
                    val = np.nan
            return val

        def calculateRowValue(row, cols, ops, axis):
            cols = list(cols)  # shallow copy
            firstCol = cols.pop(0)
            firstItem = self.table.item(row, firstCol)
            accVal = getItemValue(firstItem, axis)

            for col, op in zip(cols, ops):
                item = self.table.item(row, col)
                val = getItemValue(item, axis)
                opstr = str(op.currentText())
                func = self.operatorMappings[opstr]
                accVal = func(accVal, val)
            return accVal

        def getProbeIndex(probe, sepProbe):
            try:
                probeNumber = int(probe[-1])
                sepProbeNumber = int(sepProbe[-1])
                index = probeNumber - sepProbeNumber
            except ValueError, IndexError:
                index = np.nan
            return index

        xcols = getColumns(xquants, headerLabels)
        ycols = getColumns(yquants, headerLabels)

        if xcols is None or ycols is None:
            return

        plotCol, = getColumns(['quantity'], headerLabels)
        probeCol, = getColumns(['probe'], headerLabels)
        sepProbeCol, = getColumns(['sepProbe'], headerLabels)
        seedCol, = getColumns(['seeding'], headerLabels)
        xdata = {}
        ydata = {}
        meta = {}
        for row in range(self.table.rowCount()):
            pltItem = self.table.item(row, plotCol)
            probeItem = self.table.item(row, probeCol)
            sepProbeItem = self.table.item(row, sepProbeCol)
            seedItem = self.table.item(row, seedCol)
            try:
                plt = str(pltItem.text())
            except AttributeError:
                plt = ''
            try:
                probe = str(probeItem.text())
            except AttributeError:
                probe = ''
            try:
                sepProbe = str(sepProbeItem.text())
            except AttributeError:
                sepProbe = ''
            try:
                seed = str(seedItem.text())
            except AttributeError:
                seed = None

            if index:
                probeIndex = getProbeIndex(probe, sepProbe)
                if not probeIndex == index:
                    continue

            if (plot == 'all' or plt == plot) and probe in probes:
                xval = calculateRowValue(row, xcols, xops, xaxisAx)
                yval = calculateRowValue(row, ycols, yops, yaxisAx)
                if probe not in xdata:
                    xdata[probe] = []
                    ydata[probe] = []
                xdata[probe].append(xval)
                ydata[probe].append(yval)
                if probe not in meta:
                    meta[probe] = {'seeding': []}
                meta[probe]['seeding'].append(seed)

        if condense:
            totx = []
            toty = []
            for probe in xdata:
                x = xdata[probe]
                y = ydata[probe]
                totx.extend(x)
                toty.extend(y)
            xdata = {'all': totx}
            ydata = {'all': toty}

        #xdata, ydata = Conversion.removeNansMutually(xdata, ydata)
        for probe in xdata:
            x = xdata[probe]
            y = ydata[probe]
            if len(x) == 0 or len(x) != len(y):
                continue
            x, y = zip(*sorted(zip(x, y)))
            xdata[probe] = x
            ydata[probe] = y
            
        return xdata, ydata

    def table2DataFrame(self, table):
        rowCount = table.rowCount()
        colCount = table.columnCount()
        headerLabels = self.getHeaderLabels(table)

        df = pd.DataFrame(columns=headerLabels,
                          index=range(rowCount))

        for i in range(rowCount):
            for j in range(colCount):
                df.iloc[i, j] = table.item(i, j).data()

        return df

    def plot(self):
        if self.choice is None:
            return
        data = self.getTableData(*self.choice)
        if data is None:
            return
        xdata, ydata = data
        
        self.window.clearPlot()
        for probe in xdata:
            x = xdata[probe]
            y = ydata[probe]
            self.window.feedData(x, y)
            self.window.setPlotType('scatter')
            self.window.feedSettings(marker='d', label=probe)
            plt = self.window.plotData(stale=True)
        self.window.setAxesLabels(self.xlabel, self.ylabel)
        self.window.fig.suptitle(self.title)
        self.window.updateCanvas()
        self.window.show()
