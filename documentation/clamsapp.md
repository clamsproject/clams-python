## Using CLAMS App

This document provides general instructions for installing and using CLAMS Apps. 
App developers may provide additional information specific to their app, 
hence it's advised also to look up the app website (or code repository) to get the additional information. 

### Requirements 

Generally, a CLAMS App requires 

- To run the app in a container (as an HTTP server), container management software such as `docker` or `podman`. This is the recommended way to use CLAMS Apps.
  - (the CLAMS team is using `docker` for development and testing, hence the instructions are based on `docker` commands.)
- To run the app locally, Python3 with the `clams-python` module installed. Python 3.8 or higher is required.
- To invoke and execute analysis, HTTP client utility (such as `curl`).

For Python dependencies, usually CLAMS Apps come with `requirements.txt` files that list up the Python library. 
However, there could be other non-Python software/library that are required by the app.

### Installation

CLAMS Apps available on the CLAMS App Directory. Currently, all CLAMS Apps are open-source projects and are distributed as

1. source code downloadable from code repository
2. pre-built container image 

Please visit [the app-directory](https://apps.clams.ai) to see which apps are available and where you can download them.
 
In most cases, you can "install" a CLAMS App by either

1. downloading source code from the app code repository and manually building a container image
2. downloading pre-built container image directly

#### Build an image from source code

To download the source code, you can either use `git clone` command or download a zip file from the source code repository. 
The source code repository address can be found on the App Directory entry of the app.

From the locally downloaded project directory, run the following in your terminal to build an image from the included container specification file.

(Assuming you are using `docker` as your container manager)

```bash
$ docker build . -f Containerfile -t <IMAGE_NAME_YOU_PICK>
```

#### Download prebuilt image

Alternatively, the app maybe already be available on a container registry.

``` bash 
$ docker pull <PREBULIT_IMAGE_NAME>
```

The image name can be found on the App Directory entry of the app.

### Using CLAMS App

CLAMS Apps are primarily designed to run as an HTTP server, but some apps written based on `clams-python` SDK additionally provide CLI equivalent to the HTTP requests. 
In this session, we will first cover the usage of CLAMS apps as an HTTP server, and then cover the (optional) CLI.

#### Starting the HTTP server as a container

Once the image is built (by `docker build`) or downloaded (by `docker pull`), to create and start a container, run:

```bash
$ docker run -v /path/to/data/directory:/data -p <PORT>:5000 <IMAGE_NAME>
```

where `/path/to/data/directory` is the local location of your media files or MMIF objects and `PORT` is the *host* port number you want your container to be listening to. 
The HTTP inside the container will be listening to 5000 by default. Usually any number above 1024 is fine for the host port number, and you can use the same 5000 number for the host port number.

> **Note**
> If you are using a Mac, on recent versions of macOS, port 5000 is used by Airplay Receiver by default. So you may need to use a different port number, or turn off the Airplay Receiver in the System Preferences to release 5000.
> For more information on *safe* port numbers, see [IANA Port Number Registry](https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xhtml) or [Wikipedia](https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers).

> **Note**
> Another note for users of recent Macs with Apple Silicon (M1, M2, etc) CPU: you might see the following error message when you run the container image.
> ```
> The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8) and no specific platform was requested
> ```
> This is because the image you are trying to run is built for Intel/AMD x64 CPUs. To force the container to run on an emulation layer, you can add `--platform linux/amd64` option to the `docker run` command.


### Invoking the app server

#### To get app metadata

Once the app is running as an HTTP server, visit the server address ([localhost:5000](http://localhost:5000), or the remote host name if running on a remote computer) to get the app metadata. 
App metadata is also available at the App Directory entry of the app if the app is published on the App Directory. 
App metadata contains important information about the app that we will use in the following sections.

#### To process input media

To actually run the app and process input media through computational analysis, simply send a POST request to the app with a MMIF input as the request body.

MMIF input files can be obtained from outputs of other CLAMS apps, or you can create an *empty* MMIF only with source media locations using `clams source` command. See the help message for a more detailed instructions. 
(Make sure you have installed [`clams-python` package](https://pypi.org/project/clams-python/) version from PyPI.)

```bash
$ pip install clams-python
$ clams source --help
```

For example; by running 

```bash 
$ clams source audio:/data/audio/some-audio-file.mp3
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

If an app requires just `Document` inputs (see `input` section of the app metadata), an empty MMIF with required media file locations will suffice. 
The location has to be a URL or an absolute path, and it is important to ensure that it exists.

However, some apps only works with input MMIF that already contains some annotations of specific types. To run such apps, you need to run different apps in a sequence. 

(TODO: added CLAMS workflow documentation link here.)

When an input MMIF is ready, you can send it to the app server.
Here's an example of how to use the `curl` command, and store the response in a file `output.mmif`.

```bash
$ clams source audio:/data/audio/some-audio-file.mp3 > input.mmif
$ curl -H "Accept: application/json" -X POST -d@input.mmif -s http://localhost:5000 > output.mmif

# or using a bash pipeline 
$ clams source audio:/data/audio/some-audio-file.mp3 | curl -X POST -d@- -s http://localhost:5000 > output.mmif
```

#### Configuring the app

Running as an HTTP server, CLAMS Apps are stateless, but can be configured for each HTTP request by providing configuration parameters as [query string](https://en.wikipedia.org/wiki/Query_string). 

For example, appending `?pretty=True` to the URL will result in a JSON output with indentation for better readability.

> **Note**
> When you're using `curl` from a shell session, you need to escape the `?` or `&` characters with `\` to prevent the shell from interpreting it as a special character.
 
Different apps have different configurability. For configuration parameters of an app, please refer to `parameter` section of the app metadata.

### Using CLAMS App as a CLI program

First and foremost, not all CLAMS Apps support command line interface (CLI).
At the minimum, a CLAMS app is required to support HTTP interfaces described in the previous section.
If any of the following instructions do not work for an app, it is likely that the app does not support CLI. 

#### Python entry points 

Apps written on `clams-python` SDK have three python entry points by default: `app.py`, `metadata.py`, and `cli.py`.

#### `app.py`: Running app as a local HTTP server

`app.py` is the main entry point for running the app as an HTTP server. 
To run the app as a local HTTP server without containerization, you can run the following command from the source code directory.

```bash
$ python app.py 
```

* By default, the app will be listening to port 5000, but you can change the port number by passing `--port <NUMBER>` option.
* Be default, the app will be running in *debugging* mode, but you can change it to *production* mode by passing `--production` option to support larger traffic volume.
* As you might have noticed, the default `CMD` in the prebuilt containers is `python app.py --production --port 5000`.

#### `metadata.py`: Getting app metadata

Running `metadata.py` will print out the app metadata in JSON format. 

#### `cli.py`: Running as a CLI program

`cli.py` is completely optional for app developers, and unlike the other two above that are guaranteed to be available, `cli.py` may not be available for some apps.
When running an app as a HTTP app, the input MMIF must be passed as POST request's body, and the output MMIF will be returned as the response body.
To mimic this behavior in a CLI, `cli.py` has two positional arguments; 

``` bash 
$ python cli.py <INPUT_MMIF> <OUTPUT_MMIF>  # will read INPUT_MMIF file, process it, and write the result to OUTPUT_MMIF file
```

`<INPUT_MMIF>` and `<OUTPUT_MMIF>` are file paths to the input and output MMIF files, respectively. 
Following the common unix CLI practice, you can use `-` to represent STDIN and/or STDOUT

``` bash
# will read from STDIN, process it, and write the result to STDOUT
$ python cli.py - -  

# or equivalently
$ python cli.py 

# read from a file, write to STDOUT
$ python cli.py input.mmif -

# or equivalently
$ python cli.py input.mmif

# read from STDIN, write to a file
$ cat input.mmif | python cli.py - output.mmif
```

As with the HTTP server, you can pass configuration parameters to the CLI program. 
All parameter names are the same as the HTTP query parameters, but you need to use `--` prefix to indicate that it is a parameter.

``` bash
$ python cli.py --pretty True input.mmif output.mmif
```

Finally, when running the app as a container, you can override the default `CMD` (`app.py`) by passing a `cli.py` command to the `docker run` command.

``` bash
$ cat input.mmif | docker run -i -v /path/to/data/directory:/data <IMAGE_NAME> python cli.py 
```

Note that `input.mmif` is in the host machine, and the container is reading it from the STDIN. 
You can also pass the input MMIF file as a volume to the container. 
However, when you do so, you need to make sure that the file path in the MMIF is correctly set to the file path in the container.

> **Note**
> Here, make sure to pass [`-i` option to the `docker run`](https://docs.docker.com/reference/cli/docker/container/run/#interactive) command to make host's STDIN work properly with the container. 
