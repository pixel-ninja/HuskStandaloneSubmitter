# Husk Standalone Submitter
A custom Deadline plugin and submitter script for to allow direct submission of USD files to Husk for rendering.

## Features:
- Submit multiple USD files
- Set frame range from stage
- Set renderer (Karma CPU or XPU)
- GPU affinity (for Karma XPU)
- Submit render passes (Houdini 21+)
- Override stage settings during and after submission
- Path mapping of input and output files (untested)
- Submission of OutputFileNames to allow for easy checking/exploring from the Monitor

## Installation
### Copy Plugin Files
#### Install Script
Run the install.py script to copy the plugin and submission files to your repo.
Requires python 3 to be installed and the deadline bin directory to be in your path.

#### Manual
Copy the files to the following locations:

```
huskStandaloneSubmitter.py >
{ DeadlineRepository }/custom/scripts/Submission
```

```
HuskStandalone (DIR) >
{ DeadlineRepository }/custom/plugins/HuskStandalone
```

### Deadline Setup
In the Deadline Monitor go to:
Tools > Configure Plugin > HuskStandalone
Then set add your husk executable to the executables list.
This should be:
`{Houdin Installation Directory}/bin/husk.exe`

### Version Compatibility
Houdini 18+
Deadline 10

Certain settings only supported on newer Houdini versions (i.e. --pass is Houdini 21+).

## Usage
### Deadline Monitor
Go to Submit > HuskStandalone

### Terminal/Script
`deadlinecommand ExecuteScript <path/to/HuskStandaloneSubmission.py> [usd_paths] --modal`

## Notes
### Submission
Submission is mostly straightforward. Select your usd files, set the settings you want to override and click submit.

You can edit the settings of a running job in the monitor by right clicking on the job and selecting:
Modify Job Properties > HuskStandalone Settings.

### Determining Output Files
There is a bunch of logic that goes into determining the output files; as `--pass`, `--settings` and `--output` all affect them.

This is handled in the submission script but not in the plugin script itself so altering any of those options after submission will require manual intervention (i.e. `--pass` will not drive `--settings` and in turn `--settings` will not drive `--output`).

The basic outline is that RenderPasses can determine RenderSettings, which determine the RenderProducts which determine the ProductNames/Outputs. There can also be multiple passes/settings/products at each step.

### Render Passes
Most of the parameters mirror their husk arguments, with the notable exception of `--pass`. I have changed the submission implementation to match the useage of `--settings`. This allows for submitting multiple passes, the use of primnames instead of the full prim paths and pattern matching with * wildcards. 

As mentioned above; `--pass` will also drive `--settings` via the renderSource property.

I've suggested to SideFX that they implement UX this into Husk itself. It could just be me that wants this, but I find it hard to imagine a scenario where I have multiple render passes that don't each have their own corresponding settings/products.

### USD Parsing
All of this USD parsing is done via some very hacky regex on usdcat output for the sake of portability and minimising dependencies.

Using the proper USD python bindings would be much faster and more ergonomic but deadline is locked to python 3.10. This means it can't import the USD shipped with Houdini and would instead require a 3.10 compatible USD build/compile to be shipped with this script or be installed by users. That's not very portable so hacky regex it is.

### UI
The submission UI can be rearranged by reordering the rows of the CONTROLS variable.

To have changes reflected in the plugin options (i.e. when changing settings in the monitor after submission) regenerate the options file thusly:

`deadlinecommand ExecuteScript <path/to/HuskStandaloneSubmission.py> --generate-options`

## Thanks
Originally forked from and David Tree's Husk Submitter
https://github.com/DavidTree/HuskStandaloneSubmitter

