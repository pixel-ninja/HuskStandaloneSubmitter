import os
import subprocess
import re
from enum import Enum
from functools import partial
from dataclasses import dataclass, field
from typing import Callable, Optional

from Deadline.Scripting import ClientUtils, RepositoryUtils, FileUtils, FrameUtils
from DeadlineUI.Controls.Scripting.DeadlineScriptDialog import DeadlineScriptDialog
from ThinkboxUI.Controls.CollapsibleGroupBox import CollapsibleGroupBox
from System import Array
from System.Text import Encoding
from System.IO import Path, StreamWriter
from System.Collections.Specialized import StringCollection


class ControlType(Enum):
	label = 'LabelControl'
	text = 'TextControl'
	multifile = 'MultiFileBrowserControl'
	filesaver = 'FileSaverControl'
	checkbox = 'CheckBoxControl'
	range = 'RangeControl'
	range2 = 'RangeControl2'
	button = 'ButtonControl'
	combo = 'ComboControl'
	multilist = 'MultiSelectListControl'


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


@dataclass
class RenderInfo:
	startTimeCode: int = 1
	endTimeCode: int = 1
	renderSettingsPrimPath: str = '/Render/rendersettings'
	ProductName: list[str] = field(default_factory=list)
	RenderVar: list[str] = field(default_factory=list)
	RenderProduct: list[str] = field(default_factory=list)
	RenderSettings: list[str] = field(default_factory=list)
	RenderPass: list[str] = field(default_factory=list)
	relationships: dict[str, list[str]] = field(default_factory=dict)


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


def save_browser_location(path: str) -> None:
	txt_path = Path.Combine( GetDeadlineTempPath(), 'husk_browser_location.txt' )
	with open(txt_path, 'w') as file:
		file.write(path)


def load_browser_location() -> str:
	txt_path = Path.Combine( GetDeadlineTempPath(), 'husk_browser_location.txt' )
	if not os.path.exists(txt_path):
		return ''
	with open(txt_path, 'r') as file:
		return file.read()


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
	save_browser_location(os.path.dirname(file_paths[0]))

	# No need for batch name when submitting single file
	if len(file_paths) == 1:
		dialog.SetValue('batch_control', '')
		return
	
	common_prefix = os.path.commonprefix(file_paths)
	batch_name = os.path.basename(os.path.splitext(common_prefix)[0])
	if common_prefix:
		dialog.SetValue('batch_control', batch_name)


# Define UI
USDCAT = get_usdcat()
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
		[Control('--verbose', 'Logging Verbosity', ControlType.range, [0, 0, 9, 0, 1])],
	],

	'RenderSettingsOverrides-': [
		[Control('--res', 'Resolution', ControlType.range2, [('x', [1920, 0, 65535, 0, 1]), ('y', [1080, 0, 65535, 0, 1])], override=False)],
		[Control('--res-scale', 'Resolution Scale', ControlType.range, [100, 0, 5000, 0, 1], override=False)],
		[Control('--camera', 'Camera', ControlType.text, [''], override=False)],
		[Control('--output', 'Output/s', ControlType.filesaver, ['', ''], override=False)],
	],

	'USD-': [
			[Control('--headlight', 'Headlight', ControlType.combo, ['', ['None', 'Distant', 'Dome']], override=True)],
			[Control('--disable-scene-materials', '', ControlType.checkbox, [False, 'Disable Scene Materials'])],
			[Control('--disable-scene-lights', '', ControlType.checkbox, [False, 'Disable Scene Lights'])],
			[Control('--disable-motionblur', '', ControlType.checkbox, [False, 'Disable Motion Blur'])],
	],
}


def generate_options_file() -> None:
	'''
	Generate the HuskStandalone.options file in the repo plugin directory.
	The options are generated based on the parameters specified
	in the CONTROLS variable. 
	'''
	plugin_directory = RepositoryUtils.GetPluginDirectory('HuskStandalone')
	options_path = Path.Combine( plugin_directory, 'HuskStandalone.options' )
	writer = StreamWriter( options_path, False, Encoding.UTF8 )

	index = 0
	for category_index, (group, controls) in enumerate(CONTROLS.items()):
		category = group.rstrip('_+-')
		for control_row in controls:
			for control in control_row:
				names = []

				if control.name == 'file_paths_control':
					names = ['--usd-input']
				elif not control.name.startswith('--'):
					continue
				else:
					if control.override is not None:
						names.append(f'override_{control.name}')
					names.append(control.name)

				for name in names:
					writer.WriteLine( f'[{name}]' )

					writer.WriteLine( f'Category={category}' )
					writer.WriteLine( f'CategoryOrder={category_index}' )
					writer.WriteLine( f'Index={index}' )

					if name.startswith('override_'):
						writer.WriteLine( f'Description=Enables {name.lstrip("override_")} Husk option.' )
						writer.WriteLine( f'Label=Enable {control.label}' )
						writer.WriteLine( 'Type=Boolean' )
						writer.WriteLine( f'DefaultValue={control.override}' )
						writer.WriteLine( '' )
						index += 1
						continue

					writer.WriteLine( f'Description={control.tooltip}' )

					label = control.label
					default = control.value[0]
					option_type = 'String'

					if name == '--usd-input':
						option_type = 'Filename'
						writer.WriteLine( f'Filter={control.value[1]}' )

					match control.type:
						case ControlType.checkbox:
							option_type = 'Boolean'
							label = control.value[1]
						case ControlType.range:
							decimal_places = control.value[3]
							if decimal_places == 0:
								option_type = 'Integer'
							else:
								option_type = 'Float'
								writer.WriteLine( f'DecimalPlaces={decimal_places}' )
							writer.WriteLine( f'Minimum={control.value[1]}' )
							writer.WriteLine( f'Maximum={control.value[2]}' )
							writer.WriteLine( f'Increment={control.value[4]}' )
						case ControlType.range2:
							default = f'{control.value[0][1][0]} {control.value[1][1][0]}'
						case ControlType.combo:
							option_type = 'Enum'
							default = control.value[1][0]
							writer.WriteLine( f'Values={";".join(control.value[1])}' )

					writer.WriteLine( f'DefaultValue={default}' )
					writer.WriteLine( f'Type={option_type}' )
					writer.WriteLine( f'Label={label}' )
					writer.WriteLine( '' )
					index += 1

	writer.Close()


def get_render_info(path: str) -> RenderInfo:
	'''
	Returns a RenderInfo dataclass representing relevant layer metadata
	and all of the render prims and their relationships.
	Hacky parsing of usdcat output to avoid dealing with clashing
	Deadline/USD python versions.
	Only looks under /Render.
	ProductName will always be the last element of the RenderProduct's
	relationship list and will be the first found frame converted to printf format.
	'''
	result = RenderInfo()
	accum_path:str = ''
	accum_depth:int = -1

	usdcat = subprocess.check_output([USDCAT, '--flatten', '--mask', '/Render', path], text=True)
	finished_metadata = False
	resume = []
	for line in usdcat.splitlines():
		# Process metadate first
		if not finished_metadata:
			if line.strip() == ')':
				finished_metadata = True
				continue
			elif ' = ' not in line:
				continue
			
			key, value = line.lstrip().split(' = ')
			if hasattr(result, key):
				setattr(result, key, value.strip('"'))

			continue
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
				result.ProductName.append(matched_path)

			result.relationships[accum_path].append(matched_path)

			if resume[1] == '}':
				resume[0] = 'skip'
			continue

		# Find Render Prims
		match = re.search(r'def (?P<type>.+) "(?P<name>.+)"', line)
		if match:
			name = match.groupdict()['name']
			prim_type = match.groupdict()['type']

			current_depth:int = (len(line) - len(line.lstrip())) // 4
			if current_depth > accum_depth:
				accum_depth = current_depth
				accum_path += f'/{name}'
			elif current_depth <= accum_depth:
				diff = accum_depth - current_depth
				for _ in range(diff + 1):
					accum_path, _ = os.path.split(accum_path) 
				accum_depth -= diff
				accum_path += f'/{name}'

			if hasattr(result, prim_type):
				getattr(result, prim_type).append(accum_path)
			continue

		# Find Relationships
		match = re.search(r'(?:rel|token) (?P<type>products|renderSource|orderedVars|productName\.timeSamples) = <?(?P<path>[^>]+)>?', line)
		if match:
			if accum_path not in result.relationships:
				result.relationships[accum_path] = []

			if match.groupdict()['path'] == '[':
				resume = [r'<(.*)>', ']']
			elif match.groupdict()['path'] == '{': 
				resume = [r'\d+: "(.+)",', '}']
			else:
				result.relationships[accum_path].append(match.groupdict()['path'])

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
					for i, (label, _) in enumerate(control.value):
						if label:
							dialog.SetEnabled(f'{control.name}_{i}_label', enabled)
						dialog.SetEnabled(f'{control.name}_{i}', enabled)


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


def determine_outputs(render_info: RenderInfo, pass_value: str, settings_value: str, output_value: str) -> dict[str, tuple[list[str], list[str]]]:
	'''
	Determines the appropriate values for settings and output for each pass
	based on the values provided by looking into the usd file.
	Pass > Settings > Product > ProductName
	Render Pass drives Render Settings (via RenderSource attribute)
	Render Settings drives Render Product
	Render Product drives output/ProductNames
	'''
	result = {}
	settings_prims = []  #TODO: proper pattern matching of rendersettings value
	productnames = []

	# Get default productname #TODO: Proper handling of productname based on RenderPass/Settings/Products
	if render_info.renderSettingsPrimPath in render_info.RenderSettings:
		settings_prims.append(render_info.renderSettingsPrimPath)

	for render_settings_prim in settings_prims:
		if render_settings_prim in render_info.relationships:
			for render_product_prim in render_info.relationships[render_settings_prim]:
				productname = render_info.relationships[render_product_prim][-1]
				# Check element is a productname and not a RenderVar
				if productname in render_info.ProductName:
					productnames.append(productname)
	return {'': (settings_prims, productnames)}  #TODO: Handle this properly


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

				if control.override is not None:
					override_name = f'override_{control.name}'
					arguments[override_name] = dialog.GetValue(override_name)

				if control.type is ControlType.range2:
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
			results['fail'][os.path.basename(usd_file_path)] = "USD file doesn't exist"
			continue

		job_name = os.path.basename(usd_file_path)
		render_info: RenderInfo = get_render_info(usd_file_path)

		# Use frame range from usd file
		if not override_frames:
			frame_list = f"{render_info.startTimeCode}-{render_info.endTimeCode}"

		outputs = determine_outputs(
				render_info,
				*(dialog.GetValue(x) if dialog.GetValue(f'override_{x}') else ''
				for x in ('--pass', '--settings', '--output'))
			)

		for pass_prim, (settings_prims, productnames) in outputs.items():
			job_name_suffix = ''
			if pass_prim != '':
				job_name_suffix = '_' + os.path.basename(pass_prim)

			#Create Job file
			job_info_filename = Path.Combine( GetDeadlineTempPath(), 'husk_job_info.job' )
			writer = StreamWriter( job_info_filename, False, Encoding.Unicode )
			writer.WriteLine( 'Plugin=HuskStandalone' )
			writer.WriteLine( f'Name={job_name + job_name_suffix}')
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
			arguments['--usd-input'] = usd_file_path
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
			collapsible = group[-1]!='_'
			group_box = dialog.AddGroupBox('', group.rstrip('_+-'), collapsible=collapsible)
			if collapsible:
				group_box.clicked.connect(lambda: dialog.setFixedHeight(dialog.sizeHint().height()))
			in_group = True
			is_collapsed = group[-1] == '-'

		row, column = 0, 0
		dialog.AddGrid()

		for control_row in control_rows:
			for control in control_row:
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

				if control.type in [ControlType.multifile, ControlType.filesaver]:
					control_kwargs['browserLocation'] = load_browser_location()
				
				control_items = []
				match control.type:
					case ControlType.multifile | ControlType.filesaver | ControlType.checkbox:
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
					case ControlType.combo | ControlType.multilist:
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

	dialog.setFixedHeight(dialog.sizeHint().height())

	toggle_enabled(dialog)
	files_selected(dialog)
	dialog.SetValue('file_paths_control', ';'.join(args))

	return dialog


def __main__(*args):
	if '--generate-options' in args:
		generate_options_file()

	modal = '--modal' in args  # Allows submission from terminal without window auto closing

	# filter out non-paths from args
	file_paths = [x for x in args if os.path.exists(x)]

	dialog = submission_dialog(*file_paths)
	dialog.ShowDialog(modal=modal)

