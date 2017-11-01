from __future__ import print_function
import csv
import functools
import operator

import numpy as np
import pandas as pd
from PyQt4 import QtGui, QtCore

from windows import FigureWindow

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
    addsubplot = QtCore.pyqtSignal()
    changeaxes = QtCore.pyqtSignal('PyQt_PyObject')

    def __init__(self, quantities, plotter, parent=None):
        super(PlottingDialog, self).__init__(parent)
        self.quantities = quantities
        self.rows = {'x': None, 'y': None, 'z': None}
        self.combos = {'x': [], 'y': [], 'z': []}
        self.operators = {'x': [], 'y': [], 'z': []}
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

        self.cbShowGrid = QtGui.QCheckBox('Show grid')
        row.addWidget(self.cbShowGrid)
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
        probes = ['ua1', 'ua2', 'ua3', 'ua4', 'ua5',
                  'ua6', 'ua7', 'ua8', 'ua9']
        for probe in probes:
            cbProbe = QtGui.QCheckBox(probe)
            cbProbe.setTristate(False)
            cbProbe.setChecked(True)
            row.addWidget(cbProbe)
            self.probes.append(cbProbe)
        layout.addLayout(row)

        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('Only show values for xth probe from separatrix:')
        self.comboProbeIndex = QtGui.QComboBox()
        self.comboProbeIndex.addItem('Show all')
        inds = [str(el) for el in range(-2, len(probes))]
        self.comboProbeIndex.addItems(inds)
        row.addWidget(lbl)
        row.addWidget(self.comboProbeIndex)

        lbl = QtGui.QLabel('Group by')
        self.comboGroup = QtGui.QComboBox()
        self.comboGroup.addItems(self.quantities)
        row.addWidget(lbl)
        row.addWidget(self.comboGroup)

        lbl = QtGui.QLabel('Filter')
        self.editFilter = QtGui.QLineEdit('{"Shot": [], "probe": []}')
        row.addWidget(lbl)
        row.addWidget(self.editFilter)
        layout.addLayout(row)

        # x-axis
        row = QtGui.QHBoxLayout()
        self.rows['x'] = row
        xlbl = QtGui.QLabel('x-axis')
        row.addWidget(xlbl)
        self.addCombo('x')

        self.xRadioGroup = QtGui.QButtonGroup()
        xxradio = QtGui.QRadioButton('x')
        xyradio = QtGui.QRadioButton('y')
        self.xRadioGroup.addButton(xxradio, 0)
        self.xRadioGroup.addButton(xyradio, 1)
        xxradio.setChecked(True)
        row.addWidget(xxradio)
        row.addWidget(xyradio)

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
        yxradio = QtGui.QRadioButton('x')
        yyradio = QtGui.QRadioButton('y')
        self.yRadioGroup.addButton(yxradio, 0)
        self.yRadioGroup.addButton(yyradio, 1)
        yxradio.setChecked(True)
        row.addWidget(yxradio)
        row.addWidget(yyradio)

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

        # z-axis
        row = QtGui.QHBoxLayout()
        self.rows['z'] = row
        ylbl = QtGui.QLabel('z-axis')
        row.addWidget(ylbl)
        self.cbUseColorbar = QtGui.QCheckBox('Active')
        self.cbUseColorbar.setTristate(False)
        self.cbSharedColorbar = QtGui.QCheckBox('Share colorbar')
        self.cbSharedColorbar.setTristate(False)
        row.addWidget(self.cbUseColorbar)
        row.addWidget(self.cbSharedColorbar)
        self.addCombo('z')

        self.zRadioGroup = QtGui.QButtonGroup()
        zxradio = QtGui.QRadioButton('x')
        zyradio = QtGui.QRadioButton('y')
        self.zRadioGroup.addButton(zxradio, 0)
        self.zRadioGroup.addButton(zyradio, 1)
        zxradio.setChecked(True)
        row.addWidget(zxradio)
        row.addWidget(zyradio)

        btnAdd = QtGui.QPushButton('Add')
        btnRemove = QtGui.QPushButton('Remove')
        btnAdd.clicked.connect(functools.partial(self.addCombo, 'z'))
        btnRemove.clicked.connect(functools.partial(self.removeCombo, 'z'))
        row.addWidget(btnAdd)
        row.addWidget(btnRemove)
        layout.addLayout(row)

        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('z-axis label:')
        self.editzlabel = QtGui.QLineEdit()
        row.addWidget(lbl)
        row.addWidget(self.editzlabel)
        layout.addLayout(row)

        # subplots
        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('Current subplot')
        self.lblCurrentSubplot = QtGui.QLabel('1')
        row.addWidget(lbl)
        row.addWidget(self.lblCurrentSubplot)

        self.btnAddSubplot = QtGui.QPushButton('Add subplot')
        self.btnAddSubplot.clicked.connect(self.addSubplot)
        row.addWidget(self.btnAddSubplot)

        lbl = QtGui.QLabel('Switch to subplot')
        self.comboAxes = QtGui.QComboBox()
        self.comboAxes.addItem('1')
        self.comboAxes.currentIndexChanged.connect(self.changeAxes)
        row.addWidget(lbl)
        row.addWidget(self.comboAxes)
        layout.addLayout(row)

        # confirmation
        buttonLayout = QtGui.QHBoxLayout()
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok |
                                           QtGui.QDialogButtonBox.Cancel,
                                           QtCore.Qt.Horizontal)
        buttonBox.accepted.connect(self.broadcastUpdate)
        buttonBox.rejected.connect(self.reject)
        buttonLayout.addWidget(buttonBox)
        layout.addLayout(buttonLayout)

        self.setLayout(layout)

    def changeAxes(self):
        i = self.comboAxes.currentIndex()
        self.changeaxes.emit(i)
        txt = self.comboAxes.currentText()
        self.lblCurrentSubplot.setText(txt)

    def addSubplot(self):
        self.addsubplot.emit()
        i = self.comboAxes.count() + 1
        self.comboAxes.addItem(str(i))
        self.comboAxes.setCurrentIndex(i - 1)

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
        axisz = str(self.zRadioGroup.checkedButton().text())
        opx = self.operators['x']
        opy = self.operators['y']
        opz = self.operators['z']

        x = []
        y = []
        z = []
        for combo in self.combos['x']:
            x.append(str(combo.currentText()))
        for combo in self.combos['y']:
            y.append(str(combo.currentText()))
        for combo in self.combos['z']:
            z.append(str(combo.currentText()))

        xlabel = str(self.editxlabel.text())
        ylabel = str(self.editylabel.text())
        zlabel = str(self.editzlabel.text())
        title = str(self.editTitle.text())

        plot = str(self.comboQuantity.currentText())
        probes = [str(cb.text()) for cb in self.probes
                  if not cb.isChecked()]
        if self.cbEmptyProbe.isChecked():
            probes.append('')

        try:
            index = int(self.comboProbeIndex.currentText())
        except ValueError:
            index = False

        group = str(self.comboGroup.currentText())
        filters = {}
        try:
            filters = eval(str(self.editFilter.text()))
        except ValueError:
            pass
        colorbar = self.cbUseColorbar.isChecked()
        shared_cbar = self.cbSharedColorbar.isChecked()
        grid = self.cbShowGrid.isChecked()

        return ([x, y, z], [opx, opy, opz], [axisx, axisy, axisz],
                [xlabel, ylabel, zlabel, title], plot, probes, index,
                group, filters, colorbar, shared_cbar, grid)


class Plotter(QtCore.QObject):
    delete = QtCore.pyqtSignal()

    def __init__(self, table):
        super(Plotter, self).__init__(table)
        self.table = table
        self.window = FigureWindow(self.table)
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

        dialog = PlottingDialog(quantities, self, self.table)
        dialog.updated.connect(self.update)
        dialog.addsubplot.connect(self.addSubplot)
        dialog.changeaxes.connect(self.changeAxes)
        dialog.show()

    def __del__(self):
        self.delete.emit()

    def update(self, pars):
        self.choice = pars
        self.plot()

    def addSubplot(self):
        sharex = self.window.axes[-1]
        self.window.addSubplot(sharex=sharex)

    def changeAxes(self, axNum):
        ax = self.window.axes[axNum]
        self.window.setCurrentAxes(ax)

    def getHeaderLabels(self, table):
        headerLabels = []
        for col in range(table.columnCount()):
            lbl = str(table.horizontalHeaderItem(col).text())
            headerLabels.append(lbl)
        return headerLabels

    def getTableData(self, quants, ops, axes, labels,
                     plot, probes, index, group, filters, colorbar,
                     shared_cbar, grid):
        xquants, yquants, zquants = quants
        xops, yops, zops = ops
        xaxisAx, yaxisAx, zaxisAx = axes
        self.xlabel, self.ylabel, self.zlabel, self.title = labels
        self.shared_cbar = shared_cbar
        self.grid = grid

        df = self.table2DataFrame(self.table)

        def calculateRowValue(row, cols, ops, axis):
            def getAxis(val, ax):
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    if len(val) == 2 and not isinstance(val, basestring):
                        ax = (0 if ax == 'x' else 1)
                        val = val[ax]
                        try:
                            val = float(val)
                        except (ValueError, TypeError):
                            val = np.nan
                    else:
                        val = np.nan
                return val

            accVal = row[cols[0]]
            accVal = getAxis(accVal, axis)

            for col, op in zip(cols[1:], ops):
                val = row[col]
                val = getAxis(val, axis)
                opstr = str(op.currentText())
                func = self.operatorMappings[opstr]
                accVal = func(accVal, val)
            return accVal

        xdata = {}
        ydata = {}
        zdata = {}
        xargs = (xquants, xops, xaxisAx)
        yargs = (yquants, yops, yaxisAx)
        zargs = (zquants, zops, zaxisAx)

        # Filtering
        filters['probeIndex'] = [el for el in range(-2, 9)
                                 if str(el) == str(index)]
        filters['probe'].extend(probes)
        if str(plot) != 'all':
            filters['quantity'] = [q for q in ['te', 'ne', 'jsat']
                                   if q != str(plot)]
        for column, exclude in filters.items():
            # Convert both to string before comparing
            exclude = [str(el) for el in exclude]
            ind = ~df[column].astype(str).isin(exclude)
            df = df.loc[ind]

        # Grouping
        if group in list(df):
            grouped = df.groupby(group)
        else:
            grouped = [['all', df]]
        for group, groupdf in grouped:
            xdata[group] = groupdf.apply(calculateRowValue, args=xargs, axis=1)
            ydata[group] = groupdf.apply(calculateRowValue, args=yargs, axis=1)
            zdata[group] = groupdf.apply(calculateRowValue, args=zargs, axis=1)
            if group != 'all':
                xdata[group] = xdata[group].tolist()
                ydata[group] = ydata[group].tolist()
                zdata[group] = zdata[group].tolist()
            else:
                xdata[group] = xdata[group].values.tolist()
                ydata[group] = ydata[group].values.tolist()
                zdata[group] = zdata[group].values.tolist()
            if not colorbar:
                zdata[group] = None
        return xdata, ydata, zdata

    def table2DataFrame(self, table):
        rowCount = table.rowCount()
        headerLabels = self.getHeaderLabels(table)

        df = pd.DataFrame(columns=headerLabels,
                          index=range(rowCount))

        for i in range(rowCount):
            for j, colName in enumerate(headerLabels):
                item = table.item(i, j)
                try:
                    cont = str(item.text())
                except (ValueError, AttributeError):
                    vals = np.nan
                else:
                    if cont == '':
                        vals = np.nan
                    else:
                        vals = cont.split('|')
                        vals = tuple(vals)
                df.iloc[i, j] = vals

        # Unpack single values for easier filtering and plotting
        for i in range(rowCount):
            for j, colName in enumerate(headerLabels):
                val = df.iloc[i, j]
                try:
                    df.iloc[i, j], = val
                except (TypeError, ValueError):
                    pass

        # Add probe indices based on where they are located relative to
        # strikeline
        def getProbeIndex(probe, sepProbe):
            try:
                probeNumber = int(probe[-1])
                sepProbeNumber = int(sepProbe[-1])
                index = probeNumber - sepProbeNumber
            except (ValueError, IndexError):
                index = np.nan
            #print("Index for {} ({}) relative to {} ({}): {}".
            #      format(probe, probeNumber, sepProbe, sepProbeNumber, index))
            return index

        indices = []
        for i in range(rowCount):
            probe = str(df.loc[i, 'probe'])
            sepProbe = str(df.loc[i, 'sepProbe'])
            index = getProbeIndex(probe, sepProbe)
            indices.append(index)
        df['probeIndex'] = pd.Series(indices)
        return df

    def plot(self):
        if self.choice is None:
            return
        data = self.getTableData(*self.choice)
        if data is None:
            return
        xdata, ydata, zdata = data
        markers = ['d', 'o', 's', 'P', 'X', '^', 'v', '<', '>',
                   '.', '8', 'p', '*', '+', 'h', 'H', 'D']

        self.window.clearPlot()
        if len(zdata) and None not in zdata.values():
            ztot = [el for li in zdata.values() for el in li]
            zmax = max(ztot)
            zmin = min(ztot)
            self.window.feedSettings(vmin=zmin, vmax=zmax)
        for group, marker in zip(xdata, markers):
            x = xdata[group]
            y = ydata[group]
            z = zdata[group]
            self.window.feedData(x, y, z)
            self.window.setPlotType('scatter')
            self.window.feedSettings(marker=marker, label=group)
            self.window.plotData(stale=True, shared_cbar=self.shared_cbar)
        self.window.setAxesLabels(self.xlabel, self.ylabel, self.zlabel)
        self.window.fig.suptitle(self.title)
        leg = self.window._currentAxes.legend(loc='best')
        if None not in zdata.values() and leg:
            for hdl in leg.legendHandles:
                hdl.set_color('black')
        leg.draggable(True)
        if self.grid:
            self.window._currentAxes.grid(linestyle='--',
                                          color='lightgrey')
        self.window.updateCanvas()
        self.window.show()
