# CLO3D Script 2: Import sewn JSON and flip back panels
# Paste into CLO3D Script Editor after File → New
#
# Replace DESIGN with your design name in the file path.
# Flips all "Back" panels (Back_Left, Back_Right, WB_Back) horizontally.

import pattern_api
pattern_api.ImportPatternJSON("/tmp/clo_DESIGN_sewn.json")
count = pattern_api.GetPatternCount()
for i in range(count):
    name = pattern_api.GetPatternPieceName(i)
    if "Back" in name:
        pattern_api.FlipPatternPiece(i, True, False)
        print("Flipped " + name)
    else:
        print("Skipped " + name)
print("Seams: " + str(pattern_api.GetSeamlinePairGroupCount()))
