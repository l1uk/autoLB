# -*- coding: utf-8 -*-
"""
Helper module to split an ELOG post in smaller units fitting the maximum size of the ELOG message.

The ELOG message has a limited size, so if the user is generating the protocol of a large project (> 100 images),
the ELOG server will reject the post.

The procedure is the following:

    1. The HTML of the whole post is parsed as a beautiful soup.
    2. The structure of the initial post is identified and minimal pages are rebuild.
    3. These minimal pages can be combined in order to optimize the size of each page.
    4. Finally, a rebuild of the index is necessary in order correct all possible anchors.

The core of the job is performed by the ELOGPageSplitter class that stores the output pages in a PageList.
This is a UserList of ELOGPages and its derived classes.

Each ELOGPage subtypes knows exactly what it should contain and when it is created starting from a soup, all relevant
elements are identified and stored.

@author: Antonio Bulgheroni (antonio.bulgheroni@ec.europa.eu)

"""
# ----------------------------------------------------------------------------------------------------------------------
#  Copyright (c) 2022-2023.  Antonio Bulgheroni.
#  Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
#  documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  permit persons to whom the Software is furnished to do so, subject to the following conditions:
#  The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
#  Software.
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
#  WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
#  OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#  OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# ----------------------------------------------------------------------------------------------------------------------
from __future__ import annotations

import copy
import re
from collections import UserList
from enum import Enum, auto

import bs4.element
from bs4 import BeautifulSoup

from autologbook import autoconfig, autoerror
from autologbook.file_type_guesser import ElementTypeGuesser
from autologbook.jinja_integration import jinja_env

__author__ = 'Antonio Bulgheroni'
__email__ = 'antonio.bulgheroni@gmail.com'

# pattern to decode the elements of elog url
elog_url_pattern = re.compile(r'(?P<url>https?://[\w.-]+)(?::(?P<port>\d+))?/(?P<logbook>[\w.-]+)/(?P<msg_id>\d+)')


def is_splitting_required(html: str) -> bool:
    """
    Function to check if the html markup is fitting inside a single post or not.

    Parameters
    ----------
    html: str
        The HTML markup, whose size is checked.

    Return
    ------
    bool
        True if the html is too big to fit in a page.

    """
    if autoconfig.ELOG_PAGE_SIZE_LIMIT < 0:
        return False
    return len(html) > autoconfig.ELOG_PAGE_SIZE_LIMIT


class ELOGPageType(Enum):
    """Enumerator to name all possible ELOG page types."""
    ELOGGenericPageType = auto()
    ELOGIntroPageType = auto()
    ELOGOpticalImagePageType = auto()
    ELOGSamplePageType = auto()
    ELOGConclusionPageType = auto()
    ELOGIntroOpticalConclusionType = auto()
    ELOGIntroConclusionType = auto()
    ELOGCombinedSamplePageType = auto()


# The pages of the these types cannot be repeated.
UniquePageTypes = (ELOGPageType.ELOGIntroPageType, ELOGPageType.ELOGConclusionPageType,
                   ELOGPageType.ELOGOpticalImagePageType, ELOGPageType.ELOGIntroOpticalConclusionType,
                   ELOGPageType.ELOGIntroConclusionType)


class ELOGPostElement(Enum):
    """Enumerator to define the various elements in an ELOG post."""
    TitleDiv = 'title_div'
    IntroductionDiv = 'introduction_div'
    NavigationDiv = 'navigation_div'
    SampleDescriptionDiv = 'sample_description_div'
    SampleList = 'sample_list'
    GeneralOpticalImage = 'general_optical_image'
    SampleElements = 'sample_elements'
    ConclusionDiv = 'conclusion_div'
    GeneralAttachment = 'general_attachment'
    Footer = 'footer'
    Script = 'script'
    HTMLNavigation = 'html_navigation'


class SoupParser:
    """Mixin class to parse an HTML soup."""

    @staticmethod
    def parse_the_soup(soup: bs4.BeautifulSoup, element_filter: dict | re.Pattern | callable) -> bs4.Tag:
        """
        Find an element in a soup.

        Parameters
        ----------
        soup: bs4.BeautifulSoup
            The soup to be parsed.

        element_filter: dict | re.Pattern | callable
            The filter to be applied to the soup

        Returns
        -------
        bs4.Tag
            The TAG corresponding to the filter.

        """
        if isinstance(element_filter, dict):
            return soup.find(**element_filter)
        else:
            return soup.find(element_filter)


class ELOGPostParameters:
    """Mixin class to store the post parameters."""

    def __init__(self, *args, **kwargs):
        self._message_id = kwargs.pop('msg_id', None)
        self._logbook = kwargs.pop('logbook', '')
        self._base_url = kwargs.pop('base_url', 'https://localhost')
        self._port = kwargs.pop('port', None)

    def set_elog_parameters(self, base_url: str, logbook: str, msg_id: int, port: int = None):
        """
        Set the ELOG post parameters from the URL.

        Parameters
        ----------
        base_url: str
            The base url of the post. This can contain the port number

        logbook:
            The name of the logbook.

        msg_id:
            The message id number

        port:
            The port number. If a port is specified, then it will supersed the port in the url.
        """
        # it is possible that the port is already included in the base_url
        # https://localhost:1234
        pattern = r'(?P<url>https?://[\w.-]+)(?::(?P<port>\d+))?.*'
        match = re.match(pattern, base_url)
        if match:
            base_url = match.group('url')
            self._base_url = base_url
            new_port = match.group('port')

            if new_port:
                new_port = int(new_port)
                if new_port == port:
                    self._port = new_port
                else:
                    self._port = port if port is not None else new_port
            else:
                self._port = port
        else:
            self._base_url = base_url
            self._port = port

        self._logbook = logbook
        self._message_id = msg_id

    @property
    def url(self) -> str:
        """
        URL property

        Returns
        -------
        str:
            The URL of the post
        """
        if self._port is None:
            return f'{self._base_url}/{self._logbook}/{self._message_id}'
        else:
            return f'{self._base_url}:{self._port}/{self._logbook}/{self._message_id}'

    @url.setter
    def url(self, url: str):
        """
        URL property setter.

        Starting from a fully formed URL, the various parameters are decoded.

        Parameters
        ----------
        url: str
            The url to be set.
        """
        match = re.match(elog_url_pattern, url)
        if match:
            self._message_id = int(match.group('msg_id'))
            self._logbook = match.group('logbook')
            self._base_url = match.group('url')
            self._port = int(match.group('port')) if match.group('port') else None
        else:
            raise autoerror.InvalidConnectionParameters('Unable to match connection parameters from %s' % url)


class ELOGPage(SoupParser, ELOGPostParameters):
    """
    Base class for the ELOGPage.
    """

    def __init__(self, html_soup: BeautifulSoup, page_number: int = None, parent_page: ELOGPage = None, *args,
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._html_soup = html_soup
        self._page_number = page_number
        self._type = ELOGPageType.ELOGGenericPageType
        self._parent_page = parent_page
        self._required_element_dict = {}
        self._page_tags = {}
        self._navigation_template = 'navigation_base_template.yammy'
        self._previous_page = None
        self._next_page = None

    @property
    def page_number(self) -> int:
        """
        Page number property.

        Returns
        -------
        int:
            The page number
        """
        return self._page_number

    @page_number.setter
    def page_number(self, number: int):
        self._page_number = number

    @property
    def parent_page(self) -> ELOGPage:
        """
        Parent page property.

        Returns
        -------
        ELOGPage:
            The parent page.
        """
        return self._parent_page

    @parent_page.setter
    def parent_page(self, page: ELOGPage):
        self._parent_page = page

    def build_page(self):
        page_html = dict()
        for element, filter in self._required_element_dict.items():
            if filter:
                soup_tag = self.parse_the_soup(self._html_soup, filter)
                if soup_tag:
                    page_html[element] = soup_tag
            else:
                page_html[element] = None
        return page_html

    def get_html(self, ) -> str:
        html = str()
        for element in self._page_tags:
            html += str(self._page_tags[element])
        return html

    def is_empty(self) -> bool:
        has_content = False
        for element, tag in self._page_tags.items():
            if element not in [ELOGPostElement.TitleDiv, ELOGPostElement.Script]:
                has_content = has_content or len(str(tag))
        return not has_content

    def page_size(self, only_relevant_elements: bool = False) -> int:
        size = 0
        for element, tag in self._page_tags.items():
            if only_relevant_elements:
                if element not in [ELOGPostElement.TitleDiv, ELOGPostElement.Script]:
                    size += len(str(tag))
            else:
                size += len(str(tag))
        return size

    def _render_html_navigation(self):
        template = jinja_env.get_template(self._navigation_template)
        self._page_tags[ELOGPostElement.HTMLNavigation] = template.render(page=self)

    def _patch_title_div(self):
        if ELOGPostElement.TitleDiv not in self._page_tags:
            return
        self._page_tags[ELOGPostElement.TitleDiv] = copy.copy(self._page_tags[ELOGPostElement.TitleDiv])
        self._page_tags[ELOGPostElement.TitleDiv].find(id='intro').string += f' / Page {self.page_number + 1}'


class ELOGIntroPage(ELOGPage):

    def __init__(self, html_soup: BeautifulSoup, *args, **kwargs):
        super().__init__(html_soup, page_number=1, parent_page=self, *args, **kwargs)
        self._type = ELOGPageType.ELOGIntroPageType
        self._required_element_dict = {
            ELOGPostElement.TitleDiv: {'id': 'protocol_title_div'},
            ELOGPostElement.IntroductionDiv: {'class_': 'section_div', 'id': 'Introduction'},
            ELOGPostElement.NavigationDiv: {'class_': 'navigation_image_div'},
            ELOGPostElement.SampleDescriptionDiv: {'class_': 'section_div', 'id': 'Samples'},
            ELOGPostElement.SampleList: {'id': 'sample_list_div'},
            ELOGPostElement.HTMLNavigation: None,  # placeholder
            ELOGPostElement.Footer: {'id': 'footer'},
            ELOGPostElement.Script: {'name': 'script'}
        }
        self._page_tags = self.build_page()


class ELOGOpticalImagePage(ELOGPage):

    def __init__(self, html_soup: BeautifulSoup, page_number: int = None, parent_page: ELOGPage = None, *args,
                 **kwargs):
        super().__init__(html_soup, page_number, parent_page, *args, **kwargs)
        self._type = ELOGPageType.ELOGOpticalImagePageType
        self._required_element_dict = {
            ELOGPostElement.TitleDiv: {'id': 'protocol_title_div'},
            ELOGPostElement.GeneralOpticalImage: {'id': 'general_optical_image_section'},
            ELOGPostElement.HTMLNavigation: None,  # placeholder
            ELOGPostElement.Footer: {'id': 'footer'},
            ELOGPostElement.Script: {'name': 'script'}
        }
        self._page_tags = self.build_page()


class ELOGSamplePage(ELOGPage):

    def __init__(self, html_soup: BeautifulSoup, sample_full_name: str, page_number: int = None,
                 parent_page: ELOGPage = None, *args,
                 **kwargs):
        super().__init__(html_soup, page_number, parent_page, *args, **kwargs)
        self._type = ELOGPageType.ELOGSamplePageType
        self._sample_full_name = sample_full_name
        self._required_element_dict = {
            ELOGPostElement.TitleDiv: {'id': 'protocol_title_div'},
            ELOGPostElement.SampleElements: {'name': 'div', 'class_': 'sample_div', 'id': self._sample_full_name},
            ELOGPostElement.HTMLNavigation: None,  # placeholder
            ELOGPostElement.Footer: {'id': 'footer'},
            ELOGPostElement.Script: {'name': 'script'}
        }
        self._page_tags = self.build_page()

    @property
    def sample_name(self) -> str:
        return self._sample_full_name

    @sample_name.setter
    def sample_name(self, name: str):
        self._sample_full_name = name


class ELOGCombinedSamplePage(ELOGPage):
    def __init__(self, html_soup: BeautifulSoup, sample_full_name_list: list[str], page_number: int = None,
                 parent_page: ELOGPage = None, *args, **kwargs):
        super().__init__(html_soup, page_number, parent_page, *args, **kwargs)
        self._type = ELOGPageType.ELOGCombinedSamplePageType
        self._sample_full_name_list = sample_full_name_list
        self._required_element_dict = self.build_required_element_dict()
        self._page_tags = self.build_page()

    @property
    def sample_name_list(self) -> list[str]:
        return self._sample_full_name_list

    def build_required_element_dict(self):
        element_dict = {}
        element_dict[ELOGPostElement.TitleDiv] = {'id': 'protocol_title_div'}
        for sample in self._sample_full_name_list:
            element_dict[f'{ELOGPostElement.SampleElements}_{sample}'] = {
                'name': 'div',
                'class_': 'sample_div',
                'id': sample
            }
        element_dict[ELOGPostElement.HTMLNavigation] = None  # placeholder
        element_dict[ELOGPostElement.Footer] = {'id': 'footer'}
        element_dict[ELOGPostElement.Script] = {'name': 'script'}
        return element_dict


class ELOGConclusionPage(ELOGPage):
    def __init__(self, html_soup: BeautifulSoup, page_number: int = None, parent_page: ELOGPage = None, *args,
                 **kwargs):
        super().__init__(html_soup, page_number, parent_page, *args, **kwargs)
        self._type = ELOGPageType.ELOGConclusionPageType
        self._required_element_dict = {
            ELOGPostElement.TitleDiv: {'id': 'protocol_title_div'},
            ELOGPostElement.ConclusionDiv: {'class_': 'section_div', 'id': 'Conclusion'},
            ELOGPostElement.GeneralAttachment: {'id': 'general_attachment'},
            ELOGPostElement.HTMLNavigation: None,  # placeholder
            ELOGPostElement.Footer: {'id': 'footer'},
            ELOGPostElement.Script: {'name': 'script'}
        }
        self._page_tags = self.build_page()


class ELOGIntroOpticalConclusionPage(ELOGPage):
    def __init__(self, html_soup: BeautifulSoup, *args, **kwargs):
        super().__init__(html_soup, page_number=1, parent_page=self, *args, **kwargs)
        self._type = ELOGPageType.ELOGIntroOpticalConclusionType
        self._required_element_dict = {
            ELOGPostElement.TitleDiv: {'id': 'protocol_title_div'},
            ELOGPostElement.IntroductionDiv: {'class_': 'section_div', 'id': 'Introduction'},
            ELOGPostElement.NavigationDiv: {'class_': 'navigation_image_div'},
            ELOGPostElement.SampleDescriptionDiv: {'class_': 'section_div', 'id': 'Samples'},
            ELOGPostElement.SampleList: {'id': 'sample_list_div'},
            ELOGPostElement.GeneralOpticalImage: {'id': 'general_optical_image_section'},
            ELOGPostElement.ConclusionDiv: {'class_': 'section_div', 'id': 'Conclusion'},
            ELOGPostElement.GeneralAttachment: {'id': 'general_attachment'},
            ELOGPostElement.HTMLNavigation: None,  # placeholder
            ELOGPostElement.Footer: {'id': 'footer'},
            ELOGPostElement.Script: {'name': 'script'}
        }
        self._page_tags = self.build_page()


class ELOGIntroConclusionPage(ELOGPage):
    def __init__(self, html_soup: BeautifulSoup, *args, **kwargs):
        super().__init__(html_soup, page_number=1, parent_page=self, *args, **kwargs)
        self._type = ELOGPageType.ELOGIntroConclusionType
        self._required_element_dict = {
            ELOGPostElement.TitleDiv: {'id': 'protocol_title_div'},
            ELOGPostElement.IntroductionDiv: {'class_': 'section_div', 'id': 'Introduction'},
            ELOGPostElement.NavigationDiv: {'class_': 'navigation_image_div'},
            ELOGPostElement.SampleDescriptionDiv: {'class_': 'section_div', 'id': 'Samples'},
            ELOGPostElement.SampleList: {'id': 'sample_list_div'},
            ELOGPostElement.ConclusionDiv: {'class_': 'section_div', 'id': 'Conclusion'},
            ELOGPostElement.GeneralAttachment: {'id': 'general_attachment'},
            ELOGPostElement.HTMLNavigation: None,  # placeholder
            ELOGPostElement.Footer: {'id': 'footer'},
            ELOGPostElement.Script: {'name': 'script'}
        }
        self._page_tags = self.build_page()


class PageList(UserList):
    def __init__(self, initialdata=None):
        super().__init__(initialdata)

    def append(self, item) -> None:
        if item._type in UniquePageTypes:
            for it in self.data:
                if it._type == item._type:
                    raise autoerror.DuplicatePage(f'Attempt to add another {item._type}')
        super().append(item)

    def get_pages(self, page_type: ELOGPageType | list[ELOGPageType]) -> PageList[ELOGPage]:
        if isinstance(page_type, ELOGPageType):
            page_type = [page_type]
        page_list = PageList()
        for item in self.data:
            if item._type in page_type:
                page_list.append(item)
        return page_list


class ELOGPostSplitter:
    def __init__(self, html: str | BeautifulSoup, auto_split: bool = True, auto_combine: bool = True):
        if isinstance(html, str):
            html = BeautifulSoup(html, 'lxml')
        self._html_soup = html
        self._page_list = PageList()
        self._sample_list = None
        if auto_split:
            self.split()
        if auto_combine:
            self.combine()

    @property
    def num_of_pages(self):
        return len(self._page_list)

    def split(self):
        main_page = ELOGIntroPage(self._html_soup)
        self._page_list.append(main_page)
        general_optical_image_page = ELOGOpticalImagePage(self._html_soup, parent_page=main_page)
        if not general_optical_image_page.is_empty():
            self._page_list.append(general_optical_image_page)
        for sample in self.get_sample_list():
            self._page_list.append(ELOGSamplePage(self._html_soup, sample_full_name=sample, parent_page=main_page))
        conclusion_page = ELOGConclusionPage(self._html_soup, parent_page=main_page)
        if not conclusion_page.is_empty():
            self._page_list.append(conclusion_page)

    def get_all_pages(self) -> PageList[ELOGPage]:
        return self._page_list

    def get_main_page(self) -> ELOGPage | None:
        _list = self._page_list.get_pages([ELOGPageType.ELOGIntroPageType,
                                           ELOGPageType.ELOGIntroConclusionType,
                                           ELOGPageType.ELOGIntroOpticalConclusionType])
        if len(_list):
            return _list[0]
        else:
            return None

    def get_optical_image_page(self) -> ELOGPage | None:
        _list = self._page_list.get_pages(ELOGPageType.ELOGOpticalImagePageType)
        if len(_list):
            return _list[0]
        else:
            return None

    def get_conclusion_page(self) -> ELOGPage | None:
        _list = self._page_list.get_pages(ELOGPageType.ELOGConclusionPageType)
        if len(_list):
            return _list[0]
        else:
            return None

    def get_sample_pages(self) -> PageList[ELOGPage]:
        return self._page_list.get_pages([ELOGPageType.ELOGSamplePageType,
                                          ELOGPageType.ELOGCombinedSamplePageType])

    def combine(self):
        self._combine_unique_pages()
        self._combine_sample_pages()

    def _combine_sample_pages(self):
        pages = self.get_sample_pages()
        sizes = [page.page_size(only_relevant_elements=False) for page in pages]
        grouped_objs = []
        current_group = []
        current_group_size = 0
        for size, page in zip(sizes, pages):
            if current_group_size + size <= autoconfig.ELOG_PAGE_SIZE_LIMIT:
                current_group.append(page)
                current_group_size += size
            else:
                grouped_objs.append(current_group)
                current_group = []
                current_group_size = size
                current_group.append(page)
        grouped_objs.append(current_group)

        new_combined_sample_list = PageList()
        for group in grouped_objs:
            sample_names = [page.sample_name for page in group]
            new_combined_sample_list.append(ELOGCombinedSamplePage(self._html_soup, sample_names))
            for page in group:
                self._page_list.remove(page)

        if self._page_list[-1]._type == ELOGConclusionPage:
            conclusion_page = self.get_conclusion_page()
            self._page_list.pop()
            self._page_list.extend(new_combined_sample_list)
            self._page_list.append(conclusion_page)
        else:
            self._page_list.extend(new_combined_sample_list)

    def _combine_unique_pages(self):

        intro_page = self.get_main_page()
        if intro_page:
            intro_page_size = intro_page.page_size(only_relevant_elements=False)
        else:
            intro_page_size = 0

        optical_page = self.get_optical_image_page()
        if optical_page:
            # there is an optical image page
            optical_page_size = optical_page.page_size(only_relevant_elements=True)
        else:
            optical_page_size = 0

        conclusion_page = self.get_conclusion_page()
        if conclusion_page:
            conclusion_page_size = conclusion_page.page_size(only_relevant_elements=True)
        else:
            conclusion_page_size = 0

        if intro_page_size + optical_page_size + conclusion_page_size < autoconfig.ELOG_PAGE_SIZE_LIMIT:
            # we can fit the three pages in one
            # create it and prepend it to the page list
            self._page_list.insert(0, ELOGIntroOpticalConclusionPage(self._html_soup))
            # now remove the single ones.
            if intro_page:
                self._page_list.remove(intro_page)
            if optical_page:
                self._page_list.remove(optical_page)
            if conclusion_page:
                self._page_list.remove(conclusion_page)
        elif intro_page_size + conclusion_page_size < autoconfig.ELOG_PAGE_SIZE_LIMIT:
            # we cannot fit all three, but at least the intro and the conclusion
            self._page_list.insert(0, ELOGIntroConclusionPage(self._html_soup))
            if intro_page:
                self._page_list.remove(intro_page)
            if conclusion_page:
                self._page_list.remove(intro_page)

    def get_sample_list(self):
        if self._sample_list:
            return self._sample_list
        self._sample_list = list()
        sample_div_list = self._html_soup.find_all(class_='sample_div')
        for sample in sample_div_list:
            self._sample_list.append(sample['id'])

        return self._sample_list

    def rebuild_index(self, base_url: str, logbook: str, msg_ids: list[int], port: int = None):
        if len(msg_ids) != self.num_of_pages:
            raise autoerror.InvalidNumberOfPages('Expecting %s, got %s message ids' %
                                                 (self.num_of_pages, len(msg_ids)))

        self._assign_msg_ids(base_url, logbook, msg_ids, port)
        self._apply_anchor_lut()

    def _assign_msg_ids(self, base_url: str, logbook: str, msg_ids: list[int], port: int = None):
        main_page = self.get_main_page()
        for page_number, (msg_id, page) in enumerate(zip(msg_ids, self.get_all_pages())):
            if page._type not in [ELOGPageType.ELOGIntroPageType, ELOGPageType.ELOGIntroConclusionType,
                                  ELOGIntroOpticalConclusionPage]:
                page.parent_page = main_page

            page.set_elog_parameters(base_url, logbook, msg_id, port)
            page.page_number = page_number

        pages = [None, *self.get_all_pages(), None]
        for previous_page, current_page, next_page in zip(pages, pages[1:], pages[2:]):
            current_page._previous_page = previous_page
            current_page._next_page = next_page

    def _apply_anchor_lut(self):
        anchor_lut = self._build_anchor_lut()

        for page in self.get_all_pages():
            page._render_html_navigation()
            page._patch_title_div()

        joined_list = '|'.join(anchor_lut.keys())
        # matches against sample and section anchor
        simple_sample_pattern = f'(?P<ssp>^(?P<sample_name>({joined_list})))$'

        # matches microscope pictures, videos and sample attachments
        micro_pic_pattern = rf'(?P<mpp>^(?P<sample_name2>({joined_list}))/(?P<file_name>[^/]+\.\w+)$)'

        # matches generic attachment and optical pictures
        # #my_report.pdf
        generic_anchor_pattern = r'(?P<gap>^#(?P<file_name2>[^/]+\.\w+)$)'

        all_patterns = '|'.join([simple_sample_pattern, micro_pic_pattern, generic_anchor_pattern])

        anchors_pattern = re.compile(all_patterns)
        sample_anchors = self._html_soup.find_all(href=anchors_pattern)
        for anchor in sample_anchors:
            m = anchors_pattern.match(anchor['href'])
            if m:
                if m['ssp']:
                    # it's a simple_sample_pattern
                    old_anchor = m.group('sample_name')
                    anchor['href'] = anchor_lut[old_anchor]
                elif m['mpp']:
                    # it's an anchor to a microscope picture or video
                    old_anchor = m.group('sample_name2')
                    anchor['href'] = f'{anchor_lut[old_anchor]}/{m.group("file_name")}'
                elif m['gap']:
                    file_name = m['file_name2']
                    opt_etg = ElementTypeGuesser.from_regexp_repository('OPTICAL_IMAGE')
                    if opt_etg.is_ok(file_name):
                        page = self.get_optical_image_page() if self.get_optical_image_page() else self.get_main_page()
                        anchor['href'] = f'{page.url}#{file_name}'

                    att_etg = ElementTypeGuesser.from_regexp_repository('ATTACHMENT')
                    if att_etg.is_ok(file_name):
                        page = self.get_optical_image_page() if self.get_conclusion_page() else self.get_main_page()
                        anchor['href'] = f'{page.url}#{file_name}'

    def _build_anchor_lut(self) -> dict:
        # a dictionary with:
        # key: #old_anchor
        # value: https://host:port/logbook/msgid/#old_anchor
        anchor_lut = {}
        for page in self.get_sample_pages():
            if page._type == ELOGPageType.ELOGSamplePageType:
                sample_names = [page.sample_name]
            else:
                sample_names = page.sample_name_list

            for sample_name in sample_names:
                anchor_lut[f'#{sample_name}'] = f'{page.url}#{sample_name}'

        main_page = self.get_main_page()

        anchor_lut['#samplelist'] = f'{main_page.url}#samplelist'
        anchor_lut['#Navigation_images_customization'] = f'{main_page.url}#Navigation_images_customization'
        anchor_lut['#Introduction'] = f'{main_page.url}#Introduction'
        anchor_lut['#Samples'] = f'{main_page.url}#Samples'

        optical_image_page = self.get_optical_image_page()
        if optical_image_page is None:
            # the main page has to be intro-optical
            optical_image_page = main_page

        anchor_lut['#general_optical_image_section'] = f'{optical_image_page.url}#general_optical_image_section'

        conclusion_page = self.get_conclusion_page()
        if conclusion_page is None:
            # the main page has to be intro-conclusion.
            conclusion_page = main_page
        anchor_lut['#Conclusion'] = f'{conclusion_page.url}#Conclusion'
        anchor_lut['#Attachments'] = f'{conclusion_page.url}#Attachments'

        return anchor_lut
