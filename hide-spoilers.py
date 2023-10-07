#!/usr/bin/env python3

import os
import sys
import argparse
import datetime
import subprocess
import sqlite3
from urllib.request import pathname2url

try:
    # tomllib ships with Python 3.11+
    import tomllib # novermin -- excludes from vermin version check
except ModuleNotFoundError:
    # tomli (the base for tomllib) is compatible and makes this program
    # compatible with Python 3.6-3.10 as well as 3.11+
    import tomli as tomllib

from plexapi.server import PlexServer

from src.Database import Database

debug = False
verbose = False
dry_run = False
config = {}

def parse_args():
    parser = argparse.ArgumentParser(description='Hide Plex summaries from unseen TV episodes')

    main_group = parser.add_mutually_exclusive_group(required=True)
    main_group.add_argument('--process-all', action='store_true',  help="Main option. Hide summaries from all new episodes, and unhide from recently watched")
    main_group.add_argument('--restore-all', action='store_true',  help="Restore and unlock all summaries. Mostly useful to stop using this software")
    main_group.add_argument('--lock-all',    action='store_true',  help="Lock the summary of all episodes with hidden summaries, so that Plex won't change them back")
    main_group.add_argument('--unlock-all',  action='store_true',  help="Unlock the summary of ALL episodes, hidden summary or not")

    hide_unhide = parser.add_mutually_exclusive_group(required=False)
    hide_unhide.add_argument('--hide', metavar="plex://episode/...", help="Additionally hide summary from one episode (see README.md)")
    hide_unhide.add_argument('--unhide', metavar="plex://episode/...", help="Additionally unhide summary from one episode (see README.md)")

    parser.add_argument('--dry-run', action="store_true", help="Only print what would be changed; don't actually change anything")
    parser.add_argument('--verbose', action="store_true", help="Print each action taken")
    parser.add_argument('--config-dir', help="Path to the directory containing the configuration file (config.toml) and database")

    return parser.parse_args()

def read_config(config_dir = None):
    global config

    if config_dir:
        config_dir = os.path.abspath(config_dir)
        config_path = os.path.join(config_dir, "config.toml")
    else:
        # If config_dir = None, first look at the directory containing the script/executable,
        # then its parent directory -- as __file__ points to a subdirectory with PyInstaller 6.0+.
        script_abspath = os.path.abspath(__file__)
        config_dir = os.path.dirname(script_abspath)
        config_path = os.path.join(config_dir, "config.toml")
        if not os.path.exists(config_path):
            old_config_dir = config_dir
            config_dir = os.path.dirname(config_dir)
            config_path = os.path.join(config_dir, "config.toml")
            if not os.path.exists(config_path):
                print(f"Configuration file (config.toml) not found!\nI looked in \"{old_config_dir}\" and \"{config_dir}\".\nDo you need to copy config_sample.toml to config.toml and edit it?")
                sys.exit(1)

    try:
        conf_file = open(config_path, "rb")
        config = tomllib.load(conf_file)
        conf_file.close()
    except FileNotFoundError:
        print(f"Configuration file ({config_path}) not found!\nDo you need to copy config_sample.toml to config.toml and edit it?")
        sys.exit(1)
    except tomllib.TOMLDecodeError as e:
        print(f"Configuration file ({config_path}) invalid: {e}")
        sys.exit(2)
    except:
        print(f"Unable to read configuration file ({config_path}) -- no read permission?")
        sys.exit(4)

    if config is None or type(config) != dict:
        print("Configuration file invalid")
        sys.exit(2)

    if not 'lock_hidden_summaries' in config:
        config['lock_hidden_summaries'] = True
    if not 'lock_restored_summaries' in config:
        config['lock_restored_summaries'] = False

    if 'ignored_shows' in config:
        config['ignored_shows'] = list(filter(lambda x: len(x) > 0, config['ignored_shows'].splitlines()))
    if not 'ignored_shows' in config or type(config['ignored_shows']) != list:
        config['ignored_shows'] = []

    for setting in ('plex_url', 'plex_token', 'hidden_string', 'libraries'):
        if not setting in config or len(config[setting]) == 0:
            print(f"No {setting} specified in config.toml")
            sys.exit(8)

    for setting in config:
        if setting not in ('plex_url', 'plex_token', 'hidden_string', 'libraries',
                           'ignored_shows', 'lock_hidden_summaries', 'lock_restored_summaries'):
            print(f"Warning: unknown setting \"{setting}\" in config.toml, ignoring")

    if config['plex_url'] == "http://192.168.x.x:32400" or config['plex_token'] == "...":
        print("You need to edit config.toml and change the Plex server settings to match your server!")
        sys.exit(2)

    if not 'dbpath' in config:
        config['dbpath'] = os.path.join(config_dir, "summaries.sqlite3")

    return config

def get_plex_sections(plex):
    plex_sections = []

    for library in config['libraries']:
        try:
            plex_sections.append(plex.library.section(library))
        except:
            print(f"Warning: Plex library {library} not found, ignoring")

    return plex_sections

def update_database(plex):
    """ Download all shows + episodes from Plex and update the database, so that we're not missing anything new """

    # TODO: This never removes anything from the database. We may want to remove data referring to episodes removed from Plex.
    # I'm not 100% sure if our hidden summaries can remain hidden if you remove and then re-add something to Plex, so prior to
    # properly testing that, I'll just leave everything.

    episodes_by_guid = {}
    added_episodes = 0

    for plex_section in get_plex_sections(plex):
        for show in plex_section.all():
            for season in show:
                for episode in season:
                    # This also adds the show to the database if not present
                    if database.add_episode(episode, season, show):
                        added_episodes += 1
                    episodes_by_guid[episode.guid] = episode

    database.commit_changes()

    if debug: print(f"update_database() completed! {added_episodes} episodes inserted")

    return episodes_by_guid

def hide_summaries(database, episodes):
    """ Hides/removes the summaries of ALL episodes in the list. """
    for episode in episodes:
        # Sanity check: ensure we have the summary for this episode stored before we delete it from Plex
        try:
            summary = database.summary_for_episode(episode.guid)
        except KeyError:
            print(f"Summary for {episode.grandparentTitle} episode {episode.title} not found in database, not hiding from Plex")
            continue

        if dry_run:
            print(f"Would hide summary for {episode.grandparentTitle} episode {episode.title}")
            continue

        episode.editField("summary", config['hidden_string'], locked = config['lock_hidden_summaries'])
        if verbose: print(f"Hid summary for {episode.grandparentTitle} episode {episode.title}")

def restore_summaries(database, guids, episodes_by_guid):
    """ Restore the summaries for recently viewed episodes (guids) """

    for guid in guids:
        try:
            ep = episodes_by_guid[guid]

            if not ep.summary.startswith(config['hidden_string']):
                continue

            summary = database.summary_for_episode(guid)
            if dry_run:
                print(f"Would restore summary for {ep.grandparentTitle} episode {ep.title}")
                continue

            ep.editField("summary", summary, locked = config['lock_restored_summaries'])
            if verbose: print(f"Restored summary for {ep.grandparentTitle} episode {ep.title}")

        except:
            try:
                print(f"Failed to restore summary for episode {ep.grandparentTitle} episode {ep.title}", file=sys.stderr)
            except:
                print(f"Failed to restore summary for episode with GUID {guid} (title/series unknown)", file=sys.stderr)

            continue

def process_all(database, episodes_by_guid, also_hide=None, also_unhide=None):

    # Step 1: restore summaries of episodes we've seen (since last run)

    unseen_eps = {guid: ep for (guid,ep) in episodes_by_guid.items() if not ep.isPlayed}
    seen_eps = {guid: ep for (guid,ep) in episodes_by_guid.items() if ep.isPlayed}

    if debug: print(f"Done sorting seen vs unseen; seen {len(seen_eps)}, unseen {len(unseen_eps)}, total {len(episodes_by_guid)} episodes")

    to_unhide = set(filter(lambda x: seen_eps[x].summary.startswith(config['hidden_string']), seen_eps))

    if also_unhide:
        to_unhide.add(also_unhide)

    # Also unhide all currently hidden episodes from ignored shows
    ignored_to_unhide = [guid for (guid,ep) in episodes_by_guid.items()
                         if ep.grandparentTitle in config['ignored_shows']
                         and ep.summary.startswith(config['hidden_string'])]

    to_unhide.update(ignored_to_unhide)

    if to_unhide:
        print("Would restore" if dry_run else "Restoring" + f" {len(to_unhide)} summaries (recently watched episodes or ignored shows)")
        restore_summaries(database, to_unhide, episodes_by_guid)
    else:
        print("No watched episodes since last run")

    # Step 2: hide summaries of recently added, unseen episodes

    to_hide = {guid: ep for (guid, ep) in unseen_eps.items()
               if len(ep.summary.strip()) > 0
               and ep.grandparentTitle not in config['ignored_shows']
               and not ep.summary.startswith(config['hidden_string'])}

    if also_hide:
        try:
            to_hide[also_hide] = episodes_by_guid[also_hide]
        except:
            print(f"Failed to locate episode with GUID {also_hide} specified with --hide, ignoring", file=sys.stderr)

    if to_hide:
        print("Would hide" if dry_run else "Hiding" + f" {len(to_hide)} summaries (recently added episodes or unignored shows)")
        hide_summaries(database, to_hide.values())
    else:
        print("No new episodes to hide summaries for")

def restore_all(database, episodes_by_guid):
    return restore_summaries(database, episodes_by_guid.keys(), episodes_by_guid)

def lock_all(episodes_by_guid):
    for ep in episodes_by_guid.values():
        if verbose or dry_run:
            if dry_run:
                print(f"Would lock {ep.grandparentTitle} episode {ep.title} summary")
                continue
            else:
                print(f"Locking {ep.grandparentTitle} episode {ep.title} summary")

        ep.editField("summary", ep.summary, locked = lock)

def unlock_all(plex):
    for plex_section in get_plex_sections(plex):
        if dry_run:
            print(f"Would unlock all items in Plex library {plex_section.title}")
            continue

        if verbose: print(f"Unlocking all items in Plex library {plex_section.title}")
        plex_section.unlockAllField("summary")

if __name__=='__main__':
    args = parse_args()
    config = read_config(args.config_dir)
    if debug:
        print(f"Args: {args}")
        print(f"Config dump: {config}")

    if (args.hide or args.unhide) and not args.process_all:
        print("--hide and --unhide requires --process-all", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        verbose = True
    if args.dry_run:
        dry_run = True
    if debug:
        verbose = True

    database = Database(config, verbose, debug)
    if debug: print("Database loaded/created successfully")

    try:
        plex = PlexServer(config['plex_url'], config['plex_token'])
    except Exception as e:
        print(f"Unable to connect to Plex server! Error from API: {e}")
        sys.exit(16)

    if verbose: print("Updating database prior to operation...")
    episodes_by_guid = update_database(plex)  # TODO: this is really ugly, but saves us looping through Plex twice

    if args.process_all:
        process_all(database, episodes_by_guid, also_hide=args.hide, also_unhide=args.unhide)
    elif args.restore_all:
        restore_all(database, episodes_by_guid)
        unlock_all(plex)
    elif args.lock_all:
        episodes_to_lock = {guid: ep for (guid,ep) in episodes_by_guid.items() if ep.summary.startswith(config['hidden_string'])}
        lock_all(episodes_to_lock)
    elif args.unlock_all:
        unlock_all(plex)
