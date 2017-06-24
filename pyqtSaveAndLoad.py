#===================================================================
# Module with functions to save & restore qt widget values
# Written by: Alan Lilly 
# Website: http://panofish.net
#===================================================================

import sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
import inspect

#===================================================================
# save "ui" controls and values to registry "setting"
# ui = qmainwindow object
# settings = qsettings object
#===================================================================

def guisave(ui, settings):

    #for child in ui.children():  # works like getmembers, but because it
    #traverses the hierarachy, you would have to call guisave recursively to
    #traverse down the tree

    for name, obj in inspect.getmembers(ui):
        if isinstance(obj, QComboBox):
            name   = obj.objectName()      
            text   = obj.currentText()   
            settings.setValue(name, text)  

        if isinstance(obj, QLineEdit):
            name = obj.objectName()
            value = obj.text()
            settings.setValue(name, value)    
        
        if isinstance(obj, QCheckBox):
            name = obj.objectName()
            if obj.isTristate():
                state = obj.checkState()
            else:
                state = obj.isChecked()
            settings.setValue(name, state)

        if isinstance(obj, QRadioButton):
            name = obj.objectName()
            state = obj.isChecked()
            settings.setValue(name, state)

        if isinstance(obj, QSlider):
            name = obj.objectName()
            state = obj.value()
            settings.setValue(name, state)

        if isinstance(obj, QAction):
            if obj.isCheckable():
                name = obj.objectName()
                state = obj.isChecked()
                settings.setValue(name, state)

#===================================================================
# restore "ui" controls with values stored in registry "settings"
# ui = QMainWindow object
# settings = QSettings object
#===================================================================

def guirestore(ui, settings):

    for name, obj in inspect.getmembers(ui):
        if isinstance(obj, QComboBox):
            name = obj.objectName()
            value = unicode(settings.value(name))  
            index = obj.findText(value) 

            #if index == -1:
            #    obj.insertItems(0,[value])
            #    index = obj.findText(value)
            #    obj.setCurrentIndex(index)
            #else:
            if index > -1:
                obj.setCurrentIndex(index)   

        if isinstance(obj, QLineEdit):
            name = obj.objectName()
            value = unicode(settings.value(name))  
            obj.setText(value)  

        if isinstance(obj, QCheckBox):
            name = obj.objectName()
            value = settings.value(name)   
            if value is not None:
                if obj.isTristate():
                    obj.setCheckState(value)  
                else:
                    obj.setChecked(value)  

        if isinstance(obj, QRadioButton):
            name = obj.objectName()
            value = settings.value(name)   
            if value is not None:
                obj.setChecked(value)

        if isinstance(obj, QAction):
            if obj.isCheckable():
                name = obj.objectName()
                value = settings.value(name)   
                if value is not None:
                    obj.setChecked(value)
        
        if isinstance(obj, QSlider):
            name = obj.objectName()
            value = unicode(settings.value(name))  
            if value is not None:
                obj.setValue(value)
