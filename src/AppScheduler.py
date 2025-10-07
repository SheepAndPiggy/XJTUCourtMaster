from functools import partial
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from flask import flash

from .AppCrawler import AppCrawler


class AppScheduler(BackgroundScheduler):
    def __init__(self, username, password, *, timezone="Asia/Shanghai", encrypt_password=True):
        super(AppScheduler, self).__init__(timezone=timezone)
        self.crawler = AppCrawler(username, password, encrypt_password=encrypt_password)

        self.user_order = {}  # 用户的订单字典
        self.jobs = {}  # 正在运行的任务字典

        # 完成爬虫的初始配置
        self.crawler.login()
        self.crawler.jump_to_app()
        self.courts = self.crawler.get_courts()

        self.start()  # 启动任务

    def monitor_court(self, court_id, date, num, *, max_retry=10, if_monitor=False):
        for court in self.courts:
            if court.id == court_id:
                break
        else:
            raise ValueError(f"没有名为{court_id}的场馆")
        if court.advancenum < num:
            print("设置预订数量超过最大预订数量！")
            num = court.advancenum

        fields = self.crawler.get_fields(date, court_id)
        status = [i.status == 1 for i in fields]
        if any(status):
            print(f"场地{court_id}存在空闲场次，开始预订")
            for pos, s in enumerate(status):
                if s:  # 如果场次开放
                    field = fields[pos]
                    field_id = field.id
                    stock_id = field.stockid

                    max_retry_ = max_retry
                    while max_retry_:
                        # TODO: 可以加入智能计算优先抢哪些场次的算法
                        result, code = self.crawler.pay_field(court_id, field_id, stock_id)
                        if code == '1':
                            job_key = court_id + "/" + date + "/" + "monitor"
                            self.user_order[job_key] = result
                            num -= 1
                            break  # 退出retry循环
                        elif code == '100':
                            max_retry_ -= 1
                        elif code == '0':
                            max_retry_ -= 1
                            # TODO: 有时候系统不会显示预订成功，已经被预订也可能代表成功，需要加入检验订单列表的逻辑
                        elif code == '-1':
                            max_retry_ -= 1  # 如果SESSION过期也要减掉重试次数，防止无限循环
                            self.crawler.jump_to_app()  # 获取新的SESSION
                        else:
                            max_retry_ -= 1
                        print(f"重试[{max_retry - max_retry_}]")
                if num == 0:
                    job_key = court_id + "/" + date + "/" + "monitor"
                    if (job := self.jobs.get(job_key)) is not None:
                        self.pause_job(job.id)
                        self.remove_job(job.id)
                    print("场次预订完毕！")
                    break
        if not if_monitor:
            print(f"需要监听的场次数量：{num}")
            if num > 0:  # 如果还剩余，则进入监听模式
                print("开始监听")
                job = self.add_job(
                    partial(self.monitor_court, court_id=court_id, date=date, num=num, if_monitor=True),
                    IntervalTrigger(seconds=30),
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=60,
                    jitter=2
                )
                job_key = court_id + "/" + date + "/" + "monitor"
                self.jobs[job_key] = job
                return job
            else:
                print("场次预订完毕！")
        return None

    def _order_stock(self, date, court_id, field_id, stock_id):
        max_retry = 10
        max_retry_ = max_retry
        while max_retry_ > 0:
            self.crawler.jump_to_app()  # 预订任务隔夜，SESSION必然过期，需要重新获取
            result, code = self.crawler.pay_field(court_id, field_id, stock_id)
            if code == '1':
                job_key = court_id + "/" + date + "/" + stock_id + "/" + "order"
                self.user_order[job_key] = result
                print("场次预订完毕！")
                return  # 退出retry循环
            elif code == '100':
                max_retry_ -= 1
            elif code == '0':
                max_retry_ -= 1
                # TODO: 有时候系统不会显示预订成功，已经被预订也可能代表成功，需要加入检验订单列表的逻辑
            elif code == '-1':
                max_retry_ -= 1  # 如果SESSION过期也要减掉重试次数，防止无限循环
                self.crawler.jump_to_app()  # 获取新的SESSION
            else:
                max_retry_ -= 1
            print(f"重试[{max_retry - max_retry_}]")
        job_key = court_id + "/" + date + "/" + field_id + "/" + stock_id + "/" + "order"
        self.user_order[job_key] = False

    def order_stock(self, date, court_id, field_id, stock_id, *, order_date=None):
        for court in self.courts:
            if court.id == court_id:
                break
        else:
            raise ValueError(f"没有名为{court_id}的场馆")

        if order_date is None:
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
            n_days_ago = date_obj - timedelta(days=court.advanceday)
            order_date = datetime.combine(n_days_ago, datetime.strptime('08:40:01', '%H:%M:%S').time())
        else:
            order_date = datetime.strptime(order_date, '%Y-%m-%d %H:%M:%S')
        flash(f"订单将在{order_date}执行", "info")

        job_key = court_id + "/" + date + "/" + field_id + "/" + stock_id + "/" + "order"
        job = self.add_job(
            partial(self._order_stock, date=date, court_id=court_id, field_id=field_id, stock_id=stock_id),
            DateTrigger(run_date=order_date),
            id=job_key,
            replace_existing=True
        )
        self.jobs[job_key] = job


if __name__ == '__main__':
    pass
