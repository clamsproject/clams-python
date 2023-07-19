## Using CLAMS App

This document provides general instructions for installing and using CLAMS Apps. 
App developers may provide additional information specific to their app, 
hence it's advised also to look up the app website (or code repository) to get the additional information. 

### Requirements 

Generally, a CLAMS App requires 

- To run the app locally, Python3 with the `clams-python` module installed. Python 3.8 or higher is required.
- To run the app in a container (as an HTTP server), container management software such as `docker` or `podman`.
  - (the CLAMS team is using `docker` for development and testing)
- To invoke and execute analysis, HTTP client utility (such as `curl`).

For Python dependencies, usually CLAMS Apps come with `requirements.txt` files that list up the Python library. 
However, there could be other non-Python software/library that are required by the app.

### Installation

CLAMS Apps available on the CLAMS App Directory. Currently all CLAMS Apps are open-source projects and are distributed as

1. source code downloadable from code repository
2. pre-built container image 

Please visit [the app-directory](https://apps.clams.ai) to see which apps are available and where you can download them.
 
In most cases, you can "install" a CLAMS App by either

1. downloading source code from the app code repository and manually building a container image
2. downloading pre-built container image directly

#### Build image from source code

To download the source code, you can either use `git clone` command or download a zip file from the source code repository. 
The source code repository address can be found on the App Directory entry of the app.

From the locally downloaded project directory, run the following in your terminal to build an image from the included container specification file.

(Assuming you are using `docker` as your container manager)

```bash
docker build . -f Containerfile -t <image_name_you_pick>
```

#### Download prebuilt image

Alternatively, the app maybe already be available on a container registry.

``` bash 
docker pull <prebulit_image_name>
```

The image name can be found on the App Directory entry of the app.

### Running CLAMS App


#### Running as a container

Once the image is built (by `build`) or downloaded (by `pull`), to create a container, run:

```bash
docker run -v /path/to/data/directory:/data -p <port>:5000 <image_name>
```

where `/path/to/data/directory` is the local location of your media files or MMIF objects and `<port>` is the *host* port number you want your container to be listening to. 
The HTTP inside the container will be listening to 5000 by default. Usually any number above 1024 is fine for the host port number, and you can use the same 5000 number for the host port number.

> **Note**
> If you are using a Mac, on recent versions of macOS, port 5000 is used by Airplay Receiver by default. So you may need to use a different port number, or turn off the Airplay Receiver in the System Preferences to release 5000.
> For more information on *safe* port numbers, see [IANA Port Number Registry](https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xhtml) or [Wikipedia](https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers).

> **Note**
> Another note for users of recent Macs with Apple Silicon (M1, M2, etc) CPU: you might see the following error message when you run the container image.
> ```bash
> The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no specific platform was requested
> ```
> This is because the image you are trying to run is built for Intel/AMC CPUs. To force the container to run on an emulation layer, you can add `--platform linux/amd64` option to the `docker run` command.


#### Running as a local HTTP server

To run the app as a local HTTP server without containerization, you can run the following command from the source code directory.

```bash
python app.py 
```

* By default, a CLAMS App will be listening to port 5000, but you can change the port number by passing `--port <number>` option. 
* Be default, the app will be running in *debugging* mode, but you can change it to *production* mode by passing `--production` option to support larger traffic volume.

#### Running as a CLI program

(Not all CLAMS Apps can be run as a CLI program)

Many CLAMS Apps are written to work as a CLI-based Python Program, although they are primarily designed to be run as an HTTP server.
CLI-based execution is useful for testing and debugging purposes, and varies from app to app.
To see the command line interface, please visit the app source code repository and look for additional instructions from the app developer.

### Invoking the app server

#### App metadata

Once the app is running as an HTTP server, visit the server address ([localhost:5000](http://localhost:5000))to get the app metadata. App metadata is also available at the App Directory entry of the app. App metadata contains important information about the app that we will use in the following sections.

#### Processing input media

To actually run the app and process input media through computational analysis, simply send a POST request to the app with a MMIF input as the request body.

MMIF input files can be obtained from outputs of other CLAMS apps, or you can create an *empty* MMIF only with source media locations using `clams source` command. See the help message for a more detailed instructions. 
(Make sure you have installed [`clams-python` package](https://pypi.org/project/clams-python/) version from PyPI.)

```bash
pip install clams-python
clams source --help
```

For example; by running 

```bash 
clams source audio:/data/audio/some-audio-file.mp3
```

You will get

```json 
{
  "metadata": {
    "mmif": "http://mmif.clams.ai/X.Y.Z"
  },
  "documents": [
    {
      "@type": "http://mmif.clams.ai/vocabulary/AudioDocument/v1",
      "properties": {
        "mime": "audio",
        "id": "d1",
        "location": "file:///data/audio/some-audio-file.mp3"
      }
    }
  ],
  "views": []
}
```

If an app requires just `Document` inputs (see `input` section of the app metadata), an empty MMIF with required media file locations will suffice. The location has to be a URL or an absolute path, and it is important to ensure that it exists.

However, some apps only works with input MMIF that already contains some annotations of specific types. To run such apps, you need to run different apps in a sequence. 

(TODO: added CLAMS workflow documentation link here.)

When an input MMIF is ready, you can send it to the app server.
Here's an example of how to use the `curl` command, and store the response in a file `output.mmif`.

```bash
curl -H "Accept: application/json" -X POST -d@input.mmif -s http://localhost:5000 > output.mmif

# or using a bash pipeline 
clams source audio:/data/audio/some-audio-file.mp3 | curl -X POST -d@- -s http://localhost:5000 > output.mmif
```
Appending `?pretty=True` to the URL will result in a pretty printed output. Note that when you're using `curl` from a shell session, you need to escape the `?` or `&` characters with `\` to prevent the shell from interpreting it as a special character.

#### Configuring the app

Running as an HTTP server, CLAMS Apps are stateless, but can be configured for each HTTP request by providing configuration parameters as [query string](https://en.wikipedia.org/wiki/Query_string). 

For configuration parameters, please look for `parameter` section of the app metadata.
