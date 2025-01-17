#!/usr/bin/env python3

# Copyright 2023-2025 Thomas Backman.
# See LICENSE.txt for further license information.

# Note: Throughout this file, "item" is used to refer to a TV episode *or* a movie.
# Most code works the same regardless of type, though some code can't be shared.

import os
import sys
import time
import argparse

try:
    # tomllib ships with Python 3.11+
    import tomllib # novermin -- excludes from vermin version check
except ModuleNotFoundError:
    # tomli (the base for tomllib) is compatible and makes this program
    # compatible with Python 3.8-3.10 as well as 3.11+
    import tomli as tomllib

from plexapi.server import PlexServer
from plexapi.alert import AlertListener

config = {}

class PlexListener:
    """ Listen to Plex activity (to allow us to wait for it to finish async processing) """
    def __init__(self, server):
        self.last_update = 0
        self.alert_listener = AlertListener(server, self._callback)
        self.alert_listener.start()

    def _callback(self, msg):
        """ Receive messages from Plex """
        if 'type' not in msg or 'size' not in msg:
            return
        try:
            # I hate this, but can't find a much better way.
            # try/except doesn't work because we need to check two cases even if the first raises an exception.
            # These are the message types I've seen while unlocking, restoring and hiding summaries.
            if (msg['type'] == 'timeline' and msg['size'] >= 1 and 'state' in msg['TimelineEntry'][0]) or \
               (msg['type'] == 'activity' and msg['size'] >= 1 and 'Activity' in msg['ActivityNotification'][0] and \
                'type' in msg['ActivityNotification'][0]['Activity'] and \
                msg['ActivityNotification'][0]['Activity']['type'] in ('library.update.item.metadata', 'library.refresh.items')):

                self.last_update = time.time()
        except (KeyError, IndexError):
            return

    def time_since_last_update(self):
        """ Returns the time (in seconds) since we last received a status update """
        if self.last_update == 0:
            self.last_update = time.time()
            return 0

        return time.time() - self.last_update

    def wait_for_finish(self, timeout = 2):
        """ Waits for Plex to finish async processing (until timeout seconds have passed since the last message) """
        if not args.quiet:
            print("Waiting for Plex to finish processing...", end="", flush=True)

        while self.time_since_last_update() < timeout:
            if not args.quiet:
                print(".", end="", flush=True)
                time.sleep(0.5)
            else:
                time.sleep(0.1)

        if not args.quiet:
            print(" done", flush=True)

def parse_args():
    """ Parses command line arguments and returns the "args" object """
    parser = argparse.ArgumentParser(description='Hide Plex summaries (and more) from unseen TV episodes and movies.\n\n' +
        'When run without options, this script will hide the fields selected in the config file for all unwatched items (episodes + movies) -- ' +
        'except for shows ignored in the configuration file -- in the chosen libraries, and restore the hidden fields for all items ' +
        'watched since the last run.\n' +
        "It will look for config.toml in the same directory as the .py file, and in its parent directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    verbosity = parser.add_mutually_exclusive_group(required=False)
    verbosity.add_argument('--verbose', action="store_true", help="Print each action taken")
    verbosity.add_argument('--quiet', action="store_true", help="Only print when something goes wrong (--dry-run overrides)")

    parser.add_argument('--dry-run', action="store_true", help="Only print what would be changed; don't actually change anything")
    parser.add_argument('--config-path', metavar="PATH", help="Path to the configuration file (config.toml)")

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--restore-all', action='store_true', help="Restore all hidden fields (tell Plex to re-download them)")
    group.add_argument('--also-hide', metavar="plex://.../...", help="Additionally hide fields from one item (see README.md)")
    group.add_argument('--also-unhide', metavar="plex://.../...", help="Additionally unhide fields from one item (see README.md)")

    # Print extra debug information; not shown in the help message
    parser.add_argument('--debug', action="store_true", help=argparse.SUPPRESS)

    return parser.parse_args()

def read_config(config_path = None):
    """ Read the configuration file and return a config object """
    global config

    if not config_path:
        # First look at the directory containing the script/executable,
        # then its parent directory -- as __file__ points to a subdirectory with PyInstaller 6.0+.
        script_abspath = os.path.abspath(__file__)
        config_dir = os.path.dirname(script_abspath)
        config_path = os.path.join(config_dir, "config.toml")
        if not os.path.exists(config_path):
            old_config_dir = config_dir
            config_dir = os.path.dirname(config_dir)
            config_path = os.path.join(config_dir, "config.toml")
            if not os.path.exists(config_path):
                print(f"Configuration file (config.toml) not found!\nI looked in \"{old_config_dir}\" and \"{config_dir}\".\n" +
                       "Do you need to copy config_sample.toml to config.toml and edit it?")
                sys.exit(1)

    if os.path.isdir(config_path):
        print("Specified configuration file is a directory! --config-path should point to the configuration file itself.")
        sys.exit(1)

    try:
        with open(config_path, "rb") as conf_file:
            config = tomllib.load(conf_file)
    except FileNotFoundError:
        print(f"Configuration file ({config_path}) not found!\nDo you need to copy config_sample.toml to config.toml and edit it?")
        sys.exit(1)
    except tomllib.TOMLDecodeError as e:
        print(f"Configuration file ({config_path}) invalid: {e}")
        sys.exit(2)
    except:
        print(f"Unable to read configuration file ({config_path}) -- no read permission?")
        sys.exit(4)

    if config is None or not isinstance(config, dict):
        print("Configuration file invalid")
        sys.exit(2)

    if 'ignored_items' in config:
        config['ignored_items'] = list(filter(lambda x: len(x) > 0, config['ignored_items'].splitlines()))
    if 'ignored_items' not in config or not isinstance(config['ignored_items'], list):
        config['ignored_items'] = []

    errors = []
    for setting in ('plex_url', 'plex_token', 'hidden_summary_string', 'hidden_title_string', 'hide_summaries', 'hide_thumbnails', 'hide_titles', 'libraries'):
        if setting not in config or (type(config[setting]) == 'str' and len(config[setting]) == 0):
            errors.append(setting)
            error_found = True
    if errors:
        print("One or more settings is missing from config.toml -- please see config_sample.toml and update your config file")
        for error in errors:
            print(f"* {error}")
        sys.exit(8)

    if config['hide_thumbnails'] and not (config['hide_summaries'] or config['hide_titles']):
        print("Your config is set to hide thumbnails only, and not summaries or titles. This configuration is unfortunately not supported, "
              "as the edited title or summary is needed to identify which items are edited by the script, and which are unmodified.")
        print("If you want to hide thumbnails, enable hide_summaries or hide_titles as well.")
        sys.exit(2)

    for setting in config:
        if setting not in ('plex_url', 'plex_token', 'hidden_string', 'libraries',
                           'ignored_items', 'lock_hidden_summaries', 'hidden_summary_string', 'hidden_title_string', 'lock_edited_fields',
                           'hide_summaries', 'hide_thumbnails', 'hide_titles'):
            print(f"Warning: unknown setting \"{setting}\" in config.toml, ignoring")

    if config['plex_url'] == "http://192.168.x.x:32400" or config['plex_token'] == "...":
        print("You need to edit config.toml and change the Plex server settings to match your server!")
        sys.exit(2)

    # Not intended as a user-facing setting, but fits in config anyway
    config['in_progress_string'] = "(Restore in progress...)"

    return config

def has_hidden_field(item):
    """ True if the item has had its summary or title hidden by this script """
    summary = item.summary
    title = item.title
    return summary.startswith(config['hidden_summary_string']) or summary.startswith(config['in_progress_string']) or \
           title.startswith(config['hidden_title_string']) or title.startswith(config['in_progress_string'])

def has_field_to_hide(item):
    """ True if an item has at least one field visible that should be hidden. """
    summary = item.summary
    title = item.title

    # TODO: does the thumbnail part always work? It works for me(tm) as Plex seems to use the season thumbnail when we clear and lock an episode thumbnail.
    return (config['hide_summaries'] and len(summary) > 0 and not summary.startswith(config['hidden_summary_string'])) or \
           (config['hide_titles'] and item.type == 'episode' and len(title) > 0 and not title.startswith(config['hidden_title_string'])) or \
           (config['hide_thumbnails'] and item.type == 'episode' and item.thumb and item.thumb not in (item.parentThumb, item.grandparentThumb))

def get_plex_sections(plex):
    """ Fetch a list of Plex LibrarySection objects from our config file list of libraries """
    plex_sections = []

    for library in config['libraries']:
        try:
            section = plex.library.section(library)
            if section.type in ('movie', 'show'):
                plex_sections.append(section)
            else:
                print("Warning: Plex library {library} is not a TV or movie library, ignoring")
        except:
            print(f"Warning: Plex library {library} not found, ignoring")

    return plex_sections

def fetch_items(plex):
    """ Fetch objects representing all episodes/movies from Plex """
    if args.verbose: print("Fetching items from Plex...")

    items_by_guid = {}

    for plex_section in get_plex_sections(plex):
        if plex_section.type == 'show':
            for show in plex_section.all():
                for season in show:
                    for episode in season:
                        items_by_guid[episode.guid] = episode
                        if args.debug: print(f"Found {item_title_string(episode)} ({episode.guid})")
        elif plex_section.type == 'movie':
            for movie in plex_section.all():
                items_by_guid[movie.guid] = movie
                if args.debug: print(f"Found {item_title_string(movie)} ({movie.guid})")

    return items_by_guid

def item_title_string(item):
    """ Create a string to describe an item. """
    if item.type == 'episode':
        return f"{item.grandparentTitle} season {item.parentIndex} episode {item.index} \"{item.title}\""
    if item.type == 'movie':
        return f"{item.title} ({item.year})"

def hide_fields(items):
    """ Hides/removes the selected fields of ALL items in the list. """

    for item in items:
        if args.dry_run:
            print(f"Would hide selected fields for {item_title_string(item)}")
            continue

        if config['hide_summaries']:
            item.editField("summary", config['hidden_summary_string'], locked = config['lock_edited_fields'])

        if config['hide_titles'] and item.type == 'episode':
            item.editField("title", config['hidden_title_string'], locked = config['lock_edited_fields'])

        if config['hide_thumbnails'] and item.type == 'episode':
            item.editField("thumb", "", locked = config['lock_edited_fields'])

        if args.verbose: print(f"Hid selected fields for {item_title_string(item)}")

def restore_fields(listener, items, force_restore = False):
    """ Restore all fields for ALL edited items in the list. """

    to_restore = [item for item in items if (force_restore or has_hidden_field(item))]

    if args.dry_run:
        for item in to_restore:
            print(f"Would restore fields for {item_title_string(item)}")
        return

    for item in to_restore:
        if item.summary == config['hidden_summary_string']:
            item.editField("summary", config['in_progress_string'], locked = False)
        if item.type == 'episode' and item.title == config['hidden_title_string']:
            item.editField("title", config['in_progress_string'], locked = False)
        if item.type == 'episode' and item.thumb == "":
            item.editField("thumb", "", locked = False)

        item.refresh()
        if args.verbose: print(f"Restored fields for {item_title_string(item)}")

    # All API requests are now sent to Plex, but it may not have finished downloading summaries yet
    listener.wait_for_finish()

    if not args.quiet: print("Beginning verification...")

    # Some requests seem to randomly fail (for me usually 1 or 2 out of about 1000); we want to try downloading them again
    for _ in range(3):
        if args.debug: print("Start metadata reload...")
        for item in to_restore:
            item.reload()
        if args.debug: print("Reload finished")

        to_restore = [item for item in to_restore if has_hidden_field(item)]
        if not to_restore:
            if not args.quiet: print("All fields were successfully restored")
            return

        if not args.quiet:
            print(f"Retrying {len(to_restore)} items where Plex failed to restore fields...")
            if args.verbose:
                for item in to_restore:
                    print(f"   Retrying {item_title_string(item)}")

        for item in to_restore:
            item.refresh()

        listener.wait_for_finish()

    failed = [item for item in to_restore if has_hidden_field(item)]

    if not failed and not args.quiet:
        print("All fields were successfully restored")
        return

    for item in failed:
        # Clear any "in progress" fields for the failed items, and make sure the fields are not locked
        if len(item.summary) == 0 or item.summary == config['in_progress_string']:
            item.editField("summary", "", locked = False)
        if len(item.title) == 0 or item.title == config['in_progress_string']:
            item.editField("title", "", locked = False)
        if item.thumb == "":
            item.editField("thumb", "", locked = False)

        print(f"Failed to restore fields for {item_title_string(item)}")

def compare_items(i):
    """ Create an ordering between items: first shows (by title, season and episode), then movies (by title and year). """
    return (i.type == 'movie', # False is sorted prior to True, so this makes shows sort higher than movies
            i.grandparentTitle if i.type == 'episode' else i.title, # TV show title or movie title
            i.parentIndex if i.type == 'episode' else i.year, # Season for TV shows, year for movies
            i.index if i.type == 'episode' else 0) # Episode number for TV shows

def should_ignore_item(item):
    """ Returns true for items we should ignore (never hide any fields for) """
    assert item.type in ('episode', 'movie')
    if item.type == 'episode':
        return item.grandparentTitle in config['ignored_items']
    if item.type == 'movie':
        return item.title in config['ignored_items']

def process(listener, items, also_hide=None, also_unhide=None):
    """ The workhorse method. Hide fields for recently added items, unhide for recently watched items. """

    need_to_wait = False

    # Step 1: restore fields of items we've seen (since last run)

    unseen_items = [item for item in items if not item.isPlayed]
    seen_items = [item for item in items if item.isPlayed]

    if args.debug: print(f"Done sorting seen vs unseen; seen {len(seen_items)}, unseen {len(unseen_items)}, total {len(items)} items")

    to_unhide = {item for item in seen_items if has_hidden_field(item)}

    if also_unhide:
        to_unhide.add(also_unhide)

    # Also unhide all currently hidden episodes from ignored shows + ignored movies
    ignored_to_unhide = [item for item in items if should_ignore_item(item) and has_hidden_field(item)]

    to_unhide.update(ignored_to_unhide)

    if to_unhide:
        if (args.dry_run or not args.quiet) and not args.verbose:
            # If verbose, we print each episode restored, so we don't need this too
            print(("Would restore" if args.dry_run else "Restoring") + \
                  f" fields for {len(to_unhide)} recently watched (or ignored) items")
        restore_fields(listener, sorted(to_unhide, key=compare_items))
        # need_to_wait should still be False here, since restore_fields waits and verifies prior to returning
    elif not args.quiet:
        print("No watched items since last run")

    # Step 2: hide fields of recently added, unseen items
    # This also hides additional fields of items when settings have changed, e.g. hide_thumbnails changed from false to true

    to_hide = {item for item in unseen_items
               if not should_ignore_item(item)
               and has_field_to_hide(item)}

    if also_hide:
        to_hide.add(also_hide)

    # If --also-unhide is used on an item marked as unwatched, we need to handle this manually, or
    # it will get re-hidden immediately.
    if also_unhide and also_unhide in to_hide:
        to_hide.remove(also_unhide)

    if to_hide:
        if (args.dry_run or not args.quiet) and not args.verbose:
            # If verbose, we print each episode hidden, so we don't need this too
            print(("Would hide" if args.dry_run else "Hiding") + f" fields for {len(to_hide)} recently added (or unignored) items")
        hide_fields(sorted(to_hide, key=compare_items))
        if not args.dry_run:
            need_to_wait = True
    elif not args.quiet:
        print("No new items to hide fields for")

    return need_to_wait

def main():
    """ The main method. To avoid polluting the global namespace with variables. """
    try:
        plex = PlexServer(config['plex_url'], config['plex_token'])
    except Exception as e:
        print(f"Unable to connect to Plex server! Error from API: {e}")
        sys.exit(16)

    listener = PlexListener(plex)

    items_by_guid = fetch_items(plex)

    if args.restore_all:
        if not args.quiet: print("This can take a while.")
        restore_fields(listener, items_by_guid.values(), force_restore = True)
    else:
        also_hide_item = None
        also_unhide_item = None

        if args.also_hide:
            try:
                also_hide_item = items_by_guid[args.also_hide]
            except:
                print(f"Failed to locate item with GUID {args.also_hide} specified with --also-hide, ignoring", file=sys.stderr)

        if args.also_unhide:
            try:
                also_unhide_item = items_by_guid[args.also_unhide]
            except:
                print(f"Failed to locate item with GUID {args.also_unhide} specified with --also-unhide, ignoring", file=sys.stderr)

        need_to_wait = process(listener, items_by_guid.values(), also_hide_item, also_unhide_item)
        if need_to_wait:
            listener.wait_for_finish()

if __name__=='__main__':
    # Life is so much easier with these in the module/global namespace
    args = parse_args()
    config = read_config(args.config_path)
    if args.debug:
        args.verbose = True
        args.quiet = False
        print(f"Args: {args}")
        print(f"Config dump: {config}")

    main()
