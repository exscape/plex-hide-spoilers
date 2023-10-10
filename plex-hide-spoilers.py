#!/usr/bin/env python3

# Copyright 2023 Thomas Backman.
# See LICENSE.txt for further license information.

import os
import sys
import argparse
import datetime
import subprocess
from urllib.request import pathname2url

try:
    # tomllib ships with Python 3.11+
    import tomllib # novermin -- excludes from vermin version check
except ModuleNotFoundError:
    # tomli (the base for tomllib) is compatible and makes this program
    # compatible with Python 3.8-3.10 as well as 3.11+
    import tomli as tomllib

from plexapi.server import PlexServer

debug = False
config = {}

def parse_args():
    parser = argparse.ArgumentParser(description='Hide Plex summaries from unseen TV episodes.\n\n' +
        'When run without options, this script will hide the summaries for all unwatched episodes ' +
        '(except for shows ignored in the configuration file), and restore the summaries for all episodes ' +
        'watched since the last run.\n' +
        "It will look for config.toml in the same directory as the .py file, and in its parent directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    verbosity = parser.add_mutually_exclusive_group(required=False)
    verbosity.add_argument('--verbose', action="store_true", help="Print each action taken")
    verbosity.add_argument('--quiet', action="store_true", help="Only print when something goes wrong (--dry-run overrides)")

    parser.add_argument('--dry-run', action="store_true", help="Only print what would be changed; don't actually change anything")
    parser.add_argument('--config-path', metavar="PATH", help="Path to the configuration file (config.toml)")

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--restore-all', action='store_true', help="Restore all hidden summaries (tell Plex to re-download them)")
    group.add_argument('--also-hide', metavar="plex://episode/...", help="Additionally hide summary from one episode (see README.md)")
    group.add_argument('--also-unhide', metavar="plex://episode/...", help="Additionally unhide summary from one episode (see README.md)")

    return parser.parse_args()

def read_config(config_path = None):
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
                print(f"Configuration file (config.toml) not found!\nI looked in \"{old_config_dir}\" and \"{config_dir}\".\nDo you need to copy config_sample.toml to config.toml and edit it?")
                sys.exit(1)

    if os.path.isdir(config_path):
        print("Specified configuration file is a directory! --config-path should point to the configuration file itself.")
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
                           'ignored_shows', 'lock_hidden_summaries'):
            print(f"Warning: unknown setting \"{setting}\" in config.toml, ignoring")

    if config['plex_url'] == "http://192.168.x.x:32400" or config['plex_token'] == "...":
        print("You need to edit config.toml and change the Plex server settings to match your server!")
        sys.exit(2)

    return config

def get_plex_sections(plex):
    plex_sections = []

    for library in config['libraries']:
        try:
            plex_sections.append(plex.library.section(library))
        except:
            print(f"Warning: Plex library {library} not found, ignoring")

    return plex_sections

def fetch_episodes(plex):
    if args.verbose: print("Fetching episodes from Plex...")

    episodes_by_guid = {}

    for plex_section in get_plex_sections(plex):
        for show in plex_section.all():
            for season in show:
                for episode in season:
                    episodes_by_guid[episode.guid] = episode

    return episodes_by_guid

def episode_title_string(ep):
    """ Create a string to describe an episode. """
    return f"{ep.grandparentTitle} season {ep.parentIndex} episode {ep.index} \"{ep.title}\""

def hide_summaries(episodes):
    """ Hides/removes the summaries of ALL episodes in the list. """

    for ep in episodes:
        if args.dry_run:
            print(f"Would hide summary for {episode_title_string(ep)}")
            continue

        ep.editField("summary", config['hidden_string'], locked = config['lock_hidden_summaries'])
        if args.verbose: print(f"Hid summary for {episode_title_string(ep)}")

def restore_summaries(episodes):
    """ Restore the summaries for recently viewed episodes """

    for ep in episodes:
        if not ep.summary.startswith(config['hidden_string']):
            continue

        if args.dry_run:
            print(f"Would restore summary for {episode_title_string(ep)}")
            continue

        ep.editField("summary", ep.summary, locked = False)
        ep.refresh()
        if args.verbose: print(f"Restored summary for {episode_title_string(ep)}")

def compare_episodes(e):
    """ Create a simple ordering between episodes (by show, then season, then episode) """
    return (e.grandparentTitle, e.parentIndex, e.index)

def process(episodes, also_hide=None, also_unhide=None):

    # Step 1: restore summaries of episodes we've seen (since last run)

    unseen_eps = [ep for ep in episodes if not ep.isPlayed]
    seen_eps = [ep for ep in episodes if ep.isPlayed]

    if debug: print(f"Done sorting seen vs unseen; seen {len(seen_eps)}, unseen {len(unseen_eps)}, total {len(episodes_by_guid)} episodes")

    to_unhide = {ep for ep in seen_eps if ep.summary.startswith(config['hidden_string'])}

    if also_unhide:
        to_unhide.add(also_unhide)

    # Also unhide all currently hidden episodes from ignored shows
    ignored_to_unhide = [ep for ep in episodes
                         if ep.grandparentTitle in config['ignored_shows']
                         and ep.summary.startswith(config['hidden_string'])]

    to_unhide.update(ignored_to_unhide)

    if to_unhide:
        if args.dry_run or not args.quiet:
            print("Would restore" if args.dry_run else "Restoring" + f" {len(to_unhide)} summaries (recently watched episodes or ignored shows)")
        restore_summaries(sorted(to_unhide, key=compare_episodes))
    elif not args.quiet:
        print("No watched episodes since last run")

    # Step 2: hide summaries of recently added, unseen episodes

    to_hide = {ep for ep in unseen_eps
               if len(ep.summary.strip()) > 0
               and ep.grandparentTitle not in config['ignored_shows']
               and not ep.summary.startswith(config['hidden_string'])}

    if also_hide:
        to_hide.add(also_hide)

    if to_hide:
        if args.dry_run or not args.quiet:
            print("Would hide" if args.dry_run else "Hiding" + f" {len(to_hide)} summaries (recently added episodes or unignored shows)")
        hide_summaries(sorted(to_hide, key=compare_episodes))
    elif not args.quiet:
        print("No new episodes to hide summaries for")

if __name__=='__main__':
    args = parse_args()
    config = read_config(args.config_path)
    if debug:
        args.verbose = True
        args.quiet = False
        print(f"Args: {args}")
        print(f"Config dump: {config}")

    try:
        plex = PlexServer(config['plex_url'], config['plex_token'])
    except Exception as e:
        print(f"Unable to connect to Plex server! Error from API: {e}")
        sys.exit(16)

    episodes_by_guid = fetch_episodes(plex)

    if args.restore_all:
        restore_summaries(episodes_by_guid.values())
    else:
        also_hide_ep = None
        also_unhide_ep = None

        if args.also_hide:
            try:
                also_hide_ep = episodes_by_guid[args.also_hide]
            except:
                print(f"Failed to locate episode with GUID {args.also_hide} specified with --also-hide, ignoring", file=sys.stderr)

        if args.also_unhide:
            try:
                also_unhide_ep = episodes_by_guid[args.also_unhide]
            except:
                print(f"Failed to locate episode with GUID {args.also_unhide} specified with --also-unhide, ignoring", file=sys.stderr)

        process(episodes_by_guid.values(), also_hide_ep, also_unhide_ep)
