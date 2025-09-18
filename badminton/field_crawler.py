import json
import base64
import enum
from datetime import timezone, timedelta
from datetime import datetime

import requests
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from .captcha_handler import CaptchaHandler
from .field_parser import CourtData, FieldData


import functools

def retry(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        retry_num = 20
        for attempt in range(1, retry_num + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"重试[{attempt}]")
                if attempt == retry_num:
                    raise  # 超过重试次数抛出最后一次异常
        return None
    return wrapper


class BaseUrl(enum.Enum):
    # 获取客户端公钥的网址（防止公钥改变，虽然一般不会）
    PUBLIC_KEY_URL = "https://login.xjtu.edu.cn/token/jwt/publicKey"
    # 进行登录验证的网址
    LOGIN_URL = "https://login.xjtu.edu.cn/token/password/passwordLogin"
    # 跳转到场馆预定应用的网址
    JUMP_URL = "http://org.xjtu.edu.cn/openplatform/oauth/authorize"
    # 获取不同场馆数据的网址
    PLACE_URL = "http://202.117.17.144:8080/web/product/productData.html"
    # 获取指定场馆不同场次数据的网址
    FIELD_URL = "http://202.117.17.144:8080/web/product/findOkArea.html"
    # 获取指定场馆不可预定的场次的网址
    LOCKED_FIELD_URL = "http://202.117.17.144:8080/web/product/findLockArea.html"
    # 获取验证码的网址
    CAPTCHA_URL = "http://202.117.17.144:8080/gen"
    # 预定指定场次的网址
    PAY_URL = "http://202.117.17.144:8080/web/order/tobook.html"


class FieldCrawler(object):
    def __init__(self, username, password):
        self.session = requests.Session()

        self.public_key = self.get_public_key()  # 公钥
        self.username = self.encrypt_with_rsa(username)  # RSA加密的用户名
        self.password = self.encrypt_with_rsa(password)  # RSA加密的密码

        try:
            self.id_token, self.refresh_token = self.login()  # 用户登录
        except Exception as e:  # TODO: 需要添加更多的异常处理逻辑
            print(f"用户{username}登录失败！")
            raise e

        try:
            self.jump_to_app()  # 跳转到体育场馆预约应用
        except Exception as e:
            print("跳转到体育场馆预约应用失败！")
            raise e

        self.courts = self.get_courts()

    def get_public_key(self):
        """
        获取移动较大APP客户端RSA加密公钥
        :return: 公钥
        """
        response = self.session.get(BaseUrl.PUBLIC_KEY_URL.value)
        public_key_pem = response.content
        public_key = serialization.load_pem_public_key(
            public_key_pem,
            backend=default_backend()
        )
        return public_key

    def encrypt_with_rsa(self, data):
        """
        对用户名和密码使用公钥进行加密
        :param data: 待加密的用户名或者密码
        :return: 加密后的字符串
        """
        encrypted = self.public_key.encrypt(
            data.encode("utf-8"),
            padding.PKCS1v15()
        )
        return "__RSA__" + base64.b64encode(encrypted).decode("utf-8")

    def login(self):
        """
        用户登录
        :return: 返回登陆后的凭证id和刷新凭证id
        """
        response = self.session.post(BaseUrl.LOGIN_URL.value, params={
            "username": self.username,
            "password": self.password,
            "deviceId": "YSmx0xA4NGYDALXeG11BophK",  # 该字段可能为app安装时生成的设备Id，实际与项目无关，可随便设置
            "appId": "com.supwisdom.xjtu",
        })

        # 获取id_token
        id_token = response.json()["data"]["idToken"]
        # TODO: 此处refresh_token用于当id_token失效时向服务器请求新的id_token，请求逻辑有待更新
        refresh_token = response.json()["data"]["refreshToken"]
        return id_token, refresh_token

    def jump_to_app(self):
        """
        自动跳转至体育场馆预约界面，在此过程中自动获取服务器set的SESSION等cookies
        :return: None
        """
        headers = {
            "connection": "keep-alive",
            "x-id-token": self.id_token,
            "X-Requested-With": "com.supwisdom.xjtu",
        }
        params = {
            "responseType": "code",
            "scope": "user_info",
            "appId": 1659, # 体育场馆预约的appId
            "state": 1234,
            "redirectUri":	"http://202.117.17.144:8080/web/cas/oauth2url.html",
        }
        self.session.get(BaseUrl.JUMP_URL.value,
                                headers=headers, params=params,
                                allow_redirects=True)  # 允许自动跳转

    def get_courts(self):
        """
        获取所有体育场馆的数据信息
        :return: 场馆数据对象
        """
        params = {
            "page": 1,
            "rows": 100, # 一次性获取所有的场馆
            "merccode": 100001,
            "remark": "defaultProList"
        }
        response = self.session.get(BaseUrl.PLACE_URL.value, params=params)
        try:
            places = response.json()
            return CourtData(places)  # 将所有场馆的基本信息封装到数据库中
        except json.decoder.JSONDecodeError as e:  # TODO: 此处异常处理逻辑有待完善
            print("当前时间系统未开放！（开放时间：08:40-21:40）")
            raise e

    def get_field(self, date, court_id):
        """
        获取id为field_id的场馆中的日期为date的所有场次
        :param date: 日期，格式为YYYY-MM-DD
        :param court_id: 场次的id
        :return: None
        """
        params = {
            "s_date": date,  # 根据日期获取球场场次预约数据
            "serviceid": court_id
        }
        response = self.session.get(BaseUrl.FIELD_URL.value, params=params)
        try:
            field_data = response.json()
            return FieldData(court_id, date, field_data["object"])  # 将指定场馆指定日期的场次信息封装到数据库中
        except json.decoder.JSONDecodeError as e:
            print(f"获取{date}时间{court_id}场馆的场次信息失败！")
            raise e

    def get_captcha_result(self):
        """
        获取验证码
        :return: 验证码id和验证码背景图片，滑块图片
        """
        response = self.session.get(BaseUrl.CAPTCHA_URL.value)
        try:
            captcha_result = response.json()
        except json.decoder.JSONDecodeError as e:
            print("获取验证码失败！")
            raise e
        captcha_id = captcha_result["id"]
        h = CaptchaHandler(captcha_result["captcha"])
        track_list = h.get_track()
        return captcha_id, track_list

    @retry
    def pay_field(self, date, field_id, stock_detail):
        self.jump_to_app()  # 重新进入体育场馆预定界面，更新SESSION

        captcha_id, track_list = self.get_captcha_result()
        start_time = datetime.now(timezone.utc)
        slide_duration = track_list[-1]["t"] / 1000
        end_time = start_time + timedelta(seconds=slide_duration)

        # 转换为ISO格式
        start_iso = start_time.isoformat(timespec='milliseconds')
        end_iso = end_time.isoformat(timespec='milliseconds')

        # 生成paytoken
        pay_token = "synjones" + str(captcha_id) + "synjoneshttp://202.117.17.144:8071"
        param = {"stockdetail": stock_detail, "venueReason": "", "fileUrl": "", "address": str(field_id)}

        yzm = {
            "bgImageWidth": 260,
            "bgImageHeight": 0,
            "sliderImageWidth": 0,
            "sliderImageHeight": 159,
            "startSlidingTime": start_iso,
            "endSlidingTime": end_iso,
            "trackList": track_list,
        }
        yzm = json.dumps(yzm) + pay_token

        data = {
            "param": json.dumps(param),
            "yzm": yzm,
            "json": "true"
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        response = self.session.post(BaseUrl.PAY_URL.value, data=data, headers=headers)
        try:
            result = response.json()
            print(result)
        except json.decoder.JSONDecodeError as e:
            print(f"预定{date}时间{field_id}场馆{stock_detail}场次失败！")
            raise e
        if result["message"] == '预订成功':
            print(f"预定{date}时间{field_id}场馆{stock_detail}场次成功！")
            return result
        elif result["message"] == "已被预订":
            print(f"预定{date}时间{field_id}场馆{stock_detail}场次已被预订！")
            return result
        else:
            print(f"预定{date}时间{field_id}场馆{stock_detail}场次失败！")
            raise ValueError


class PayScheduler:
    def __init__(self, session):
        self.session = session
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_listener(self.job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self.scheduler.start()
        self.jobs = {}  # 保存任务信息

    def schedule_pay(self, order_id, schedule_time, date, field_id, stock_detail, tot_data):
        # 使用 cron 表达式，设定每天的 08:40:00 执行任务
        run_time = datetime.strptime(schedule_time, "%Y-%m-%d %H:%M:%S")

        # 在每天的 08:40:00 执行
        job = self.scheduler.add_job(
            self.session.pay_field,
            'cron',  # 使用 cron 触发器
            hour=run_time.hour,
            minute=run_time.minute,
            second=run_time.second,
            args=[date, field_id, stock_detail]
        )
        self.jobs[str(order_id)] = [job, tot_data]
        print(f"支付任务已调度，订单 {order_id} 将在 {run_time} 执行")

    def cancel_pay(self, order_id):
        job_info = self.jobs.pop(str(order_id), None)
        if job_info:
            job = job_info[0]
            self.scheduler.remove_job(job.id)
            print(f"支付任务已取消，订单 {order_id}")

    def shutdown(self):
        self.scheduler.shutdown()
        print("调度器已关闭")

    def job_listener(self, event):
        """监听任务完成或出错"""
        job_id = event.job_id
        # 找到对应的订单
        for order_id, (job, tot_data) in self.jobs.items():
            if job.id == job_id:
                if event.exception:
                    tot_data['status'] = '失败'
                    print(f"订单 {order_id} 支付失败")
                else:
                    tot_data['status'] = '成功'
                    print(f"订单 {order_id} 支付成功")
                break



if __name__ == '__main__':
    pass


