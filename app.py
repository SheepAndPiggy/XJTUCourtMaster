import json
import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify

from badminton.field_crawler import FieldCrawler, PayScheduler

app = Flask(__name__, template_folder='templates')
app.secret_key = "your_secret_key"
user_session = None
user_scheduler = None


@app.route("/")
def _index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    global user_session
    global user_scheduler
    global username

    # 读取账户密码
    with open("data/user.json", "r") as f:
        data = json.load(f)
        username = data.get("username", "")
        password = data.get("password", "")

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        try:
            user_session = FieldCrawler(username, password) if user_session is None else user_session
            user_scheduler = PayScheduler(user_session) if user_scheduler is None else user_scheduler
            flash("登录成功！", "success")
            session.pop('_flashes', None)  # 清空消息队列
            # 保存账户和密码
            with open("data/user.json", "w") as f:
                data = {"username": username, "password": password}
                json.dump(data, f, indent=2)
            return redirect(url_for("index"))
        except Exception as e:
            flash("用户名或密码错误！", "danger")
            return redirect(url_for("login"))

    try:
        # 如果文件里有用户名和密码，尝试自动登录
        if username and password:
            try:
                user_session = FieldCrawler(username, password) if user_session is None else user_session
                user_scheduler = PayScheduler(user_session) if user_scheduler is None else user_scheduler
                flash("自动登录成功！", "success")
                session.pop('_flashes', None)  # 清空消息队列
                return redirect(url_for("index"))
            except:
                flash("自动登录失败，请重新输入。", "danger")

    except FileNotFoundError:
        pass

    return render_template("login.html", username=username, password=password)


@app.route("/logout")
def logout():
    global user_session
    global user_scheduler
    user_session = None
    user_scheduler = None
    with open("data/user.json", "w") as f:
        f.write(json.dumps({"username": "", "password": ""}))  # 清空用户名和密码
    return redirect(url_for("login"))

@app.route("/index", methods=["GET", "POST"])
def index():
    venues = user_session.courts.load_all_courts()
    return render_template("index.html", username=username, venues=venues)


@app.route("/venue/<int:venue_id>/")
@app.route("/venue/<int:venue_id>/<string:date>")
def venue_detail(venue_id, date=None):
    if not date:
        date = datetime.date.today()
        date = date.strftime("%Y-%m-%d")

    # 根据ID获取场馆信息
    venue = user_session.courts.get_court_by_id(int(venue_id))
    if not venue:
        return "场馆不存在"

    field_obj = user_session.get_field(date, venue_id)
    field_data = field_obj.get_fields_by_date_and_court(date, venue_id)
    fields = [i["field_name"] for i in field_data]
    field_indexs = [i["field_index"] for i in field_data]
    n_fields = list(set(zip(field_indexs, fields)))
    n_fields.sort()
    fields = [i[1] for i in n_fields]
    schedule = field_obj.get_schedule(date, venue_id)

    return render_template("venue_detail.html",
                           court_id=venue_id,
                           venue=venue,
                           username=username,
                           courts=fields,
                           schedule=schedule,
                           current_date=date)


@app.route('/reserve', methods=['POST'])
def reserve():
    try:
        data = request.get_json()  # 解析 JSON 数据
        court_id = data.get("court_id")
        time = data.get("time")
        field_id = data.get("field_id")
        stock_id = data.get("stock_id")
        date = data.get("date")
        name = data.get("name")
        run_date = data.get("run_date")

        if run_date == "current":
            now = datetime.datetime.now()
            future_time = now + datetime.timedelta(seconds=10)
            run_date = future_time.strftime("%Y-%m-%d %H:%M:%S")

        place = user_session.courts.get_court_by_id(court_id)
        field_name = place.get("court_name")
        data["field_name"] = field_name
        data["status"] = "正在监听"

        order_id = len(user_scheduler.jobs)
        data["order_id"] = order_id

        stock_detail = {str(stock_id): str(field_id)}

        user_scheduler.schedule_pay(order_id, run_date, date, court_id, stock_detail, data)
        return {"success": True}
    except Exception as e:
        return {"success": False}


@app.route("/lists", methods=["GET", "POST"])
def lists():
    lists = [i[1] for i in user_scheduler.jobs.values()]
    return render_template("list.html", bookings=lists)


@app.route("/cancel_booking", methods=["POST"])
def cancel_booking():
    data = request.get_json()
    order_id = data.get("order_id")
    user_scheduler.cancel_pay(order_id)
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True)
