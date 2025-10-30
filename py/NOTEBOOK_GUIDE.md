# Jupyter Notebook Guide - display_data.ipynb

## Overview

The `display_data.ipynb` notebook has been updated to work with the new HDF5 structure and provides comprehensive visualization tools for oscilloscope data.

## What's New

✅ **Fixed HDF5 path handling** - Now correctly loads from `/sweeps/sweep_XXX/` structure
✅ **Enhanced plotting functions** - Time domain, FFT, spectrogram
✅ **Multi-channel support** - Plot all channels at once
✅ **Better error handling** - Graceful handling of missing data
✅ **Interactive plots** - Plotly-based with zoom, pan, hover

## Available Functions

### Data Loading
- `list_sweeps(file)` - List all sweeps in HDF5 file
- `list_channels(file, sweep)` - List channels in a sweep
- `load_waveform(file, sweep, channel)` - Load waveform data
- `get_sweep_info(file, sweep)` - Get sweep metadata

### Visualization
- `plot_time_series(t, v, channel)` - Time-domain waveform
- `plot_fft(f, mag, channel, fmax=None)` - FFT magnitude spectrum
- `plot_spectrogram(Sxx, f, t_spec, channel)` - Time-frequency plot
- `plot_multi_channel(file, sweep, channels, fft=False)` - Plot multiple channels

### Signal Processing
- `compute_fft(signal, fs)` - Compute FFT spectrum
- `compute_spectrogram(signal, fs, nperseg=256)` - Compute spectrogram

## Quick Start

### 1. Start Jupyter
```bash
cd py
jupyter notebook display_data.ipynb
```

### 2. Run Cell 0 (Functions)
This loads all the helper functions. You should see:
```
✓ Functions loaded successfully!

Available functions:
  - load_waveform(file, sweep, channel)
  - list_channels(file, sweep)
  ...
```

### 3. Run Example Cells
The notebook includes pre-configured examples:

**Cell 1: Basic Loading**
```python
h5file = 'data/data2_20251027_091947.h5'
channels = list_channels(h5file, sweep=0)
t, v, attrs = load_waveform(h5file, 0, 'Accel')
plot_time_series(t, v, 'Accel')
```

**Cell 2: FFT Analysis**
```python
fs = attrs['sample_rate']
f, mag = compute_fft(v, fs)
plot_fft(f, mag, 'Accel', fmax=50e3)  # Show up to 50 kHz
```

**Cell 3: Spectrogram**
```python
f_spec, t_spec, Sxx = compute_spectrogram(v, fs, nperseg=256)
plot_spectrogram(Sxx, f_spec, t_spec, 'Accel')
```

## Usage Examples

### Example 1: Compare Multiple Channels

```python
# Load HDF5 file
h5file = 'data/data2_20251027_091947.h5'

# Plot all channels in time domain
plot_multi_channel(h5file, sweep=0, fft=False)

# Plot all channels in frequency domain
plot_multi_channel(h5file, sweep=0, fft=True, fmax=100e3)
```

### Example 2: Analyze Specific Frequency Range

```python
# Load data
t, v, attrs = load_waveform(h5file, 0, 'AE')
fs = attrs['sample_rate']

# Compute FFT
f, mag = compute_fft(v, fs)

# Find peaks in 10-50 kHz range
mask = (f >= 10e3) & (f <= 50e3)
peak_freq = f[mask][np.argmax(mag[mask])]
peak_mag = mag[mask].max()

print(f"Peak in 10-50 kHz: {peak_freq/1e3:.2f} kHz, magnitude: {peak_mag:.3e} V")

# Plot with zoom
plot_fft(f, mag, 'AE', fmax=50e3)
```

### Example 3: Compare Sweeps Over Time

```python
h5file = 'data/data2_20251027_091947.h5'
sweeps = list_sweeps(h5file)

# Create subplot figure
from plotly.subplots import make_subplots
fig = make_subplots(rows=len(sweeps), cols=1,
                    subplot_titles=[f"Sweep {i}" for i in range(len(sweeps))])

for i, sweep_name in enumerate(sweeps):
    sweep_num = int(sweep_name.split('_')[1])
    t, v, attrs = load_waveform(h5file, sweep_num, 'Accel')

    fig.add_trace(
        go.Scatter(x=t*1e3, y=v, mode='lines', name=f'Sweep {sweep_num}'),
        row=i+1, col=1
    )

    fig.update_xaxes(title_text="Time (ms)", row=i+1, col=1)
    fig.update_yaxes(title_text="Voltage (V)", row=i+1, col=1)

fig.update_layout(height=300*len(sweeps), showlegend=False)
fig.show()
```

### Example 4: Export Data for External Analysis

```python
import pandas as pd

# Load waveform
t, v, attrs = load_waveform(h5file, 0, 'AE')

# Create DataFrame
df = pd.DataFrame({
    'time_s': t,
    'voltage_V': v
})

# Save to CSV
df.to_csv('exported_waveform.csv', index=False)
print(f"Exported {len(df)} points to exported_waveform.csv")

# Also save metadata
with open('exported_metadata.json', 'w') as f:
    json.dump(attrs, f, indent=2)
```

### Example 5: Batch Processing Multiple Files

```python
import glob

# Find all HDF5 files
files = sorted(glob.glob('data/*.h5'))

results = []
for h5file in files:
    try:
        # Get sweep info
        info = get_sweep_info(h5file, 0)

        # Load and analyze
        t, v, attrs = load_waveform(h5file, 0, 'AE')
        fs = attrs['sample_rate']
        f, mag = compute_fft(v, fs)

        # Find peak
        peak_idx = np.argmax(mag)

        results.append({
            'file': h5file,
            'timestamp': info['timestamp_local'],
            'peak_freq_kHz': f[peak_idx]/1e3,
            'peak_mag_V': mag[peak_idx],
            'rms_V': np.sqrt(np.mean(v**2))
        })
    except Exception as e:
        print(f"Error processing {h5file}: {e}")

# Display results
df = pd.DataFrame(results)
print(df)
```

## Plotly Tips

All plots are interactive! You can:
- **Zoom**: Click and drag
- **Pan**: Hold Shift + drag
- **Reset**: Double-click
- **Save**: Click camera icon to save PNG
- **Hover**: See exact values

## Latest Acquisition Data

The most recent full acquisition is:
```
File: data/data2_20251027_091947.h5
Channels: AE, Accel, UL, Temp
Points: ~125k per channel
Sample rate: 12.5 MHz
Sweeps: 3
```

## Troubleshooting

### "KeyError: sweep_000"
- Old error - fixed! Make sure you're using the updated notebook

### "No module named scipy"
```bash
pip install scipy
```

### Plots not showing
- Make sure you're running in Jupyter, not regular Python
- Try: `%matplotlib inline` at top of notebook

### Memory issues with large files
```python
# Load only part of the data
with h5py.File(h5file, 'r') as f:
    t = f['/sweeps/sweep_000/AE/time'][:10000]  # First 10k points
    v = f['/sweeps/sweep_000/AE/voltage'][:10000]
```

## Next Steps

1. **Capture Data**: Run `python3 acquire_scope_data.py config.json`
2. **Open Notebook**: `jupyter notebook display_data.ipynb`
3. **Update Cell 1**: Set `h5file` to your new file
4. **Explore**: Run the example cells and modify as needed

## Additional Resources

- **HDF5 Structure**: See `METADATA_README.md`
- **Acquisition Guide**: See `SESSION_SUMMARY.md`
- **Test Scope**: `python3 test_scope_connection.py`
- **Inspect Files**: `python3 inspect_hdf5.py data/your_file.h5`
