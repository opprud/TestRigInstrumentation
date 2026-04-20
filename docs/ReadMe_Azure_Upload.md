# Azure Upload & HDF5 Compression

## Azure Upload

Upload test data (HDF5 files) directly from the Dashboard to Azure Blob Storage.

### Setup

Add an `azure` section to `config.json`:

```json
"azure": {
    "connection_string": "YOUR_CONNECTION_STRING_HERE",
    "default_container": "data"
}
```

The connection string can be either an AccountKey or SAS-based string. You can find it in the Azure Portal under **Storage account → Access keys** or **Shared access signature**.

Install the Python dependency (already included in `requirements.txt`):

```bash
pip install azure-storage-blob azure-core
```

### Usage

1. Run a test as usual from the Dashboard
2. When the test is complete, click the **Upload Azure** button in the Controls section
3. The dialog opens and displays a list of all available HDF5 files — select the one you want to upload
4. Choose the target **container** (or type a new container name)
5. Optionally edit the **blob name** (the filename in Azure)
6. Click **Upload**
7. The progress bar shows real-time upload progress
8. Click **Cancel** to abort the upload at any time

### File Browser

The dialog automatically scans the `data/` directory and any run folders for `.h5` and `.hdf5` files. Files are listed newest first and include file size, date, and parent folder.

### Troubleshooting

| Problem | Solution |
|---|---|
| "No module named 'azure'" | Run `pip install azure-storage-blob azure-core` |
| "Could not resolve host" | Verify the storage account name in your connection string is correct |
| Upload stuck at 0% | Check internet connectivity from the Pi with `curl -I https://YOURACCOUNT.blob.core.windows.net` |
| "Upload already in progress" | An upload is already running — wait for it to finish or cancel it first |

---

## HDF5 Compression

Reduce HDF5 test data file size by enabling compression.

### Setup

In `config.json` under the `store` section:

```json
"store": {
    "output_file": "data/keratech22.hdf5",
    "timestamped": true,
    "compress": "gzip",
    "compression_level": 4,
    "chunk": false,
    "attrs": {
        "project": "ForeverBearing",
        "operator": "morten",
        "scope_model": "MSO-X 2024A"
    }
}
```

### Compression Settings

**`compress`** — choose the compression algorithm:

| Value | Description |
|---|---|
| `"none"` | No compression (default). Fastest write speed. |
| `"gzip"` | Good compression ratio. Best for archiving and upload. |
| `"lzf"` | Fast compression, lower ratio. Good for real-time acquisition. |

**`compression_level`** — only applies to gzip (1–9):

| Level | Speed | File Size |
|---|---|---|
| 1 | Fastest | Largest |
| 4 | Balanced (default) | Good reduction |
| 9 | Slowest | Smallest |

### Enabling Compression

Set `compress` to `"gzip"`:

```json
"compress": "gzip",
"compression_level": 4
```

### Disabling Compression

Set `compress` to `"none"`:

```json
"compress": "none"
```

### Verification

Compression can be verified in two ways.

**Via Python on the Pi:**

```bash
python3 -c "
import h5py
f = h5py.File('PATH_TO_YOUR_FILE.h5', 'r')
ds = f['sweeps/sweep_000/AE/voltage']
print(f'compression: {ds.compression}')
print(f'compression_opts: {ds.compression_opts}')
print(f'chunks: {ds.chunks}')
f.close()
"
```

Expected output with gzip enabled:
```
compression: gzip
compression_opts: 4
chunks: (1954,)
```

**Via myHDF5 viewer:**

1. Go to https://myhdf5.hdfgroup.org
2. Upload your HDF5 file
3. Navigate to a voltage dataset and click **Inspect**
4. Under `filters` you should see `"name": "deflate"` with `"cd_values": [4]`

Note: "deflate" is the internal HDF5 name for the gzip algorithm.

### Compression in Test Profiles

Compression settings can also be set per test profile. Add a `store` section to your profile JSON, and it will override the values in `config.json`:

```json
{
    "name": "Long duration test with compression",
    "duration_minutes": 480,
    "store": {
        "compress": "gzip",
        "compression_level": 4
    }
}
```

### Recommendations

- **Short tests (< 30 min):** `"none"` — files are small enough that compression adds little benefit
- **Long tests (> 1 hour):** `"gzip"` level 4 — good balance between speed and file size
- **Upload to Azure:** `"gzip"` recommended — significantly reduces upload time for large files