# Wuecampy

Wuecampy consists of two parts:

## download.py

Download all files from wuecampus to the local file system.

It will deprecate old files, but not notice if a file changed. Just delete it and have it redownload.

### Installation

```bash
    # Download
    git clone https://github.com/Kamik423/wuecampy.git
    # Install pip requirements
    cd wuecampy
    pip install -r requirements.txt
```

The script expects a library named `passwords` containing your wuecampus credentials.
Either replace those lines in the code (`download.py`) or create a file with this data structure:

```python
class sb_at_home:
    snr = 's123456'         # s-number
    password = 'Passw0rd'   # password
```

### Usage

With your relative or absolute paths, something along the lines of:

```bash
    ./download.py example_download_folder
```

The download folder must contain a `config.yaml` and a `mask.txt`.
Both are documented inside the example files in [example_download_folder](example_download_folder)


## wuecampy.py

The underlying library for interfacing with wuecampus.
It has classes for wuecampus, courses, section, files and assignments.
It is documented in the source code and used by `download.py`

# License

The project is licensed under the [MIT-License](license.md).

*GNU Terry Pratchett*
