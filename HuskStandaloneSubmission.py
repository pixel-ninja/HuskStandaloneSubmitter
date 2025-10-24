import os
import subprocess
import re
from enum import Enum
from functools import partial
from dataclasses import dataclass
from typing import Callable, Optional

from Deadline.Scripting import ClientUtils, RepositoryUtils, FileUtils, FrameUtils
from DeadlineUI.Controls.Scripting.DeadlineScriptDialog import DeadlineScriptDialog
from System import Array
from System.Text import Encoding
from System.IO import Path, StreamWriter
from System.Collections.Specialized import StringCollection


class ControlType(Enum):
	label = 'LabelControl'
	text = 'TextControl'
	multifile = 'MultiFileBrowserControl'
	checkbox = 'CheckBoxControl'
	range = 'RangeControl'
	range2 = 'RangeControl2'
	button = 'ButtonControl'
	combo = 'ComboControl'

@dataclass
class Control:
	name: str
	label: str
	type: ControlType
	value: list 
	tooltip: str = ''
	override: bool | None = None
	pre_space: bool = False
	callback: Optional[Callable[[DeadlineScriptDialog], None]] = None


def get_usdcat() -> str:
	'''
	Sets the USDCAT variable to the usdcat executable based on the husk executable.
	'''
	husk_settings = RepositoryUtils.GetPluginConfig('HuskStandalone')
	executable_list = husk_settings.GetConfigEntry('USD_RenderExecutable')
	executable = FileUtils.SearchFileList(executable_list)
	if not executable:
		raise Exception("Husk executable not found.")

	usdcat = executable.split('husk')[0] + 'usdcat'
	if os.name == 'nt':
		usdcat += '.exe'

	if not os.path.exists(usdcat):
		raise Exception("Houdini usdcat binary not found.")
	
	return usdcat


def get_usd_metadata(path: str) -> dict[str, str]:
	'''
	Return the layer metadata of a usd file as a dictionary via usdcat.
	Hacky parsing of usdcat output to avoid dealing with clashing Deadline/USD python versions.
	'''
	layer_metadata = {}
	usdcat = subprocess.check_output([USDCAT, '--layerMetadata', path], text=True)
	for line in usdcat.splitlines()[2:-2]:
		key, value = line.lstrip().split(' = ')
		layer_metadata[key] = value
	
	return layer_metadata


def get_render_info(path: str) -> dict[str, list[str] | dict[str, list[str]]]:
	'''
	Returns a dictionary of representing all of the render prims and their relationships.
	Hacky parsing of usdcat output to avoid dealing with clashing Deadline/USD python versions.
	Only looks under /Render.
	ProductName will always be the last element of the RenderProduct's relationship list
	and will be the first found frame converted to printf format.
	'''
	result = {
		'ProductName': [],
		'RenderVar': [],
		'RenderProduct': [],
		'RenderSettings': [],
		'RenderPass': [],
		'Relationships': {}
	}
	
	accum_path:str = ''
	accum_depth:int = -1

	usdcat = subprocess.check_output([USDCAT, '--flatten', '--mask', '/Render', path], text=True)
	resume = []
	for line in usdcat.splitlines():
		# Resume list
		if resume:
			if resume[1] in line:
				resume = []
				continue

			if resume[0] == 'skip':
				continue
			
			match = re.search(resume[0], line)
			if not match:
				resume = []
				continue

			matched_path = match.group(1)

			if resume[1] == '}':
				matched_path = FrameUtils.ReplaceFrameNumberWithPrintFPadding(matched_path)
				result['ProductName'].append(matched_path)

			result['Relationships'][accum_path].append(matched_path)

			if resume[1] == '}':
				resume[0] = 'skip'
			continue

		# Find Render Prims
		match = re.search(r'def (?P<type>.+) "(?P<name>.+)"', line)
		if match:
			name = match.groupdict()['name']
			type = match.groupdict()['type']

			current_depth:int = (len(line) - len(line.lstrip())) // 4
			if current_depth > accum_depth:
				accum_depth = current_depth
				accum_path += f'/{name}'
			elif current_depth <= accum_depth:
				diff = accum_depth - current_depth
				for i in range(diff + 1):
					accum_path, _ = os.path.split(accum_path) 
				accum_depth -= diff
				accum_path += f'/{name}'

			if type in result.keys():
				result[type].append(accum_path)
			continue

		# Find Relationships
		match = re.search(r'(?:rel|token) (?P<type>products|renderSource|orderedVars|productName\.timeSamples) = <?(?P<path>[^>]+)>?', line)
		if match:
			if accum_path not in result['Relationships']:
				result['Relationships'][accum_path] = []

			if match.groupdict()['path'] == '[':
				resume = [r'<(.*)>', ']']
			elif match.groupdict()['path'] == '{': 
				resume = [r'\d+: "(.+)",', '}']
			else:
				result['Relationships'][accum_path].append(match.groupdict()['path'])

	return result


def toggle_enabled(dialog: DeadlineScriptDialog) -> None:
	for control_rows in CONTROLS.values():
		for control_row in control_rows:
			for control in control_row:
				if control.override is None:
					continue
				enabled = dialog.GetValue(f'override_{control.name}')
				if control.label:
					dialog.SetEnabled(f'{control.name}_label', enabled)

				if control.type is not ControlType.range2:
					dialog.SetEnabled(control.name, enabled)
				else:
					for i, (label, value) in enumerate(control.value):
						if label:
							dialog.SetEnabled(f'{control.name}_{i}_label', enabled)
						dialog.SetEnabled(f'{control.name}_{i}', enabled)

	return
	for override_name, control_names in TOGGLES.items():
		enabled = dialog.GetValue(override_name)
		for control_name in control_names:
			dialog.SetEnabled(control_name, enabled)
			dialog.SetEnabled(f'{control_name}_label', enabled)


def files_selected(dialog: DeadlineScriptDialog):
	'''
	Sets the Batch Name to the shortest common prefix of input files
	when multiple files are selected.

	eg. Scene_v005.FG.usd;Scene_v005.BG.usd -> Scene_v005
	'''
	file_paths_string = dialog.GetValue('file_paths_control')
	if not file_paths_string:
		return

	file_paths = file_paths_string.split(';')

	# No need for batch name when submitting single file
	if len(file_paths) == 1:
		dialog.SetValue('batch_control', '')
		return
	
	common_prefix = os.path.commonprefix(file_paths)
	batch_name = os.path.basename(os.path.splitext(common_prefix)[0])
	if common_prefix:
		dialog.SetValue('batch_control', batch_name)


# Define UI
WINDOW_TITLE = 'Deadline Husk Submitter'
MAX_COLUMNS = 6
CONTROLS = {  # End key with _,+ or - for group, expanded group or collapsed group
	'Submission_': [
		[Control('file_paths_control', 'USD File/s', ControlType.multifile, ['', 'USD Files (*.usd);;USDA Files (*.usda);;USDC Files(*.usdc);;USDZ Files(*.usdz)'], callback=files_selected)],
		[Control('batch_control', 'Batch Name', ControlType.text, [''])],
		[Control('comment_control', 'Comment', ControlType.text, [''])],
		[Control('chunk_control', 'Frames Per Task', ControlType.range, [5, 1, 1000, 0, 1])],
		[Control('framerange_control', 'Frame Range', ControlType.range2, [('Start', [1001, -65535, 65535, 0, 1]), ('End', [1250, -65535, 65535, 0, 1])], override=False)],
	],

	'Rendering-': [
		[Control('--renderer', 'Renderer', ControlType.combo, ['', ['BRAY_HdKarmaXPU', 'BRAY_HdKarma']])],
		[Control('--pixel-samples', 'Pixel Samples', ControlType.range, [128, 1, 65535, 0, 1], override=False)],
		[Control('--pass', 'Pass Prim/s', ControlType.text, [''], override=False)],
		[Control('--settings', 'Settings Prim/s', ControlType.text, [''], override=False)],
		[Control('--slap-comp', 'Slap Comp', ControlType.text, [''], override=False)],
		[Control('--tile-count', 'Auto Tile', ControlType.range2, [('x', [4, 1, 65535, 0, 1]), ('y', [4, 1, 65535, 0, 1])], override=False)],
		[Control('--verbose', 'Logging Verbosity', ControlType.range, [0, 0, 9, 0, 1], override=False)],
	],

	'RenderSettingsOverrides-': [
		[Control('--res', 'Resolution', ControlType.range2, [('x', [1920, 0, 65535, 0, 1]), ('y', [1080, 0, 65535, 0, 1])], override=False)],
		[Control('--res-scale', 'Resolution Scale', ControlType.range, [100, 0, 5000, 0, 1], override=False)],
		[Control('--camera', 'Camera', ControlType.text, [''], override=False)],
	],

	'USD-': [
			[Control('--headlight', 'Headlight', ControlType.combo, ['', ['None', 'Distant', 'Dome']], override=True)],
			[Control('--disable-scene-materials', '', ControlType.checkbox, [False, 'Disable Scene Materials'])],
			[Control('--disable-scene-lights', '', ControlType.checkbox, [False, 'Disable Scene Lights'])],
			[Control('--disable-motionblur', '', ControlType.checkbox, [False, 'Disable Motion Blur'])],
	],
}

TOGGLES = {
	'override_frames_control': ['start_control', 'end_control'],
}

USDCAT = get_usdcat()


def format_results_message(results: dict[str, dict[str, str]]) -> str:
	'''
	Take the stdout results of the job submissions and format them nicely for display.
	'''
	result_output = ''
	for k, v in results.items():
		if not v:
			continue

		if k == 'success':
			result_output += '---| Successful Submissions |---\n'
		else:
			result_output += '-!!|   Failed Submissions   |!!-\n'

		for job_name, stdout in v.items():
			result_output += f'{job_name}\n'
			if k == 'fail':
				result_output += ''.join([f'\t{s}' for s in stdout.splitlines(True) if s.strip()])
				result_output += '\n'

		result_output += '\n'

	result_output = result_output.rstrip()
	return result_output


def submit_pressed(dialog: DeadlineScriptDialog) -> None:
	usd_file_paths_string = dialog.GetValue('file_paths_control')
	
	if not usd_file_paths_string:
		dialog.ShowMessageBox('No USD Files Selected', 'Error')
		return

	usd_file_paths = usd_file_paths_string.split(';')

	# Ensure valid framerange
	if not dialog.GetValue('framerange_control_1') >= dialog.GetValue('framerange_control_0'):
		dialog.ShowMessageBox( "End Frame must be higher than Start Frame", "Error" )
		return

	# Get dialog values
	override_frames = dialog.GetValue('override_framerange_control')
	frame_list = f"{dialog.GetValue('framerange_control_0')}-{dialog.GetValue('framerange_control_1')}"
	batch_name = dialog.GetValue('batch_control')
	comment = dialog.GetValue('comment_control')
	chunk_size = dialog.GetValue('chunk_control')
	arguments = {}

	# Get Argument Values
	for control_rows in CONTROLS.values():
		for control_row in control_rows:
			for control in control_row:
				if not control.name.startswith('--'):
					continue
				if control.override is not None and not dialog.GetValue(f'override_{control.name}'):
					continue
				
				if control.type is ControlType.range2:
					if control.name == '--tile-count':
						arguments['--autotile'] = True
					value0 = dialog.GetValue(f'{control.name}_0')
					value1 = dialog.GetValue(f'{control.name}_1')
					arguments[control.name] = f'{value0} {value1}'
				else:
					arguments[control.name] = dialog.GetValue(control.name)


	# Iterate through files and submit each USD
	results = {'success': {}, 'fail': {}}
	for job_index, usd_file_path in enumerate(usd_file_paths):
		if not os.path.exists(usd_file_path):
			dialog.ShowMessageBox( "USD file doesn't exist!\n" + usd_file_path, 'Error' )
			continue

		# Use frame range from usd file
		if not override_frames:
			layer_metadata = get_usd_metadata(usd_file_path)
			frame_list = f"{layer_metadata['startTimeCode']}-{layer_metadata['endTimeCode']}"

		# Get Outputs
		#NOTE: This is a mess
		#TODO: Extract into a separate function to at least hide it away
		render_settings_prims = []
		render_product_prims = []
		productnames = []
		if True:  #TODO: Proper conditional handling
			render_info = get_render_info(usd_file_path)
			# Get default productname #TODO: Proper handling of productname based on RenderPass/Settings/Products
			default_render_settings_prim = '/Render/rendersettings' 
			if default_render_settings_prim in render_info['RenderSettings']:
				render_settings_prims.append(default_render_settings_prim)
				for render_settings_prim in render_settings_prims:
					if render_settings_prim in render_info['Relationships']:
						for render_product_prim in render_info['Relationships'][render_settings_prim]:
							render_product_prims.append(render_product_prim)
							productname = render_info['Relationships'][render_product_prim][-1]
							# Check element is a productname and not a RenderVar
							if productname in render_info['ProductName']:
								productnames.append(productname)

		job_name = os.path.basename(usd_file_path)

		#Create Job file
		job_info_filename = Path.Combine( GetDeadlineTempPath(), 'husk_job_info.job' )
		writer = StreamWriter( job_info_filename, False, Encoding.Unicode )
		writer.WriteLine( 'Plugin=HuskStandalone' )
		writer.WriteLine( f'Name={job_name}')
		if batch_name:
			writer.WriteLine( f'BatchName={batch_name}')
		writer.WriteLine( f'Comment={comment}')
		writer.WriteLine( f'Frames={frame_list}')
		writer.WriteLine( f'ChunkSize={chunk_size}')
		for i, productname in enumerate(productnames):
			writer.WriteLine( f'OutputFilename{i}={productname}' )
		writer.Close()

		# Create plugin info file.
		plugin_info_filename = Path.Combine( GetDeadlineTempPath(), 'husk_plugin_info.job' )
		writer = StreamWriter( plugin_info_filename, False, Encoding.Unicode )
		writer.WriteLine( f'SceneFile={usd_file_path}')
		writer.WriteLine( f'ArgumentList={";".join(arguments.keys())}')
		for argument, value in arguments.items():
			writer.WriteLine( f'{argument}={value}' )
		writer.Close()

		# Setup the command line arguments.
		job_arguments = StringCollection()
		job_arguments.Add( job_info_filename )
		job_arguments.Add( plugin_info_filename )


		# Progress in titlebar
		dialog.SetTitle(f'{WINDOW_TITLE} - Submitting Job {job_index + 1}')

		# Now submit the job.
		result = ClientUtils.ExecuteCommandAndGetOutput( job_arguments )
		results['success' if 'Result=Success' in result else 'fail'][job_name] = result

	# Display results/errors
	dialog.SetTitle(f'{WINDOW_TITLE} - Submission Complete')
	dialog.ShowMessageBox( format_results_message(results), "Submission Results" )
	dialog.SetTitle(WINDOW_TITLE)


def submission_dialog(*args) -> DeadlineScriptDialog:
	dialog = DeadlineScriptDialog()
	dialog.SetTitle(WINDOW_TITLE)
	dialog.SetIcon(dialog.GetIcon('HuskStandalone'))

	for group, control_rows in CONTROLS.items():
		in_group = False
		is_collapsed = False
		if group[-1] in '_+-':
			dialog.AddGroupBox('', group.rstrip('_+-'), collapsible=group[-1]!='_')
			in_group = True
			is_collapsed = group[-1] == '-'

		row, column = 0, 0
		dialog.AddGrid()

		for control_row in control_rows:
			num_controls = len(control_row)
			for i, control in enumerate(control_row):
				if control.pre_space:
					dialog.AddHorizontalSpacerToGrid('', row, column)
					column += 1

				# No need for overrides on checkboxes with no label
				if not (control.type is ControlType.checkbox and not control.label):
					override = dialog.AddSelectionControlToGrid(f'override_{control.name}', ControlType.checkbox.value, control.override, '', row, column, control.tooltip, expand=False)
					override.ValueModified.connect(partial(toggle_enabled, dialog))
					column += 1
					if control.override is None:
						override.setVisible(False)

				if control.label:
					dialog.AddControlToGrid(f'{control.name}_label',
						ControlType.label.value, control.label, row, column, colSpan=1, expand=False)
					column += 1

				control_args = [control.name, control.type.value, *control.value, row, column, control.tooltip]
				control_kwargs = {
					'expand': control.type not in [ControlType.button, ControlType.checkbox],
					'colSpan': MAX_COLUMNS - column,
				}
				
				control_items = []
				match control.type:
					case ControlType.multifile | ControlType.checkbox:
						control_items.append(dialog.AddSelectionControlToGrid(*control_args, **control_kwargs))
					case ControlType.range:
						control_items.append(dialog.AddRangeControlToGrid(*control_args, **control_kwargs))
					case ControlType.range2:
						for item_num, item in enumerate(control.value):
							label, value = item
							control_kwargs['colSpan'] = 2
							control_kwargs['expand'] = True
							if label:
								dialog.AddControlToGrid(f'{control.name}_{item_num}_label',
								ControlType.label.value, label, row, column, expand=False)
								control_kwargs['colSpan'] = 1
								column += 1
							control_args = [f'{control.name}_{item_num}', control.type.value[:-1], *value, row, column, control.tooltip]
							control_items.append(dialog.AddRangeControlToGrid(*control_args, **control_kwargs))
							column += control_kwargs['colSpan']
					case ControlType.combo:
						control_items.append(dialog.AddComboControlToGrid(*control_args, **control_kwargs))
					case _:
						control_items.append(dialog.AddControlToGrid(*control_args, **control_kwargs))
				
				if control.callback is not None:
					for control_item in control_items:
						control_item.ValueModified.connect(partial( control.callback, dialog ))
				column += 1

			row, column = row + 1, 0

		dialog.EndGrid()

		if in_group:
			dialog.EndGroupBox(isCollapsed=is_collapsed)

	#SubmitButton
	dialog.AddGrid()
	dialog.AddHorizontalSpacerToGrid('', 0, 0)
	submitButton = dialog.AddControlToGrid('submit_button', 'ButtonControl', 'Submit', 0, 1, expand=False)
	submitButton.ValueModified.connect(partial(submit_pressed, dialog))

	#CloseButton
	closeButton = dialog.AddControlToGrid('CloseButton', 'ButtonControl', 'Close', 0, 2, expand=False)
	closeButton.ValueModified.connect(dialog.closeEvent)
	dialog.EndGrid()

	toggle_enabled(dialog)
	files_selected(dialog)
	dialog.SetValue('file_paths_control', ';'.join(args))

	return dialog


def __main__(*args):
	modal = bool(*args)  # Allows submission from terminal without window auto closing

	dialog = submission_dialog(*args)
	dialog.ShowDialog(modal=modal)

