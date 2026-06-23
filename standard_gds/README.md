# Standard GDS Files

This directory is intentionally a placeholder. The standard GDS files used for
XOR comparison are external validation inputs and are not included in this
package.

If you have the standard files, place them here or point
`compare_gds_geometry.py` at their directory with `--standard-dir` or
`LIDAR_STANDARD_GDS_DIR`.

Expected file names:

```text
clements_8x8_comp_LiDAR_id-2.gds
multiportmmi_8x8_comp_LiDAR_id-2_bak.gds
multiportmmi_16x16_comp_LiDAR_id-2_bak.gds
```

These files are never read by the router during generation. They are used only
by geometry comparison scripts.
