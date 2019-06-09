import PyQt5.Qt as qt
import sys
from moviepy.video.io import ffmpeg_reader
from moviepy.video.io import ffmpeg_writer
import time
import os

class CutDialog(qt.QTableWidget):
    sg_try_pause = qt.pyqtSignal(str)
    sg_try_start = qt.pyqtSignal(str)
    sg_try_cancel = qt.pyqtSignal(str)
    def __init__(self,parent = None):
        super(CutDialog,self).__init__(0,5,parent)
        self.setHorizontalHeaderLabels(['src-file','dst-file','process','re-time','op'])
        self.filelist = []
        self.setWindowTitle('视频剪辑')
        self.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.layout = qt.QGridLayout()
        self.setLayout(self.layout)

    def _update(self,dst,progress ,re_time ):
        index = self.filelist.index(dst)
        if progress != -1:
           self.cellWidget(index,2).setValue(progress)

        if re_time != '':
            self.item(index,3).setText(re_time)

    def _addRow(self,src,dst):
        if self.filelist.__contains__(dst) == True:
            return False
        index = self.filelist.__len__()
        self.filelist.append(dst)
        self.insertRow(index)
        src_item = qt.QTableWidgetItem(src)
        src_item.setToolTip(src)
        dst_item = qt.QTableWidgetItem(dst)
        dst_item.setToolTip(dst)
        self.setItem(index, 0, src_item)
        self.setItem(index, 1, dst_item)
        self.setItem(index, 3, qt.QTableWidgetItem('99:99:99'))
        progressBar = qt.QProgressBar()
        progressBar.setMinimum(0)
        progressBar.setMaximum(100)
        progressBar.setValue(0)
        self.setCellWidget(index,2,progressBar)

        btn = qt.QPushButton('operation')
        btn.setObjectName(dst)
        btn.installEventFilter(self)
        menu = qt.QMenu()
        menu.addAction('pause',self._try_pause)
        menu.addAction('start', self._try_start)
        menu.addAction('cancel', self._try_cancel)
        btn.setMenu(menu)
        self.setCellWidget(index,4,btn)
        return True

    def _delRow(self,dst):
        index = self.filelist.index(dst)
        self.removeRow(index)
        del self.filelist[index]

    def _try_pause(self):
        self.sg_try_pause.emit(self.clickName)

    def _try_start(self):
        self.sg_try_start.emit(self.clickName)

    def _try_cancel(self):
        self.sg_try_cancel.emit(self.clickName)

    def eventFilter(self, obj, event):
        if(obj.metaObject().className() == 'QPushButton' and event.type() == qt.QMouseEvent.MouseButtonPress):
            self.clickName = obj.objectName()
        return False

class ThreadPool(qt.QObject):
    def __init__(self):
        super(ThreadPool,self).__init__()
        self.maxThreads = qt.QThreadPool.globalInstance().maxThreadCount()
        self.freeList = []
        self.currentThreads = 0
        self.busyList = []
        for i in range(self.maxThreads):
            thread = qt.QThread()
            # thread.finished.connect(self.onFinished)
            self.freeList.append(thread)
    def requireThreads(self):
        self.checkThreads()
        if self.currentThreads < self.maxThreads:
            thread = self.freeList.pop()#出栈最后一个
            self.busyList.append(thread)
            self.currentThreads = self.currentThreads+1
            return thread
        else:
            return False
    def checkThreads(self):
        for thread in self.busyList:
            if not thread.isRunning():
                self.freeList.append(thread)
                self.busyList.remove(thread)
                self.currentThreads = self.currentThreads - 1

    def __del__(self):
        for thread in self.busyList:
            thread.quit()
            thread.wait()
        for thread in self.freeList:
            thread.quit()
            thread.wait()

class CutOp(qt.QObject):
    sg_cancel = qt.pyqtSignal(str)#str:dst,outfilename
    sg_update = qt.pyqtSignal(str,int,str)#str:dst,int:progrocess value,str:time
    sg_finished = qt.pyqtSignal(str)
    def __init__(self,filename,begin,end,cutfps,size,fps,outfilename,inv = False):
        super(CutOp,self).__init__()
        self.mutex_process = qt.QMutex(qt.QMutex.Recursive)  #used for pause,start,cancel function
        self.cancel = False
        self.pause = False
        self.filename = filename
        self.begin = begin
        self.end = end
        self.cutfps = cutfps
        self.outfilename = outfilename
        self.size = size
        self.fps = fps
        self.inv = inv

    #filename:src filename
    #begin:video cut beginning point
    #end:video cut ending point
    #cutfps:cut n frames per second in original video.for example:
    #       cutfps=1,then we cut 1 frame per second at time point:begin,begin+1,begin+2...
    #       cutfps=2,then we cut 2 frames per second at time point:begin,begin+0.5,begin+1,...
    #       the max cutfps = video.fps,because 1 second contains video.fps frames in source video
    #note that:if begin < end then we get the invert video,which means,the frames' order is from end to begin

    def cutVideo(self):
        filename = self.filename
        begin = self.begin
        end = self.end
        cutfps = self.cutfps
        outfilename = self.outfilename
        size = self.size
        fps = self.fps

        video = ffmpeg_reader.FFMPEG_VideoReader(filename)
        if self.inv ==True:
            begin = video.duration
            end = 0
            cutfps = video.fps
            fps = video.fps
            size = video.size
        # print(video)
        writer = ffmpeg_writer.FFMPEG_VideoWriter(outfilename, size, fps)
        step = (end - begin) / abs(begin - end) / cutfps
        iter = begin
        current_percent = 0
        time1 = time.time()

        while abs(iter - end) > abs(step):
            self.mutex_process.lock()  #request for mutex,if the pause function called, the 'while' loop can not get the mutex and block the thread
            if(self.cancel):
                self.mutex_process.unlock()
                self.sg_cancel.emit(outfilename)
                break
            img = video.get_frame(iter)
            writer.write_frame(img)
            iter += step
            new_percent = abs(iter-begin)/abs(begin-end)*100
            if int(new_percent-current_percent)> 0 :
                diff_percent = new_percent-current_percent
                current_percent = new_percent
                time2 = time.time()
                time_str = qt.QTime(0,0,0).addSecs((time2-time1)*(100-current_percent)/(diff_percent)).toString()
                self.sg_update.emit(outfilename,current_percent,time_str)
                time1 = time2
            self.mutex_process.unlock()
        writer.close()
        if self.cancel == False:   #judge the break exit,finish or cancel
           self.sg_finished.emit(outfilename)

    def _pause(self,outfilename):
        if self.pause or outfilename != self.outfilename:
            return
        self.mutex_process.lock()
        self.pause = True

    def _start(self,outfilename):
        if self.pause == False or outfilename != self.outfilename:
            return
        self.mutex_process.unlock()
        self.pause = False

    def _cancel(self,outfilename):
        if self.outfilename != outfilename:
            return
        if self.pause:
            self._start(outfilename)
        self.cancel = True

class VideoCutTool(qt.QObject):
    sg_forceCancel = qt.pyqtSignal(str)
    def __init__(self,parent = qt.QObject()):
        super(VideoCutTool,self).__init__(parent)
        self.label_ViewPort = qt.QLabel()
        self.btn_OpenFile = qt.QPushButton('打开文件')
        self.btn_begin = qt.QPushButton('begin')
        self.btn_end   = qt.QPushButton('end')
        self.btn_cut   = qt.QPushButton('cut')
        self.btn_play = qt.QPushButton('play')
        self.widget_MainWindow = qt.QWidget()

        self.cutMenu = qt.QMenu()
        self.cutMenu.addAction('cutVideo',self._cut)
        self.cutMenu.addAction('cutImage',self._cut_img,qt.QKeySequence('ctrl+c'))
        self.cutMenu.addAction('invVideo',self._inv_video)
        self.btn_cut.setMenu(self.cutMenu)

        self.slider_timeBar = qt.QSlider(qt.Qt.Horizontal)
        self.slider_timeBar.setMinimum(0)
        self.slider_timeBar.setMaximum(1200)
        self.isReaderOpen = False
        self.slider_timeBar.installEventFilter(self)
        self.label_time = qt.QLabel('00:00:00')
        self.layout = qt.QGridLayout()
        self.spinbox_fps = qt.QSpinBox()
        self.spinbox_fps.setMinimum(1)
        self.spinbox_fps.setMaximum(30)
        self.label_cutfps = qt.QLabel('cutfps:')

        self.HBoxLayout = qt.QHBoxLayout()
        self.HBoxLayout.addWidget(self.slider_timeBar)
        self.HBoxLayout.addWidget(self.label_time)
        self.HBoxLayout.addWidget(self.btn_play)
        self.HBoxLayout.addWidget(self.btn_begin)
        self.HBoxLayout.addWidget(self.btn_end)
        self.HBoxLayout.addWidget(self.label_cutfps)
        self.HBoxLayout.addWidget(self.spinbox_fps)
        self.HBoxLayout.addWidget(self.btn_cut)
        self.HBoxLayout.addWidget(self.btn_OpenFile)

        self.btn_begin.installEventFilter(self)
        self.btn_end.installEventFilter(self)
        self.btn_cut.installEventFilter(self)
        self.btn_play.installEventFilter(self)


        self.layout.addWidget(self.label_ViewPort,0,0)
        self.layout.addLayout(self.HBoxLayout,1,0)

        self.widget_MainWindow.setLayout(self.layout)
        self.widget_MainWindow.show()
        self.widget_MainWindow.setWindowTitle('SimpleVideoCutTool')
        self.btn_OpenFile.clicked.connect(self._openfile)

        self.reader = None
        self.time = 0
        self.beginPos = 0
        self.endPos = 0
        self.playState = False
        self.timer = qt.QTimer()
        self.timer.timeout.connect(self._play)

        self.cutDialog = CutDialog()
        self.cutDialog.setMinimumSize(qt.QSize(800,300))
        self.action_showCutDialog = qt.QAction()
        self.action_showCutDialog.setShortcut('ctrl+w')
        self.action_showCutDialog.triggered.connect(self.cutDialog.show)
        self.widget_MainWindow.addAction(self.action_showCutDialog)
        # self.thread_dic = {}
        # self.cutop_dic = {}

        self.screenWidth = qt.QApplication.primaryScreen().availableSize().width()   #获取屏幕尺寸
        self.screenHeight = qt.QApplication.primaryScreen().availableSize().height()

        self.threadPool = ThreadPool() #线程池
        self.taskQueue = []            #耗时任务队列
        self.runningList = {}          #正在运行的任务


    def _updateViewPort(self,img):
        qimage = qt.QImage(img.data, img.shape[1], img.shape[0], qt.QImage.Format_RGB888)
        if img.shape[1] > self.screenWidth*0.7 or img.shape[0] > self.screenHeight*0.8:
            ratio = min(self.screenWidth*0.7/img.shape[1],self.screenHeight*0.8/img.shape[0])
            qimage = qimage.scaled(img.shape[1]*ratio,img.shape[0]*ratio)
        self.label_ViewPort.setPixmap(qt.QPixmap().fromImage(qimage, qt.Qt.AutoColor))

    def _openfile(self):
        filedlg = qt.QFileDialog()
        filedlg.setFileMode(qt.QFileDialog.ExistingFile)
        filedlg.setMimeTypeFilters(['video/mp4','video/mpeg','video/x-flv','video/x-msvideo'])
        if not filedlg.exec():
            return
        strlist = filedlg.selectedFiles()
        if strlist.__len__() == 1:
            if self.isReaderOpen:
                self.reader.close()
            self.reader = ffmpeg_reader.FFMPEG_VideoReader(strlist[0])
            img = self.reader.get_frame(0)
            self._updateViewPort(img)
            self.spinbox_fps.setMaximum(self.reader.fps)
            self.isReaderOpen = True
            self.timer.setInterval(1000/self.reader.fps)
            self.time = 0
            self.slider_timeBar.setValue(0)
            self.label_time.setText('00:00:00')


    #放入剪贴板
    def _cut_img(self):
        if self.isReaderOpen == False:
            return
        self.cutImg = self.reader.get_frame(self.time)
        qimage = qt.QImage(self.cutImg.data, self.cutImg.shape[1], self.cutImg.shape[0], qt.QImage.Format_RGB888)
        qt.QApplication.clipboard().setImage(qimage)

    def createTask(self,str,begin,end,cutfps,size,fps,outfilename,inv):
        cutop = CutOp(str, begin, end, cutfps, size, fps, outfilename,inv)
        self.cutDialog.sg_try_pause.connect(cutop._pause)
        self.cutDialog.sg_try_cancel.connect(cutop._cancel)
        self.cutDialog.sg_try_start.connect(cutop._start)
        self.sg_forceCancel.connect(cutop.sg_cancel)
        cutop.sg_update.connect(self.cutDialog._update)
        cutop.sg_finished.connect(self._onfinish)
        cutop.sg_cancel.connect(self._onfinish)
        return cutop

    def _inv_video(self):
        filedlg = qt.QFileDialog()
        filedlg.setFileMode(qt.QFileDialog.ExistingFiles)
        filedlg.setMimeTypeFilters(['video/mp4', 'video/mpeg', 'video/x-flv', 'video/x-msvideo'])

        if not filedlg.exec():
            return
        selectedFiles = filedlg.selectedFiles()
        filedlg.close()
        filedlg.setFileMode(qt.QFileDialog.DirectoryOnly)
        if not filedlg.exec():
            return

        savepath = filedlg.selectedFiles()[0]
        for str in selectedFiles:
            path,name = os.path.split(str)
            name,sffix = os.path.splitext(name)
            outfilename = savepath+'\\'+name+'inv'+sffix
            if os.path.exists(outfilename):
                continue
            if self.cutDialog._addRow(str, outfilename) == False:
                # print('重复任务')
                qt.QMessageBox(0, 'reapt mission', 'mission:\'' + outfilename + '\'has already existed').exec()
                continue
            cutop = self.createTask(str,0,0,0,0,0,outfilename,inv=True)
            thread = self.threadPool.requireThreads()  #申请线程
            if not thread:
                self.taskQueue.append(cutop)
            else:
                cutop.moveToThread(thread)
                cutop.sg_cancel.connect(thread.quit)
                cutop.sg_finished.connect(thread.quit)
                thread.started.connect(cutop.cutVideo)
                thread.start()
                self.runningList[outfilename] = cutop
                self.cutDialog.show()

    def _cut(self):
        if self.isReaderOpen == False:
            return
        begin = self.beginPos
        end = self.endPos
        size = self.reader.size
        fps = self.reader.fps
        cutfps = self.spinbox_fps.value()
        filename = self.reader.filename
        filedlg = qt.QFileDialog()
        filedlg.setMimeTypeFilters(['video/mp4','video/x-msvideo','video/x-flv'])
        filedlg.setAcceptMode(qt.QFileDialog.AcceptSave)
        if not filedlg.exec():
            return
        outfilename = filedlg.selectedFiles()[0]

        if self.cutDialog._addRow(filename, outfilename) == False:
            # print('重复任务')
            qt.QMessageBox(0,'reapt mission','mission:\''+outfilename+'\'has already existed').exec()
            return
        cutop = self.createTask(filename,begin,end,cutfps,size,fps,outfilename,False)
        thread = self.threadPool.requireThreads()  # 申请线程
        if not thread:
            self.taskQueue.append(cutop)
        else:
            cutop.moveToThread(thread)
            thread.started.connect(cutop.cutVideo)
            thread.start()
            self.runningList[outfilename] = cutop
            self.cutDialog.show()

    def _onfinish(self,outfilename):
        del self.runningList[outfilename]
        self.cutDialog._delRow(outfilename)

        thread = self.threadPool.requireThreads()  # 申请线程
        if thread and self.taskQueue.__len__()>0:
            cutop = self.taskQueue.pop(0)
            cutop.moveToThread(thread)
            cutop.sg_cancel.connect(thread.quit)
            cutop.sg_finished.connect(thread.quit)
            thread.started.connect(cutop.cutVideo)
            thread.start()
            self.runningList[cutop.outfilename] = cutop
            self.cutDialog.show()

    def _forceCancel(self,outfilename):
        self.sg_forceCancel.emit(outfilename)


    def _play(self):
        if self.time >= self.reader.duration:
            self.timer.stop()
            self.time = 0
            self.playState = False
            self.btn_play.setText('play')
            self.slider_timeBar.setValue(0)
            self.label_time.setText('00:00:00')
            img = self.reader.get_frame(0)
            self._updateViewPort(img)
            return
        img = self.reader.get_frame(self.time)
        self.time += 1/self.reader.fps
        self.slider_timeBar.setValue(self.time / self.reader.duration * self.slider_timeBar.maximum())
        self.label_time.setText(qt.QTime(0,0,0).addSecs(self.time).toString())
        self._updateViewPort(img)

    def eventFilter(self, QObject, QEvent):
        if QObject == self.slider_timeBar:
            if QEvent.type() == qt.QEvent.MouseButtonRelease and self.isReaderOpen:
                img = self.reader.get_frame(self.time)
                self._updateViewPort(img)
            elif QEvent.type() == qt.QEvent.MouseMove and qt.QMouseEvent(QEvent).buttons()&qt.Qt.LeftButton:
                self.time = self.reader.duration* self.slider_timeBar.value()\
                        /(self.slider_timeBar.maximum()-self.slider_timeBar.minimum())
                str_time = qt.QTime(0,0,0).addSecs(self.time).toString()
                self.label_time.setText(str_time)

        if QObject == self.btn_begin and self.isReaderOpen:
            if QEvent.type() == qt.QEvent.MouseButtonPress:
                self.beginPos = self.time

        if QObject == self.btn_end:
            if QEvent.type() == qt.QEvent.MouseButtonPress and self.isReaderOpen:
                self.endPos = self.time
        # if QObject == self.btn_cut:
        #     if QEvent.type() == qt.QEvent.MouseButtonPress and self.isReaderOpen:
        #         self._cut()

        if QObject == self.btn_play:
            if QEvent.type() == qt.QEvent.MouseButtonPress and self.isReaderOpen:
                if self.playState == False:
                    self.timer.start()
                    self.playState = True
                    self.btn_play.setText('stop')
                else:
                    self.timer.stop()
                    self.playState = False
                    self.btn_play.setText('play')
        return False

app = qt.QApplication(sys.argv)
tool = VideoCutTool()
sys.exit(app.exec())

