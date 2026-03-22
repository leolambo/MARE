# CLO3D Script 1: Import panels and export for ID round-trip
# Paste into CLO3D Script Editor after File → New
#
# Replace DESIGN with your design name in the file paths.

import pattern_api
pattern_api.ImportPatternJSON("/tmp/clo_DESIGN_panels.json")
pattern_api.ExportPatternJSON("/tmp/clo_DESIGN_export.json")
print("Patterns: " + str(pattern_api.GetPatternCount()))
print("Exported — tell AL to inject seams")
