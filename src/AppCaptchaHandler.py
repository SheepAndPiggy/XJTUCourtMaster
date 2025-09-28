import base64
import random

import cv2
import numpy as np


class CaptchaHandler(object):
    def __init__(self, captcha_json_data):
        self.background_image_width = captcha_json_data["backgroundImageWidth"]
        self.background_image_height = captcha_json_data["backgroundImageHeight"]
        self.slider_image_width = captcha_json_data["sliderImageWidth"]
        self.slider_image_height = captcha_json_data["sliderImageHeight"]

        background_image = self.base64_to_cv2(captcha_json_data["backgroundImage"])
        slider_image = self.base64_to_cv2(captcha_json_data["sliderImage"])
        self.background_image = cv2.resize(background_image, (self.background_image_width, self.background_image_height))
        self.slider_image = cv2.resize(slider_image, (self.slider_image_width, self.slider_image_height))

    @staticmethod
    def base64_to_cv2(base64_str):
        # 去掉前缀 "data:image/jpeg;base64,"
        base64_data = base64_str.split(",")[1]
        # 解码
        img_data = base64.b64decode(base64_data)
        # 转 numpy 数组
        img_array = np.frombuffer(img_data, np.uint8)
        # 解码成 OpenCV 图像
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)  # 彩色图
        return img

    def _show_image(self):
        top_left, bottom_right = self.find_gap_position()

        # 创建一个画布，高度取背景高度，宽度 = 滑块宽度 + 背景宽度
        canvas = np.zeros((self.background_image_height, self.background_image_width + self.slider_image_width, 3), dtype=np.uint8)
        canvas[0:self.slider_image_height, 0:self.slider_image_width] = self.slider_image
        canvas[0:self.background_image_height, self.slider_image_width:self.slider_image_width + self.background_image_width] = self.background_image

        top_left = (top_left[0] + self.slider_image_width, top_left[1])
        bottom_right = (bottom_right[0] + self.slider_image_width, bottom_right[1])
        cv2.rectangle(canvas, top_left, bottom_right, (0, 0, 255), 2)

        cv2.imshow("Captcha Images", canvas)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def _cut_bg_img(self, margin=10):
        # 预处理滑块：转灰度 + 二值化
        slider_gray = cv2.cvtColor(self.slider_image, cv2.COLOR_BGR2GRAY)
        _, slider_bin = cv2.threshold(slider_gray, 50, 255, cv2.THRESH_BINARY)

        # 找到非黑色区域（即滑块缺口形状）
        coords = cv2.findNonZero(slider_bin)
        x, y, w, h = cv2.boundingRect(coords)

        # 只取有效缺口形状区域
        slider_crop = slider_gray[y:y + h, x:x + w]

        # 裁剪背景图的对应水平区域
        H, W = self.background_image.shape[:2]
        y1 = max(y - margin, 0)
        y2 = min(y + h + margin, H)
        bg_crop = self.background_image[y1:y2, :]

        return bg_crop, slider_crop

    def find_gap_position(self):
        bg_gray = cv2.cvtColor(self.background_image, cv2.COLOR_BGR2GRAY)
        slider_gray = cv2.cvtColor(self.slider_image, cv2.COLOR_BGR2GRAY)

        # 高斯滤波降噪
        bg_gray = cv2.GaussianBlur(bg_gray, (5, 5), 0)
        slider_gray = cv2.GaussianBlur(slider_gray, (5, 5), 0)

        # 边缘检测（Canny 算法）
        bg_edges = cv2.Canny(bg_gray, 100, 200)
        slider_edges = cv2.Canny(slider_gray, 100, 200)

        # 模板匹配
        result = cv2.matchTemplate(bg_edges, slider_edges, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        top_left = max_loc
        bottom_right = (top_left[0] + slider_edges.shape[1], top_left[1] + slider_edges.shape[0])

        return top_left, bottom_right

    def get_track(self):
        top_left, bottom_right = self.find_gap_position()
        center_x = (top_left[0] + bottom_right[0]) // 2
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

