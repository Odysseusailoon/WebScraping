# encoding: utf-8

import requests
from PIL import Image
from urllib import quote
from StringIO import StringIO

from bs4 import BeautifulSoup

import logging

import re

import winsound

from time import sleep

from base import BaseWebScraping


class JwScraping(BaseWebScraping):
    """
    JwScraping is for web scraping on our jw system.
    Support login with captcha (manually input)

    """
    def __init__(self):
        BaseWebScraping.__init__(self)

        self.user = ""
        self.password = ""
        self.login_state = False

    def init_from_config(self, json_path):
        props = self.read_json(json_path)

        self.refresh_session()

        self.update_header(props['headers'])
        self.user = props['user']
        self.password = props['password']
        self.url_prefix = props['url_prefix']

    def _input_captcha(self):
        img_url = self.url_prefix + r'ValidateCode.jsp'

        res = self.ses.get(img_url, stream=True)
        image = Image.open(res.raw)
        image.show()
        captcha = raw_input("Input the captcha in the previous image: ")
        return captcha

    def login(self):
        """Login to the system."""
        url = self.url_prefix + r"login.do"

        captcha = self._input_captcha()
        form = {'userName': self.user, 'password': self.password,
                'returnUrl': 'null',
                'ValidateCode': captcha}

        res = self.ses.post(url, data=form)

        decoded_content = res.content.decode('utf-8')
        self.login_state = 'teachinginfo' in decoded_content
        if self.login_state:
            msg = 'User {} login success!'.format(self.user)
            self.logger.info(msg)
        else:
            msg = 'User {} login FAILED!'.format(self.user)
            self.logger.warn(msg)


class JwCourse(object):
    """
    Basic data type of a course in our jw system.

    Attributes
    ----------
    id : str
        a series of digits represent the ID of the course in the system.
    name : str
        A custom name.
    academy : str
        The college the course belongs to.
    type : str
        Type of the course.

    """
    def __init__(self, id_, type_, name="", academy=""):
        self.id = str(id_)
        self.name = name
        self.academy = str(academy)
        self.type = type_  # 'tongxiu', 'tongshi', 'kuayuanxi', 'gongxuan'

    def __repr__(self):
        return "{}: ID={}, college={}".format(self.name, self.id, self.academy)

    def __str__(self):
        return self.__repr__()


class PriorityQueue(object):
    """
    A priority queue supporting loop.
    Small value means higher priority.

    Attributes
    ----------
    __queue : list
        container
    __size : int
        size of __queue
    __priority : int
        current priority upper limit.

    """
    def __init__(self):
        self.__queue = []
        self.__size = 0
        self.__priority = 65535

    @property
    def size(self):
        return self.__size

    @property
    def priority(self):
        return self.__priority

    def get_pos(self, pos):
        return self.__queue[pos]

    def put(self, item, prior=0):
        for idx in range(self.size):
            if self.get_pos(idx)[0] > prior:
                self.__queue.insert(idx, (prior, item))
                break
        else:
            self.__queue.append((prior, item))

        self.__size += 1

    def generator(self):
        for prior, item in self.__queue:
            if prior >= self.priority:
                break
            result = yield item
            if result:
                self.__priority = prior
                break


class CourseGrasper(JwScraping):
    """CourseGrasper is a class used to grasp course."""
    def __init__(self):
        JwScraping.__init__(self)

        self.COURSE_RENEW_TYPE_MAP = {'tongxiu': 'commonRenew',
                                      'tongshi': 'discussRenew',
                                      'gongxuan': 'publicRenew',
                                      'kuayuanxi': 'openRenew'}
        self.RENEW_PAGE_MAP = {'xueqixuanke': 'index.do',
                               'gong': 'publicCourseList.do',
                               'kuayuanxi': 'open.do',
                               'tongxiu': r'commonRenew.do'}

    def visit_once(self, course_type):
        # TODO this func has not been updated
        infix = 'student/elective/'
        postfix = self.RENEW_PAGE_MAP[course_type]

        url = self.url_prefix + infix + postfix

        res = self.ses.get(url)
        if res.status_code == 200:
            self.logger.info('Visited {} success.'.format(course_type))
        else:
            self.logger.warn('Visited {} failed.'.format(course_type))

    def notify_change(self):

        fp = r'E:\SYS Files\Documents\Python files\WebScraping\NJU_Login\jiaowu\SeizeCourse\ringtong.wav'
        flag1 = False  # self._check_xuanke_page_sections()
        flag2 = self._check_renew_page()

        if flag1 or flag2:
            self.logger.warn("Please go check the course and shut me down!")
            if flag1:
                self.logger.info("flag 1 is True!")
                winsound.PlaySound(fp, winsound.SND_ALIAS)
            if flag2:
                winsound.PlaySound(fp, winsound.SND_ALIAS)
                self.logger.info("flag 1 is True!")

    def _check_xuanke_page_sections(self):
        """Check whether there are more than 3 sections on the course selecting page."""
        page = r'student/elective/index.do'
        url = self.url_prefix + page

        res = self.ses.get(url)
        content = res.content.decode('utf8')

        soup = BeautifulSoup(content, 'html.parser')
        main = soup.find_all('div', {'id': 'Function'})[0]
        sections = main.find_all('li')
        for i in sections:
            print i.text

        bool_list = map(lambda sec: u'通修课补选' in sec.text, sections)
        return any(bool_list)

    def _check_renew_page(self):
        """Check whether course renew of tongxiu has started."""
        course_type = 'tongxiu'

        self.visit_once(course_type)

        url0, params_0 = self.generate_params(course_type,
                                              submit_id=None,
                                              academy="",
                                              xianlin=True)
        res0 = self.ses.post(url0, params_0)
        content = res0.content.decode('utf8')

        msg = u'现在还没有开始通修课补选'

        return msg not in content

    def grasp_course_renew(self, course_obj):
        """
        Submit request to select certain course, return whether success.

        Parameters
        ----------
        course_obj : JwCourse

        Returns
        -------
        success : bool

        """
        # first visit once
        if course_obj.type == 'tongxiu':
            self.visit_once('tongxiu')

        url0, params_0 = self.generate_params(course_obj.type,
                                              submit_id=None,
                                              academy=course_obj.academy,
                                              xianlin=True)
        res0 = self.ses.post(url0, params_0)
        if not res0.status_code == 200:
            self.logger.warn("Error! Visit once failed.")

        # then submit request
        url, params_ = self.generate_params(course_obj.type,
                                            submit_id=course_obj.id,
                                            academy=course_obj.academy,
                                            xianlin=True)
        res = self.ses.post(url, params=params_)

        err_msg = self.check_res(res)
        if err_msg:
            self.logger.info(str(course_obj) + "  ---  " + err_msg)
            return False
        else:
            return True

    def _check_course_type(self, t):
        if t not in self.COURSE_RENEW_TYPE_MAP:
            raise NotImplementedError("course type of {} not support yet.".format(t))

    def generate_params(self, course_type, submit_id=None, academy="", xianlin=True):
        """
        Generate URL of various tasks.

        Parameters
        ----------
        course_type : str
            {'tongshi', 'tongxiu', 'gongxuan'}
        submit_id : int or str, default None
            ID of the course to be selected,
            if None return CourseList URL, else return submit URL.
        academy : str or int
            ID for different colleges that the course belong to.
        xianlin : bool
            True for Xianlin campus, False for Gulou campus.

        Returns
        -------
        res : tuple
            (URL, params_dict)

        """
        self._check_course_type(course_type)

        params = dict()
        params_additional = dict()

        # construct parameters dict
        if course_type == 'tongxiu':
            params_additional['courseKind'] = '15'  # 15 means SiZhengKe
        elif course_type == 'tongshi' or course_type == 'gongxuan':
            params_additional['campus'] = quote('仙林校区') if xianlin else quote('鼓楼校区')
        elif course_type == 'kuayuanxi':
            params_additional['academy'] = str(academy)

        method = self.COURSE_RENEW_TYPE_MAP[course_type]
        # submit or just check the course list
        if submit_id:
            method = 'submit' + self._cap_first_letter(method)
            params['classId'] = str(submit_id)
        else:
            method = method + 'CourseList'

        if course_type == 'tongxiu' and not submit_id:
            method = 'commonCourseRenewList'  # this is a typo of the system, not me

        params['method'] = method
        params.update(params_additional)

        infix = r'student/elective/courseList.do'
        url = self.url_prefix + infix
        return url, params

    @staticmethod
    def check_res(request_res):
        """Check the result of course registration.

        Returns
        -------
        err_msg : str or None
            None means no error.

        """
        res_str = request_res.content.decode('utf8')

        # success_str = u'\u8bfe\u7a0b\u9009\u62e9\u6210\u529f' # 课程选择成功
        # full_str = u'\u73ed\u7ea7\u5df2\u6ee1' # 课程已满
        # conflict_str = u'\u548c\u5df2\u9009\u8bfe\u7a0b\u5b58\u5728\u65f6\u95f4\u51b2\u7a81'

        # if success_str in res_str:
        #     err_msg = None
        # elif full_str in res_str:
        #     err_msg = 'Course is FULL'
        # elif conflict_str in res_str:
        #     err_msg = 'Course is conflict with others'
        # else:
        #     err_msg = 'Other failure'
        pattern = r'function initSelectedList[\s,\S]*?alert\((".*?")\)'
        search_res = re.search(pattern, res_str)
        err_msg = search_res.group(1)
        return err_msg


def main_with_captcha():
    """Main function to add courses and priorities and grasp them."""
    props_path = r'E:\SYS Files\Documents\Python files\WebScraping\NJU_Login\jiaowu\SeizeCourse\jiaowu.json'

    grasper = CourseGrasper()
    grasper.init_from_config(props_path)
    grasper.login()
    assert grasper.login_state

    from scipy.stats import chi2
    """
    # when use this program, we only need to change following lines to add course and priority
    ganjiguo_tue = JwCourse(99975432, 'tongxiu', 'GanJiGuo_Tue', '15')
    ganjiguo_fri = JwCourse(99975431, 'tongxiu', 'GanJiGuo_Fri', '15')
    gaojing_mon = JwCourse(99972222, 'tongxiu', 'GaoJing_Mon', '15')
    mao_gai_pq = PriorityQueue()
    mao_gai_pq.put(ganjiguo_tue, 0)
    mao_gai_pq.put(ganjiguo_fri, 1)
    mao_gai_pq.put(gaojing_mon, 2)

    gen = mao_gai_pq.generator()
    target_course = gen.next()
    while True:
        r = chi2.rvs(df=2)
        sleep(r)

        select_success = grasper.grasp_course(target_course)

        try:
            target_course = gen.send(select_success)
        except StopIteration:
            gen = mao_gai_pq.generator()
            target_course = gen.next()
            # break
    """
    while True:
        r = chi2.rvs(df=2)
        sleep(r)
        grasper.logger.info("sleep {:.1f} seconds...".format(r))
        grasper.notify_change()


def test_priority_queue():
    pq = PriorityQueue()
    pq.put('3', 3)
    pq.put('1', 1)
    pq.put('0', 0)
    pq.put('5', 5)
    pq.put('7', 7)
    gen = pq.generator()
    gen.next()
    gen.send(False)
    gen.send([])
    assert pq.priority == 65535
    assert gen.next() == '5'
    try:
        gen.send(True)
    except StopIteration:
        pass
    assert pq.priority == 5
    pq.put('4', 4)

    i = 0
    gen = pq.generator()
    while 1:
        try:
            i = gen.next()
        except StopIteration:
            break
    assert i == '4'

    print 'priority_queue test passed'


def test_generate_api():
    q = CourseGrasper()
    print q.generate_params('tongxiu', False, True)
    print q.generate_params('tongxiu', 74533, False)
    print q.generate_params('tongshi', False, True)
    print q.generate_params('gongxuan', False, True)
    print 'func generate_api test passed'

if __name__ == '__main__':
    main_with_captcha()
