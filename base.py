# encoding: utf-8

import requests
from PIL import Image
from urllib import quote
from StringIO import StringIO

import logging


class BaseWebScraping(object):
    """
    Base class for web scraping tasks using requests.
    Support request headers, cookie.

    Attributes
    ----------
    ses : requests.Session
    url_prefix : str
    logger : logging.Logger

    """
    def __init__(self):
        self.ses = None
        self.url_prefix = ""

        self.logger = logging.getLogger(self.__class__.__name__)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(levelname)-6s %(asctime)s %(name)s %(message)s')
        handler.setFormatter(formatter)
        while self.logger.handlers:
            self.logger.handlers.pop()
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    @property
    def headers(self):
        return self.ses.headers

    def init_from_config(self, json_path):
        pass

    def refresh_session(self):
        self.ses = requests.Session()

    def update_header(self, dic):
        if not self.ses:
            return

        self.ses.headers.update(dic)

    @staticmethod
    def _dict_to_url(d):
        """
        from {'k1': 'v1', 'k2': 'v2'} to 'k1=v1&k2=v2'

        """
        l = ['='.join([str(k), str(v)]) for k, v in d.items()]
        res = '&'.join(l)
        return res

    @staticmethod
    def _cap_first_letter(s):
        res = s[0].upper() + s[1:]
        return res

    @staticmethod
    def read_json(file_path):
        """Returns a dict."""
        import json
        import codecs
        f = codecs.open(file_path, 'r', 'utf-8')
        res = json.load(f)
        return res

    @staticmethod
    def url_encode(s):
        """s must be unicode."""
        return quote(s)

    def show_img(self, url):
        res = self.ses.get(url, stream=True)
        image = Image.open(res.raw)
        image.show()

    def url2byte(self, url):
        res = self.ses.get(url)#, stream=True)
        r = StringIO(res.content)

        """
        with open('download.jpg', 'wb') as f:
            f.write(raw)
        """
        c = r.read()
        with open('download.jpg', 'wb') as f:
            f.write(c)
        return c
