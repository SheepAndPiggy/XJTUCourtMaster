import re
import json
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
import numpy as np

from src.AppScheduler import AppScheduler

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"
scheduler = None
fields = None


def current_username():
    return session.get("username", "访客")


@app.route("/home", methods=["GET"])
def home():
    q = (request.args.get("q") or "").strip().lower()

    def hit(v):
        return (q in v["name"].lower()) or (q in (v.get("memo") or "").lower())

    venues = [c.properties for c in scheduler.courts]
    venues = [v for v in venues if not q or hit(v)]
    return render_template(
        "home.html",
        active_page="home",
        username=current_username(),
        venues=venues,
        logout_url=url_for("logout"),
    )


def get_venue(venue_id:int):
    venues = [c.properties for c in scheduler.courts]
    return next((v for v in venues if v["id"] == str(venue_id)), None)

@app.get("/venue_detail/<int:venue_id>")
def venue_detail(venue_id:int):
    v = get_venue(venue_id)
    if not v:
        abort(404)
    # 默认日期：今天（也可从 querystring 读取并回填给 input）
    return render_template("venue_detail.html", venue=v,
                           current_date=date.today().isoformat(),
                           username=current_username())


@app.get("/api/venues/<int:venue_id>/schedule")
def api_venue_schedule(venue_id:int):
    global fields
    v = get_venue(venue_id)
    if not v:
        return jsonify({"error":"venue not found"}), 404

    qd = request.args.get("date")
    try:
        y,m,d = map(int, (qd or date.today().isoformat()).split("-"))
        target = date(y,m,d)
    except Exception:
        return jsonify({"error":"invalid date"}), 400

    fields = scheduler.crawler.get_fields(target, venue_id)

    ts = np.unique([f.time_no for f in fields])
    first_times = [int(t.split(":")[0]) for t in ts]
    indexs = np.argsort(first_times)
    times = [{"id": t, "label": t} for t in ts[indexs]]

    cs = np.unique([f.sname for f in fields]).tolist()
    cs_nums = [int(re.search("(\d+)", c).group(1)) for c in cs]
    cs = sorted(cs, key=lambda c: cs_nums[cs.index(c)])
    courts = [{"id": c, "name": c} for c in cs]

    cells = {}
    for c in courts:
        for t in times:
            key = f"{c['id']}|{t['id']}"
            for f in fields:
                if f.sname == c["name"] and f.time_no == t["label"]:
                    status = f.status
                    price = f.price
                    stock_id = f.stockid
                    field_id = f.id
                    break
            else:
                status = -1
                price = -1
                stock_id = -1
                field_id = -1
            if status <= 0:
                status = "closed"
            elif status == 2:
                status = "occupied"
            else:
                status = "available"
            cells[key] = {"price": price, "status": status,
                          "stock_id":  stock_id,
                          "court_id": field_id}

    return jsonify({
        "venue_id": venue_id,
        "date": target.isoformat(),
        "courts": courts,
        "times": times,
        "cells": cells
    })


# === 新增：全局监听模式
@app.post("/api/venues/<int:venue_id>/listen")
def api_venue_listen(venue_id:int):
    v = get_venue(venue_id)
    if not v:
        return jsonify({"error":"venue not found"}), 404

    data = request.get_json(silent=True) or {}
    qdate = data.get("date") or date.today().isoformat()
    try:
        y,m,d = map(int, qdate.split("-")); _ = date(y,m,d)
    except Exception:
        return jsonify({"error":"invalid date"}), 400

    try:
        num = int(data.get("num", 1))
    except Exception:
        return jsonify({"error":"invalid num"}), 400

    if num < 1:
        return jsonify({"error":"num must be >= 1"}), 400

    scheduler.monitor_court(str(venue_id), qdate, num)
    watch_id = f"W-{venue_id}-{qdate.replace('-','')}-{num}"
    return jsonify({"ok": True, "watch_id": watch_id})


@app.post("/api/venues/<int:venue_id>/book")
def api_venue_book(venue_id:int):
    v = get_venue(venue_id)
    if not v:
        return jsonify({"error":"venue not found"}), 404

    data = request.get_json(silent=True) or {}
    qdate = data.get("date") or date.today().isoformat()
    court_id = (data.get("court_id") or "").strip()
    stock_id = (data.get("stock_id") or "").strip()

    if not court_id or not stock_id:
        return jsonify({"error":"missing court_id or stock_id"}), 400

    scheduler.order_stock(qdate, str(venue_id), str(court_id), str(stock_id))
    order_id = f"O-{venue_id}-{qdate.replace('-','')}-{court_id}-{abs(hash(stock_id))%100000}"
    return jsonify({"ok": True, "order_id": order_id})


@app.route("/sessions", methods=["GET"])
def session_manage():
    jobs = scheduler.jobs
    keys = list(jobs.keys())
    tasks = []
    for num, key in enumerate(keys):
        if key.endswith("order"):
            venue_id, date, field_id, stock_id, mode = key.split("/")
        else:
            venue_id, date, mode = key.split("/")
        mode = "listen" if mode == "monitor" else "book"
        v = get_venue(venue_id)
        venue_name = v["name"]
        if scheduler.user_order.get(key) is None:
            status = "listening"
        elif scheduler.user_order.get(key) is False:
            status = "failed"
        else:
            status = "success"
        task = {
            "id": num,
            "date": date,
            "venue_name": venue_name,
            "mode": mode,
            "status": status
        }
        tasks.append(task)

    sessions = sorted(tasks, key=lambda x: x["id"])  # 使显示顺序为 1,2,3…（配合模板里的 loop.index）
    return render_template(
        "sessions.html",
        active_page="sessions",
        username=session.get("username"),
        sessions=sessions,
        logout_url=url_for("logout"),
    )


@app.post("/tasks/<int:task_id>/delete")
def task_delete(task_id:int):
    global scheduler
    # 从 TASKS 中删除对应任务
    jobs = scheduler.jobs
    if task_id >= len(jobs):
        flash("任务不存在或已删除。", "error")
    else:
        key = list(jobs.keys())[task_id]
        del jobs[key]
        if key in scheduler.user_order:
            del scheduler.user_order[key]
        flash(f"已删除任务 {task_id}", "success")
    return redirect(url_for("session_manage"))


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    flash(f"如遇到页面卡住的情况，请查看程序终端，根据提示输入手机验证码（再次登录即可正常登录）")
    global scheduler
    if scheduler is not None:
        return redirect(url_for("home"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        try:
            scheduler = AppScheduler(username, password)
            session["username"] = username
            with open("data/users.json", "w") as file:
                json.dump({"username": username, "password": scheduler.crawler.password}, file, indent=2)
        except:
            flash("用户名或密码错误！", "error")
            return render_template("login.html")
        flash(f"欢迎，{username}！", "success")
        return redirect(url_for("home"))
    else:
        with open("data/users.json", "r") as file:
            data = json.load(file)
        username = data["username"]
        password = data["password"]
        if username == "" and password == "":
            return render_template("login.html")
        try:
            scheduler = AppScheduler(username, password, encrypt_password=False)
            session["username"] = username
            return redirect(url_for("home"))
        except:
            flash("自动登录失败！", "error")
            return render_template("login.html")


@app.post("/logout")
def logout():
    global scheduler
    session.clear()
    scheduler = None
    with open("data/users.json", "w") as file:
        json.dump({"username": "", "password": ""}, file, indent=2)
    flash("已退出登录", "info")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=False)
