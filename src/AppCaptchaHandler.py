import json
import sqlite3
import base64
import random

import requests
import numpy as np
import cv2


class CaptchaDatabase:
    CAPTCHA_COLS = [
        "backgroundImage",
        "sliderImage",
        "backgroundImageWidth",
        "backgroundImageHeight",
        "sliderImageWidth",
        "sliderImageHeight",
        "data",
    ]

    @staticmethod
    def get_captcha_data():
        response = requests.get("http://202.117.17.144:8080/gen")
        result = response.json()
        return result

    @staticmethod
    def init_db(db_path: str = "captchas.db"):
        sql = """
        CREATE TABLE IF NOT EXISTS captchas (
          id TEXT PRIMARY KEY,
          backgroundImage TEXT,
          sliderImage TEXT,
          backgroundImageWidth INTEGER,
          backgroundImageHeight INTEGER,
          sliderImageWidth INTEGER,
          sliderImageHeight INTEGER,
          data TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_captchas_bg_wh
          ON captchas (backgroundImageWidth, backgroundImageHeight);
        CREATE INDEX IF NOT EXISTS idx_captchas_slider_wh
          ON captchas (sliderImageWidth, sliderImageHeight);
        """
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(sql)
        finally:
            conn.close()

    @staticmethod
    def _row_from_item(item: dict):
        cid = item.get("id")
        c = item.get("captcha", {}) or {}

        # data 字段统一转为 JSON 文本（None 保持为 None）
        data_val = c.get("data")
        if data_val is not None and not isinstance(data_val, (str, bytes)):
            data_val = json.dumps(data_val, ensure_ascii=False)

        row = [
            cid,
            c.get("backgroundImage"),
            c.get("sliderImage"),
            c.get("backgroundImageWidth"),
            c.get("backgroundImageHeight"),
            c.get("sliderImageWidth"),
            c.get("sliderImageHeight"),
            data_val,
        ]
        return row

    @classmethod
    def insert_many(cls, items: list, db_path: str = "captchas.db"):
        """
        批量插入；当 id 冲突时不插入（忽略）。
        """
        if not items:
            return 0

        conn = sqlite3.connect(db_path)
        try:
            with conn:
                sql = """
                INSERT OR IGNORE INTO captchas (
                  id, backgroundImage, sliderImage,
                  backgroundImageWidth, backgroundImageHeight,
                  sliderImageWidth, sliderImageHeight, data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """
                rows = [cls._row_from_item(it) for it in items]
                cur = conn.executemany(sql, rows)
                return cur.rowcount
        finally:
            conn.close()

    @staticmethod
    def load_many(db_path: str = "captchas.db"):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                cur = conn.execute(f"SELECT * FROM captchas")
                while True:
                    rows = cur.fetchmany(100)
                    if not rows:
                        break
                    for row in rows:
                        yield row
        finally:
            conn.close()


class CaptchaLoader:
    @staticmethod
    def _change_to_cv2(img):
        img = img.split(",")[-1]
        img_data = base64.b64decode(img)
        np_arr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return img

    @staticmethod
    def to_float(gray):
        g = gray.astype(np.float32)
        # 全局零均值/单位方差（可换成局部CLAHE）
        g = (g - g.mean()) / (g.std() + 1e-6)
        return g

    @classmethod
    def features(cls, gray, mode="grad"):
        """把灰度图转成更稳健的特征图：raw / edge / grad"""
        if mode == "raw":
            return cls.to_float(gray)
        if mode == "edge":
            e = cv2.Canny(gray, 50, 150)
            return cls.to_float(e)
        if mode == "grad":
            gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
            mag = cv2.magnitude(gx, gy)
            return cls.to_float(mag)
        raise ValueError("mode must be raw/edge/grad")

    @classmethod
    def find_slider_pos(cls, captcha_img, slider_img):
        captcha_img = cls._change_to_cv2(captcha_img)
        slider_img = cls._change_to_cv2(slider_img)

        c_hsv = cv2.cvtColor(captcha_img, cv2.COLOR_BGR2HSV)
        _, _, bg = cv2.split(c_hsv)

        s_hsv = cv2.cvtColor(slider_img, cv2.COLOR_BGR2HSV)
        _, _, sl = cv2.split(s_hsv)
        mask = sl > 10
        coords = np.column_stack(np.where(mask))
        y_min, x_min = coords.min(axis=0)
        y_max, x_max = coords.max(axis=0)
        sl = sl[y_min:y_max + 1, x_min:x_max + 1]

        bg = cls.features(bg)
        sl = cls.features(sl)

        res = cv2.matchTemplate(bg, sl, method=cv2.TM_CCOEFF_NORMED)
        minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(res)
        x, y = maxLoc
        return x, x + sl.shape[1]

    @classmethod
    def show_captcha(cls, captcha_img, slider_img):
        bx, hx = cls.find_slider_pos(captcha_img, slider_img)
        captcha_img = cls._change_to_cv2(captcha_img)

        h, w = captcha_img.shape[:2]
        cv2.line(captcha_img, (bx, 0), (bx, h), (0, 0, 255), 2)
        cv2.line(captcha_img, (hx, 0), (hx, h), (0, 0, 255), 2)
        cv2.imshow("Captcha_S", captcha_img)

        cv2.waitKey(0)
        cv2.destroyAllWindows()


class CaptchaHandler(object):
    def __init__(self, captcha_json_data):
        self.background_image_width = captcha_json_data["backgroundImageWidth"]
        self.background_image_height = captcha_json_data["backgroundImageHeight"]
        self.slider_image_width = captcha_json_data["sliderImageWidth"]
        self.slider_image_height = captcha_json_data["sliderImageHeight"]

        self.bx, self.hx = CaptchaLoader.find_slider_pos(captcha_json_data["backgroundImage"],
                                                             captcha_json_data["sliderImage"])

    def get_track(self):
        center_x = (self.bx + self.hx) // 2
        distance = center_x - self.slider_image_width // 2

        distance = int(260 / self.background_image_width * distance)  # 缩放窗口宽度
        track = []
        current_x = 0  # 设置滑动起始位置
        current_v = 0  # 设置初始速度
        current_t = random.randint(1000, 2500)  # 设置滑动起始时间
        low_speed_threshold = distance * random.uniform(3 / 4, 4 / 5)  # 开始减速的距离阈值
        start_sep_time = random.randint(50, 100)  # 设置开始的间隔时间，模拟人手开始滑动的慢速
        current_sep_time = random.randint(10, 30)  # 设置滑动过程的间隔时间
        end_sep_time = random.randint(5, 10)  # 设置结束的间隔时间

        track.append({"x": current_x, "y": 0, "type": "down", "t": current_t})
        if_first = True
        while current_x < distance:
            if if_first:
                sep_time = start_sep_time
                if_first = False
            else:
                sep_time = current_sep_time

            if current_x < low_speed_threshold:
                a = random.uniform(1500, 3000)  # 设置加速阶段加速度
            else:
                a = random.uniform(-2000, -1500)  # 设置减速阶段加速度
            current_t += sep_time
            current_x += 1 / 2 * a * (sep_time / 1000) ** 2 + current_v * (sep_time / 1000)
            current_v += a * sep_time / 1000
            track.append({"x": int(current_x), "y": 0, "type": "move", "t": current_t})
        track.append({"x": int(current_x), "y": 0, "type": "up", "t": current_t + end_sep_time})
        return track

