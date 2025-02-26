import re
import sys
import os
import mimetypes
import traceback
import glob

from System import Array
from System.Collections.Specialized import *
from System.IO import Path, StreamWriter, File, Directory
from System.Text import *
from System.Diagnostics import *
from collections import OrderedDict

# from Deadline.Scripting import *
from Deadline.Scripting import  RepositoryUtils, FrameUtils, ClientUtils, PathUtils, StringUtils

from DeadlineUI.Controls.Scripting.DeadlineScriptDialog import DeadlineScriptDialog

import imp
imp.load_source( 'IntegrationUI', RepositoryUtils.GetRepositoryFilePath( "submission/Integration/Main/IntegrationUI.py", True ) )
import IntegrationUI

########################################################################
## Globals
########################################################################

########################################################################
## UH USD submitter
## V0.2 David Tree - davidtree.co.uk
## Edited by Matt Tillman - pixelninja.design
########################################################################
scriptDialog = None
ProjectManagementOptions = None
settings = None
shotgunPath = None
startup = None
versionID = None
deadlineJobID = None

LoggingMap = OrderedDict({"None":0,
                          "Basic":1,
                          "Enhanced":4,
                          "Godlike":7,
                          "David":9})

def __main__( *args ):
    SubmissionDialog().ShowDialog( False )

def GetSettingsFilename():
    return Path.Combine( GetDeadlineSettingsPath(), "CommandLineSettings.ini" )

def SubmissionDialog():
    global scriptDialog
    global ProjectManagementOptions

    global settings
    global shotgunPath
    global startup
    global versionID
    global deadlineJobID

    scriptDialog = DeadlineScriptDialog()
    scriptDialog.SetTitle( "Submit USD to Deadline" )
    scriptDialog.SetIcon( scriptDialog.GetIcon( 'DraftPlugin' ) )

    scriptDialog.AddGrid()
    #	(	 	self, 	name, 	control, 	value, 	row, 	column, 	tooltip = "", 	expand = True, 	rowSpan = -1, 	colSpan = -1 )

    scriptDialog.AddControlToGrid( "JobOptionsSeparator", "SeparatorControl", "Job Description", 0, 0, colSpan=6 )
    # JOB NAME
    scriptDialog.AddControlToGrid( "NameLabel", "LabelControl", "Job Names", 1, 0, "The name of your job. This is optional, and if left blank, it will default to 'Untitled'.")
    scriptDialog.AddControlToGrid( "NameBox", "TextControl", "Untitled", 1, 1, colSpan=5 )
    # COMMENT Label
    scriptDialog.AddControlToGrid( "CommentLabel", "LabelControl", "Comment", 2, 0, "A simple description of your job. This is optional and can be left blank.", False )
    scriptDialog.AddControlToGrid( "CommentBox", "MultiLineTextControl", "", 2, 1, colSpan=5 )
    #file dialog
    scriptDialog.AddControlToGrid( "InputLabel", "LabelControl", "USD Files", 4, 0, "The USD file you wish to render.", False )
    filesToProcess = scriptDialog.AddSelectionControlToGrid( "USDFilePath", "MultiFileBrowserControl", "", "USD Files (*.usd);;USDA Files (*.usda);;USDC Files(*.usdc);;USDZ Files(*.usdz)", 4, 1, colSpan=5 )
    filesToProcess.ValueModified.connect(FileSelectionChanged)

    # Renderer
    scriptDialog.AddControlToGrid( "RendererLabel", "LabelControl", "Renderer", 5, 0)
    scriptDialog.AddComboControlToGrid("RendererCombo","ComboControl","None",["BRAY_HdKarmaXPU","BRAY_HdKarma"],5,1)

    #Frame Boxes
    scriptDialog.AddControlToGrid( "StartFrameLabel", "LabelControl", "Start", 6, 0, "Start Frame", False )
    scriptDialog.AddRangeControlToGrid( "StartFrame", "RangeControl", 1001,-65535,65535,0,1, 6,1 )
    scriptDialog.AddControlToGrid( "EndFrameLabel", "LabelControl", "End", 6, 2, "End Frame", False )
    scriptDialog.AddRangeControlToGrid( "EndFrame", "RangeControl", 1250,-65535,65535,0,1, 6,3 )
    scriptDialog.AddControlToGrid( "ChunkSizeLabel", "LabelControl", "Chunk", 6, 4, "Frames Per Task", False )
    scriptDialog.AddRangeControlToGrid( "ChunkSize", "RangeControl", 4,1,100,0,1, 6, 5 )

    # Extra Arguments
    extra_args_default = ""
    extra_args_default += "--res-scale 100\n"
    extra_args_default += "--headlight none\n"
    scriptDialog.AddControlToGrid( "ExtraArgsLabel", "LabelControl", "Extra Args", 7, 0, "Extra commandline arguments to pass to husk", False )
    scriptDialog.AddControlToGrid( "ExtraArgs", "MultiLineTextControl", extra_args_default, 7, 1, colSpan=5 )

    scriptDialog.EndGrid()

    #collapsed settings
    scriptDialog.AddGroupBox("AdvancedGroup","Advanced Settings",True)
    scriptDialog.AddGrid()

    #Logging level
    scriptDialog.AddControlToGrid( "LogLevelLabel", "LabelControl", "Log Level", 0, 0)
    scriptDialog.AddComboControlToGrid("LogLevelCombo","ComboControl","None",["None","Basic","Enhanced","Godlike","David"],0,1)
    scriptDialog.EndGrid()
    scriptDialog.EndGroupBox(True)

    #SubmitButton
    scriptDialog.AddGrid()
    submitButton = scriptDialog.AddControlToGrid( "SubmitButton", "ButtonControl", "Submit", 0, 3, expand=False,colSpan=1 )
    submitButton.ValueModified.connect(SubmitButtonPressed)
    #closeButton
    closeButton = scriptDialog.AddControlToGrid( "CloseButton", "ButtonControl", "Close", 0, 4, expand=False, colSpan=1)
    closeButton.ValueModified.connect(scriptDialog.closeEvent)
    scriptDialog.EndGrid()

    #Load sticky settings
    #settings = ("DepartmentBox","PoolBox","SecondaryPoolBox","GroupBox","PriorityBox","IsBlacklistBox","MachineListBox","LimitGroupBox","DraftTemplateBox","InputBox","OutputDirectoryBox","OutputFileBox","frameListBox")
    settings = ()
    scriptDialog.LoadSettings( GetSettingsFilename(), settings )
    scriptDialog.EnabledStickySaving( settings, GetSettingsFilename() )

    return scriptDialog


def FileSelectionChanged(*args):
    usdFiles = scriptDialog.GetValue("USDFilePath")
    jobNames = ';'.join([os.path.basename(usdFile) for usdFile in usdFiles.split(';')])
    scriptDialog.SetValue("NameBox", jobNames)


def SubmitButtonPressed():
    usdFilesString = scriptDialog.GetValue('USDFilePath')
    
    if not usdFilesString:
        scriptDialog.ShowMessageBox('No USD Files Selected', 'Error')
        return

    usdFiles = usdFilesString.split(';')

    # Ensure valid framerange
    if not scriptDialog.GetValue("EndFrame") > scriptDialog.GetValue("StartFrame"):
        scriptDialog.ShowMessageBox( "End Frame must be higher than Start Frame", "Error" )
        return

    # Get dialog values
    jobNamesString = scriptDialog.GetValue( "NameBox" )
    if not jobNamesString:
        jobNames = ['Miscellaneous Unnamed USD Job']
    else:
        jobNames = jobNamesString.split(';')

    if len(jobNames) != len(usdFiles):
        jobNames = jobNames[0] * len(usdFiles)

    frameList = "{0}-{1}".format(scriptDialog.GetValue("StartFrame"),scriptDialog.GetValue("EndFrame"))
    comment = scriptDialog.GetValue( "CommentBox" )
    chunkSize = scriptDialog.GetValue("ChunkSize")
    renderer = scriptDialog.GetValue( "RendererCombo" )
    logLevel = LoggingMap[scriptDialog.GetValue("LogLevelCombo")]
    extraArgs = scriptDialog.GetValue( "ExtraArgs" ).replace("\n", " ").replace("\r", " ").replace(";", "")

    # Iterate through files and submit each USD
    for usdFile, jobName in zip(usdFiles, jobNames):
        #is file existing
        if not os.path.exists(usdFile):
            scriptDialog.ShowMessageBox( "USD file doesn't exist!\n" + usdFile, "Error" )
            continue

        #Create Job file
        jobInfoFilename = Path.Combine( GetDeadlineTempPath(), "usd_job_info.job" )
        writer = StreamWriter( jobInfoFilename, False, Encoding.Unicode )
        writer.WriteLine( "Plugin=HuskStandalone" )
        writer.WriteLine( "Name={}".format(jobName))
        writer.WriteLine( "Comment={}".format(comment))

        writer.WriteLine( "Frames={}".format(frameList))
        writer.WriteLine( "ChunkSize={}".format(chunkSize) )
        writer.Close()

        # Create plugin info file.
        pluginInfoFilename = Path.Combine( GetDeadlineTempPath(), "USD_plugin_info.job" )
        writer = StreamWriter( pluginInfoFilename, False, Encoding.Unicode )
        writer.WriteLine( "SceneFile=\"{}\"".format(usdFile))
        writer.WriteLine( "Renderer={}".format(renderer))
        writer.WriteLine( "LogLevel={}".format(logLevel))
        writer.WriteLine( "ExtraArgs={}".format(extraArgs))
        writer.Close()

        # Setup the command line arguments.
        arguments = StringCollection()

        arguments.Add( jobInfoFilename )
        arguments.Add( pluginInfoFilename )

        # Now submit the job.
        results = ClientUtils.ExecuteCommandAndGetOutput( arguments )
        scriptDialog.ShowMessageBox( results, "Submission Results: " + jobName )
