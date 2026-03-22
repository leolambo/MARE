# CLO3D Script 3 (optional): Set fabric color
# Paste into CLO3D Script Editor after importing and arranging.
#
# Also set manually: Fabric Library → FABRIC 1 → Physical Properties:
#   - Preset: Woven
#   - Weight: 300 g/m²
#   - Bending: 1.0

import fabric_api
fabric_api.SetFabricPBRMaterialBaseColor(0, 0, 0, 0.15, 0.1, 0.1, 1.0)
print("Fabric color set (dark charcoal twill)")
