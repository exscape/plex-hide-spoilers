Hide summaries (with potential spoilers) from unseen episodes in Plex.

While this works great for me, it is not "production quality" (yet?). You may find a use for it, but it does still need work.

## TODO items

* Improve (well... support) Plex login. The program ccurrently requires a Plex token, fetched from a logged-in browser.
* Support movie libraries (currently only tested on TV shows)
* Allow thumbnail replacement/blurring
* Improve handling of episodes/shows deleted from Plex (currently, nothing is ever deleted from the program's database)

## Requirements

In short, you need a recent enough Python version (3.11 is definitely recent enough, not sure about older versions than that), and the [Python Plex API bindings](https://python-plexapi.readthedocs.io/en/latest/introduction.html).

## Usage

You can, for example, call this (with the --process-all argument) from cron or a systemd timer.
With --process-all, the script will hide the summaries from all unseen episodes (except from ignored shows, see the configuration file), and *unhide* the summaries from all episodes you've seen since the last run.

### With Tautulli

A nicer way to use it is together with **[Tautulli](https://tautulli.com/)**, which allows you to run scripts on certain Plex events.
I have it set up to run on "Watched", "Recently added" and (because why not) "Plex Server Back Up".

Under the "Arguments" tab, use "--process-all", except for Watched where I recommend using "--process-all <episode>--unhide plex://episode/{plex\_id}</episode>" instead.
There seems to be a race condition where Tautulli considers the episode watched and calls the script, but Plex has not marked it as watched, and so the script won't do anything.
With the extra --unhide argument, the episode summary will be restored anyway.
