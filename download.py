#! /usr/bin/env python3
"""Download all wuecampus courses as described in a mask.txt
"""

import argparse
import os
import re
import shutil
from pathlib import Path
from typing import Any, List

import passwords
import wuecampy
import yaml
from colorama import Fore, Style
from tqdm import tqdm

STRIP_ANSI_PATTERN = re.compile(r"\x1b\[[;\d]*[A-Za-z]", re.VERBOSE).sub


def strip_ANSI(stripping_string: str) -> str:
    """String ANSI formatting from string?
    https://stackoverflow.com/questions/14889454/printed-length-of-a-string-in-python

    Args:
        stripping_string (str): An input string

    Returns:
        str: The stripped string
    """
    return STRIP_ANSI_PATTERN("", stripping_string)


class Status:
    """Status strings to be printed

    Attributes:
        adding     (str): Indicator for adding     files
        deprecated (str): Indicator for deprecated files
        nothing    (str): Indicator for            files nothing happens to
        removing   (str): Indicator for removing   files
    """

    adding = f"{Fore.GREEN}[+]{Style.RESET_ALL}"
    removing = f"{Fore.RED}[-]{Style.RESET_ALL}"
    deprecated = f"{Fore.CYAN}[x]{Style.RESET_ALL}"
    nothing = f"{Fore.WHITE }[~]{Style.RESET_ALL}"


def rule_to_regex(rule: str, prefix: str = "", suffix: str = "") -> "re.Pattern":
    """Convert a rule from the mast to regular expressions.

    Args:
        rule (str): The line from the mast
        prefix (str, optional): Regex to be prepended
        suffix (str, optional): Regex to be appended

    Returns:
        re.Pattern: A regular expression
    """
    rule = rule.replace(".", "\\.")
    rule = rule.replace("*", "[^/]*")
    rule = rule.replace("#", "(|/|/?.*/?)")
    rule = prefix + rule + suffix
    return re.compile(rule)


class Rule:
    """A rule permitting or banning specific files.

    Attributes:
        is_allowing (bool): Is allowing (True) or banning (False) the pattern.
        line (str): The line this represents from mask.txt
        matcher (str): The matching part of the line
        regex (re.Pattern): The regular expression to match the path
        static_root (re.Pattern): The root of the search path,
            permitting further search
    """

    line: str
    is_allowing: bool
    matcher: str
    regex: "re.Pattern"
    static_root: "re.Pattern"

    def __init__(self, line: str):
        """Set up variables

        Args:
            line (str): The line from mask.txt
        """
        self.line = line
        self.is_allowing = line[0] == "+"
        self.matcher = line.split(" ", 1)[1]
        self.regex = rule_to_regex(self.matcher, "^", "$")
        self.static_root = rule_to_regex(self.matcher.split("#")[0], "^")

    def __repr__(self) -> str:
        """A string representation"""
        return f'RULE "{self.line}"'

    def matches_root(self, path: str) -> bool:
        """Does it match the root of the searchpath, permitting further search.

        Args:
            path (str): The path to be matched

        Returns:
            bool: The truth value
        """
        match = self.static_root.match(str(path))
        return match is not None and len(match[0])

    def matches(self, path: str) -> bool:
        """Does it match the rule.

        Args:
            path (str): The path to be matched

        Returns:
            bool: The truth value
        """
        match = self.regex.match(str(path))
        return match is not None and len(match[0])

    def add(self, path: str) -> bool:
        """Does this rule enforce adding this path.

        Args:
            path (str): The path to be matched

        Returns:
            bool: The truth value
        """
        return self.is_allowing and self.matches(path)

    def remove(self, path: str) -> bool:
        """Does this rule enforce removing this path.

        Args:
            path (str): The path to be matched

        Returns:
            bool: The truth value
        """
        return not self.is_allowing and self.matches(path)


class RuleTree:
    """A set of rules, representing a mask.txt file."""

    rules: List[Rule] = []

    def __init__(self, mask: str):
        """Initiate from a mask.

        Args:
            mask (str): The contents of a mask.txt
        """
        for line in mask.split("\n"):
            line = line.replace("\t", "    ")
            line = line.split("//")[0].rstrip()
            if line:
                self.rules.append(Rule(line))

    def matches_any_root(self, path: str) -> bool:
        """Does it match the root of any searchpath, permitting further search.

        Args:
            path (str): The path to be matched

        Returns:
            bool: The truth value
        """
        for rule in self.rules:
            if rule.is_allowing and rule.matches_root(path):
                return True
        return False

    def sync_file(self, path: str) -> bool:
        """Should a specific file be downloaded.

        Args:
            path (str): The path to be matched

        Returns:
            bool: The truth value
        """
        sync = False
        for rule in self.rules:
            sync = (sync or rule.add(path)) and not rule.remove(path)
        return sync


class Config:
    """A configuration, representing a config.yaml

    Attributes:
        config_file (str): The content of the config.yaml
        old_prefix (str): The prefix to be applied to old files
        uec_suffix (str): The suffix to removed from files with a
            "Unicode Encoding Conflict". This is a dropbox problem
        max_pbar_depth (int): Maximum amount of progress bars. -1 for all.
        current_pbar_depth (int): The amount of progress bars that can still
            be displayed in addition to the current ones
        rules (RuleTree): The rules in this configuration
        root_path (Path): The root path to be synced to
        log_deprecated (bool): Log deprectated files
        log_all (bool): Log every single file and message
        delete_old (bool): Delete old files
    """

    config_file: str
    old_prefix = "(OLD) "
    uec_suffix = " (Unicode Encoding Conflict)"
    max_pbar_depth = -1
    current_pbar_depth = max_pbar_depth
    rules: RuleTree
    root_path: Path
    log_deprecated: bool = False
    log_all: bool = False
    delete_old: bool = False

    @classmethod
    def initiate_from_file(cls, config_file: str):
        """Initiate the variables by reading from a file

        Args:
            config_file (str): The path of the config.yaml
        """
        with open(config_file) as f:
            try:
                config = yaml.load(f, Loader=yaml.FullLoader)
            except:
                config = yaml.load(f)

        cls.config_file = config_file
        cls.old_prefix = config.get("OLD", cls.old_prefix)
        cls.uec_suffix = config.get("UEC", cls.uec_suffix)
        cls.max_pbar_depth = config.get("Max Bars", cls.max_pbar_depth)
        cls.current_pbar_depth = cls.max_pbar_depth
        cls.log_deprecated = config.get("Log Deprecated", cls.log_deprecated)
        cls.log_all = config.get("Log All", cls.log_all)
        cls.delete_old = config.get("Delete old", cls.delete_old)

    @classmethod
    def absolute_path(cls, path: Path) -> Path:
        """The absolute path of a download folder relative path

        Args:
            path (Path): The path to be converted

        Returns:
            Path: The absolute path
        """
        return cls.root_path / path

    @classmethod
    def relative_path(cls, path: Path) -> Path:
        """The path relative to the download folder of an absolute path

        Args:
            path (Path): The path to be converted

        Returns:
            Path: The relative path
        """
        return path.relative_to(cls.root_path)


def pretty_print(*messages: List[Any], keep: bool = False):
    """Print or log a message.

    Args:
        *messages (List[Any]): Any amount of objects to be printed
        keep (bool, optional): Keep this message (True) or
            overwrite it with the next one (False)
    """
    message = " ".join((str(m) for m in messages))
    if not pretty_print.keep_last:
        message = "\033[1A\033[K" + message
    max_width = shutil.get_terminal_size((80, 20)).columns
    current_length = len(strip_ANSI(message))
    if current_length > max_width:
        message = message[: max_width - current_length - 1] + "…"
    tqdm.write(message)
    pretty_print.keep_last = keep


def log(*messages: List[Any]):
    """Log a message permanently.

    Args:
        *messages (List[Any]): Any amount of objects to be printed
    """
    pretty_print(*messages, keep=True)


def status(*messages: List[Any]):
    """Print a message temporarily and overwrite it with the next one.

    Args:
        *messages (List[Any]): Any amount of objects to be printed
    """
    pretty_print(*messages, keep=Config.log_all)


def keep_current_status():
    """Keep the message that is the current status."""
    pretty_print.keep_last = True


keep_current_status()


def recursive_fix_unicode(folder: str):
    """Fix unicode encoding conflicts that occur in dropbox.

    Args:
        folder (str): The root folder from wich to be fixed.
    """
    if not os.path.exists(folder):
        log(Status.nothing, "Directory does not exist anymore")
        return
    for sub in os.listdir(folder):
        path = "{}/{}".format(folder, sub)
        if os.path.isdir(path):
            if Config.uec_suffix in sub:
                log(Status.removing, path)
                try:
                    os.rename(
                        path,
                        path.replace(Config.uec_suffix, "").replace(
                            Config.old_prefix, ""
                        ),
                    )
                except OSError:
                    log(Status.nothing, "Path does not exist anymore")
            recursive_fix_unicode(path)
        else:
            if Config.uec_suffix in sub:
                log(Status.removing, path)
                try:
                    os.rename(
                        path,
                        path.replace(Config.uec_suffix, "").replace(
                            Config.old_prefix, ""
                        ),
                    )
                except OSError:
                    log(Status.nothing, "Directory not exist anymore")


def undeprecate(directory: Path) -> Path:
    """The undeprecated version of a path name.

    Args:
        directory (Path): The path to be undeprecated

    Returns:
        Path: The undeprecated version
    """
    parent = directory.parent
    name = directory.name
    if name.startswith(Config.old_prefix):
        name = name.lstrip(Config.old_prefix)
    return parent / name


def deprecate(directory: Path) -> Path:
    """The deprecated version of a path name.

    Args:
        directory (Path): The path to be deprecated

    Returns:
        Path: The deprecated version
    """
    parent = directory.parent
    name = directory.name
    if not name.startswith(Config.old_prefix):
        name = Config.old_prefix + name
    return parent / name


def is_deprecated(directory: Path) -> bool:
    """Is a path deprecated

    Args:
        directory (Path): The path to compare

    Returns:
        bool: The truth value
    """
    return directory.name.startswith(Config.old_prefix)


def recover_old_file(file: Path):
    """Make a file that is deprecated not deprecated.

    Args:
        file (Path): The file to be recovered
    """
    path = Config.absolute_path(file)
    os.rename(deprecate(path), path)


def make_old_file(file: Path):
    """Make a file that is not deprecated deprecated.

    Args:
        file (Path): The file to be deprecated
    """
    path = Config.absolute_path(file)
    os.rename(path, deprecate(path))


def make_old_file_if_not_already(file: Path):
    """Ensure that a file is deprecated and print it to the console.

    Args:
        file (Path): The path to be deprecated.
    """
    if Config.delete_old:
        file_to_delete = file
        if is_deprecated(file) or Config.absolute_path(deprecate(file)).exists():
            file_to_delete = deprecate(file)
        file_to_delete = Config.absolute_path(file_to_delete)
        if file.is_dir() or file_to_delete.is_dir():
            shutil.rmtree(file_to_delete)
        else:
            os.remove(file_to_delete)
        log(Status.removing, file)
    else:
        if is_deprecated(file) or Config.absolute_path(deprecate(file)).exists():
            pretty_print(Status.deprecated, file, keep=Config.log_deprecated)
        else:
            log(Status.deprecated, file)
            make_old_file(file)


def touchdir_absolute(directory: Path):
    """Make sure an absolute directory exists.

    Args:
        directory (Path): The directory to touch
    """
    if not directory.exists():
        path = Path("/")
        for part in directory.parts:
            path /= part
            if path.exists():
                continue
            elif deprecate(path).exists():
                recover_old_file(path)
            else:
                os.makedirs(path)


def touchdir_relative(directory: Path):
    """Make sure a relative directory exists.

    Args:
        directory (Path): The directory to touch
    """
    absolute_directory = Config.absolute_path(directory)
    touchdir_absolute(absolute_directory)


def ensure_downloaded(file: wuecampy.AbstractedFile):
    """Make sure that a file is downloaded

    Args:
        file (wuecampy.AbstractedFile): The file to ensure
    """
    touchdir_relative(file.path().parent)
    log_message = file.path()
    download_path = Config.absolute_path(file.path())
    if download_path.exists():
        status(Status.nothing, log_message)
    elif deprecate(download_path).exists():
        log(Status.adding, log_message)
        recover_old_file(file.path())
    else:
        log(Status.adding, log_message)
        file.download_to(str(download_path))


def sync_file(file: wuecampy.AbstractedFile) -> bool:
    """Download a file if it matches the rules else ignore it.

    Args:
        file (wuecampy.AbstractedFile): The file to be synced

    Returns:
        bool: Do the rules match the file
    """
    if Config.rules.sync_file(file.path()):
        ensure_downloaded(file)
        return True
    return False


def sync_directory(directory: wuecampy.AbstractedDirectory) -> bool:
    """Downlaod all files in a directory if they match the rules.

    Args:
        directory (wuecampy.AbstractedDirectory): The directory to sync.

    Returns:
        bool: Any files of this directory are on the file system.
    """
    iterator = directory.get_children()
    has_pbar = False
    existing_directories: List[Path] = []
    existing_files: List[Path] = []
    current_dir = Config.absolute_path(directory.path())
    contains_files = False
    if current_dir.exists():
        for child in current_dir.iterdir():
            if not child.name.startswith("."):
                relative_child_path = undeprecate(Config.relative_path(child))
                if child.is_dir():
                    existing_directories.append(relative_child_path)
                else:
                    existing_files.append(relative_child_path)
    if Config.current_pbar_depth != 0:
        has_pbar = True
        Config.current_pbar_depth -= 1
        iterator = tqdm(iterator, leave=False)
    for child in iterator:
        if child.is_file():
            child_contains_files = sync_file(child)
            contains_files = contains_files or child_contains_files
            if child.path() in existing_files and child_contains_files:
                existing_files.remove(child.path())
        else:
            if Config.rules.matches_any_root(str(child.path())):
                child_contains_files = sync_directory(child)
                contains_files = contains_files or child_contains_files
                if child.path() in existing_directories and child_contains_files:
                    existing_directories.remove(child.path())
    if has_pbar:
        Config.current_pbar_depth += 1
    if directory.path().parts:
        for deprecated_directory in existing_directories:
            make_old_file_if_not_already(deprecated_directory)
        for deprecated_file in existing_files:
            make_old_file_if_not_already(deprecated_file)
    return contains_files


def main():
    """Synchronize the wuecampus filesystem with the local one."""
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="path to download to")
    args = parser.parse_args()
    root_path = Path(args.path)
    mask_path = root_path / "mask.txt"
    with open(mask_path, "r") as mask_file:
        mask = mask_file.read()
    aliases_path = root_path / "aliases.yaml"
    aliases = (
        yaml.safe_load(aliases_path.open("r")) or {} if aliases_path.exists() else {}
    )
    Config.initiate_from_file(root_path / "config.yaml")
    Config.rules = RuleTree(mask)
    Config.root_path = root_path
    status("Fixing Unicode Encoding Conflicts")
    recursive_fix_unicode(root_path)
    status("Logging in")
    campus = wuecampy.wuecampus(
        passwords.sb_at_home.snr,
        passwords.sb_at_home.password,
        aliases=aliases,
        # verbose=True,
    )
    campus.login()
    sync_directory(campus)
    status("Fixing Unicode Encoding Conflicts")
    recursive_fix_unicode(root_path)
    status(f"{Fore.GREEN}Done.{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
