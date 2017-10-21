from __future__ import print_function
import csv
import functools

from PyQt4 import QtGui, QtCore

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
        print('Setting {} to {}'.format(featName, value))
        table = self.table
        feature = next((feat for feat in self.features
                        if feat.name == featName), None)
        if feature is None:
            print('No feature {} found'.format(featName))
            return

        row = table.rowCount() - 1
        col = feature.column

        print('Row: {}, Col: {}'.format(row, col))

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
            print('"quantity" found in column {}'.format(quantCol))
            print('Checking quantity in row {}'.format(row))
                
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
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok
                | QtGui.QDialogButtonBox.Cancel, QtCore.Qt.Horizontal)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        layout.addRow(buttonBox)

        self.setLayout(layout)

    @staticmethod
    def getConfirmation(parent=None, action=None):
        dialog = ConfirmDialog(parent, action)
        result = dialog.exec_()
        return result == QtGui.QDialog.Accepted
