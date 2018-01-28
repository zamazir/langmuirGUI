from PyQt4.QtCore import Qt, QVariant
from PyQt4.QtGui import QApplication, QTableWidget, QTableWidgetItem

class MyTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        if ( isinstance(other, QTableWidgetItem) ):
            my_value, my_ok = self.data(Qt.EditRole).toInt()
            other_value, other_ok = other.data(Qt.EditRole).toInt()

            if ( my_ok and other_ok ):
                return my_value < other_value

        return super(MyTableWidgetItem, self).__lt__(other)

if ( __name__ == '__main__' ):
    app = None
    if ( QApplication.instance() is None ):
        app = QApplication([])

    widget = QTableWidget()
    widget.setWindowFlags(Qt.Dialog)
    widget.setSortingEnabled(True)

    widget.setRowCount(50)
    widget.setColumnCount(3)
    for row in range(50):
       # create a normal QTableWidgetItem
       a = QTableWidgetItem()
       a.setText(str(row))
       widget.setItem(row, 0, a)

       # create a proper sorted item
       b = QTableWidgetItem()
       b.setData(Qt.EditRole, QVariant(row))
       widget.setItem(row, 1, b)

       # create a custom sorted item
       c = MyTableWidgetItem()
       c.setData(Qt.EditRole, QVariant(row))
       widget.setItem(row, 2, c)

    widget.show()
    if ( app ):
        app.exec_()


