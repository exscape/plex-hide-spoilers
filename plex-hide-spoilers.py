#!/usr/bin/env python3

# Copyright 2023-2025 Thomas Backman.
# See LICENSE.txt for further license information.

# Note: Throughout this file, "item" is used to refer to a TV episode *or* a movie.
# Most code works the same regardless of type, though some code can't be shared.

import os
import re
import sys
import time
import argparse

from plexapi.server import PlexServer
from plexapi.alert import AlertListener

try:
    # tomllib ships with Python 3.11+
    import tomllib # novermin -- excludes from vermin version check
except ModuleNotFoundError:
    # tomli (the base for tomllib) is compatible and makes this program
    # compatible with Python 3.8-3.10 as well as 3.11+
    import tomli as tomllib

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

class Action:
    def __init__(self, item, action, field):
        # Lazy man's enums
        assert action in ('hide', 'restore')
        assert field in ('summary', 'title', 'thumb')
        self.item = item
        self.action = action
        self.field = field

    def __repr__(self):
        return f"{self.action} {self.field} of {item_title_string(self.item)}"

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
        config['ignored_items'] = [stripped for line in config['ignored_items'].splitlines() if len(stripped := line.strip()) > 0]
    if 'ignored_items' not in config or not isinstance(config['ignored_items'], list):
        config['ignored_items'] = []

    errors = []
    for setting in ('plex_url', 'plex_token', 'hidden_summary_string', 'hidden_title_string', 'hide_summaries', 'hide_thumbnails', 'hide_titles', 'libraries'):
        if setting not in config or (isinstance(config[setting], str) and len(config[setting]) == 0):
            errors.append(setting)
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
    if not args.quiet: print("Fetching items from Plex...")

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

def has_summary(item):
    return len(item.summary) > 0 and not has_hidden_summary(item)

def has_title(item):
    return len(item.title) > 0 and not has_hidden_title(item) and not generic_title.match(item.title)

def has_thumbnail(item):
    return item.thumb and len(item.thumb) > 0 and not has_hidden_thumbnail(item)

def has_hidden_summary(item):
    return item.summary.startswith(config['hidden_summary_string']) or item.summary.startswith(config['in_progress_string'])

def has_hidden_title(item):
    return item.title.startswith(config['hidden_title_string']) or item.title.startswith(config['in_progress_string'])

def has_hidden_thumbnail(item):
    # TODO: I'm not sure if this is always a valid or not; I can only say that it works for me(tm).
    # Worst-case, it could cause the script to process an item every time it's run.
    return item.type == 'episode' and item.thumb and item.thumb in (item.parentThumb, item.grandparentThumb)

def has_any_hidden_field(item):
    """ True if the item has had its summary or title hidden by this script """
    return has_hidden_summary(item) or has_hidden_title(item) or has_hidden_thumbnail(item)

def item_title_string(item):
    """ Create a string to describe an item. """
    if item.type == 'episode' and has_title(item):
        return f"{item.grandparentTitle} season {item.parentIndex} episode {item.index} \"{item.title}\""
    elif item.type == 'episode':
        return f"{item.grandparentTitle} season {item.parentIndex} episode {item.index}"
    if item.type == 'movie':
        return f"{item.title} ({item.year})"

def compare_items(i):
    """ Create an ordering between items: first shows (by title, season and episode), then movies (by title and year). """
    return (i.type == 'movie', # False is sorted prior to True, so this makes shows sort higher than movies
            i.grandparentTitle if i.type == 'episode' else i.title, # TV show title or movie title
            i.parentIndex if i.type == 'episode' else i.year, # Season for TV shows, year for movies
            i.index if i.type == 'episode' else 0) # Episode number for TV shows

def compare_actions(a):
    """ Create an ordering between actions: sort by hide/restore, then episode/movie """
    return (a.action,) + compare_items(a.item)

def should_ignore_item(item):
    """ Returns true for items we should ignore (never hide any fields for) """
    assert item.type in ('episode', 'movie')
    if item.type == 'episode':
        return item.grandparentTitle.strip() in config['ignored_items']
    if item.type == 'movie':
        return item.title.strip() in config['ignored_items']

def prune_unnecessary_actions(action_list):
    if args.debug: print(f"Before action pruning: {len(action_list)} actions")
    action_list = [action for action in action_list
                   if not (action.action == 'hide' and
                           ((action.field == 'summary' and not has_summary(action.item)) or
                            (action.field == 'title' and not has_title(action.item)) or
                            (action.field == 'thumb' and not has_thumbnail(action.item))))]
    if args.debug: print(f"After action pruning: {len(action_list)} actions")

    return action_list

def calculate_actions(items, also_hide=None, also_unhide=None):
    """ Examine all items and calculate which actions we need to take """

    # There are four cases to handle: two common, two less common, but they can all be handled by the same logic.
    # 1) Show all configured fields from recently seen items
    # 2) Hide all configured fields from unseen items with fields showing (typically recently added items)
    # 3) Hide *some* fields from unseen items (when the config file was changed to hide more fields than previously)
    # 4) Show *some* fields from unseen items (when the config file was changed to show more fields than previously)

    if not args.quiet: print("Calculating action list...")

    action_list = []

    for item in items:
        # Case 1: show all fields for recently seen items, plus ignored items that have hidden fields
        if (item.isPlayed or should_ignore_item(item)):
            if has_hidden_summary(item):
                action_list.append(Action(item, 'restore', 'summary'))
            if has_hidden_title(item):
                action_list.append(Action(item, 'restore', 'title'))
            if has_hidden_thumbnail(item):
                action_list.append(Action(item, 'restore', 'thumb'))
        elif not item.isPlayed and not should_ignore_item(item):
            # Cases 2+3+4: check each field in turn, and create up to one action per field and item
            if has_hidden_summary(item) != config['hide_summaries']:
                action_list.append(Action(item, 'hide' if config['hide_summaries'] else 'restore', 'summary'))
            if item.type == 'episode' and has_hidden_title(item) != config['hide_titles']:
                action_list.append(Action(item, 'hide' if config['hide_titles'] else 'restore', 'title'))
            if item.type == 'episode' and item.thumb and has_hidden_thumbnail(item) != config['hide_thumbnails']:
                action_list.append(Action(item, 'hide' if config['hide_thumbnails'] else 'restore', 'thumb'))

    # There are cases where the code above created unnecessary actions; for example,
    # if has_hidden_summary is false and hide_summaries is true, an action is created to hide the summary.
    # However, it can be the case that there is no summary *at all*, and in that case, we shouldn't
    # replace the empty string with "Summary hidden."
    action_list = prune_unnecessary_actions(action_list)

    # Handle the also_hide and also_unhide arguments.
    # First remove any Action relating to them to avoid duplicates, then add them in.
    if also_hide or also_unhide:
        action_list = [action for action in action_list if action.item not in (also_hide, also_unhide)]
        if also_unhide:
            if has_hidden_summary(also_unhide):
                action_list.append(Action(also_unhide, 'restore', 'summary'))
            if has_hidden_title(also_unhide):
                action_list.append(Action(also_unhide, 'restore', 'title'))
            if has_hidden_thumbnail(also_unhide):
                action_list.append(Action(also_unhide, 'restore', 'thumb'))
        if also_hide:
            if config['hide_summaries']:
                action_list.append(Action(also_hide, 'hide', 'summary'))
            if config['hide_titles'] and also_hide.type == 'episode':
                action_list.append(Action(also_hide, 'hide', 'title'))
            if config['hide_thumbnails'] and also_hide.type == 'episode':
                action_list.append(Action(also_hide, 'hide', 'thumb'))

    return sorted(action_list, key=compare_actions)

def calculate_actions_restore_all(items):
    """ Create an action list that restores everything hidden or locked by this script. """

    if not args.quiet: print("Creating action list for full restore...")

    action_list = []

    for item in items:
        if has_hidden_summary(item):
            action_list.append(Action(item, 'restore', 'summary'))
        if has_hidden_title(item):
            action_list.append(Action(item, 'restore', 'title'))
        if has_hidden_thumbnail(item):
            action_list.append(Action(item, 'restore', 'thumb'))

    return sorted(action_list, key=compare_actions)

def perform_actions(listener, actions):
    """ Actually perform the hide/restore actions that were previously calculated """

    if len(actions) == 0:
        if not args.quiet: print("Nothing to do! Exiting.")
        return

    if not args.quiet:
        num_actions = len(actions)
        num_hides = len({action.item for action in actions if action.action == 'hide'})
        num_restores = len({action.item for action in actions if action.action == 'restore'})
        print(f"Performing {num_actions} actions (hiding fields on {num_hides} items, restoring fields on {num_restores} items)")

    for action in actions:
        if args.verbose: print(f"{'Hiding' if action.action == 'hide' else 'Restoring'} {'thumbnail' if action.field == 'thumb' else action.field} for {item_title_string(action.item)}")

        if action.action == 'hide':
            if action.field == 'summary':
                value = config['hidden_summary_string']
            elif action.field == 'title':
                value = config['hidden_title_string']
            else:
                value = ""

            action.item.editField(action.field, value, locked = config['lock_edited_fields'])
        elif action.action == 'restore':
            # Unlock the field. We also write a temporary message which shows up in Plex almost immediately,
            # while it is still downloading the correct data.
            action.item.editField(action.field, config['in_progress_string'] if action.field != "thumb" else "", locked = False)

    restored_items = {action.item for action in actions if action.action == 'restore'}

    # Tell Plex to re-download data for the restored items, now that every field to restore has been unlocked
    for item in restored_items:
        item.refresh()

    # All API requests have now been sent to Plex, but it may not have finished downloading summaries yet; wait until it's done
    listener.wait_for_finish()

    if not restored_items:
        # We only need to verify / possibly retry if one or more items were restored; hides won't fail unless connection
        # to the server was lost or similar. Plex metadata downloads for restores will fail now and then even with
        # a stable connection.
        if not args.quiet: print("All fields were successfully edited")
        return

    if not args.quiet: print("Beginning verification...")

    to_retry = restored_items # Filtered in the beginning of the loop, after reloading metadata

    for _ in range(3):
        if args.debug: print("Start metadata reload...")
        for item in to_retry:
            item.reload()
        if args.debug: print("Reload finished")

        to_retry = sorted([item for item in to_retry if has_any_hidden_field(item)], key=compare_items)
        if not to_retry:
            if not args.quiet: print("All fields were successfully edited")
            return

        if not args.quiet:
            print(f"Retrying {len(to_retry)} items where Plex failed to restore fields...")
            if args.verbose:
                for item in to_retry:
                    print(f"   Retrying {item_title_string(item)}")

        for item in to_retry:
            item.refresh()

        listener.wait_for_finish()

    failed = sorted([item for item in to_retry if has_any_hidden_field(item)], key=compare_items)

    if not failed and not args.quiet:
        print("All fields were successfully edited")
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

    if failed:
        print("Note: this can mean that Plex simply couldn't find a title/summary/thumbnail for the episode(s)/movie(s) above.")

    sys.exit(0)

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
        actions = calculate_actions_restore_all(items_by_guid.values())
        perform_actions(listener, actions)
        return

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

    actions = calculate_actions(items_by_guid.values(), also_hide_item, also_unhide_item)

    if args.dry_run:
        for action in actions:
            print(f"Would {action.action} {'thumbnail' if action.field == 'thumb' else action.field} for {item_title_string(action.item)}")
        if not actions and not args.quiet:
            print("No changes would be performed.")
        return
    elif not actions and not args.quiet:
        print("Nothing to do! Exiting.")
    elif actions:
        perform_actions(listener, actions)

if __name__=='__main__':
    # Life is so much easier with these in the module/global namespace
    args = parse_args()
    config = read_config(args.config_path)
    generic_title = re.compile(r"^Episode #?\d+")
    if args.debug:
        args.verbose = True
        args.quiet = False
        print(f"Args: {args}")
        print(f"Config dump: {config}")

    main()
