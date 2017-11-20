# encoding: utf-8

import datetime
import hashlib
import re
from time import sleep
from collections import defaultdict

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from base import BaseWebScraping
import ruokuai


class ShouldTerminateException(Exception):
    pass

class ToeflScraping(BaseWebScraping):
    """
    JwScraping is for web scraping on our jw system.
    Support login with captcha (manually input)

    """
    def __init__(self):
        BaseWebScraping.__init__(self)

        self.user = ""
        self.password = ""
        self.login_state = False

        self.encoding = 'gb2312'

        self.__epoch = datetime.datetime.utcfromtimestamp(0)
        self.last_seat_query_url = ""

    def init_from_config(self, json_path):
        props = self.read_json(json_path)

        self.refresh_session()

        self.update_header(props['headers'])
        self.user = props['user']
        self.password = props['password']
        self.url_prefix = props['url_prefix']

        self.last_seat_query_url = self.url_prefix

    def milli_since_epoch(self):
        now = datetime.datetime.utcnow()
        delta = now - self.__epoch
        res = delta.total_seconds() * 1e3
        return int(res)

    def _input_captcha(self):
        # milli seconds since 19700101, mimic `new Date().getTime()` of JavaScript
        a = self.milli_since_epoch()
        # random number between 0 and 1, mimic `Math.Random()` of JavaScript
        r = np.random.random()
        a_len, r_len = 14, 16  # from source code of the website
        img_url = self.url_prefix + "{:14.16f}".format(a+r) + 'VerifyCode3.jpg'

        # self.show_img(img_url)
        # captcha = raw_input("Input the captcha in the previous image: ")
        captcha = self.img_url_ruokuai(img_url)
        return captcha

    @staticmethod
    def get_md5(s):
        m = hashlib.md5()
        m.update(s)
        return m.hexdigest()

    def get_encoded_pwd(self, captcha):
        s1 = self.password + self.user
        s1_md5 = self.get_md5(s1)
        s2 = s1_md5 + captcha.lower()
        s2_md5 = self.get_md5(s2)
        encoded_password = s2_md5
        return encoded_password

    def login(self):
        """Login to the system."""
        url = self.url_prefix + "TOEFLAPP"

        captcha = self._input_captcha()

        encoded_password = self.get_encoded_pwd(captcha)

        form = {'username': self.user,
                '__act': '__id.24.TOEFLAPP.appadp.actLogin',
                'password': encoded_password,
                'LoginCode': captcha,
                'btn_submit.x': str(25 + np.random.randint(-3, 3)),
                'btn_submit.y': str(6 + np.random.randint(-3, 3))}

        res = self.ses.post(url, data=form)
        res.encoding = self.encoding
        decoded_content = res.text

        self.login_state = 'Refresh' in decoded_content
        return self.login_state

    def visit_homepage(self):
        url = self.url_prefix + 'MyHome/?'
        self.update_header({'Referer': self.url_prefix + 'TOEFLAPP'})
        res = self.ses.get(url)
        res.encoding = self.encoding
        decoded_content = res.text
        return 'RMB'.encode(self.encoding) in decoded_content

    def get_register_page_captcha(self):
        url = self.url_prefix + 'CityAdminTable'
        self.update_header({'Referer': self.url_prefix + 'MyHome?'})
        res = self.ses.get(url)
        res.encoding = self.encoding
        decoded_content = res.text

        ptn = r'img src="/cn/(\d+\.\d+)'
        search_res = re.search(ptn, decoded_content)
        img_id = search_res.group(1)
        postfix = r'.VerifyCode2.jpg'
        img_url = self.url_prefix + img_id + postfix

        """
        self.show_img(img_url)
        captcha = raw_input("Input the captcha in the previous image: ")
        """
        captcha = self.img_url_ruokuai(img_url)
        return captcha

    def img_url_ruokuai(self, url):
        img_byte = self.url2byte(url)
        captcha, err_msg = ruokuai.bypass_captcha(img_byte)
        if err_msg:
            if u'快豆不足' in err_msg:
                print "Error msg: {}".format(err_msg)
                print "Terminate!"
                raise ShouldTerminateException
            self.logger.warn("RuoKuai error: {}".format(err_msg))
        return captcha

    def seize_seats(self, month='201710', province='Shanghai'):
        captcha_pass = False
        decoded_content = ""
        err_count = 0
        while not captcha_pass:
            err_count += 1
            if err_count > 8:
                raise ValueError("captcha err_count > 8 in seize seats")
            url = self.url_prefix + r'SeatsQuery'

            captcha = self.get_register_page_captcha()

            form = {'mvfAdminMonths': month,
                    'mvfSiteProvinces': province,
                    'whichFirst': 'AS',
                    'afCalcResult': captcha,
                    '__act': '__id.34.AdminsSelected.adp.actListSelected',
                    'submit.x': str(np.random.randint(-7, 7) + 45),
                    'submit.y': str(np.random.randint(-7, 7) + 8)}

            self.update_header({'Referer': self.url_prefix + 'CityAdminTable'})
            self.last_seat_query_url = url + '?' + self._dict_to_url(form)
            res = self.ses.post(url, form)
            res.encoding = self.encoding
            decoded_content = res.text

            if u'请重新输入验证码' in decoded_content:
                self.logger.info("Re-enter captcha in seize_seats.")
            elif u'操作太频繁' in decoded_content:
                sleep_len = 31 + np.random.rand() * 3
                self.logger.info("Too frequent, sleep for {:.2f} seconds".format(sleep_len))
                sleep(sleep_len)
            else:
                captcha_pass = True

        time_dic = self.str2dic(decoded_content)

        register_res = self.process_time_dic(time_dic)
        return register_res

    def str2dic(self, s):
        """Convert query results from html string to pd.DataFrame"""
        time_dic = defaultdict(list)

        soup = BeautifulSoup(s, 'html.parser')
        main = soup.find_all('div', {'id': 'maincontent'})[0]

        sections_raw = main.find_all('tr')
        if not sections_raw:
            self.logger.warn("No sections in maincontent. HTML is:")
            self.logger.info(main.text)
            return time_dic

        # E0E0E0 means time, CCCCCC means seat info
        color_allowed = [u'#E0E0E0', u'#CCCCCC']
        sections = filter(lambda x: x.attrs['bgcolor'] in color_allowed, sections_raw)

        date = '0'*8
        for sec in sections:
            color = sec.attrs['bgcolor']

            if color == color_allowed[0]:
                date = sec.text.encode('ascii', 'ignore')[:9]
            else:  # color == color_allowed[1]
                tds = sec.find_all('td')

                location = tds[2].text
                status = tds[4].text
                location_code = tds[1].text
                if status == u'有名额':
                    status_bool = True
                elif status == u'名额已报满':
                    status_bool = False
                else:
                    raise NotImplementedError(u"status = ".format(status))

                site_dic = {'location': location,
                            'status': status_bool,
                            'location_code': location_code}
                time_dic[date].append(site_dic)

        return time_dic

    def process_time_dic(self, d):
        date_ddl = 20171018
        register_res = False
        for date, sites in d.viewitems():
            if int(date) > date_ddl:
                continue

            for site_dic in sites:
                if site_dic['status']:
                    print '='*10 + "Register! "
                    print site_dic
                    register_res = self.register(date, site_dic['location_code'])
                    if register_res:
                        self.logger.warn(u"Register! location={}, date={}".format(site_dic['location'], date))
                        break
            else:
                self.logger.info("No sites available.")
        return register_res

    def register(self, date, location_code):
        date_code = date + 'A'

        url = r'https://toefl.etest.net.cn/cn/'

        form = dict()
        form['__act'] = 'SITE.9.{:s}ADMIN.9.{:s}__id.30.AdminsSelected.adp.actRegister'.format(location_code, date_code)
        form['siteadmin'] = '{:s}={:s}'.format(date_code, location_code)
        s = u'注册'
        s_gb2312 = s.encode(self.encoding)
        form['Submit'] = self.url_encode(s_gb2312)

        self.update_header({'Referer': self.last_seat_query_url})
        res = self.ses.post(url, form)
        res.encoding = self.encoding
        decoded_content = res.text
        self.logger.warn("Register response HTML:\n" + decoded_content)

        return False


def main_with_captcha():
    """Main function to add courses and priorities and grasp them."""
    props_path = r'E:\SYS Files\Documents\Python files\WebScraping\NJU_Login\jiaowu\SeizeCourse\toefl.json'
    err_count = 0

    grasper = ToeflScraping()
    grasper.init_from_config(props_path)

    login_success = False
    homepage_success = False
    while not (login_success and homepage_success):
        err_count += 1
        if err_count > 8:
            grasper.logger.warn("login retry = 8, sleep.")
            return
        login_success = grasper.login()
        homepage_success = grasper.visit_homepage()
    msg = 'User {} login success!'.format(grasper.user)
    grasper.logger.info(msg)

    for i in range(300):
        # raw = raw_input("Input month.city, eg: [YYYYMM].[Shanghai]")
        rand = np.random.rand()
        if rand > 0.66:
            raw = '201710.Jiangsu'
        elif rand > 0.33:
            raw = '201710.Zhejiang'
        else:
            raw = "201710.Shanghai"

        if raw:
            month, city = raw.split('.')
        else:
            month, city = "201710.Shanghai".split('.')

        if i % 1 == 0:
            grasper.logger.info("grasping... count={} month={}, city={}".format(i, month, city))

        register_success = grasper.seize_seats(month, city)
        if register_success:
            grasper.logger.warn("register success!")
            raise ValueError("register success!")
        sleep(2)

    del grasper


if __name__ == "__main__":
    while True:
        try:
            main_with_captcha()
            sleep(61)
        except ShouldTerminateException:
            break
        except Exception, e:
            print "except in main: {}".format(e)
