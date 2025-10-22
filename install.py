#!/usr/bin/env python3
import os
import shutil
import subprocess

def main():
	print('Installing Husk Standalone Submitter')
	try:
		print('Getting Deadline Repository Path')
		repository_path = subprocess.check_output(
			['deadlinecommand', '-GetRepositoryPath'],
			text=True
		).rstrip()
	except subprocess.CalledProcessError as e:
		print(
			'Error getting repository path from deadlinecommand.\n'
			'Ensure the deadline bin folder is in your path environment variable.')
		return

	script = './HuskStandaloneSubmission.py'
	plugin = './HuskStandalone'
	plugin_dst = os.path.join(repository_path, 'custom', 'plugins', 'HuskStandalone')
	script_dst = os.path.join(repository_path, 'custom', 'scripts', 'Submission')

	#Copy to Deadline Repository
	print(f'Copying {plugin} to {plugin_dst}')
	try:
		shutil.copytree(plugin, plugin_dst, dirs_exist_ok=True)
	except Exception as e:
		print(f'Failed\n{e}')
		return

	print(f'Copying {script} to {script_dst}')
	try:
		shutil.copy(script, script_dst)
	except Exception as e:
		print(f'Failed\n{e}')
		return

	print('Complete!')


if __name__ == '__main__':
	main()
