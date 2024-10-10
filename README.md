# Husk Standalone Submitter

Submitter script for Deadline to allow direct submission of USD files to Husk.
<H2>
Features:
</H2>
<ul>
  <li> - Submit multiple USD files</li>
  <li> - Set Frame Ranges</li>
  <li> - Set Renderer (Karma CPU or XPU)</li>
  <li> - Set Chunk size</li>
  <li> - Add extra husk arguments</li>

</ul>

<H2>
Setting Husk.exe Location
</H2>

To set the location of Husk.exe. load the Deadline Monitor goto Tools > Configure Plugin > HuskStandalone and set the Husk Path. This should be your Houdini installation directory\bin\husk.exe

<H2>
Version Compatibility:
</H2>

Houdini 18.0+
Deadline 10

<H1>
Installation
</H1>

Copy the files to the following locations:

huskStandaloneSubmitter.py
DeadlineRepository \custom\scripts\Submission

HuskStandalone (DIR)
DeadlineRepository \custom\plugins\HuskStandalone

<H3>
Forked and based on from David Tree's Husk Submitter
</H3>
https://github.com/DavidTree/HuskStandaloneSubmitter
