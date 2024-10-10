#!/usr/bin/env python3

from System import *
from System.Diagnostics import *
from System.IO import *

import os

from Deadline.Plugins import *
from Deadline.Scripting import *

from pathlib import Path

def GetDeadlinePlugin():
    return HuskStandalone()

def CleanupDeadlinePlugin(deadlinePlugin):
    deadlinePlugin.Cleanup()

class HuskStandalone(DeadlinePlugin):
    # functions inside a class must be indented in python - DT
    def __init__( self ):
        import sys
        if sys.version_info.major == 3:
            super().__init__()

        self.InitializeProcessCallback += self.InitializeProcess
        self.RenderExecutableCallback += self.RenderExecutable # get the renderExecutable Location
        self.RenderArgumentCallback += self.RenderArgument # get the arguments to go after the EXE


    def Cleanup( self ):
        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback

    def InitializeProcess( self ):
        self.SingleFramesOnly=False
        self.StdoutHandling=True
        self.PopupHandling=False

        self.AddStdoutHandlerCallback("USD ERROR(.*)").HandleCallback += self.HandleStdoutError # detect this error
        self.AddStdoutHandlerCallback( r"ALF_PROGRESS ([0-9]+(?=%))" ).HandleCallback += self.HandleStdoutProgress

    # get path to the executable
    def RenderExecutable(self):
        #if we know submitter's Hou version we could eventualy use it
        version = self.GetPluginInfoEntryWithDefault( "Version", "" )
        pathList = self.GetConfigEntry("USD_RenderExecutable").replace("XX.X.XXX", version)
        executableFound = FileUtils.SearchFileList(pathList)
        if version == "" or not executableFound:       
            self.LogInfo("Failed to find executable:\nconfig:{}\nVersion:{}\n".format(pathList, version))
        return executableFound

    # get the settings that go after the filename in the render command, 3Delight only has simple options.
    def RenderArgument( self ):

        # construct fileName
        #this will only support 1 frame per task

        usdFile = self.GetPluginInfoEntry("SceneFile")
        usdFile = RepositoryUtils.CheckPathMapping( usdFile )
        usdFile = usdFile.replace( "\\", "/" )

        usdPaddingLength = FrameUtils.GetPaddingSizeFromFilename( usdFile )

        frame = self.GetStartFrame()
        frame_count = self.GetEndFrame() - frame + 1

        argument = ""
        argument += usdFile + " "

        argument += "--verbose a{} ".format(self.GetPluginInfoEntry("LogLevel"))  # alfred style output and full verbosity
        argument += "--frame {} ".format(frame)
        argument += "--frame-count {} ".format(frame_count)
        argument += "--make-output-path "
        argument += self.GetPluginInfoEntry("ExtraArgs").replace("\n", " ") + " "

        #renderer handled in job file.
        # outputPath = self.GetPluginInfoEntry("OutputPath")
        # outputPath = RepositoryUtils.CheckPathMapping( outputPath )
        #argument += "-o {0}".format(outputPath)
        #argument += " --make-output-path" + " "

        renderer = self.GetPluginInfoEntryWithDefault("Renderer", None)
        if renderer is not None:
            argument += "--renderer {} ".format(renderer)

        self.LogInfo( "Rendering USD file: " + usdFile )

        # Do karma GPU Environment vars
        self.kmaGPUAffinity()

        return argument

    # just incase we want to implement progress at some point
    def HandleStdoutProgress(self):
        self.SetStatusMessage(self.GetRegexMatch(0))
        self.SetProgress(float(self.GetRegexMatch(1)))

    # what to do when an error is detected.
    def HandleStdoutError(self):
        self.FailRender(self.GetRegexMatch(0))

    def kmaGPUAffinity(self):
        # Set which GPUs to use
        # More accurately disable which GPUs not to use
        # Assumes max 4 GPUS
        MAX_GPUS = 4
        VAR_STRING_TEMPLATE = "KARMA_XPU_DISABLE_DEVICE_{}"

        if self.OverrideGpuAffinity():
            selectedGPUs = list(self.GpuAffinity())
            print("SELECTED GPUS", selectedGPUs)

            for gpu in range(MAX_GPUS):
                if gpu in selectedGPUs:
                    continue

                # The set process function doesn't work for some reason
                # self.SetProcessEnvironmentVariable(VAR_STRING_TEMPLATE.format(gpu) , "1")
                os.environ[VAR_STRING_TEMPLATE.format(gpu)] = "1"

