from __future__ import print_function
import csv
import functools
import operator
import re
import os

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib as mpl
from PyQt4 import QtGui, QtCore

from windows import FigureWindow
from conversion import Conversion
from sorttable import MyTableWidgetItem

class FeaturePicker(QtCore.QObject):
    goto = QtCore.pyqtSignal('PyQt_PyObject', 'PyQt_PyObject', 'PyQt_PyObject')
    tableChanged = QtCore.pyqtSignal()
    tableCleared = QtCore.pyqtSignal()
    tableLoaded = QtCore.pyqtSignal()
    tableSaved = QtCore.pyqtSignal()

    def __init__(self, table):
        super(FeaturePicker, self).__init__()
        self.table = table
        table.cellDoubleClicked.connect(self.selectFeature)
        table.horizontalHeader().setMovable(True)
        table.verticalHeader().setMovable(True)

        self.currentFeatureCell = None
        self.currentCanvas = None
        self.features = []
        self._cbids = {}
        self.canvases = {}
        self.tableColumnOrder = None
        self.saved = False

        self.table.cellChanged.connect(self.disable)
        self.table.cellChanged.connect(self.onTableChange)
        self.table.itemChanged.connect(self.onTableChange)
        self.table.setSortingEnabled(True)

    def addCanvas(self, quantity, canvas):
        self.canvases[quantity] = canvas

    def addFeature(self, event=None, featName=None, meta=False):
        table = self.table
        self.table.setSortingEnabled(False)
        if event or featName is None:
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
        self.table.setSortingEnabled(True)

    def setFeatureWidget(self, featName, widget):
        row = self.table.rowCount() - 1
        col = self.getFeatureColumn(featName)
        self.table.setCellWidget(row, col, widget)

    def getHeaderLabels(self):
        headerLabels = []
        for col in range(self.table.columnCount()):
            lbl = str(self.table.horizontalHeaderItem(col).text())
            headerLabels.append(lbl)
        return headerLabels

    def insertData(self, row, label, value, overwrite=False):
        headerLabels = self.getHeaderLabels()
        try:
            col = headerLabels.index(label)
        except ValueError:
            self.addFeature(featName=label)
            col = self.table.columnCount()
        try:
            item = self.table.item(row, col)
        except:
            item = None
        if not item or overwrite:
            item = QtGui.QTableWidgetItem(str(value))
            self.table.setItem(row, col, item)

    def getFeatureColumn(self, featName):
        feature = next((feat for feat in self.features
                        if feat.name == featName), None)
        if feature is None:
            print('No feature {} found'.format(featName))
            return
        return feature.column

    def setFeatureValue(self, featName, value):
        table = self.table
        row = table.rowCount() - 1
        col = self.getFeatureColumn(featName)

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
            self.table.blockSignals(True)
            self.table.setRowCount(0)
            self.table.blockSignals(False)
            self.tableCleared.emit()
            self.saved = True

    def saveTable(self):
        table = self.table
        path = QtGui.QFileDialog.getSaveFileName(self.table,
                                                 'Save File',
                                                 '', 'CSV (*.csv)')
        if not path.isEmpty():
            with open(unicode(path), 'w') as stream:
                writer = csv.writer(stream)
                headerLabels = []
                for col in range(1, table.columnCount()):
                    label = table.horizontalHeaderItem(col).text()
                    headerLabels.append(str(label))
                writer.writerow(headerLabels)
                for row in range(table.rowCount()):
                    rowdata = []
                    for column in range(1, table.columnCount()):
                        item = table.item(row, column)
                        if item is not None:
                            rowdata.append(
                                unicode(item.text()).encode('utf8'))
                        else:
                            rowdata.append('')
                    writer.writerow(rowdata)
            self.tableSaved.emit()

    def onTableChange(self, event):
        self.tableChanged.emit()
        self.saved = False

    def loadTable(self, path=None, col_order=None):
        self.table.blockSignals(True)
        if col_order is None:
            col_order = self.tableColumnOrder
        self.tableWidgets = []
        if not path:
            path = QtGui.QFileDialog.getOpenFileName(self.table,
                                                     'Open File',
                                                     '',
                                                     'CSV (*.csv)')
        if os.path.isfile(path):
            self.features = []
            self.disable()
            with open(unicode(path), 'r') as stream:
                self.table.setRowCount(0)
                self.table.setColumnCount(0)
                for i, rowdata in enumerate(csv.reader(stream)):
                    if i == 0:
                        header = rowdata
                        header.insert(0, 'Go to')

                        permutate = lambda l: l
                        if col_order:
                            col_order = [el for el in col_order
                                         if el in header]
                            ordered_header = col_order + [el for el in header
                                                          if el not in col_order]
                            ordered_indices = map(lambda x: header.index(x),
                                                            ordered_header)
                            permutate = lambda l: list(np.array(l)[ordered_indices])
                            header = ordered_header

                        self.table.setColumnCount(len(header))
                        self.table.setHorizontalHeaderLabels(header)
                        for col, lbl in enumerate(header):
                            feature = Feature(lbl, col, True)
                            self.features.append(feature)
                        continue
                    rowdata.insert(0, '')
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    rowdata = permutate(rowdata)
                    for column, data in enumerate(rowdata):
                        #item = QtGui.QTableWidgetItem(data.decode('utf8'))
                        data = data.decode('utf8')
                        try:
                            data = float(data)
                        except:
                            pass
                        item = QtGui.QTableWidgetItem()
                        item.setData(QtCore.Qt.EditRole, QtCore.QVariant(data))
                        self.table.setItem(row, column, item)

                    # Add go to button
                    shot = rowdata[header.index('Shot')]
                    start = rowdata[header.index('CELMA start')]
                    end = rowdata[header.index('CELMA end')]
                    widget = QtGui.QPushButton('View')
                    widget.clicked.connect(
                        functools.partial(self.goto.emit, shot, start, end))
                    self.table.setCellWidget(row, 0, widget)
                    self.tableWidgets.append(widget)
            self.table.resizeColumnsToContents()
            self.saved = True
        else:
            pass
            #logger.error("File {} does not exist".format(path))
        self.table.blockSignals(False)

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
    removesubplot = QtCore.pyqtSignal()
    changeaxes = QtCore.pyqtSignal('PyQt_PyObject')
    maxrowsChanged = QtCore.pyqtSignal('PyQt_PyObject')
    maxcolsChanged = QtCore.pyqtSignal('PyQt_PyObject')

    def __init__(self, quantities, groups, annots=None, features=None,
                 maxrows=3, maxcols=2, parent=None):
        super(PlottingDialog, self).__init__(parent)
        self.quantities = quantities
        self.groups = groups
        self.annots = []
        self.features = []
        self.rows = {'x': None, 'y': None, 'z': None}
        self.combos = {'x': [], 'y': [], 'z': []}
        self.operators = {'x': [], 'y': [], 'z': []}
        self.operatorMappings = {'-': operator.sub,
                                 '+': operator.add,
                                 '*': operator.mul,
                                 '/': operator.div}
        #self.probes = []

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
        
        self.maxrows = maxrows
        self.maxcols = maxcols

        # probes
        probes = ['ua1', 'ua2', 'ua3', 'ua4', 'ua5',
                  'ua6', 'ua7', 'ua8', 'ua9']
        #probeLbl = QtGui.QLabel('Probes:')
        #row.addWidget(probeLbl)
        #self.cbEmptyProbe = QtGui.QCheckBox('None')
        #self.cbEmptyProbe.setTristate(False)
        #self.cbEmptyProbe.setChecked(True)
        #row.addWidget(self.cbEmptyProbe)
        #for probe in probes:
        #    cbProbe = QtGui.QCheckBox(probe)
        #    cbProbe.setTristate(False)
        #    cbProbe.setChecked(True)
        #    row.addWidget(cbProbe)
        #    self.probes.append(cbProbe)

        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('Annotations:')
        row.addWidget(lbl)
        if annots:
            self.annots = [None] * len(annots)
            for annot, (qid, checked) in annots.iteritems():
                cb = QtGui.QCheckBox(annot.strip('[]'))
                cb.setTristate(False)
                if checked:
                    cb.setChecked(True)
                self.annots[qid] = (annot, cb)
        for _, cb in self.annots:
            row.addWidget(cb)
        layout.addLayout(row)

        row = QtGui.QHBoxLayout()
        lbl1 = QtGui.QLabel('Check which features should ')
        self.cbFeaturesNOT = QtGui.QCheckBox('not')
        self.cbFeaturesNOT.setTristate(False)
        lbl2 = QtGui.QLabel(' be present:')
        row.addWidget(lbl1)
        row.addWidget(self.cbFeaturesNOT)
        row.addWidget(lbl2)
        row.addWidget(lbl2)
        self.cbHighlight = QtGui.QCheckBox('Highlight')
        self.cbHighlight.setTristate(False)
        row.addWidget(self.cbHighlight)
        row.addStretch()
        layout.addLayout(row)

        row = QtGui.QHBoxLayout()
        row.addWidget(lbl)
        if features:
            self.features = [None] * len(features)
            for feat, (qid, checked) in features.iteritems():
                cb = QtGui.QCheckBox(feat.strip('[]'))
                cb.setTristate(False)
                if checked:
                    cb.setChecked(True)
                self.features[qid] = (feat, cb)
        for _, cb in self.features:
            row.addWidget(cb)
        layout.addLayout(row)

        row = QtGui.QHBoxLayout()
        # quantity
        lbl = QtGui.QLabel('Quantity:')
        self.comboQuantity = QtGui.QComboBox()
        self.comboQuantity.addItems(['all', 'te', 'ne', 'jsat'])
        row.addWidget(lbl)
        row.addWidget(self.comboQuantity)

        lbl = QtGui.QLabel('Only show values for xth probe from separatrix:')
        self.comboProbeIndex = QtGui.QComboBox()
        self.comboProbeIndex.addItem('Show all')
        inds = [str(el) for el in range(-2, len(probes))]
        self.comboProbeIndex.addItems(inds)
        row.addWidget(lbl)
        row.addWidget(self.comboProbeIndex)

        lbl = QtGui.QLabel('Group by')
        self.comboGroup = QtGui.QComboBox()
        self.comboGroup.addItem('None')
        self.comboGroup.addItem('Shot')
        self.comboGroup.addItems(self.groups)
        row.addWidget(lbl)
        row.addWidget(self.comboGroup)
        layout.addLayout(row)
        
        row = QtGui.QHBoxLayout()
        self.cb2D = QtGui.QCheckBox('Compare probes')
        row.addWidget(self.cb2D)

        self.cbRegression = QtGui.QCheckBox('Regression')
        row.addWidget(self.cbRegression)

        self.cbShowLines = QtGui.QCheckBox('Show lines')
        row.addWidget(self.cbShowLines)

        self.cbFixX = QtGui.QCheckBox('Fix x')
        row.addWidget(self.cbFixX)

        self.cbFixY = QtGui.QCheckBox('Fix y')
        row.addWidget(self.cbFixY)

        self.comboOrient = QtGui.QComboBox()
        self.comboOrient.addItems(['Vertical', 'Horizontal'])
        row.addWidget(self.comboOrient)

        lbl = QtGui.QLabel('Max rows:')
        self.editMaxRows = QtGui.QLineEdit(str(self.maxrows))
        row.addWidget(self.editMaxRows)

        lbl = QtGui.QLabel('Max cols:')
        self.editMaxCols = QtGui.QLineEdit(str(self.maxcols))
        row.addWidget(self.editMaxCols)
        layout.addLayout(row)
        
        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('Filter')
        self.editFilter = QtGui.QLineEdit('{"Shot": []}')
        row.addWidget(lbl)
        row.addWidget(self.editFilter)

        self.radioFilterMode = QtGui.QButtonGroup()
        negativeFilter = QtGui.QRadioButton('Negative')
        positiveFilter = QtGui.QRadioButton('Positive')
        self.radioFilterMode.addButton(positiveFilter, 0)
        self.radioFilterMode.addButton(negativeFilter, 1)
        positiveFilter.setChecked(True)
        row.addWidget(positiveFilter)
        row.addWidget(negativeFilter)
        layout.addLayout(row)

        row = QtGui.QHBoxLayout()
        lbl = QtGui.QLabel('Filter range')
        self.comboRangeFilter = QtGui.QComboBox()
        self.comboRangeFilter.addItems(quantities)
        self.editRangeFilter = QtGui.QLineEdit()
        row.addWidget(lbl)
        row.addWidget(self.comboRangeFilter)
        row.addWidget(self.editRangeFilter)
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

        self.btnRemoveSubplot = QtGui.QPushButton('Remove subplot')
        self.btnRemoveSubplot.clicked.connect(self.removeSubplot)
        row.addWidget(self.btnRemoveSubplot)

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

        self.editMaxRows.textChanged.connect(self.updateMaxRows)
        self.editMaxCols.textChanged.connect(self.updateMaxCols)

    def changeAxes(self):
        i = self.comboAxes.currentIndex()
        self.changeaxes.emit(i)
        txt = self.comboAxes.currentText()
        self.lblCurrentSubplot.setText(txt)

    def updateMaxRows(self):
        n = str(self.editMaxRows.text())
        try:
            self.maxrows = int(n)
        except ValueError:
            pass
        else:
            self.maxrowsChanged.emit(self.maxrows)
 
    def updateMaxCols(self):
        m = str(self.editMaxCols.text())
        try:
            self.maxcols = int(m)
        except ValueError:
            pass
        else:
            self.maxcolsChanged.emit(self.maxcols)

    def addSubplot(self):
        i = self.comboAxes.count()
        if i < self.maxrows * self.maxcols:
            self.addsubplot.emit()
            self.comboAxes.addItem(str(i + 1))
            self.comboAxes.setCurrentIndex(i)

    def removeSubplot(self):
        if self.comboAxes.count() < 2:
            return
        self.removesubplot.emit()
        self.comboAxes.removeItem(self.comboAxes.count() - 1)

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

        def getLabel(qtlabel, lbls, ops):
            if qtlabel.text():
                return str(qtlabel.text())
            else:
                txt = ''
                if len(ops):
                    ops = [str(op.currentText()) for op in ops]
                    ops.insert(0, '')
                else:
                    ops = ['']
                for lbl, op in zip(lbls, ops):
                    txt += op + lbl
                return txt

        xlabel = getLabel(self.editxlabel, x, opx)
        ylabel = getLabel(self.editylabel, y, opy)
        zlabel = getLabel(self.editzlabel, z, opz)
        title = str(self.editTitle.text())

        plot = str(self.comboQuantity.currentText())
        #probes = [str(cb.text()) for cb in self.probes
        #          if not cb.isChecked()]
        #if self.cbEmptyProbe.isChecked():
        #    probes.append('')
        
        annots = [annot for annot, cb in self.annots if cb.isChecked()]
        exclude_feats = self.cbFeaturesNOT.isChecked()
        features = [feat for feat, cb in self.features if cb.isChecked()]
        hl = self.cbHighlight.isChecked()

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
        
        filters = (filters,
                   str(self.radioFilterMode.checkedButton().text()) ==
                       'Negative')

        try:
            frange = [np.float64(el) for el in str(self.editRangeFilter.text()).split(',')]
        except ValueError:
            frange = None
        rangeFilter = (str(self.comboRangeFilter.currentText()), frange)
        colorbar = self.cbUseColorbar.isChecked()
        shared_cbar = self.cbSharedColorbar.isChecked()
        grid = self.cbShowGrid.isChecked()
        regression = self.cbRegression.isChecked()
        twoD = self.cb2D.isChecked()
        plotType = ('plot' if self.cbShowLines.isChecked() else 'scatter')
        fix = (self.cbFixX.isChecked(),
               self.cbFixY.isChecked())
        orient = str(self.comboOrient.currentText())
        try:
            n = int(self.editMaxRows.text())
        except ValueError:
            n = None
        try:
            m = int(self.editMaxCols.text())
        except ValueError:
            m = None

        return ([x, y, z], [opx, opy, opz], [axisx, axisy, axisz],
                #[xlabel, ylabel, zlabel, title], plot, probes, index,
                [xlabel, ylabel, zlabel, title], plot, annots, index,
                group, filters, colorbar, shared_cbar, grid, regression,
                twoD, rangeFilter, plotType, fix, orient, [n, m], features,
                exclude_feats, hl)


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
        self.annots = {'[Range]': (1, ['CELMA start', '-', 'CELMA end'], 0),
                       'Tdiv':  (2, ['Tdiv'], 0),
                       '[Shot]':  (0, ['Shot'], 0),
                       'Ptot':  (3, ['Ptot'], 0),
                       'nbar':  (4, ['nbar'], 0),
                       'seed':  (5, ['seeding'], 0),
                       'dWmhd':  (6, ['dWmhd'], 0)}
        self.features = {'Bump': (0, 'bump', 0),
                         'Te min': (1, 'detachMax', 0),
                         '1st step': (2, 'step1', 0),
                         '2nd step': (3, 'step2', 0)}
        self.choice = self.chooseQuantities()

    def chooseQuantities(self):
        df = self.table2DataFrame(self.table)
        df = df.apply(functools.partial(pd.to_numeric, errors='ignore'))
 
        def containsCoordinates(series):
            for el in series:
                if type(el) is tuple and len(el) == 2:
                    return True
            return False

        quantities = [quant for quant in df.columns
                      if (df[quant].dtype.char in ('l', 'd')
                          or containsCoordinates(df[quant]))
                      and 1 < len(df[quant].unique())]
        groups = [quant for quant in df.columns
                  if not containsCoordinates(df[quant])
                  and 1 < len(df[quant].unique()) < 11]

        annots = {key: (qid, checked)
                  for key, (qid, quants, checked) in self.annots.iteritems()}
        feats = {key: (qid, checked)
                 for key, (qid, quants, checked) in self.features.iteritems()}
        dialog = PlottingDialog(quantities, groups, annots, feats, parent=self.table)
        dialog.updated.connect(self.update)
        dialog.addsubplot.connect(self.addSubplot)
        dialog.removesubplot.connect(self.removeSubplot)
        dialog.changeaxes.connect(self.changeAxes)
        dialog.maxrowsChanged.connect(self.window.setMaxRows)
        dialog.maxcolsChanged.connect(self.window.setMaxCols)
        dialog.show()

    def __del__(self):
        self.delete.emit()

    def update(self, pars):
        self.choice = pars
        self.plot()

    def addSubplot(self):
        sharex = self.window.axes[-1]
        self.window.addSubplot(sharex=sharex)

    def removeSubplot(self):
        self.window.removeSubplot()

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
                     #plot, probes, index, group, filters, colorbar,
                     plot, annots, index, group, filters, colorbar,
                     shared_cbar, grid, regression, twoD,
                     rangeFilter, plotType, fix, orient, nm,
                     features, exclude_feats, highlight):
        xquants, yquants, zquants = quants
        xops, yops, zops = ops
        xaxisAx, yaxisAx, zaxisAx = axes
        self.xlabel, self.ylabel, self.zlabel, self.title = labels
        self.shared_cbar = shared_cbar
        self.grid = grid
        self.regression = regression
        self.groupedby = group
        self.selected_annots = annots
        self._plot = plot
        self.probeIndex = str(index)
        self.rangeFilter = rangeFilter
        self.twoD = twoD
        filters, negateFilter = filters
        self.plotType = plotType
        self.fixAxes = fix
        self.orientation = orient
        self.maxrows, self.maxcols = nm

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
                        val = val
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

        def getTime(row):
            try:
                return float(row[feat][0])
            except (KeyError, TypeError):
                return np.nan

        #filters_ind = np.ones(df.shape[0], dtype=bool)
        # Filter by plot type and probeIndex
        if str(plot) != 'all':
            ind = df['quantity'].astype(str).isin([str(plot)])
            ind = ind.as_matrix()
            df = df[ind]
            #filters_ind *= ind
        if index is not False:
            ind = df['probeIndex'].astype(str).isin([str(index)])
            ind = ind.as_matrix()
            df = df[ind]
            #filters_ind *= ind

        # Apply custom filter
        for column, filtr in filters.items():
            # Convert both to string before comparing
            filtr = [str(el) for el in filtr]
            if not len(filtr):
                continue
            if negateFilter:
                ind = ~df[column].astype(str).isin(filtr)
            else:
                ind = df[column].astype(str).isin(filtr)
            df = df[ind]
            #filters_ind *= ind

        if self.rangeFilter:
            quant, frange = self.rangeFilter
            try:
                ind = ((df[quant] >= frange[0]) &
                        (df[quant] <= frange[1]))
            except TypeError:
                pass
            else:
                df = df[ind]
                #filters_ind *= ind

        filters_ind = np.ones(df.shape[0], dtype=bool)
        # Filter based on what features are present or missing
        df2 = pd.DataFrame()
        for feature in features:
            column = self.features[feature][1]
            if exclude_feats:
                ind = df[column].isnull()
            else:
                ind = ~df[column].isnull()
            filters_ind *= ind.as_matrix()
            df2[column + '_good'] = ind
        df2['acc_good'] = filters_ind
        df2['Tdiv'] = df['Tdiv']
        df2['nbar'] = df['nbar']
        print(df2.to_string())

        if not any(filters_ind):
            print('No data set passed the filter')
        df["highlight"] = True
        if highlight:
            df["highlight"] = filters_ind
        else:
            df = df[filters_ind]
        
        print("\n", filters_ind.sum(), "matches found.")

        # Grouping
        if twoD:
            feat = yquants[0]
            grouped = df.groupby(['Shot', 'CELMA start', 'quantity'])
            for key, grp in grouped:
                grp = grp.set_index('probeIndex').transpose()
                times = grp.apply(getTime)
                diffs = times.as_matrix()[:-1] - times.as_matrix()[1:]
                diffs = np.append(diffs, np.nan)
                df.loc[((df["Shot"] == key[0]) &
                        (df["CELMA start"] == key[1]) &
                        (df["quantity"] == key[2])), feat] = diffs

        xdata = {}
        ydata = {}
        zdata = {}
        annotations = {}
        highlights = {}
        xargs = (xquants, xops, xaxisAx)
        yargs = (yquants, yops, yaxisAx)
        zargs = (zquants, zops, zaxisAx)

        if group in list(df):
            grouped = df.groupby(group)
        else:
            grouped = [['all', df]]
        for group, groupdf in grouped:
            xdata[group] = groupdf.apply(calculateRowValue, args=xargs, axis=1)
            ydata[group] = groupdf.apply(calculateRowValue, args=yargs, axis=1)
            zdata[group] = groupdf.apply(calculateRowValue, args=zargs, axis=1)
            annotations[group] = self._assemble_annotations(groupdf, group)

            if group != 'all':
                xdata[group] = xdata[group].values
                ydata[group] = ydata[group].values
                zdata[group] = zdata[group].values
            else:
                xdata[group] = xdata[group].values
                ydata[group] = ydata[group].values
                zdata[group] = zdata[group].values
            highlights[group] = groupdf['highlight'].as_matrix()
            if not colorbar:
                zdata[group] = np.zeros(len(xdata[group]))
                zdata[group][:] = np.nan
        return xdata, ydata, zdata, annotations, highlights

    def _assemble_annotations(self, df, group):
        """
        Assemble annotations from data for the selected quantitees.
        """
        notitle = re.compile('\[(.*?)\]')
        size = df.shape[0]
        annotations = [''] * size

        for label in self.selected_annots:
            _, quants, _ = self.annots[label]

            prefix = label + ': ' if not notitle.match(label) else ''
            annotations = [a + '\n' + prefix
                           for a in annotations]
            for quant in quants:
                try:
                    annotations = [str(a) + str(b) 
                              for a, b in zip(annotations, list(df[quant]))]
                except KeyError:
                    annotations = [str(a) + str(b)
                              for a, b in zip(annotations, [quant] * size)]
        return np.array(annotations)

    def table2DataFrame(self, table):
        headerLabels = self.getHeaderLabels(table)
        df = pd.DataFrame(columns=headerLabels,
                          index=range(table.rowCount()))

        for j in range(table.columnCount()):
            for i in range(table.rowCount()):
                item = table.item(i, j)
                try:
                    cont = str(item.text())
                except AttributeError:
                    # Empty cell
                    val = np.nan
                else:
                    if cont.isdigit():
                        # Integers
                        val = np.int(cont)
                    else:
                        try:
                            # Floats
                            val = np.float(cont)
                        except ValueError:
                            vals = cont.split('|')
                            if len(vals) == 1:
                                # String that can't be converted to number
                                # (like probe)
                                # OR like empty string, so check for that
                                # Strip question marks first
                                val, = vals
                                val = val.replace('?','')
                                if not len(val):
                                    val = np.nan
                            elif len(vals) == 2:
                                # Coordinates
                                try:
                                    vals = [np.float(v) for v in vals]
                                except ValueError:
                                    vals = [np.nan, np.nan]
                                # conversion needed because of error 'unhashable
                                # type list' in chooseQuantities otherwise
                                val = tuple(vals)
                            else:
                                val = np.nan
                df.iloc[i, j] = val

        # Unpack single values for easier filtering and plotting
        #for i in range(table.rowCount()):
        #    for j in range(table.columnCount()):
        #        val = df.iloc[i, j]
        #        try:
        #            df.iloc[i, j], = val
        #        except (TypeError, ValueError):
        #            pass

        # Add probe indices based on where they are located relative to
        # strikeline
        def getProbeIndex(probe, sepProbe):
            try:
                probeNumber = int(probe[-1])
                sepProbeNumber = int(sepProbe[-1])
                index = probeNumber - sepProbeNumber
            except (ValueError, IndexError):
                index = np.nan
            return index

        indices = []
        for i in range(table.rowCount()):
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
        xdata, ydata, zdata, annotations, highlights = data
        markers = ['d', 'o', 's', 'P', 'X', '^', 'v', '<', '>',
                   '.', '8', 'p', '*', '+', 'h', 'H', 'D']
        cmap = mpl.cm.get_cmap('gist_rainbow')
        colors = cmap(np.linspace(0, 1, len(xdata)))

        self.window.clearPlot()
        self.window.clearSettings()

        self.window.setSubplotOrientation(self.orientation)
        self.window.setMaxRows(self.maxrows)
        self.window.setMaxCols(self.maxcols)
        #if len(zdata) and None not in zdata.values():
        #    ztot = [el for li in zdata.values() for el in li]
        #    zmax = max(ztot)
        #    zmin = min(ztot)
        #    self.window.feedSettings(vmin=zmin, vmax=zmax)
        self.window.setAutoscale([not fix for fix in self.fixAxes])
        for group, marker, color in zip(xdata, markers, colors):
            x = xdata[group]
            y = ydata[group]
            z = zdata[group]
            t = annotations[group]
            h = highlights[group]

            self.window.setPlotType(self.plotType)
            self.window.feedData(x[h], y[h], z[h])
            self.window.plotData(stale=True, shared_cbar=self.shared_cbar,
                                 marker=marker, color=color, label=group)
            if len(x[~h]):
                self.window.feedData(x[~h], y[~h], z[~h])
                self.window.plotData(stale=True, shared_cbar=self.shared_cbar,
                                     marker=marker, color=color, label=group,
                                     alpha=0.1)
            self.window.annotate(t[h], x[h], y[h], stale=True)
            if self.regression:
                x, y = self.regress(x, y)
                self.window.feedData(x, y)
                self.window.setPlotType('plot')
                self.window.plotData(stale=True, color=color, marker=marker,
                                     label=str(group) + ' fit')
        self.window.setAxesLabels(self.xlabel, self.ylabel, self.zlabel)
        self.window.fig.suptitle(self.title)

        zaxis = not np.isnan(zdata.values()[0]).all()
        
        #zlabel = self.zlabel if zaxis else None

        self.set_window_title()

        leg = self.window._currentAxes.legend()
        if zaxis and leg:
            for hdl in leg.legendHandles:
                hdl.set_color('black')
        if leg:
            leg.draggable(True)
        if self.grid:
            self.window._currentAxes.grid(linestyle='--',
                                          color='lightgrey')
        self.window.updateCanvas()
        self.window.show()

    def set_window_title(self, title=None):
        if not title:
            labels = [self.xlabel, self.ylabel, self.zlabel, 'groupedBy',
                      self.groupedby, 'probe' + self.probeIndex]
            title = '_'.join([lbl for lbl in labels if lbl])
            title = self._plot + '-' + title
            if self.twoD:
                title = '2D_' + title
        # Fixed by re-implementing FigureCanvas in windows.py
        self.window.canvas.set_window_title(title)

    def regress(self, x, y):
        def fit(x, m, t):
            return m * x + t
        x, y = Conversion.removeNansMutually(x, y)
        y = y[x.argsort()]
        x = x[x.argsort()]
        slope, intercept, r, p, stderr = stats.linregress(x, y)
        return x, fit(x, slope, intercept)
