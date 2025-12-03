# ForeverBearing Dataset 

A short intorduction to reading data collected from experiments 

## Test configuration
See `config.json` 

## File format
The file format is [hdf5](https://en.wikipedia.org/wiki/Hierarchical_Data_Format) a Hierarchical data format allwing the storeage of multiple streams including metadata.

To examine the format, run `python inspect_hdf5.py <datafile>`

To load the file, see example in `python plot_waveform.py <datafile>`

