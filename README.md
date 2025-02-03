A script to hide summaries (with potential spoilers) from unseen episodes (and/or movies) in Plex.  
Episode titles and thumbnails can also be hidden.

Please open a Github issue if things aren't working properly, or even if you just have questions!

# Features

* Choose what to hide: summaries (TV and/or movies), episode titles, episode thumbnails.
* Choose exactly which libraries to include (can be TV libraries, movie libraries, or both)
* Ignore list for shows and individual movies (leaves all fields showing, even when unwatched)
* Doesn't need to run on the Plex server -- can run on e.g. a Windows desktop with the Plex server on a NAS
* Fairly performant: runs in a few seconds with a fairly large library
* Tested on Windows and Linux, but should run on just about anything that runs Python

# Stuff left to do

* Improve Plex login. The script currently requires a Plex token, fetched from a logged-in browser.

# Shortcomings

* Really only usable on a server with a single user, since fields are hidden for everyone on the server.

# Updating from v0.2 or earlier

v0.3 contains many changes and is close to being a full rewrite.  
Enough configuration variables changed that I decided to not to support old config files; it would be unclear which defaults to use, among other issues.

I would recommend renaming your old config to config\_old, copying config\_sample to config, and then editing the old config to copy the unchanged settings over to the new one. (Sorry for the inconvenience!)

The following settings remain exactly as they were and can be kept/copied over:  
plex\_url, plex\_token, libraries, ignored\_items

hidden\_string and lock\_hidden\_summaries were removed. (Edited fields are now always locked; disabling that setting was rarely a good idea.)

The following settings were added:
hidden\_summary\_string (string to show in Plex for a hidden summary)  
hidden\_title\_string (string to show in Plex for a hidden title)
hide\_summaries (true/false)  
hide\_titles (true/false)  
hide\_thumbnails (true/false)  
process\_thumbnails (true/false, see config\_sample.toml for a detailed explanation)

# Installation

## Windows

### Binary builds (easiest)

The easiest way to install (recommended for most users) is to use the binary builds. They contain the script itself, a Python interpreter, and all dependencies.

I use PyInstaller to create an easy-to-run build of the script, which while perfectly safe unfortunately seems to trigger Windows Defender at times. I got a detection of "Trojan:Win32/Wacatac.B!ml" when trying it on a different program I've written and know is safe. I have NOT gotten any warnings about this script!  
If you get such a warning, you can either take me at my word when I say that it's a false detection and entirely safe, or use the manual install method detailed below to have more control.

To install this way, download the [latest binary release](https://github.com/exscape/plex-hide-spoilers/releases/) (the latest one named ...-windows.zip), unpack the zip contents where you want them, and then skip to the [Configuration](#configuration) section below.

### Using pip

If you want to do it the harder way, you're somewhat on your own, as I have little experience doing this on Windows.  
I only recommend installing this way if you know how without the instructions, really, but open a Github issue if these instructions don't work and I'll try to help (and update the instructions).

First, make sure you have [Python](https://www.python.org/downloads/) installed. Version 3.8 or higher should work, but generally speaking, download the latest version available, as of this writing 3.13. Let the installer add Python to your PATH, and if needed, reboot.

Download the [latest source release](https://github.com/exscape/plex-hide-spoilers/releases/), and unzip it to your chosen install folder.  
Open up a command prompt or Powershell, cd to the folder and run:

```pwsh
py -m venv venv
Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope CurrentUser
.\venv\Scripts\activate
Set-ExecutionPolicy -ExecutionPolicy Default -Scope CurrentUser
pip install -r .\requirements.txt
```

The execution policy change is (at least for me, on Windows 11 22H2) required for the venv to activate.  
That should get you the script and all dependencies. You should now be able to run it with `python plex-hide-spoilers.py` (**not** `py plex-hide-spoilers.py` as the py launcher doesn't seem to use the virtual environment we just created!).  
If that prints out an error about a missing configuration file, you're good to go! Jump down to [Configuration](#configuration) below.

Note that in order to run the script (with e.g. Task Scheduler) without starting a Powershell prompt and activating the virtual environment, you need to launch it with venv\Scripts\python.exe as the interpreter.  
For example: C:\\...\\plex-hide-spoilers\\venv\\Scripts\\python.exe C:\\...\\plex-hide-spoilers\\plex-hide-spoilers.py

If you don't do this, you will get import errors unless you have the dependencies installed globally.

## Linux

### Binary builds (easiest)

The easiest way to install is to use the binary builds. They contain the script itself, a Python interpreter, and all dependencies. 

Download the [latest binary release](https://github.com/exscape/plex-hide-spoilers/releases/) (the latest one named ...-linux-amd64.tar.bz2), and unpack the zip contents where you want them, then skip to the [Configuration](#configuration) section below.

### Using pip

First, you need at least Python 3.8 installed.  
Next, sure you have pip and venv installed (`apt install python3-pip python3-venv` on Debian, Ubuntu and derivatives).  
Then download the [latest source release](https://github.com/exscape/plex-hide-spoilers/releases/) from Github, unpack it somewhere, and run the following commands (as your user, not as root!):  

```bash
$ python3 -m venv venv
$ source venv/bin/activate
$ python3 -m pip install -r requirements.txt
```

You then need to launch the application in the context of the virtual environment, which can be done in multiple different ways. One is to use the full path to the venv/bin/python3 link, for example `/home/xyz/plex-hide-spoilers/venv/bin/python3 /home/xyz/plex-hide-spoilers/plex-hide-spoilers.py`. While verbose, this is probably the safest way for use in e.g. cron jobs or other ways of scheduling tasks.

Next, look at the [Configuration](#configuration) section below.

# Configuration

Regardless of your operating system, you need to copy the "config\_sample.toml" file to "config.toml" and edit it (with any text editor, Notepad works for Windows users).  
Most settings should be quite straightforward with the comments in the file.

For the "plex\_token" setting, you need to fetch a Plex token from a browser that is currently signed in to your Plex server.  
See for example [this guide](https://www.plexopedia.com/plex-media-server/general/plex-token/) on how to fetch a token. (Ignore the part later in the article about server tokens, the bit you want is at the top!)

If you have any issues with this, open an issue and I'll look at adding proper Plex authentication.

# Usage

When run with no arguments, the script will hide the configured fields from all unseen episodes/movies (except those from ignored shows, see the configuration file), and *unhide* the fields from all episodes/movies you've seen since the last run.  
While the recommended usage is with Tautulli or using a task scheduler, make sure to run the script manually first, to ensure everything is correctly configured.

## With Tautulli

**Please note:** On Windows, running the script via Tautulli will probably show a cmd.exe window while running. I'm not aware of a way to stop this from happening; if you know of a way that works, please create an issue and I'll include it in the README.

A nice way to use the script is together with **[Tautulli](https://tautulli.com/)**, which allows you to run scripts on certain Plex events.
I have it set up to run on "Watched", "Recently added" and (because why not) "Plex Server Back Up".

Under the "Arguments" tab, you can leave everything empty, except for Watched where I recommend using "\<episode\>--also-unhide plex://episode/{plex\_id}\</episode\>\<movie\>--also-unhide plex://movie/{plex\_id}\</movie\>" instead.  
There can be a race condition where Tautulli considers the item watched and calls the script, but Plex has not marked it as watched, and so the script won't do anything.  
With the extra --also-unhide argument, the episode summary will be restored anyway.

## With Windows Task Scheduler

There shouldn't be much of anything to consider here, once everything is configured and works when run manually. If you used the binary download, simply point Task Scheduler to plex-hide-spoilers.exe after editing the configuration file.

If you installed manually with pip, make sure to use the python.exe located under venv\\Scripts in the script install directory, or you'll get import errors and the script won't run. (With task scheduler, it may fail silently and **appear** to run but not do anything at all.)

## With cron, systemd timer etc

As with Windows Task Scheduler above, when running from cron or similar and when installed from source/using pip, keep in mind to use the python binary located under venv\\bin in the script install directory, or you will likely get import failures.  
You might want to use the `--quiet` argument to only print warnings and errors, to avoid getting an email every time the script successfully runs.
