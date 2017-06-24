from PyQt4 import QtGui, QtCore, Qt
from PyQt4.QtCore import pyqtSignal

class SchizoSlider(QtGui.QSlider):
    """ A slider with multiple handles
    
        This class emits the same signals as the QSlider base class, with the 
        exception of valueChanged
    """
    valueChanged = pyqtSignal('PyQt_PyObject')
    valueChangedByUser = pyqtSignal('PyQt_PyObject')

    def __init__(self, *args):
        super(SchizoSlider, self).__init__(*args)
        
        self._low = self.minimum()
        self._high = self.maximum()
        self._middle = (self.maximum() - self.minimum())/2

        self.pressed_control = QtGui.QStyle.SC_None
        self.hover_control = QtGui.QStyle.SC_None
        self.click_offset = 0
        
        # 0 for the low, 1 for the middle, 2 for the high -1 for all
        self.active_slider = 0

    def low(self):
        return self._low

    def setLow(self, low):
        self._low = int(low)
        self.update()
        self.valueChanged.emit(low)

    def middle(self):
        return self._middle

    def setMiddle(self, middle):
        self._middle = int(middle)
        self.update()
        self.valueChanged.emit(middle)

    def high(self):
        return self._high

    def setHigh(self, high):
        self._high = int(high)
        self.update()
        self.valueChanged.emit(high)
        
        
    def paintEvent(self, event):
        # based on http://qt.gitorious.org/qt/qt/blobs/master/src/gui/widgets/qslider.cpp

        painter = QtGui.QPainter(self)
        style = QtGui.QApplication.style() 
        
        for i, value in enumerate([self._low, self._middle, self._high]):
            opt = QtGui.QStyleOptionSlider()
            self.initStyleOption(opt)

            # Only draw the groove for the first slider so it doesn't get drawn
            # on top of the existing ones every time
            if i == 0:
                opt.subControls = QtGui.QStyle.SC_SliderHandle#QtGui.QStyle.SC_SliderGroove | QtGui.QStyle.SC_SliderHandle
            else:
                opt.subControls = QtGui.QStyle.SC_SliderHandle

            if self.tickPosition() != self.NoTicks:
                opt.subControls |= QtGui.QStyle.SC_SliderTickmarks

            if self.pressed_control:
                opt.activeSubControls = self.pressed_control
                opt.state |= QtGui.QStyle.State_Sunken
            else:
                opt.activeSubControls = self.hover_control

            opt.sliderPosition = value
            opt.sliderValue = value                                  
            style.drawComplexControl(QtGui.QStyle.CC_Slider, opt, painter, self)
            
        
    def mousePressEvent(self, event):
        event.accept()
        
        style = QtGui.QApplication.style()
        button = event.button()
        
        # In a normal slider control, when the user clicks on a point in the 
        # slider's total range, but not on the slider part of the control the
        # control would jump the slider value to where the user clicked.
        # For this control, clicks which are not direct hits will slide both
        # slider parts
                
        if button:
            opt = QtGui.QStyleOptionSlider()
            self.initStyleOption(opt)

            self.active_slider = -1
            
            for i, value in enumerate([self._low, self._middle, self._high]):
                opt.sliderPosition = value                
                hit = style.hitTestComplexControl(style.CC_Slider, opt, event.pos(), self)
                if hit == style.SC_SliderHandle:
                    self.active_slider = i
                    self.pressed_control = hit
                    
                    self.triggerAction(self.SliderMove)
                    self.setRepeatAction(self.SliderNoAction)
                    self.setSliderDown(True)

                    rectHandle=style.subControlRect(QtGui.QStyle.CC_Slider,opt, QtGui.QStyle.SC_SliderHandle,self.window())
                    x=self.__pick(event.pos()) + self.__pick(self.pos())
                    y=rectHandle.bottom()+rectHandle.height()+self.pos().y()
                    QtGui.QToolTip.showText(QtCore.QPoint(x,y), str(value), self.window())

                    break

            if self.active_slider < 0:
                self.pressed_control = QtGui.QStyle.SC_SliderHandle
                self.click_offset = self.__pixelPosToRangeValue(self.__pick(event.pos()))
                self.triggerAction(self.SliderMove)
                self.setRepeatAction(self.SliderNoAction)
        else:
            event.ignore()

            
    def mouseMoveEvent(self, event):
        if self.pressed_control != QtGui.QStyle.SC_SliderHandle:
            event.ignore()
            return
        
        event.accept()
        opt = QtGui.QStyleOptionSlider()
        self.initStyleOption(opt)
        style = QtGui.QApplication.style()
        rectHandle = style.subControlRect(
                        QtGui.QStyle.CC_Slider,opt, 
                        QtGui.QStyle.SC_SliderHandle,self.window())
        new_pos = self.__pixelPosToRangeValue(self.__pick(event.pos()) - rectHandle.width()/2)
        
        if self.active_slider < 0:
            offset = new_pos - self.click_offset 
            self._high += offset
            self._middle += offset
            self._low += offset
            if self._low < self.minimum():
                diff = self.minimum() - self._low
                self._low += diff
                self._high += diff
            if self._high > self.maximum():
                diff = self.maximum() - self._high
                self._low += diff
                self._high += diff            
        elif self.active_slider == 0:
            if new_pos >= self._middle:
                new_pos = self._middle - 1
            self._low = new_pos
        elif self.active_slider == 1:
            if new_pos <= self._low:
                new_pos = self._low + 1
            elif new_pos >= self._high:
                new_pos = self._high - 1
            self._middle = new_pos
        else:
            if new_pos <= self._middle:
                new_pos = self._middle + 1
            self._high = new_pos

        x=self.__pick(event.pos()) + self.__pick(self.pos())
        y=rectHandle.bottom()+rectHandle.height()+self.pos().y()
        QtGui.QToolTip.showText(QtCore.QPoint(x,y), str(new_pos), self.window())

        self.click_offset = new_pos

        self.update()

        self.valueChanged.emit(new_pos)
        self.valueChangedByUser.emit(new_pos)
            
    def __pick(self, pt):
        if self.orientation() == QtCore.Qt.Horizontal:
            return pt.x()
        else:
            return pt.y()
           
           
    def __pixelPosToRangeValue(self, pos):
        opt = QtGui.QStyleOptionSlider()
        self.initStyleOption(opt)
        style = QtGui.QApplication.style()

        gr = style.subControlRect(style.CC_Slider, opt, style.SC_SliderGroove, self)
        sr = style.subControlRect(style.CC_Slider, opt, style.SC_SliderHandle, self)
        
        if self.orientation() == QtCore.Qt.Horizontal:
            slider_length = sr.width()
            slider_min = gr.x()
            slider_max = gr.right() - slider_length + 1
        else:
            slider_length = sr.height()
            slider_min = gr.y()
            slider_max = gr.bottom() - slider_length + 1
            
        return style.sliderValueFromPosition(self.minimum(), self.maximum(),
                                             pos-slider_min, slider_max-slider_min,
                                             opt.upsideDown)

if __name__ == "__main__":
    import sys
    def echo(value):
        print value
    app = QtGui.QApplication(sys.argv)
    slider = SchizoSlider(Qt.Qt.Horizontal)
    slider.setMinimum(-10000)
    slider.setMaximum(10000)
    slider.setLow(0)
    slider.setMiddle(5000)
    slider.setHigh(10000)
    slider.setTickPosition(QtGui.QSlider.TicksBelow)
    QtCore.QObject.connect(slider, QtCore.SIGNAL('sliderMoved(int)'), echo)
    slider.show()
    slider.raise_()
    app.exec_()
