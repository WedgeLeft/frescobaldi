# This file is part of the Frescobaldi project, http://www.frescobaldi.org/
#
# Copyright (c) 2008 - 2012 by Wilbert Berendsen
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# See http://www.gnu.org/licenses/ for more information.

"""
Updates a document using convert-ly.
"""

from __future__ import unicode_literals

import textwrap
import os
import subprocess

from PyQt4.QtCore import QSettings, QSize
from PyQt4.QtGui import (
    QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QTabWidget, QTextBrowser, QVBoxLayout)

import app
import util
import qutil
import widgets
import htmldiff
import cursordiff
import lilypondinfo
import documentinfo
import textformats


def convert(mainwindow):
    """Shows the dialog."""
    dlg = Dialog(mainwindow)
    dlg.addAction(mainwindow.actionCollection.help_whatsthis)
    dlg.setLilyPondInfo(lilypondinfo.preferred())
    dlg.setDocument(mainwindow.currentDocument())
    dlg.setModal(True)
    dlg.show()
    dlg.run()
    if dlg.exec_():
        c = mainwindow.textCursor()
        c.select(c.Document)
        text = dlg.convertedText()
        if dlg.copyCheck.isChecked():
            msgs = textwrap.fill(dlg.messages.toPlainText())
            text += '\n\n%{\n' + msgs + '\n%}\n'
        cursordiff.insert_text(c, text)
    dlg.deleteLater()


class Dialog(QDialog):
    def __init__(self, parent=None):
        super(Dialog, self).__init__(parent)
        
        self._info = None
        self._text = ''
        self._convertedtext = ''
        self._encoding = None
        
        self.fromVersionLabel = QLabel()
        self.fromVersion = QLineEdit()
        self.reason = QLabel()
        self.toVersionLabel = QLabel()
        self.toVersion = QLineEdit()
        self.messages = QTextBrowser()
        self.diff = QTextBrowser(lineWrapMode=QTextBrowser.NoWrap)
        self.copyCheck = QCheckBox(checked=
            QSettings().value('convert_ly/copy_messages', True, bool))
        self.tabw = QTabWidget()
        
        self.tabw.addTab(self.messages, '')
        self.tabw.addTab(self.diff, '')
        
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Reset |
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Reset).clicked.connect(self.run)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        top = QHBoxLayout()
        top.addWidget(self.fromVersionLabel)
        top.addWidget(self.fromVersion)
        top.addWidget(self.reason)
        top.addStretch()
        top.addWidget(self.toVersionLabel)
        top.addWidget(self.toVersion)
        
        layout.addLayout(top)
        layout.addWidget(self.tabw)
        layout.addWidget(self.copyCheck)
        layout.addWidget(widgets.Separator())
        layout.addWidget(self.buttons)
        
        app.translateUI(self)
        qutil.saveDialogSize(self, 'convert_ly/dialog/size', QSize(600, 300))
        app.settingsChanged.connect(self.readSettings)
        self.readSettings()
        self.finished.connect(self.saveCopyCheckSetting)
        
    def translateUI(self):
        self.fromVersionLabel.setText(_("From version:"))
        self.toVersionLabel.setText(_("To version:"))
        self.copyCheck.setText(_("Save convert-ly messages in document"))
        self.copyCheck.setToolTip(_(
            "If checked, the messages of convert-ly are appended as a "
            "comment to the end of the document."))
        self.tabw.setTabText(0, _("&Messages"))
        self.tabw.setTabText(1, _("&Changes"))
        self.buttons.button(QDialogButtonBox.Reset).setText(_("Run Again"))
        self.setCaption()
    
    def saveCopyCheckSetting(self):
        QSettings().setValue('convert_ly/copy_messages', self.copyCheck.isChecked())
    
    def readSettings(self):
        font = textformats.formatData('editor').font
        self.diff.setFont(font)
        
    def setCaption(self):
        version = self._info and self._info.versionString() or _("<unknown>")
        title = _("Convert-ly from LilyPond {version}").format(version=version)
        self.setWindowTitle(app.caption(title))

    def setLilyPondInfo(self, info):
        self._info = info
        self.setCaption()
        self.toVersion.setText(info.versionString())
        self.setConvertedText()
    
    def setConvertedText(self, text=''):
        self._convertedtext = text
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(text))
        if text:
            self.diff.setHtml(htmldiff.htmldiff(
                self._text, text,
                _("Current Document"), _("Converted Document"),
                wrapcolumn=100))
        else:
            self.diff.clear()
    
    def convertedText(self):
        return self._convertedtext or ''
    
    def setDocument(self, doc):
        v = documentinfo.info(doc).versionString()
        if v:
            self.fromVersion.setText(v)
            self.reason.setText(_("(set in document)"))
        else:
            self.reason.clear()
        self._text = doc.toPlainText()
        self._encoding = doc.encoding() or 'UTF-8'
        self.setConvertedText()
        
    def run(self):
        """Runs convert-ly (again)."""
        fromVersion = self.fromVersion.text()
        toVersion = self.toVersion.text()
        if not fromVersion or not toVersion:
            self.messages.setPlainText(_(
                "Both 'from' and 'to' versions need to be set."))
            return
        info = self._info
        convert_ly = os.path.join(info.bindir(), info.convert_ly)
        
        # on Windows the convert-ly command is not directly executable, but
        # must be started using the LilyPond-provided Python interpreter
        if os.name == "nt":
            if not os.access(convert_ly, os.R_OK) and not convert_ly.endswith('.py'):
                convert_ly += '.py'
            command = [info.python(), convert_ly]
        else:
            command = [convert_ly]
        command += ['-f', fromVersion, '-t', toVersion, '-']
        
        # if the user wants english messages, do it also here: LANGUAGE=C
        env = None
        if QSettings().value("lilypond_settings/no_translation", False, bool):
            if os.name == "nt":
                # Python 2.7 subprocess on Windows chokes on unicode in env
                env = util.bytes_environ()
                env[b'LANGUAGE'] = b'C'
            else:
                env = dict(os.environ)
                env['LANGUAGE'] = 'C'
        
        with qutil.busyCursor():
            try:
                proc = subprocess.Popen(command,
                    universal_newlines = True,
                    env = env,
                    stdin = subprocess.PIPE,
                    stdout = subprocess.PIPE,
                    stderr = subprocess.PIPE)
                out, err = proc.communicate(self._text.encode(self._encoding))
            except OSError as e:
                self.messages.setPlainText(_(
                    "Could not start {convert_ly}:\n\n"
                    "{message}\n").format(convert_ly = convert_ly, message = e))
                return
            self.messages.setPlainText(err.decode('UTF-8'))
            self.setConvertedText(out.decode('UTF-8'))
            if not out or self._convertedtext == self._text:
                self.messages.append('\n' + _("The document has not been changed."))


