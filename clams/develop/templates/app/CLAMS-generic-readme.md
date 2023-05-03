# CLAMS App

This document provides general instructions for installing and using CLAMS apps. 
App developers may provide additional information specific to their app, 
hence it's advised also to look up the app website (or code repository) to get the additional information. 

## Requirements 

Generally, an CLAMS app requires 

- Python3 with the `clams-python` module installed; to run the app locally. 
- `docker` or `podman`; to run the app in a container (as an HTTP server).
- An HTTP client utility (such as `curl`); to invoke and execute analysis.

For Python dependencies, usually apps come with `requirements.txt` files that list up the Python library. 
However, there could be other non-Python software/library that are required by the app.

## Installation

Currently, CLAMS apps available on the CLAMS app-directory are all open-source projects and are distributed as

1. source code downloadable from code repository
2. pre-built container image 

Please visit [the app-directory](https://github.com/clamsproject/clams-apps) to see which apps are available and where you can download them.
 
In most cases, you can "install" a CLAMS app by either
1. downloading source code from the app code repository and manually building a container image
2. downloading pre-built container image directly

## Building container image

From the project directory, run the following in your terminal to build an image from the included container specification file.

(Assuming you are using `docker` as your container manager)

```bash
docker build . -f Containerfile -t <app_name>
```

Alternatively, the app maybe already be available on a container registry.

``` bash 
docker pull <app_name>
```

## Running the image

Then to create a container using that image, run:

```bash
docker run -v /path/to/data/directory:/data -p <port>:5000 <app_name>
```

where `/path/to/data/directory` is the local location of your media files or MMIF objects and <port> is the *host* port number you want your container to be listening to. 
The HTTP inside the container will be listening to 5000 by default. 

## Invoking the app
Once the app is running as an HTTP server, to invoke the app and get automatic annotations, simply send a POST request to the app with a MMIF input as request body.

MMIF input files can be obtained from outputs of other CLAMS apps, or you can create an empty MMIF only with source media locations using `clams source` command. See the help message for a more detailed instructions. 
(Make sure you have installed [`clams-python` package](https://pypi.org/project/clams-python/) version from PyPI.)

```bash
pip install clams-python
clams source --help
```


