#!/usr/bin/env python3
import os

from System import *
from System.Diagnostics import *
from System.IO import *

from Deadline.Plugins import *
from Deadline.Scripting import *


def GetDeadlinePlugin():
	return HuskStandalone()


def CleanupDeadlinePlugin(deadlinePlugin):
	deadlinePlugin.Cleanup()


class HuskStandalone(DeadlinePlugin):
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

		self.AddStdoutHandlerCallback('USD ERROR(.*)').HandleCallback += self.HandleStdoutError # detect this error
		self.AddStdoutHandlerCallback( r'ALF_PROGRESS ([0-9]+(?=%))' ).HandleCallback += self.HandleStdoutProgress


	def RenderExecutable(self):
		# get path to the executable
		#if we know submitter's Hou version we could eventualy use it
		version = self.GetPluginInfoEntryWithDefault( 'Version', '' )
		path_list = self.GetConfigEntry('USD_RenderExecutable').replace('XX.X.XXX', version)
		executable_path = FileUtils.SearchFileList(path_list)
		if version == '' or not executable_path:
			self.LogInfo('Failed to find executable:\nconfig:{}\nVersion:{}\n'.format(path_list, version))
		return executable_path


	def RenderArgument( self ):
		'''
		Construct argument string to pass to Husk.
		'''
		usd_file_path = self.GetPluginInfoEntry('--usd-input')
		usd_file_path = RepositoryUtils.CheckPathMapping( usd_file_path )
		usd_file_path = usd_file_path.replace( '\\', '/' )

		frame = self.GetStartFrame()
		frame_count = self.GetEndFrame() - frame + 1

		argument = ''
		argument += f'--usd-input "{usd_file_path}"'
		argument += f' --frame {frame}'
		argument += f' --frame-count {frame_count}'
		argument += f' --make-output-path'
		for arg_name in self.GetPluginInfoEntry('ArgumentList').split(';'):
			if arg_name == '--usd-input':
				continue

			if arg_name.startswith('override'):
				continue
			
			print(f'override_{arg_name}', self.GetBooleanPluginInfoEntryWithDefault(f'override_{arg_name}', True))
			if not self.GetBooleanPluginInfoEntryWithDefault(f'override_{arg_name}', True):
				continue

			value = self.GetPluginInfoEntry(arg_name)
			if value == 'False':
				continue
			elif value == 'True':
				argument += f' {arg_name}'
			else:
				argument += f' {arg_name} {value}'

			if arg_name == '--verbose':
				argument += 'a'  # Required for progress handling

		self.LogInfo(f"Rendering USD file: {usd_file_path}")

		# Do karma GPU Environment vars
		self.KarmaGPUAffinity()

		return argument


	def HandleStdoutProgress(self):
		# just incase we want to implement progress at some point
		self.SetStatusMessage(self.GetRegexMatch(0))
		self.SetProgress(float(self.GetRegexMatch(1)))


	def HandleStdoutError(self):
		# what to do when an error is detected.
		self.FailRender(self.GetRegexMatch(0))


	def KarmaGPUAffinity(self):
		'''
		Set which GPUs to use using Karma Environment Variables
		More accurately disable which GPUs not to use
		Assumes max 4 GPUS
		'''
		MAX_GPUS = 4
		VAR_STRING_TEMPLATE = "KARMA_XPU_DISABLE_DEVICE_{}"

		if self.OverrideGpuAffinity():
			selected_GPUs = list(self.GpuAffinity())
			print("SELECTED GPUS", selected_GPUs)

			for gpu in range(MAX_GPUS):
				if gpu in selected_GPUs:
					continue

				os.environ[VAR_STRING_TEMPLATE.format(gpu)] = "1"

