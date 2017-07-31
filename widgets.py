from collections import namedtuple
from funcs import *
from PyQt5 import QtCore, QtGui, QtWidgets

def setBold(item, bold=True):
    font = item.font()
    font.setBold(bold)
    item.setFont(font)

dateRange = namedtuple('dateRange', 'first, last')

class WeekCalendar(QtWidgets.QCalendarWidget):
    weekSelect = QtCore.pyqtSignal(object, object)
    def __init__(self, *args, **kwargs):
        QtWidgets.QCalendarWidget.__init__(self, *args, **kwargs)
        self.table = self.findChild(QtWidgets.QTableView)
        self.table.setMouseTracking(True)
        self.table.installEventFilter(self)
        self.baseFormat = [self.weekdayTextFormat(d) for d in xrange(1, 8)]
        self.selectFormat = QtGui.QTextCharFormat()
        font = self.baseFormat[2].font()
        font.setBold(True)
        self.selectFormat.setFont(font)
        self.currentFirst = self.baseDate = QtCore.QDate(2001, 12, 31)
        self.clicked.connect(self.getWeek)

    def getWeek(self, qdate):
        start_date = qdate.addDays(-qdate.dayOfWeek() + 1)
        end_date = start_date.addDays(7)
        if start_date > self.maximumDate() or end_date < self.minimumDate():
            return
        self.weekSelect.emit(start_date, end_date)

    def eventFilter(self, source, event):
        if source == self.table:
            if event.type() == QtCore.QEvent.MouseMove:
                index = self.table.indexAt(event.pos())
                if index.row() > 0:
                    first_day = int(self.table.model().index(index.row(), 1).data())
                    year = self.yearShown()
                    month = self.monthShown()
                    if index.row() == 1 and first_day > 7:
                        if month == 1:
                            month = 12
                            year -= 1
                        else:
                            month -= 1
                    if index.row() > 4 and first_day < 14:
                        if month == 12:
                            month = 1
                            year += 1
                        else:
                            month += 1
                    self.highlightWeek(QtCore.QDate(year, month, first_day))
                else:
                    self.highlightWeek(None)
#                    self.weekHover.emit(-1, -1)
            elif event.type() == QtCore.QEvent.Leave:
                self.highlightWeek(None)
#                self.weekHover.emit(-1, -1)
        return QtWidgets.QCalendarWidget.eventFilter(self, source, event)

    def highlightWeek(self, first_day):
        if self.currentFirst:
            for d, fmt in enumerate(self.baseFormat):
                date = self.currentFirst.addDays(d)
                self.setDateTextFormat(date, fmt)
        if first_day is None:
            self.currentFirst = None
            return
        for d in xrange(7):
            date = first_day.addDays(d)
            self.setDateTextFormat(date, self.selectFormat)
        self.currentFirst = first_day


class WeekValidator(QtGui.QValidator):
    def __init__(self, *args, **kwargs):
        QtGui.QValidator.__init__(self, *args, **kwargs)
        self.charMatch = QtCore.QRegularExpression('^[\d\/]*$')
        self.partialMatch = QtCore.QRegularExpression('^20[\d]{0,2}\/[\d]{0,2}$|^20[\d]{0,2}$')
        self.fullMatch = QtCore.QRegularExpression('^20\d\d\/[\d]{1,2}$')
        self.setDateRange(QtCore.QDate(2002, 1, 1), QtCore.QDate.currentDate())

    def setDateRange(self, first, last):
        self.dateRange = dateRange(first.addDays(1 - first.dayOfWeek()), last.addDays(8 - last.dayOfWeek() if last.dayOfWeek() != 1 else 0))

    def validate(self, text, pos):
        if not self.charMatch.match(text).hasMatch():
            return self.Invalid, text, pos
        if not self.partialMatch.match(text).hasMatch():
            return self.Invalid, text, pos
        if not self.fullMatch.match(text).hasMatch():
            return self.Intermediate, text, pos
        year, week = map(int, text.split('/'))
        if not self.dateRange.first.year() <= year <= self.dateRange.last.year():
            if year < self.dateRange.first.year():
                year = self.dateRange.first.year()
            else:
                year = self.dateRange.last.year()
            return self.Intermediate, '{}/{}'.format(year, week), pos
        mon = firstMonOfWeek(year, week)
        if not self.dateRange.first <= mon <= self.dateRange.last:
            if mon < self.dateRange.first:
                week, year = self.dateRange.first.weekNumber()
            else:
                week, year = self.dateRange.last.weekNumber()
            return self.Intermediate, text, pos
        return self.Acceptable, text, pos


class WeekSelection(QtWidgets.QComboBox):
    weekSelect = QtCore.pyqtSignal(object, object)
    def __init__(self, *args, **kwargs):
        QtWidgets.QComboBox.__init__(self, *args, **kwargs)
        self.weekCalendar = WeekCalendar(self)
        self.weekCalendar.setWindowFlags(QtCore.Qt.Popup)
        self.weekCalendar.weekSelect.connect(self.selectWeek)
        weekItems = ['{}/{}'.format(y, w) for y in xrange(2002, QtCore.QDate.currentDate().year() + 1) for w in xrange(1, 53)]
        self.addItems(weekItems)
        self.activated.connect(self.activepress)
        self.setEditable(True)
        self.weekValidator = WeekValidator(self)
        self.lineEdit().setValidator(self.weekValidator)
        self.dateRange = dateRange(QtCore.QDate(2002, 1, 1), QtCore.QDate.currentDate())

    def wheelEvent(self, event):
        event.accept()
        try:
            year, week = map(int, self.currentText().split('/'))
        except:
            return
        if event.angleDelta().y() > 0:
            week += 1
            if week == 53 and QtCore.QDate(year, 12, 28).weekNumber()[0] != 53:
                year += 1
                week = 1
            elif week > 53:
                year += 1
                week = 1
        else:
            week -= 1
            if week == 0:
                week, _ = QtCore.QDate(year - 1, 12, 28).weekNumber()
                year -= 1
        start_date = firstMonOfWeek(year, week)
        end_date = start_date.addDays(7)
        if start_date <= self.dateRange.last and end_date >= self.dateRange.first:
            self.setCurrentText('{}/{}'.format(year, week))
            self.setToolTip('Week from {} to {}'.format(start_date.toString('dd MMMM yyyy'), end_date.addDays(-1).toString('dd MMMM yyyy')))
            self.weekSelect.emit(start_date, start_date.addDays(7))

    def selectWeek(self, start_date, end_date):
        self.weekCalendar.hide()
        self.setCurrentText('{1}/{0}'.format(*start_date.weekNumber()))
        self.weekSelect.emit(start_date, end_date)

    def activepress(self, *args):
        text = self.currentText()
        if self.weekValidator.validate(text, len(text))[0] == self.weekValidator.Acceptable:
            year, week = map(int, text.split('/'))
            start_date = firstMonOfWeek(year, week)
            self.weekSelect.emit(start_date, start_date.addDays(7))

    def setDateRange(self, first, last):
        self.dateRange = dateRange(first, last)
        self.weekCalendar.setDateRange(first, last)
        self.weekValidator.setDateRange(first, last)
        self.setCurrentText('{1}/{0}'.format(*first.weekNumber()))


    def showPopup(self):
        self.blockSignals(True)
        self.weekCalendar.show()
        self.blockSignals(False)
        screen = QtWidgets.QApplication.desktop().availableGeometry()
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        if pos.x() + self.weekCalendar.width() > screen.x() + screen.width():
            pos.setX(screen.x() + screen.width() - self.weekCalendar.width())
        if pos.y() + self.weekCalendar.height() > screen.y() + screen.height():
            pos.setY(pos.y() - self.height() - self.weekCalendar.height())
        self.weekCalendar.move(pos)

    def hidePopup(self):
        self.weekCalendar.hide()


class BrowserTooltip(QtWidgets.QLabel):
    def __init__(self, *args, **kwargs):
        QtWidgets.QLabel.__init__(self, *args, **kwargs)
        self.setAutoFillBackground(True)
        self.setVisible(False)

    def setText(self, text):
        QtWidgets.QLabel.setText(self, text)
        self.setMinimumWidth(self.fontMetrics().width(text))
        self.setMaximumWidth(self.minimumWidth())


class TextBrowser(QtWidgets.QTextBrowser):
    def __init__(self, *args, **kwargs):
        QtWidgets.QTextBrowser.__init__(self, *args, **kwargs)
        self.label = BrowserTooltip(self)
        self.label.move(self.frameWidth(), self.height() - self.label.height() - self.frameWidth())

    def mouseMoveEvent(self, event):
        anchor = self.anchorAt(event.pos())
        if anchor and not anchor.startswith('#'):
            if anchor.startswith('http'):
                anchor = 'Open in browser: {}'.format(anchor)
            self.label.setText(anchor)
            if not self.label.isVisible():
                self.label.move(self.frameWidth(), self.height() - self.label.height() - self.frameWidth())
                self.label.setVisible(True)
        else:
            self.label.setVisible(False)
        QtWidgets.QTextBrowser.mouseMoveEvent(self, event)

    def resizeEvent(self, event):
        QtWidgets.QTextBrowser.resizeEvent(self, event)
        self.label.move(self.frameWidth(), self.height() - self.label.height() - self.frameWidth())


class HistoryBtn(QtWidgets.QPushButton):
    def __init__(self, *args, **kwargs):
        QtWidgets.QPushButton.__init__(self, *args, **kwargs)
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.showMenu)
        self.menu = QtWidgets.QMenu(self)

    def setHistory(self, history, func, icon):
        self.history = history
        self.historyFunc = func
        self.setIcon(self.style().standardIcon(icon))

    def mousePressEvent(self, event):
        self.timer.start()
        QtWidgets.QPushButton.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        self.timer.stop()
        if self.menu.isVisible():
            self.menu.hide()
            return
        QtWidgets.QPushButton.mouseReleaseEvent(self, event)

    def showMenu(self):
        items = self.historyFunc()
        if not items:
            return
        self.setDown(False)
        self.menu = QtWidgets.QMenu(self)
        for id, title in items:
            item = QtWidgets.QAction(title.replace('&', '&&'), self.menu)
            item.setData(id)
            self.menu.addAction(item)
        res = self.menu.exec_(self.mapToGlobal(QtCore.QPoint(0, self.height())))
        if res:
            self.history.goTo(res.data())


class ShiftSpinBox(QtWidgets.QSpinBox):
    def __init__(self, *args, **kwargs):
        QtWidgets.QSpinBox.__init__(self, *args, **kwargs)

    def wheelEvent(self, event):
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            step = 1000
        else:
            step = 100
        if event.angleDelta().y() > 1:
            self.setValue(self.value() + step)
        else:
            self.setValue(self.value() - step)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_PageUp, QtCore.Qt.Key_PageDown):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                step = 1000
            else:
                step = 100
            if event.key() == QtCore.Qt.Key_PageUp:
                self.setValue(self.value() + step)
            else:
                self.setValue(self.value() - step)
        else:
            QtWidgets.QSpinBox.keyPressEvent(self, event)


class TopLists(QtWidgets.QTextBrowser):
    def __init__(self, *args, **kwargs):
        QtWidgets.QTextBrowser.__init__(self, *args, **kwargs)
        self.label = BrowserTooltip(self)
        self.label.move(self.frameWidth(), self.height() - self.label.height() - self.frameWidth())

        self.document().setDefaultStyleSheet(
            '''
            a {
                text-decoration: none;
                color: #811;
                }
            ul li {
                margin-left: <indent>px;
                color: darkGray;
                }
            '''.replace('<indent>', '{}'.format(20 - self.document().indentWidth()))
            )

    def setStats(self, tracks_dict, artists_dict, albums_dict):
        html = '<h2>Top tracks</h2><ul>'
        top_tracks = sorted(tracks_dict.items(), key=lambda (k, v): v, reverse=True)
        for track, count in top_tracks[:10]:
            html += u'<li><a href="lastfm://track/{_artist}/{_album}/{_title}">{artist} - {title}</a> ({count})</li>'.format(
                _artist=urlEncode(track.artist.name), 
                artist=tagReplace(track.artist.name), 
                _album='_', 
                _title=urlEncode(track.title),
                title=tagReplace(track.title), 
                count=count, 
                )
        html += '</ul><h2>Top artists</h2><ul>'
        top_artists = sorted(artists_dict.items(), key=lambda (k, v): v, reverse=True)
        for artist, count in top_artists[:10]:
            html += u'<li><a href="lastfm://artist/{_artist}">{artist}</a> ({count})</li>'.format(
                _artist=urlEncode(artist.name), 
                artist=tagReplace(artist.name), 
                count=count
                )
        html += '</ul><h2>Top albums</h2><ul>'
        top_albums = sorted(albums_dict.items(), key=lambda (k, v): v,  reverse=True)
        for (artist, album), count in top_albums[:10]:
            html += u'<li><a href="lastfm://album/{_artist}/{_title}">{artist} - {title}</a> ({count})</li>'.format(
                _artist=urlEncode(artist.name), 
                artist=tagReplace(artist.name), 
                _title = urlEncode(album), 
                title=tagReplace(album), 
                count=count
                )
        html += '</ul>'
        self.setHtml(html)

    def mouseMoveEvent(self, event):
        anchor = self.anchorAt(event.pos())
        if anchor and not anchor.startswith('#'):
            if anchor.startswith('http'):
                anchor = 'Open in browser: {}'.format(anchor)
            self.label.setText(anchor)
            if not self.label.isVisible():
                self.label.move(self.frameWidth(), self.visibleRegion().boundingRect().height() - self.label.height() + self.visibleRegion().boundingRect().y())
                self.label.setVisible(True)
        else:
            self.label.setVisible(False)
        QtWidgets.QTextBrowser.mouseMoveEvent(self, event)

    def resetSize(self):
        height = self.document().size().height() + self.fontMetrics().height()
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)

    def resizeEvent(self, event):
        QtWidgets.QTextBrowser.resizeEvent(self, event)
        self.resetSize()
        self.label.move(self.frameWidth(), self.visibleRegion().boundingRect().height() - self.label.height() + self.visibleRegion().boundingRect().y())


class YearPlays(QtWidgets.QWidget):
    grad = QtGui.QLinearGradient()
    grad.setCoordinateMode(grad.StretchToDeviceMode)
    grad.setColorAt(0, QtGui.QColor(255, 55, 55, 128))
    grad.setColorAt(1, QtGui.QColor(QtCore.Qt.red))
    grad.setStart(0, 0)
    grad.setFinalStop(1, 0)
    brush = QtGui.QBrush(grad)
    yearpen = QtGui.QColor(QtCore.Qt.lightGray)
    yearpenHighlight = QtGui.QColor(QtCore.Qt.red)
    textpen = QtGui.QColor(QtCore.Qt.black)
    countpen = QtGui.QPen(QtCore.Qt.darkGray)
    countpen.setStyle(QtCore.Qt.DotLine)

    yearSelect = QtCore.pyqtSignal(int)

    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self._expanded = False
        self.track_years = {}
        self.widths = {}
        self.max_count = 1
        self.count_units = .1
        self.text_font = self.font()
        self.text_font.setPointSize(12)
        self.sorted_years = []
        self.metrics = QtGui.QFontMetrics(self.text_font)
        self.width_delta = self.metrics.width('8888')
#        self.year_height = self.metrics.height() * self.expansion
        self.month_height = self.metrics.height() * .23
        self.setMinimumHeight(self.year_height + self.metrics.height())
        self.setMaximumHeight(self.year_height + self.metrics.height())
        self.paintFont = self.font()
        self.paintFont.setUnderline(True)
        self.setMouseTracking(True)
        self.compute()
        self.highlightYear = None

    @property
    def year_height(self):
        return self.metrics.height() * self.expansion

    @property
    def expanded(self):
        return self._expanded

    @expanded.setter
    def expanded(self, state):
        self._expanded = state
        self.setMinimumHeight(len(self.track_years) * self.year_height + self.metrics.height())
        self.setMaximumHeight(self.minimumHeight())
        self.update()

    @property
    def expansion(self):
        return 3 if self.expanded else 1.5

    def reset(self):
        self.setYears({})

    def setYears(self, track_years):
        self.track_years = {}
        self.track_months = {}
        self.month_widths = {}
        self.max_count = 1
        for year, months in track_years.items():
            self.track_months[year] = months
            self.track_years[year] = sum(months)
        self.setMinimumHeight(len(track_years) * self.metrics.height() * self.expansion + self.metrics.height())
        self.setMaximumHeight(self.minimumHeight())
        self.widths = {}
        self.sorted_years = sorted(self.track_years.keys())
        self.compute()

    def compute(self):
        if not self.track_years:
            return
        self.max_count = max(self.track_years.values())
        if self.max_count == 0: self.max_count = 1
        width = self.width() - 2 - self.width_delta
        for year in sorted(self.track_years.keys()):
            year_width = self.track_years[year] * width / self.max_count
            self.widths[year] = year_width
            month_widths = []
            max_width = year_width - 3
            max_month = max(self.track_months[year])
            if max_month == 0: max_month = 1
            for month in self.track_months[year]:
                month_widths.append(month * max_width / max_month)
            self.month_widths[year] = month_widths
        self.count_units = float(max(self.widths.values())) / self.max_count
        self.update()

    def event(self, event):
        if event.type() == QtCore.QEvent.ToolTip and self.track_years:
            x = event.pos().x()
            if x < self.width_delta:
                event.ignore()
                return True
            year_id = int(event.pos().y() / self.year_height)
            if year_id >= len(self.track_years):
                event.ignore()
                return True
            rect = QtCore.QRect(self.width_delta, year_id, self.width() - self.width_delta, self.year_height)
            year = sorted(self.track_years.keys())[year_id]
            text = u'Scrobbles for year {}: <b>{}</b><br/><table border="0">'.format(year, self.track_years[year])
            locale = QtCore.QLocale()
            for month in xrange(12):
                count = self.track_months[year][month]
                if count == 0: continue
                text += u'<tr><td>{}:</td><td>{}</td></tr>'.format(locale.standaloneMonthName(month + 1), count)
            text += '</table>'
            QtWidgets.QToolTip.showText(event.globalPos(), text, self, rect)
            return True
            
        return QtWidgets.QWidget.event(self, event)

    def mouseMoveEvent(self, event):
        if event.pos().x() > self.width_delta:
            self.setCursor(QtCore.Qt.ArrowCursor)
            self.highlightYear = None
            self.update()
            return
        year_id = int(event.pos().y() / self.year_height)
        if not 0 <= year_id < len(self.sorted_years):
            self.setCursor(QtCore.Qt.ArrowCursor)
            self.highlightYear = None
            self.update()
            return
        self.highlightYear = self.sorted_years[year_id]
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.update()

    def mousePressEvent(self, event):
        if self.highlightYear and event.button() == QtCore.Qt.LeftButton:
            self.yearSelect.emit(self.highlightYear)

    def leaveEvent(self, event):
        self.highlightYear = None
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    def paintEvent(self, event):
        qp = QtGui.QPainter()
        qp.begin(self)
        qp.setRenderHint(qp.Antialiasing)

        height_delta = self.metrics.height() * self.expansion
        height = height_delta - 2
        qp.save()
        qp.translate(.5, .5 - height_delta)
        qp.setBrush(self.brush)
        qp.setFont(self.paintFont)
        for year in sorted(self.track_years.keys()):
            qp.translate(0, height_delta)
            qp.setPen(self.yearpenHighlight if year == self.highlightYear else self.textpen)
            qp.drawText(2, 0, self.width_delta, height_delta, QtCore.Qt.AlignCenter, str(year))
            qp.setPen(self.yearpen)
            qp.drawRect(self.width_delta, 1, self.widths[year], height)
            if self.expanded:
                qp.save()
                qp.setPen(self.textpen)
                qp.translate(self.width_delta + 1, self.month_height)
                for m, month_width in enumerate(self.month_widths[year]):
                    qp.drawLine(0, m * self.month_height, month_width, m * self.month_height)
                qp.restore()

        qp.restore()
        if self.max_count > 100:
            if self.max_count <= 1000:
                div = 200
            elif self.max_count <= 2500:
                div = 500
            elif self.max_count <= 5000:
                div = 1000
            elif self.max_count <= 10000:
                div = 2000
            else:
                div = 5000
            lines = self.max_count / div
            qp.setPen(self.countpen)
            for l in xrange(lines):
                x = self.width_delta + self.count_units * div * (l + 1)
                qp.drawLine(x, 0, x, self.height() - self.metrics.height())
                qp.drawText(0, 0, x, self.height(), QtCore.Qt.AlignRight|QtCore.Qt.AlignBottom, str(div * (l + 1)))

        qp.end

    def resizeEvent(self, event):
        self.compute()


class WeekPlays(QtWidgets.QWidget):
    grad = QtGui.QLinearGradient()
    grad.setCoordinateMode(grad.StretchToDeviceMode)
    grad.setColorAt(0, QtGui.QColor(255, 55, 55, 128))
    grad.setColorAt(1, QtGui.QColor(QtCore.Qt.red))
    grad.setStart(0, 0)
    grad.setFinalStop(1, 0)
    brush = QtGui.QBrush(grad)
    pen = QtGui.QColor(QtCore.Qt.lightGray)
    textpen = QtGui.QColor(QtCore.Qt.black)
    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.track_days = {d:0 for d in xrange(1, 8)}
        self.max_count = 1
        self.widths = {}
        self.dayHeight = max(self.fontMetrics().height(), 18)
        self.setMinimumHeight(self.dayHeight * 7)
        self.days = tuple(QtCore.QDate.shortDayName(d, QtCore.QDate.StandaloneFormat).title() for d in xrange(1, 8))
        self.width_delta = max(self.fontMetrics().width(d) for d in self.days) + 4
        self.compute()

    def setDays(self, track_days):
        self.track_days = track_days
        self.compute()

    def compute(self):
        self.max_count = max(self.track_days.values())
        if self.max_count == 0: self.max_count = 1
        width = self.width() - 2 - self.width_delta
        for day in sorted(self.track_days.keys()):
            day_width = self.track_days[day] * width / self.max_count
            self.widths[day - 1] = day_width
        self.update()

    def event(self, event):
        if event.type() == QtCore.QEvent.ToolTip and self.track_days:
            if not any(self.track_days.values()):
                event.ignore()
                return True
            x = event.pos().x()
            if x < self.width_delta:
                event.ignore()
                return True
            day = int(event.pos().y() / self.dayHeight)
            if day >= len(self.track_days):
                event.ignore()
                return True
            rect = QtCore.QRect(self.width_delta, day, self.width() - self.width_delta, self.dayHeight)
            text = u'Scrobbles for {}:<br/><b>{}</b>'.format(QtCore.QDate.longDayName(day + 1).title(), self.track_days[day + 1])
            QtWidgets.QToolTip.showText(event.globalPos(), text, self, rect)
            return True
            
        return QtWidgets.QWidget.event(self, event)

    def paintEvent(self, event):
        qp = QtGui.QPainter()
        qp.begin(self)
        qp.setRenderHint(qp.Antialiasing)
        qp.setBrush(self.brush)
#        qp.setFont(self.paintFont)
        qp.translate(.5, .5 - self.dayHeight)
        height = self.dayHeight - 2
        for day in xrange(7):
            qp.translate(0, self.dayHeight)
            qp.setPen(self.textpen)
            qp.drawText(2, 0, self.width_delta, self.dayHeight, QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter, str(self.days[day]))
            qp.setPen(self.pen)
            qp.drawRect(self.width_delta, 1, self.widths[day], height)

    def resizeEvent(self, event):
        self.compute()


class TimePlays(QtWidgets.QWidget):
    grad = QtGui.QLinearGradient()
    grad.setCoordinateMode(grad.StretchToDeviceMode)
    grad.setColorAt(0, QtGui.QColor(255, 55, 55, 128))
    grad.setColorAt(1, QtCore.Qt.red)
    grad.setStart(0, 1)
    grad.setFinalStop(0, 0)
    brush = QtGui.QBrush(grad)
    pen = QtGui.QColor(QtCore.Qt.lightGray)
    textpen = QtGui.QColor(QtCore.Qt.black)
    def __init__(self, *args, **kwargs):
        QtWidgets.QWidget.__init__(self, *args, **kwargs)
        self.track_times = {x:0 for x in xrange(24)}
        self.heights = self.track_times.copy()
        self.text_font = self.font()
        self.text_font.setPointSize(12)
        self.metrics = QtGui.QFontMetrics(self.text_font)
        self.max_hour_width = max(self.metrics.width(str(x)) for x in xrange(10, 24))
        self.compute()

    def reset(self):
        self.setTimes({x:0 for x in xrange(24)})

    def setTimes(self, track_times):
        self.track_times = track_times
        self.compute()

    def compute(self):
        self.col_width = self.width() / 24.
        max_count = max(self.track_times.values())
        if max_count == 0: max_count = 1
        height = self.height() - 2 - self.metrics.height()
        for col in xrange(24):
            self.heights[col] = self.track_times[col] * height / max_count
        self.update()

    def event(self, event):
        if event.type() == QtCore.QEvent.ToolTip and self.track_times:
            if not any(self.track_times.values()):
                event.ignore()
                return True
            y = event.pos().y()
            if y > self.height() - self.metrics.height():
                event.ignore()
                return True
            hour = int(event.pos().x() / self.col_width)
            if hour >= len(self.track_times):
                event.ignore()
                return True
            rect = QtCore.QRect(hour * self.col_width, 0, self.col_width, self.height() - self.metrics.height())
            last = hour + 1
            if last == 24: last = 0
            text = u'Scrobbles from {:02}:00 to {:02}:00:<br/><b>{}</b>'.format(hour, last, self.track_times[hour])
            QtWidgets.QToolTip.showText(event.globalPos(), text, self, rect)
            return True
            
        return QtWidgets.QWidget.event(self, event)

    def paintEvent(self, event):
        qp = QtGui.QPainter()
        qp.begin(self)
        qp.setRenderHint(qp.Antialiasing)
        qp.translate(.5 - self.col_width, .5)
        qp.setBrush(self.brush)
        bottom = self.height() - 2
        metrics_height = self.metrics.height()
        text_top = bottom - metrics_height
        text_delta = self.col_width * 2
        if self.max_hour_width > self.col_width:
            if self.max_hour_width > self.col_width * 2:
                span = 3
            else:
                span = 2
        else:
            span = 1
        for hour in xrange(24):
            qp.translate(self.col_width, 0)
            qp.setPen(self.pen)
            qp.drawRect(0, text_top, self.col_width, -self.heights[hour])
            qp.setPen(self.textpen)
            if hour == 0: continue
            if hour % span: continue
            qp.drawText(-self.col_width, text_top, text_delta, metrics_height, QtCore.Qt.AlignHCenter, '{}'.format(hour))
        qp.end()

    def resizeEvent(self, event):
        self.compute()






