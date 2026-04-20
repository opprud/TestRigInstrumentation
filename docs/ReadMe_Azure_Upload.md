# Azure Upload & HDF5 Komprimering

## Azure Upload

Upload testdata (HDF5-filer) direkte fra Dashboard til Azure Blob Storage.

### Opsætning

Tilføj en `azure` sektion i `config.json`:

```json
"azure": {
    "connection_string": "DIN_CONNECTION_STRING_HER",
    "default_container": "data"
}
```

Connection string kan enten være en AccountKey- eller SAS-baseret string. Du finder den i Azure Portal under **Storage account → Access keys** eller **Shared access signature**.

Installer Python-afhængigheden (er inkluderet i `requirements.txt`):

```bash
pip install azure-storage-blob azure-core
```

### Brug

1. Kør en test som normalt fra Dashboard
2. Når testen er færdig, klik **Upload Azure** knappen i Controls-sektionen
3. Dialogen åbner og viser en liste over alle tilgængelige HDF5-filer — vælg den du vil uploade
4. Vælg target **container** (eller skriv et nyt containernavn)
5. Rediger eventuelt **blob-navnet** (filnavnet i Azure)
6. Klik **Upload**
7. Progress bar viser fremskridt i realtid
8. Klik **Annuller** hvis du vil stoppe upload undervejs

### Filbrowser

Dialogen scanner automatisk `data/` mappen og eventuelle run-folders for `.h5` og `.hdf5` filer. Filerne vises sorteret med nyeste først og inkluderer filstørrelse, dato og mappe.

### Fejlfinding

| Problem | Løsning |
|---|---|
| "No module named 'azure'" | Kør `pip install azure-storage-blob azure-core` |
| "Could not resolve host" | Tjek at storage account-navnet i connection string er korrekt |
| Upload hænger ved 0% | Tjek internetforbindelse fra Pi med `curl -I https://DITACCOUNT.blob.core.windows.net` |
| "Upload already in progress" | En upload kører allerede — vent eller annuller den først |

---

## HDF5 Komprimering

Reducer filstørrelsen på HDF5-testdata ved at slå komprimering til.

### Opsætning

I `config.json` under `store`-sektionen:

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

### Komprimeringsindstillinger

**`compress`** — vælg komprimeringsalgoritme:

| Værdi | Beskrivelse |
|---|---|
| `"none"` | Ingen komprimering (default). Hurtigst at skrive. |
| `"gzip"` | God komprimering. Bedst til arkivering og upload. |
| `"lzf"` | Hurtig komprimering, mindre reduktion. Godt til realtid. |

**`compression_level`** — kun relevant for gzip (1-9):

| Level | Hastighed | Filstørrelse |
|---|---|---|
| 1 | Hurtigst | Størst |
| 4 | Balanceret (default) | God reduktion |
| 9 | Langsomst | Mindst |

### Slå komprimering til

Sæt `compress` til `"gzip"`:

```json
"compress": "gzip",
"compression_level": 4
```

### Slå komprimering fra

Sæt `compress` til `"none"`:

```json
"compress": "none"
```

### Verificering

Komprimeringen kan verificeres på to måder.

**Via Python på Pi'en:**

```bash
python3 -c "
import h5py
f = h5py.File('STIEN_TIL_DIN_FIL.h5', 'r')
ds = f['sweeps/sweep_000/AE/voltage']
print(f'compression: {ds.compression}')
print(f'compression_opts: {ds.compression_opts}')
print(f'chunks: {ds.chunks}')
f.close()
"
```

Forventet output med gzip:
```
compression: gzip
compression_opts: 4
chunks: (1954,)
```

**Via myHDF5 viewer:**

1. Gå til https://myhdf5.hdfgroup.org
2. Upload din HDF5-fil
3. Naviger til et voltage-dataset og klik **Inspect**
4. Under `filters` skal der stå `"name": "deflate"` med `"cd_values": [4]`

Bemærk: "deflate" er det interne HDF5-navn for gzip.

### Komprimering i test-profiler

Komprimeringsindstillinger kan også sættes per test-profil. Tilføj en `store`-sektion i din profil-JSON, og den vil overskrive config.json:

```json
{
    "name": "Langtidstest med komprimering",
    "duration_minutes": 480,
    "store": {
        "compress": "gzip",
        "compression_level": 4
    }
}
```

### Anbefalinger

- **Korte tests (< 30 min):** `"none"` — filerne er små nok til at komprimering ikke gør den store forskel
- **Lange tests (> 1 time):** `"gzip"` level 4 — god balance mellem hastighed og størrelse
- **Upload til Azure:** `"gzip"` anbefales — reducerer upload-tid markant for store filer