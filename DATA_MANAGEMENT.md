# Data Management

## Git Configuration

The repository is configured to ignore large data files while preserving directory structure.

### What's Ignored

✅ **Data Files** (not tracked in git):
- `py/data/*.h5` - HDF5 oscilloscope captures (~24-72 MB each)
- `py/data/*.csv` - CSV exports
- `py/data/*.dat` - Binary data files
- `*.log` - Log files (e.g., `visa_io.log`)

✅ **Python artifacts**:
- `__pycache__/`
- `*.pyc`
- `.venv/` virtual environments

✅ **IDE/OS files**:
- `.DS_Store` (macOS)
- `.vscode/`
- `.idea/`

✅ **React/Node**:
- `node_modules/`
- `react/dist/`
- `react/build/`

### What's Tracked

✓ **Configuration files**:
- `py/config.json`
- `py/modbus_config.json`
- `py/config_test.json`
- `py/config_with_telemetry.json`

✓ **Python scripts**:
- `py/*.py` - All Python source code
- `py/display_data.ipynb` - Jupyter notebook

✓ **Documentation**:
- `*.md` files
- `CLAUDE.md`

✓ **Directory structure**:
- `py/data/.gitkeep` - Preserves empty data directory

## Data Storage Recommendations

### Local Development

Store captured data in `py/data/`:
```bash
python3 acquire_scope_data.py config.json
# Creates: py/data/data3_20251027_093131.h5
```

Files are automatically ignored by git.

### File Naming Convention

The acquisition script uses timestamped filenames:
```
<base_name>_YYYYMMDD_HHMMSS.h5

Examples:
  data2_20251027_091947.h5
  test_acquisition_20251027_091317.h5
  test_with_telemetry_20251027_084848.h5
```

Configure base name in `config.json`:
```json
{
  "store": {
    "output_file": "data/experiment_name.h5",
    "timestamped": true
  }
}
```

### Data Backup Strategy

**HDF5 files can be large (20-70 MB each).** Recommended backup approach:

1. **Network Storage** (Recommended):
   ```bash
   # Copy to network drive after acquisition
   rsync -avz py/data/*.h5 /Volumes/NetworkDrive/ForeverBearing/
   ```

2. **Cloud Backup** (if available):
   ```bash
   # Upload to cloud storage (Dropbox, Google Drive, etc.)
   rclone copy py/data/ remote:ForeverBearing/data/
   ```

3. **External Drive**:
   ```bash
   # Periodic backup to external drive
   cp py/data/*.h5 /Volumes/Backup/ForeverBearing/$(date +%Y%m%d)/
   ```

4. **Archive Old Data**:
   ```bash
   # Archive data older than 30 days
   mkdir -p py/data/archive
   find py/data -name "*.h5" -mtime +30 -exec mv {} py/data/archive/ \;
   ```

### Disk Space Management

**Typical file sizes:**
- 1000 points, 1 channel: ~28 KB
- 125k points, 4 channels, 3 sweeps: ~24 MB
- 250k points, 4 channels, 10 sweeps: ~72 MB

**Monitor disk usage:**
```bash
# Check data folder size
du -sh py/data/

# List files by size
ls -lhS py/data/*.h5

# Count files
ls -1 py/data/*.h5 | wc -l
```

**Clean up test files:**
```bash
# Remove small test acquisitions
find py/data -name "test_*.h5" -size -1M -delete

# Remove files older than 90 days
find py/data -name "*.h5" -mtime +90 -delete
```

## Sharing Data

### Export for Colleagues

If you need to share specific captures with collaborators:

```bash
# Create shareable package
mkdir export_package
cp py/data/data2_20251027_091947.h5 export_package/
cp py/config.json export_package/
cp py/METADATA_README.md export_package/
cp py/inspect_hdf5.py export_package/
tar -czf experiment_20251027.tar.gz export_package/

# Or use zip
zip -r experiment_20251027.zip export_package/
```

### Git LFS (Optional)

For version controlling important reference datasets, you could use Git LFS:

```bash
# Install Git LFS (one-time setup)
git lfs install

# Track HDF5 files in a specific location
git lfs track "py/data/reference/*.h5"

# Add reference data
cp important_baseline.h5 py/data/reference/
git add py/data/reference/important_baseline.h5
git commit -m "Add reference baseline measurement"
```

**Note:** This is only recommended for critical reference files, not routine captures.

## Data Organization

### Recommended Structure

```
py/data/
├── .gitkeep                          # Tracked in git
├── 2025-10-27/                       # Date-based folders (optional)
│   ├── data2_20251027_091947.h5
│   ├── data3_20251027_093131.h5
│   └── test_20251027_091317.h5
├── archive/                          # Old data
│   └── 2025-10/...
└── reference/                        # Important baselines (Git LFS)
    └── baseline_bearing_new.h5
```

### Organize by Date (Optional)

```bash
#!/bin/bash
# organize_data.sh - Group files by date

for file in py/data/*.h5; do
    if [ -f "$file" ]; then
        # Extract date from filename (YYYYMMDD)
        date=$(basename "$file" | grep -oE '[0-9]{8}' | head -1)

        if [ ! -z "$date" ]; then
            # Create date folder
            mkdir -p "py/data/$date"

            # Move file
            mv "$file" "py/data/$date/"
        fi
    fi
done
```

## Verification

### Check .gitignore is Working

```bash
# Should show NO .h5 or .log files
git status

# Verify data files are ignored
git check-ignore py/data/*.h5
# Should output: py/data/*.h5

# List all ignored files
git status --ignored
```

### Test with New Capture

```bash
# Run acquisition
python3 acquire_scope_data.py config.json

# Check git status - new .h5 should NOT appear
git status

# Verify only .gitkeep is tracked
git ls-files py/data/
# Should show: py/data/.gitkeep
```

## Summary

✅ `.gitignore` configured to exclude data files
✅ `py/data/.gitkeep` preserves directory structure
✅ All HDF5 captures automatically ignored
✅ Log files excluded from git
✅ Configuration files tracked

Your data files are safe from accidental commits while the repository structure remains clean! 🎉
