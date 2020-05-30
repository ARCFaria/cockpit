#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.


# This module creates the primary window.  This window houses widgets
# to control the most important hardware elements.  It is only
# responsible for setting up the user interface; it assume that the
# devices have already been initialized.

import json
import os.path
import pkg_resources

import wx
import wx.adv

import cockpit.gui
import cockpit.gui.fileViewerWindow

from cockpit import depot
from .dialogs.experiment import multiSiteExperiment
from .dialogs.experiment import singleSiteExperiment
from cockpit import events
import cockpit.experiment.experiment
from . import fileViewerWindow
import cockpit.interfaces.imager
from . import joystick
from . import keyboard
import cockpit.util.files
import cockpit.util.userConfig
from . import viewFileDropTarget
from cockpit.gui import mainPanels


ROW_SPACER = 12
COL_SPACER = 8


class MainWindowPanel(wx.Panel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Find out what devices we have to work with.
        lightToggles = depot.getHandlersOfType(depot.LIGHT_TOGGLE)

        ## Maps LightSource handlers to their associated panels of controls.
        self.lightToPanel = dict()

        # Construct the UI.
        # Sizer for all controls. We'll split them into bottom half (light
        # sources) and top half (everything else).
        self.Sizer = wx.BoxSizer(wx.VERTICAL)

        # Panel for holding the non-lightsource controls.
        topPanel = wx.Panel(self)
        self.topPanel=topPanel
        topSizer = wx.BoxSizer(wx.VERTICAL)


        # A row of buttons for various actions we know we can take.
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        # Abort button
        abortButton = wx.Button(topPanel, wx.ID_ANY, "abort")
        abortButton.SetLabelMarkup("<span foreground='red'><big><b>ABORT</b></big></span>")
        abortButton.Bind(wx.EVT_BUTTON, lambda event: events.publish(events.USER_ABORT))
        buttonSizer.Add(abortButton, 1, wx.EXPAND)
        # Experiment & review buttons
        for lbl, fn in ( ("Single-site\nexperiment", lambda evt: singleSiteExperiment.showDialog(self) ),
                         ("Multi-site\nexperiment", lambda evt: multiSiteExperiment.showDialog(self) ),
                         ("View last\nfile", self.onViewLastFile) ):
            btn = wx.Button(topPanel, wx.ID_ANY, lbl)
            btn.Bind(wx.EVT_BUTTON, fn)
            buttonSizer.Add(btn, 1, wx.EXPAND)
        # Video mode button
        videoButton = wx.ToggleButton(topPanel, wx.ID_ANY, "Live")
        videoButton.Bind(wx.EVT_TOGGLEBUTTON, lambda evt: cockpit.interfaces.imager.videoMode())
        events.subscribe(cockpit.events.VIDEO_MODE_TOGGLE, lambda state: videoButton.SetValue(state))
        buttonSizer.Add(videoButton, 1, wx.EXPAND)

        # Snap image button
        snapButton = wx.Button(topPanel, wx.ID_ANY, "Snap\nimage")
        snapButton.Bind(wx.EVT_BUTTON, lambda evt: cockpit.interfaces.imager.imager.takeImage())
        buttonSizer.Add(snapButton, 1, wx.EXPAND)
        # Increase font size in top row buttons.
        for w in [child.GetWindow() for child in buttonSizer.Children]:
            w.SetFont(w.GetFont().Larger())
        topSizer.Add(buttonSizer)
        topSizer.AddSpacer(ROW_SPACER)

        # Make UIs for any other handlers / devices and insert them into
        # our window, if possible.
        # Light power things will be handled later.
        lightPowerThings = depot.getHandlersOfType(depot.LIGHT_POWER)
        lightPowerThings.sort(key = lambda l: l.wavelength)
        # Camera UIs are drawn separately. Currently, they are drawn first,
        # but this separation may make it easier to implement cameras in
        # ordered slots, giving the user control over exposure order.
        cameraThings = depot.getHandlersOfType(depot.CAMERA)
        # Ignore anything that is handled specially.
        ignoreThings = lightToggles + lightPowerThings
        ignoreThings += cameraThings
        # Remove ignoreThings from the full list of devices.
        otherThings = list(depot.getAllDevices())
        otherThings.sort(key = lambda d: d.__class__.__name__)
        otherThings.extend(depot.getAllHandlers())
        rowSizer = wx.WrapSizer(wx.HORIZONTAL)

        # Add objective control
        # If only one objective device (usual), add to end of top row,
        # otherwise add to start of 2nd row.
        hs = depot.getHandlersOfType(depot.OBJECTIVE)
        if len(hs) == 1:
            buttonSizer.Add(mainPanels.ObjectiveControls(self.topPanel), flag=wx.LEFT, border=2)
        else:
            rowSizer.Add(mainPanels.ObjectiveControls(self.topPanel), flag=wx.EXPAND)
            rowSizer.AddSpacer(COL_SPACER)
        ignoreThings.extend(hs)

        # Make the UI elements for the cameras.
        rowSizer.Add(mainPanels.CameraControlsPanel(self.topPanel), flag=wx.EXPAND)
        rowSizer.AddSpacer(COL_SPACER)

        # Add light controls.
        lightfilters = sorted(depot.getHandlersOfType(depot.LIGHT_FILTER))
        ignoreThings.extend(lightfilters)

        # Add filterwheel controls.
        rowSizer.Add(mainPanels.FilterControls(self.topPanel), flag=wx.EXPAND)

        # Make the UI elements for eveything else.
        for thing in ignoreThings:
            if thing in otherThings:
                otherThings.remove(thing)
        for thing in sorted(otherThings):
            if depot.getHandler(thing, depot.CAMERA):
                # Camera UIs already drawn.
                continue
            item = thing.makeUI(topPanel)
            if item is not None:
                itemsizer = wx.BoxSizer(wx.VERTICAL)
                itemsizer.Add(cockpit.gui.mainPanels.PanelLabel(topPanel, thing.name))
                itemsizer.Add(item, 1, wx.EXPAND)
                if rowSizer.GetChildren():
                    # Add a spacer.
                    rowSizer.AddSpacer(COL_SPACER)
                rowSizer.Add(itemsizer, flag=wx.EXPAND)

        topSizer.Add(rowSizer)
        topPanel.SetSizerAndFit(topSizer)

        self.Sizer.Add(topPanel, flag=wx.EXPAND)
        self.Sizer.AddSpacer(ROW_SPACER)

        ## Panel for holding light sources.
        self.Sizer.Add(mainPanels.LightControlsPanel(self), flag=wx.EXPAND)

        keyboard.setKeyboardHandlers(self)
        self.joystick = joystick.Joystick(self)

        self.SetDropTarget(viewFileDropTarget.ViewFileDropTarget(self))

        # Show the list of windows on right-click.
        self.Bind(wx.EVT_CONTEXT_MENU, lambda event: keyboard.martialWindows(self))


    ## User clicked the "view last file" button; open the last experiment's
    # file in an image viewer. A bit tricky when there's multiple files
    # generated due to the splitting logic. We just view the first one in
    # that case.
    def onViewLastFile(self, event = None):
        filenames = cockpit.experiment.experiment.getLastFilenames()
        if filenames:
            window = fileViewerWindow.FileViewer(filenames[0], self)
            if len(filenames) > 1:
                print ("Opening first of %d files. Others can be viewed by dragging them from the filesystem onto the main window of the Cockpit." % len(filenames))


class MainWindow(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title="Cockpit")
        panel = MainWindowPanel(self)

        menu_bar = wx.MenuBar()

        file_menu = wx.Menu()
        menu_item = file_menu.Append(wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnOpen, menu_item)
        menu_item = file_menu.Append(wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.OnClose, menu_item)
        menu_bar.Append(file_menu, '&File')

        # TODO: this should probably go into a separate class so we
        # can have multiple views and controls on the list of
        # available channels (see issue #597).
        self._channels = {}
        exposure_menu = wx.Menu()
        self.Bind(wx.EVT_MENU, self.OnAddChannel,
                  exposure_menu.Append(wx.ID_ANY, item='Add channel…'))
        self.Bind(wx.EVT_MENU, self.OnRemoveChannel,
                  exposure_menu.Append(wx.ID_ANY, item='Remove channel…'))
        self.Bind(wx.EVT_MENU, self.OnExportChannels,
                  exposure_menu.Append(wx.ID_ANY, item='Export channels…'))
        self.Bind(wx.EVT_MENU, self.OnImportChannels,
                  exposure_menu.Append(wx.ID_ANY, item='Import channels…'))
        exposure_menu.AppendSeparator()
        menu_bar.Append(exposure_menu, '&Channels')

        help_menu = wx.Menu()
        menu_item = help_menu.Append(wx.ID_ANY, item='Online repository')
        self.Bind(wx.EVT_MENU,
                  lambda evt: wx.LaunchDefaultBrowser('https://github.com/MicronOxford/cockpit/'),
                  menu_item)
        menu_item = help_menu.Append(wx.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self._OnAbout, menu_item)
        menu_bar.Append(help_menu, '&Help')

        self.SetMenuBar(menu_bar)

        self.SetStatusBar(StatusLights(parent=self))

        sizer = wx.BoxSizer()
        sizer.Add(panel)
        self.SetSizerAndFit(sizer)

        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # Because mainPanels.PanelLabel uses a font larger than the
        # default, we need to recompute the Frame size at show time.
        # Workaround for https://trac.wxwidgets.org/ticket/16088
        if 'gtk3' in wx.PlatformInfo:
            self.Bind(wx.EVT_SHOW, self.OnShow)


    def OnShow(self, event: wx.ShowEvent) -> None:
        self.Fit()
        event.Skip()

    def OnOpen(self, event: wx.CommandEvent) -> None:
        filepath = wx.LoadFileSelector('Select file to open', '', parent=self)
        if not filepath:
            return
        try:
            cockpit.gui.fileViewerWindow.FileViewer(filepath, parent=self)
        except Exception as ex:
            cockpit.gui.ExceptionBox('Failed to open \'%s\'' % filepath,
                                     parent=self)


    ## Do any necessary program-shutdown events here instead of in the App's
    # OnExit, since in that function all of the WX objects have been destroyed
    # already.
    def OnClose(self, event):
        events.publish('program exit')
        event.Skip()


    def OnAddChannel(self, event: wx.CommandEvent) -> None:
        """Add current channel configuration to list."""
        name = wx.GetTextFromUser('Enter name for new channel:',
                                  caption='Add new channel',
                                  parent=self)
        if not name:
            return
        new_channel = {}
        events.publish('save exposure settings', new_channel)

        if name not in self._channels:
            menu = event.GetEventObject()
            self.Bind(wx.EVT_MENU, self.OnApplyChannel,
                      menu.Append(wx.ID_ANY, item=name))
        else:
            answer = wx.MessageBox('There is already a channel named "%s".'
                                   ' Replace it?' % name,
                                   caption='Channel already exists',
                                   parent=self, style=wx.YES_NO)
            if answer != wx.YES:
                return

        self._channels[name] = new_channel


    def OnRemoveChannel(self, event: wx.CommandEvent) -> None:
        """Remove one channel."""
        if not self._channels:
            wx.MessageBox('There are no channels to be removed.',
                          caption='Failed to remove channel',
                          parent=self, style=wx.OK)
            return

        name = wx.GetSingleChoice('Choose channel to be removed:',
                                  caption='Remove a channel',
                                  aChoices=list(self._channels.keys()),
                                  parent=self)
        if not name:
            return

        menu = event.GetEventObject()
        menu.DestroyItem(menu.FindItemById(menu.FindItem(name)))
        self._channels.pop(name)


    def OnExportChannels(self, event: wx.CommandEvent) -> None:
        """Save all channels to a file."""
        filepath = wx.SaveFileSelector('Select file to export', '', parent=self)
        if not filepath:
            return
        try:
            with open(filepath, 'w') as fh:
                json.dump(self._channels, fh)
        except:
            cockpit.gui.ExceptionBox('Failed to write to \'%s\'' % filepath,
                                     parent=self)


    def OnImportChannels(self, event: wx.CommandEvent) -> None:
        """Add all channels in a file."""
        filepath = wx.LoadFileSelector('Select file to import', '', parent=self)
        if not filepath:
            return
        try:
            with open(filepath, 'r') as fh:
                new_channels = json.load(fh)
        except:
            cockpit.gui.ExceptionBox('Failed to read to \'%s\'' % filepath,
                                     parent=self)
        duplicated = [n for n in new_channels.keys() if n in self._channels]
        if duplicated:
            answer = wx.MessageBox('The import will overwrite the following'
                                   ' channels: %s. Do you want to continue?'
                                   % ', '.join(duplicated),
                                   caption='Duplicated channels on loaded file',
                                   parent=self, style=wx.YES_NO)
            if answer != wx.YES:
                return

        menu = event.GetEventObject()
        for name, channel in new_channels.items():
            # Duplicated channels only need to update our dict but new
            # channels also need a new menu item.
            if name not in duplicated:
                self.Bind(wx.EVT_MENU, self.OnApplyChannel,
                          menu.Append(wx.ID_ANY, item=name))
            self._channels[name] = channel


    def OnApplyChannel(self, event: wx.CommandEvent) -> None:
        name = event.GetEventObject().FindItemById(event.GetId()).GetLabel()
        channel = self._channels[name]
        events.publish('load exposure settings', channel)


    def _OnAbout(self, event):
        wx.adv.AboutBox(CockpitAboutInfo(), parent=self)


class StatusLights(wx.StatusBar):
    """A window status bar with the Cockpit status lights.

    The status bar can have any number of status light, each status
    light being a separate field.  New lights are created on the fly
    as required by publishing `UPDATE_STATUS_LIGHT` events.  The same
    event is used to update its text.
    """
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Maps status light names to the light field/pane index.
        self._nameToField = {} # type: typing.Dict[str, int]
        self._defaultBackgroundColour = self.GetBackgroundColour()
        self._notificationColour = wx.YELLOW

        listener = cockpit.gui.EvtEmitter(self, events.UPDATE_STATUS_LIGHT)
        listener.Bind(cockpit.gui.EVT_COCKPIT, self._OnNewStatus)

        # Some lights that we know we need.
        events.publish(events.UPDATE_STATUS_LIGHT, 'image count', '')
        events.publish(events.UPDATE_STATUS_LIGHT, 'device waiting', '')


    def _AddNewLight(self, lightName: str) -> None:
        """Append new status light to the status bar."""
        new_field_index = self.GetFieldsCount() # type: int
        if not self._nameToField:
            # If the map is empty, this is the first light.  However,
            # a status bar always has at least one field, so use the
            # existing field if this is the first light.
            assert new_field_index == 1
            new_field_index = 0
        else:
            self.SetFieldsCount(new_field_index +1)
        self.SetStatusStyles([wx.SB_SUNKEN]* (new_field_index +1))
        self._nameToField[lightName] = new_field_index


    def _OnNewStatus(self, event: cockpit.gui.CockpitEvent) -> None:
        """Update text of specified status light."""
        assert len(event.EventData) == 2
        lightName = event.EventData[0] # type: str
        text = event.EventData[1] # type: str
        if lightName not in self._nameToField:
            self._AddNewLight(lightName)
        self.SetStatusText(text, self._nameToField[lightName])

        # This changes the colour of the whole bar, not only the
        # status (see issue #565).
        if any([self.GetStatusText(i) for i in range(self.FieldsCount)]):
            self.SetBackgroundColour(self._notificationColour)
        else:
            self.SetBackgroundColour(self._defaultBackgroundColour)


def CockpitAboutInfo() -> wx.adv.AboutDialogInfo:
    # TODO: we should be reading all of the stuff here from somewhere
    # that is shared with setup.py.  Maybe we need our own metadata
    # class which this function would then convert.
    info = wx.adv.AboutDialogInfo()
    info.SetName('Cockpit')

    info.SetVersion(pkg_resources.get_distribution('cockpit').version)
    info.SetDescription('Hardware agnostic microscope user interface')
    info.SetCopyright('Copyright © 2020\n'
                      '\n'
                      'Cockpit comes with absolutely no warranty.\n'
                      'See the GNU General Public Licence, version 3 or later,'
                      ' for details.')


    # Authors are sorted alphabetically.
    for dev_name in ['Chris Weisiger',
                     'David Miguel Susano Pinto',
                     'Eric Branlund',
                     'Ian Dobbie',
                     'Julio Mateos-Langerak',
                     'Mick Phillips',
                     'Nicholas Hall',]:
        info.AddDeveloper(dev_name)

    # wxWidgets has native and generic implementations for the about
    # dialog.  However, native implementations other than GTK are
    # limited on the info they can include.  If website, custom icon
    # (instead of inherited from the parent), and license are used on
    # platforms other than GTK the generic dialog is used which we
    # want to avoid.
    if wx.Platform == '__WXGTK__':
        info.SetWebSite('https://www.micron.ox.ac.uk/software/cockpit/')

        # We should not have to set this, it should be set later via
        # the AboutBox parent icon.  We don't yet have icons working
        # (issue #388), but remove this when it is.
        info.SetIcon(wx.Icon(os.path.join(cockpit.gui.BITMAPS_PATH,
                                          'cockpit-8bit.ico')))

        info.SetLicence('Cockpit is free software: you can redistribute it'
                        ' and/or modify\nit under the terms of the GNU General'
                        ' Public License as published by\nthe Free Software'
                        ' Foundation, either version 3 of the License, or\n(at'
                        ' your option) any later version\n'
                        '\n'
                        'Cockpit is distributed in the hope that it will be'
                        ' useful,\nbut WITHOUT ANY WARRANTY; without even the'
                        ' implied warranty of\nMERCHANTABILITY or FITNESS FOR A'
                        ' PARTICULAR PURPOSE.  See the\nGNU General Public'
                        ' License for more details.\n'
                        '\n'
                        'You should have received a copy of the GNU General'
                        ' Public License\nalong with Cockpit.  If not, see '
                        ' <http://www.gnu.org/licenses/>.')
    return info


## Create the window.
def makeWindow():
    window = MainWindow()
    window.Show()
    return window
