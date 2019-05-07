#! /usr/bin/env python3

"""Wuecampus management library.

Attributes:
    TMP_DOWNLOAD_DIR (Path): Temporary download directory (home)
"""

import re
import unicodedata
from abc import ABC, abstractmethod
from shutil import move
from pathlib import Path
from typing import List, Optional

import mechanicalsoup
from tqdm import tqdm

TMP_DOWNLOAD_DIR = Path.home()


def normalized(string: str) -> str:
    """A normalized version of a string.

    Args:
        string (str): The string to normalize

    Returns:
        str: The normalized string
    """
    return_string = string
    return_string = return_string.replace("/", "or")
    return_string = return_string.replace(":", " ")
    return_string = unicodedata.normalize("NFD", return_string)
    return return_string


class url:
    """Storing urls.

    Attributes:
        courses_page (str): The page listing all courses
        grade_page (str): The page listing the grades
        login_page (str): The login page
        main_page (str): The main page
    """

    login_page = "https://wuecampus2.uni-wuerzburg.de/moodle/login/index.php"
    main_page = "https://wuecampus2.uni-wuerzburg.de/moodle/"
    grade_page = (
        "https://wuecampus2.uni-wuerzburg.de/moodle/grade/"
        "report/user/index.php?id={}"
    )
    courses_page = "https://wuecampus2.uni-wuerzburg.de/moodle/my/index.php"


class AbstractedFileStructureElement(ABC):
    """An abstracted file structure element (file or directory)
    """

    parent: Optional["AbstractedFileStructureElement"]

    @abstractmethod
    def has_children(self) -> bool:
        """Does this AFSE have children (it is a directory)
        """
        ...

    @abstractmethod
    def get_children(self) -> List["AbstractedFileStructureElement"]:
        """Get a list of the cildren of the AFSE.
        """
        ...

    @abstractmethod
    def is_file(self) -> bool:
        """Is the AFSE a file.
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """The filename or directory name.
        """
        ...

    def path(self) -> Path:
        """The path of the AFSE.
        """
        if self.parent is None:
            return Path(self.name())
        return self.parent.path() / self.name()


class AbstractedDirectory(AbstractedFileStructureElement):
    """A object that can be mapped to a directory on the local file system.
    """

    def has_children(self) -> bool:
        return True

    def is_file(self) -> bool:
        return False


class AbstractedFile(AbstractedDirectory, ABC):
    """An object that can be mapped to a file on the local file system.
    """

    def has_children(self) -> bool:
        return False

    def get_children(self) -> List[AbstractedFileStructureElement]:
        return []

    def is_file(self) -> bool:
        return True

    @abstractmethod
    def download_to(self, to: str):
        """Download the file to a given path INCLUDING file name.
        """
        ...

    @abstractmethod
    def download_to_path(self, to: str):
        """Download the file to a given path WITHOUT file name.
        """
        ...


class activity(AbstractedFileStructureElement):
    """Activity management class.
    """

    campus: "wuecampus"
    course_: "course"
    section_: "section"
    title: str

    def name(self) -> str:
        return normalized(self.title)


class activity_file(activity, AbstractedFile):
    """A file hosted on wuecampus.

    Attributes:
        campus (wuecampus): The corresponding wuecampus object.
        course_ (course): The course the file is in
        extension_string (str): The extension [pdf, txt, ...]
        kind (str): The kind of activity
        link (str): The link to the object
        link_object: A bs4 href object
        parent (AbstractedFileStructureElement): The section this file is in
        section_ (section): The section this file is in
        title (str): The title of the file
    """

    def __init__(
        self,
        campus: "wuecampus",
        course_: "course",
        section_: "section",
        title: str,
        link_object,
        kind: str,
    ):
        """Initialize the object.

        Args:
            campus (wuecampus): The corresponding wuecampus object.
            course_ (course): The course the file is in
            section_ (section): The section this file is in
            title (str): The title of the file
            link_object: A bs4 href object
            kind (str): The kind of activity
        """
        self.campus = campus
        self.course_ = course_
        self.section_ = section_
        self.title = normalized(title)
        self.link_object = link_object
        self.kind = kind
        self.link = (
            re.search(r"http[^']*resource[^']*", link_object.get("onclick")).group(0)
            if link_object.get("onclick")
            else link_object.get("href")
        )
        self.extension_string = ""
        self.parent = section_

    def get_file(self) -> "requests.Session.get":
        """Get and stream the file download.

        Returns:
            requests.Session.get: The get object.
        """
        return self.campus.browser.get(self.link, stream=True)

    def save_file_to(self, to: str):
        """Save the file to a given download path INCLUDING file name.

        Args:
            to (str): The download path.
        """
        download_target = TMP_DOWNLOAD_DIR / to.split("/")[-1]
        with open(download_target, "wb") as handle:
            for data in tqdm(
                self.get_file().iter_content(chunk_size=1024),
                unit="kB",
                unit_scale=True,
            ):
                handle.write(data)
        move(download_target, to)

    def save_file_to_path(self, path: str):
        """Save the file to a given download path WITHOUT file name.

        Args:
            to (str): The download path.
        """
        self.save_file_to(path + "/" + self.title + "." + self.extension_string)

    def download_to(self, to: str):
        self.save_file_to(to)

    def download_to_path(self, to: str):
        self.save_file_to_path(to)

    def extension(self) -> str:
        """Compute the extension of the file.

        Returns:
            str: The extension
        """
        primitive_extension = (
            self.link_object.find_all("img")[0].get("src").split("/")[-1]
            if "img" in str(self.link_object)
            else self.link_object.get_text().split(".")[-1]
        )
        if primitive_extension in ["pdf", "zip"]:
            self.extension_string = primitive_extension
        else:
            if self.campus.verbose:
                msg = "complex extension: {}".format(primitive_extension)
                if self.campus.use_tqdm:
                    tqdm.write(msg)
                else:
                    tqdm.write(msg)
        if self.extension_string == "":
            i = self.campus.browser.get(self.link, allow_redirects=False)
            if "location" in i.headers:
                self.extension_string = ".".join(
                    i.headers["location"].split("/")[-1].split(".")[1:]
                ).split("?")[0]
            else:
                self.extension_string = ".".join(
                    i.headers["Content-Disposition"].split('"')[-2].split(".")[1:]
                )
        if self.title.endswith("." + self.extension_string):
            self.title = self.title.rstrip(self.extension_string)[:-1]
        return self.extension_string

    def name(self) -> str:
        return f"{self.title}.{self.extension()}"

    def __repr__(self):
        return '"File" activity "{}" in {}'.format(self.title, self.section_)


class section(AbstractedDirectory):
    """Section management class.

    Attributes:
        campus (wuecampus): The corresponding wuecampus object
        course_ (course): The course the section is in
        id_ (str): The section id (wuecampus thing)
        link (str): The link to the section
    """

    def __init__(
        self, campus: "wuecampus", course_: "course", title: str, link: str, id_: str
    ):
        """Initialize the section object

        Args:
            campus (wuecampus): The corresponding wuecampus object
            course_ (course): The course the section is in
            title (str): The section title
            link (str): The link to the section
            id_ (str): The link to the section
        """
        self.campus = campus
        self.course_ = course_
        self.title = normalized(title)
        self.link = link
        self.id_ = id_
        self.parent = course_

    def all_activities(self) -> List[activity]:
        """All activities in the section.

        Returns:
            List[activity]: All activiites
        """
        self.campus.browser.open(self.link)
        page = self.campus.browser.get_current_page()
        try:
            current_section = page.find_all("li", id="section-{}".format(self.id_))[0]
            activities_ = []
            for activity_ in current_section.find_all("li", class_="activity"):
                activity_kind = activity_.get("class")[1]
                activity_title = "undefined"
                if activity_kind == "resource":
                    i_ = activity_.find_all(class_="instancename")[0].children
                    activity_title = str(next(i_)).strip()
                    activities_.append(
                        activity_file(
                            self.campus,
                            self.course_,
                            self,
                            activity_title,
                            activity_.find_all("a")[0],
                            activity_kind,
                        )
                    )
                if activity_kind == "assign":
                    i_ = activity_.find_all(class_="instancename")[0].children
                    activity_title = str(next(i_)).strip()
                    activities_.append(
                        activity_assignment(
                            self.campus,
                            self.course_,
                            self,
                            activity_title,
                            activity_.find_all("a")[0],
                            activity_kind,
                        )
                    )
                else:
                    if self.campus.verbose:
                        msg = "unknown activity: {}".format(activity_kind)
                        if self.campus.use_tqdm:
                            tqdm.write(msg)
                        else:
                            print(msg)
            return activities_
        except IndexError:
            return []

    def all_files(self) -> List[activity_file]:
        """All files in the section

        Returns:
            List[activity_file]: The files
        """
        return [a for a in self.all_activities() if a.kind == "resource"]

    def all_assignments(self) -> List["activity_assignment"]:
        """All assignments in the section.

        Returns:
            List[activity_assignment]: The assignments
        """
        return [a for a in self.all_activities() if a.kind == "assign"]

    def get_children(self):
        return self.all_activities()

    def name(self):
        return normalized(self.title)

    def __repr__(self):
        return 'section "{}" in {}'.format(self.title, self.course_)


class inline_section(section):
    """Section management class for sections without own link.

    Attributes:
        campus (wuecampus): The corresponding wuecampus object
        course_ (course): The course the section is in
        div: a bs4 object for the div tag the section is in
    """

    def __init__(self, campus: "wuecampus", course_: "course", title: str, div):
        """Initialize the inline section.

        Args:
            campus (wuecampus): The corresponding wuecampus object
            course_ (course): The course the section is in
            title (str): The section title
            div: The div tag
        """
        self.campus = campus
        self.course_ = course_
        self.title = normalized(title)
        self.div = div
        self.parent = course_

    def all_activities(self):
        activities_ = []
        for activity_ in self.div.find_all("li", class_="activity"):
            activity_kind = activity_.get("class")[1]
            activity_title = "undefined"
            if activity_kind == "resource":
                i_ = activity_.find_all(class_="instancename")[0].children
                activity_title = str(next(i_)).strip()
                activities_.append(
                    activity_file(
                        self.campus,
                        self.course_,
                        self,
                        activity_title,
                        activity_.find_all("a")[0],
                        activity_kind,
                    )
                )
            if activity_kind == "assign":
                i_ = activity_.find_all(class_="instancename")[0].children
                activity_title = str(next(i_)).strip()
                activities_.append(
                    activity_assignment(
                        self.campus,
                        self.course_,
                        self,
                        activity_title,
                        activity_.find_all("a")[0],
                        activity_kind,
                    )
                )
            else:
                if self.campus.verbose:
                    msg = "unknown activity: {}".format(activity_kind)
                    if self.campus.use_tqdm:
                        tqdm.write(msg)
                    else:
                        print(msg)
        return activities_

    def __repr__(self):
        return 'isection "{}" in {}'.format(self.title, self.course_)


class activity_assignment(activity, section):
    """An assignment.

    Attributes:
        link (str): The link to the assignment
        link_object: A bs4 a object
    """

    def __init__(
        self,
        campus: "wuecampus",
        course_: "course",
        section_: "section",
        title: str,
        link_object,
        kind: str,
    ):
        """Initialize the assignment

        Args:
            campus (wuecampus): The corresponding wuecampus object
            course_ (course): The course the assignment is in
            section_ (section): The section the assignment is in
            title (str): The title of the section
            link_object: The bs4 object of th elink
            kind (str): The kind of assignment
        """
        self.campus = campus
        self.course_ = course_
        self.section_ = section_
        self.title = normalized(title)
        self.link_object = link_object
        self.kind = kind
        self.link = link_object.get("href")
        self.extension_string = ""
        self.parent = section_

    def all_files(self):
        self.campus.browser.open(self.link)
        page = self.campus.browser.get_current_page()
        files = []
        for td in page.find_all("li", yuiconfig='{"type":"html"}'):
            td_title = td.find_all("a")[0].get_text()
            td_link = td.find_all("a")[0]
            files.append(
                activity_file(
                    self.campus, self.course_, self, td_title, td_link, "resource"
                )
            )
        return files

    def get_children(self):
        return self.all_files()

    def __repr__(self):
        return '"Assignment" activity "{}" in {}'.format(self.title, self.section_)


class course(AbstractedDirectory):
    """Course management class.

    Attributes:
        campus (TYPE): The corresponding wuecampus activity
        id (TYPE): The id (wuceampus thingy)
        link (TYPE): The link to the course
    """

    def __init__(self, campus: "wuecampus", title: str, link: str, id: str):
        """Initialzie the course object

        Args:
            campus (wuecampus): The corresponding wuecampus activity
            title (str): The title of the course
            link (str): The link to the course
            id (str): The id (wuceampus thingy)
        """
        self.campus = campus
        self.title = normalized(title)
        self.link = link
        self.id = id
        self.parent = campus

    def all_sections(self) -> List[section]:
        """All sections in the course

        Returns:
            List[section]
        """
        self.campus.browser.open(self.link)
        page = self.campus.browser.get_current_page()
        sections_ = []
        for section_ in page.find_all("li", class_="section-summary"):
            try:
                section_title = section_.find_all("a")[0].get_text()
                section_link = section_.find_all("a")[0].get("href")
                section_id = (
                    re.search("section=\d+", section_link).group(0).split("=")[-1]
                )
                sections_.append(
                    section(self.campus, self, section_title, section_link, section_id)
                )
            except IndexError:
                pass
        for isection in page.find_all("li", class_="section"):
            section_title = next(isection.children).get_text()
            if section_title != "":
                sections_.append(
                    inline_section(self.campus, self, section_title, isection)
                )
        return sections_

    def section_with_name(self, name: str) -> section:
        """Get a section with a given name

        Args:
            name (str): The name of the section

        Returns:
            section: The section
        """
        return [s for s in self.all_sections() if s.title.endswith(name)][0]

    def get_children(self) -> List[AbstractedFileStructureElement]:
        return self.all_sections()

    def name(self) -> str:
        return normalized(self.title)

    def __repr__(self):
        return 'course "{}"'.format(self.title)


class wuecampus(AbstractedDirectory):
    """Wuecampus management class.

    Attributes:
        browser: A mechanicalsoup browser
        password (str): The password
        username (str): The username
        use_tqdm (bool): Redirect prints through tqdm
        verbose (bool): Verbose logging
    """

    username = ""
    password = ""
    browser = mechanicalsoup.StatefulBrowser()

    def __init__(self, username: str, password: str, verbose=False, use_tqdm=False):
        """Setup with username and password.

        Args:
            username (str): The username
            password (str): The password
            verbose (bool, optional): Verbose logging
            use_tqdm (bool, optional): Redirect prints through tqdm
        """
        self.username = username
        self.password = password
        self.verbose = verbose
        self.use_tqdm = use_tqdm
        self.parent = None

    def all_courses(self) -> List[course]:
        """Get all courses in wuecampus
        
        Returns:
            List[course]
        """
        self.browser.open(url.courses_page)
        page = self.browser.get_current_page()
        courses_ = []
        for link in page.find_all(class_="jmu-accordion"):  # col-lg-6
            course_title = link.get_text()
            course_link = link.get("href")
            course_id = re.search("id=\d+", course_link).group(0)[3:]
            courses_.append(course(self, course_title, course_link, course_id))
        return courses_

    def course_with_name(self, name: str) -> course:
        """Get a course with a given name

        Args:
            name (str): The name of the course

        Returns:
            course: The course
        """
        return [c for c in self.all_courses() if c.title.endswith(name)][0]

    def get_children(self) -> List[AbstractedFileStructureElement]:
        return self.all_courses()

    def login(self):
        """Log in a user.
        """
        self.browser.open(url.login_page)
        form = self.browser.select_form()
        form["username"] = self.username
        form["password"] = self.password
        self.browser.submit_selected()

    def name(self) -> str:
        return ""

    def __repr__(self):
        return 'wuecampus instance for user "{}"'.format(self.username)
