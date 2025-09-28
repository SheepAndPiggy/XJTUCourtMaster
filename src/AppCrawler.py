import enum
import re
import base64
import json
from datetime import timezone, timedelta, datetime
from json import JSONDecodeError

import requests
from requests import RequestException
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from flask import flash

from .AppDataBase import CourtProperties, FieldProperties, OrderProperties
from .AppCaptchaHandler import CaptchaHandler



class BaseUrl(enum.Enum):
    # 获取客户端公钥的网址（防止公钥改变，虽然一般不会）
    PUBLIC_KEY_URL = "https://login.xjtu.edu.cn/token/jwt/publicKey"
    # 获取MFA多因素认证的验证码的网址
    MFA_URL = "https://login.xjtu.edu.cn/token/mfa/detect"
    # 获取手机验证码gid的网址
    STATE_URL = "https://login.xjtu.edu.cn/token/mfa/initByType/securephone"
    # 发送验证码的网址
    SEND_URL = "https://login.xjtu.edu.cn/attest/api/guard/securephone/send"
    # 验证验证码的网址
    VALID_URL = "https://login.xjtu.edu.cn/attest/api/guard/securephone/valid"
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


class AppCrawler:
    def __init__(self, username: str, password: str, encrypt_password=True):
        self.session = requests.Session()

        self.public_key = self.get_public_key()

        self.raw_username = username
        self.username = self.encrypt_with_rsa(username)
        if encrypt_password:
            self.password = self.encrypt_with_rsa(password)
        else:
            self.password = password
        self.deviceId = "YSmx0xA4NGYDALXeG11BophG"  # TODO: 考虑随机生成

        self.id_token = None
        self._refresh_token = None

    def get_public_key(self):
        """
        获取移动较大APP客户端RSA加密公钥
        :return: 公钥
        """
        try:
            response = self.session.get(BaseUrl.PUBLIC_KEY_URL.value)
        except RequestException as e:
            print("移动交大APP公钥请求失败！")
            raise e
        public_key_pem = response.content
        public_key = serialization.load_pem_public_key(
            public_key_pem,
            backend=default_backend()
        )
        return public_key

    def encrypt_with_rsa(self, user_data: str):
        """
        对用户名和密码使用公钥进行加密
        :param user_data: 待加密的用户名或者密码
        :return: 加密后的字符串
        """
        encrypted = self.public_key.encrypt(
            user_data.encode("utf-8"),
            padding.PKCS1v15()
        )
        return "__RSA__" + base64.b64encode(encrypted).decode("utf-8")

    def get_msa_state(self):  # TODO: 需要判断什么时候需要MFA验证
        """
        获取MFA验证码（多半为手机验证码）
        MFA验证码：除了用户名和密码之外，需要提供的第二种或更多种验证因素中的一种临时代码
        :return: MFA验证码
        """
        try:
            response = self.session.post(BaseUrl.MFA_URL.value, params={
                "username": self.username,
                "password": self.password,
                "deviceId": self.deviceId
            })
        except RequestException as e:
            print("MFA验证码请求失败！")
            raise e

        try:
            mfa_state = response.json().get("data", {}).get("state")
            secure_phone = response.json().get("data", {}).get("need", False)
        except (JSONDecodeError, AttributeError) as e:
            print("无法解析MFA验证码！")
            raise e
        return mfa_state, secure_phone

    def get_secure_phone(self, mfa_state):
        try:
            response = self.session.get(BaseUrl.STATE_URL.value, params={"state": mfa_state})
            gid = response.json().get("data", {}).get("gid", None)
            phone = response.json().get("data", {}).get("securePhone", None)
            response = self.session.post(BaseUrl.SEND_URL.value, json={"gid": gid})
            if response.json().get("code") != 0:
                raise ValueError("发送手机验证码失败！")
            return gid, phone
        except Exception as e:
            print("发送手机验证码失败！")
            flash("发送手机验证码失败！", "error")
            raise e

    def login(self):
        """
        用户登录
        :return: 返回登录后的凭证id和刷新凭证id
        """
        mfa_state, secure_phone = self.get_msa_state()

        if secure_phone:  # 如果需要进行验证码验证
            gid, phone = self.get_secure_phone(mfa_state)
            phone_code = input(f"请输入手机({phone})验证码: ")
            try:
                response = self.session.post(BaseUrl.VALID_URL.value, json={"code": phone_code, "gid": gid})
            except Exception as e:
                print("验证码验证失败！")
                flash("验证码验证失败！", "error")
                raise e

        try:
            response = self.session.post(BaseUrl.LOGIN_URL.value, params={
                "username": self.username,
                "password": self.password,
                "deviceId": self.deviceId,
                "appId": "com.supwisdom.xjtu",
                "mfaState": mfa_state
            }, timeout=10)
        except requests.exceptions.Timeout as e:
            print("登录超时！请检查网络连接！")
            raise e
        except requests.exceptions.ConnectionError as e:
            print("网络连接失败！请检查网络设置！")
            raise e

        if response.status_code == 200:
            print(f"用户{self.raw_username}登录成功！")
        elif response.status_code == 400:
            print("未通过MFA认证！")
            raise ValueError("未通过MFA认证！")
        elif response.status_code == 401:
            print("用户名或密码错误！")
            raise ValueError("用户名或密码错误！")
        elif response.status_code == 403:
            print("访问被拒绝！IP可能被服务器封禁！")
            raise requests.RequestException("访问被拒绝！IP可能被服务器封禁！")
        elif response.status_code >= 500:
            print("服务器内部错误！")
            raise requests.RequestException("服务器内部错误！")
        else:
            print(f"HTTP错误！[{response.status_code}]")
            raise requests.RequestException(f"HTTP错误！[{response.status_code}]")

        try:
            # 获取id_token
            self.id_token = response.json()["data"]["idToken"]
            # TODO: 此处refresh_token用于当id_token失效时向服务器请求新的id_token，请求逻辑有待更新
            self._refresh_token = response.json()["data"]["refreshToken"]
        except (JSONDecodeError, AttributeError) as e:
            print("解析登录返回信息失败！")
            raise e
        return self

    def jump_to_app(self):
        """
        自动跳转至体育场馆预约界面，在此过程中自动获取服务器set的SESSION等cookies
        :return: None
        """
        if self.id_token is None:
            print("请先登录！")
            raise ValueError("请先登录！")

        headers = {
            "connection": "keep-alive",
            "x-id-token": self.id_token,
            "X-Requested-With": "com.supwisdom.xjtu",
        }
        params = {
            "responseType": "code",
            "scope": "user_info",
            "appId": 1659,  # 体育场馆预约的appId
            "state": 1234,
            "redirectUri": "http://202.117.17.144:8080/web/cas/oauth2url.html",
        }

        try:
            self.session.get(BaseUrl.JUMP_URL.value,
                             headers=headers, params=params,
                             allow_redirects=True, timeout=10)  # 允许自动跳转
        except RequestException as e:
            print("跳转到体育场馆预约应用失败！")
            raise e
        return self

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
        try:
            response = self.session.get(BaseUrl.PLACE_URL.value, params=params, timeout=10)
        except RequestException as e:
            print("获取场馆信息失败！")
            return None
        try:
            places = response.json()
            return [CourtProperties(i) for i in places]
        except JSONDecodeError as e:  # TODO: 此处异常处理逻辑有待完善
            print("获取场馆信息失败！可能是由于当前时间系统未开放（开放时间：08:40-21:40）")
            return None

    def get_fields(self, date, court_id):
        """
        获取id为field_id的场馆中的日期为date的所有场次
        :param date: 日期，格式为YYYY-MM-DD
        :param court_id: 场次的id
        :return: None
        """
        pattern = r'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$'
        if not bool(re.match(pattern, str(date))):
            print("日期格式错误！应为YYYY-MM-DD")
            raise ValueError("日期格式错误！应为YYYY-MM-DD")

        params = {
            "s_date": date,  # 根据日期获取球场场次预约数据
            "serviceid": court_id
        }
        try:
            response = self.session.get(BaseUrl.FIELD_URL.value, params=params, timeout=10)
        except RequestException as e:
            print(f"获取{date}时间{court_id}场馆的场次信息失败！")
            return None
        try:
            field_data = response.json()
            objects = field_data.get("object")
            if objects is None:
                return None
            return [FieldProperties(i) for i in objects]
        except JSONDecodeError as e:
            print(f"获取{date}时间{court_id}场馆的场次信息失败！")
            return None

    def get_captcha_result(self):
        """
        获取验证码
        :return: 验证码id和验证码背景图片，滑块图片
        """
        response = self.session.get(BaseUrl.CAPTCHA_URL.value)
        try:
            captcha_result = response.json()
        except JSONDecodeError as e:
            print("获取验证码失败！")
            raise e
        captcha_id = captcha_result["id"]
        h = CaptchaHandler(captcha_result["captcha"])
        track_list = h.get_track()
        return captcha_id, track_list

    def pay_field(self, court_id, field_id, stock_id):
        try:
            captcha_id, track_list = self.get_captcha_result()
        except:
            return None, "100"
        start_time = datetime.now(timezone.utc)
        slide_duration = track_list[-1]["t"] / 1000
        end_time = start_time + timedelta(seconds=slide_duration)

        # 转换为ISO格式
        start_iso = start_time.isoformat(timespec='milliseconds')
        end_iso = end_time.isoformat(timespec='milliseconds')

        # 生成paytoken
        pay_token = "synjones" + str(captcha_id) + "synjoneshttp://202.117.17.144:8071"
        stock_detail = {str(stock_id): str(field_id)}
        param = {"stockdetail": stock_detail, "venueReason": "", "fileUrl": "", "address": str(court_id)}

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
        try:
            response = self.session.post(BaseUrl.PAY_URL.value, data=data, headers=headers)
        except RequestException as e:
            print(f"预定场馆{court_id}-场地{field_id}-场次{stock_id}失败！message[未知网络请求问题]")
            return None, None
        try:
            result = response.json()
            result_id = result.get("result")
            message = result.get("message")
            objects = result.get("object")
            if result_id == '1':
                print(f"预定场馆{court_id}-场地{field_id}-场次{stock_id}成功！message[{message}]")
                result_info = objects.get("order", {})
                return OrderProperties(result_info), '1'
            elif result_id == '100':
                print(f"预定场馆{court_id}-场地{field_id}-场次{stock_id}失败！message[{message}]")
                return None, '100'  # 验证码错误
            elif result_id == '0':
                print(f"预定场馆{court_id}-场地{field_id}-场次{stock_id}失败！message[{message}]")
                if message == "未支付":  # 未支付也算预定成功
                    return None, "1"
                return None, '0'  # 各种原因，例如已被预订，不在预订时间内
            elif result_id is None:
                print(f"预定场馆{court_id}-场地{field_id}-场次{stock_id}失败！message[{message}]")
                return None, '-1'  # 用户没有登录，需要运行jump_to_app
            else:
                print(f"预定场馆{court_id}-场地{field_id}-场次{stock_id}失败！message[{message}]")
                return None, '0'  # 可能的未知原因
        except JSONDecodeError:
            print(f"预定场馆{court_id}-场地{field_id}-场次{stock_id}失败！message[解析json数据失败]")
            return None, None


if __name__ == '__main__':
    pass
