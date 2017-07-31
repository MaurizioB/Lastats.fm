from PyQt5 import QtCore

def firstMon(year):
    date = QtCore.QDate(year, 1, 1)
    return date.addDays(8 - date.dayOfWeek())
#    if date.dayOfWeek() != 1:
#        return date.addDays(8 - date.dayOfWeek())
#    return date

def firstMonOfWeek(year, week):
    date = QtCore.QDate(year, 1, 1).addDays((week - 1) * 7)
    if date.dayOfWeek() == 1:
        return date
    return date.addDays(8 - date.dayOfWeek())

def urlEncode(txt):
    try:
        return txt.replace('%', '%25').replace('/', '%2F').replace('#', '%23')
    except:
        print 'error with NoneType for urlEncode!'
        return ''

def urlDecode(txt):
    return txt.replace('%23', '#').replace('%2F', '/').replace('%25', '%')

def tagReplace(txt):
    try:
        return txt.replace('<', '&lt;').replace('>', '&gt;')
    except:
        print 'error with NoneType for tagReplace!'
        return ''

