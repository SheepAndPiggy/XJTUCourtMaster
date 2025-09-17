import sqlite3


class FieldData(object):
    def __init__(self, court_id, date, fields):
        self.db_path = "data/courts.db"
        self.court_id = court_id
        self.date = date
        fields = list(map(lambda f: self.parse_data(f), fields))
        self.save_to_db(fields)

    def parse_data(self, field):
        field_id = field.get('id')  # 场地的id
        status = field.get('status')  # 当前场次状态（1表示可预约）
        field_name = field.get('sname')  # 场地的名称
        field_index = field.get('name')  # 场地的名称（'1','2','3'......）便于排序
        price = field.get('stock', {}).get('price')  # 场地的价格
        field_time = field.get('stock', {}).get('time_no')  # 场次对应的时间字符串
        stock_id = field.get("stockid")  # 场次的id
        return {
            "court_id": self.court_id,
            "date": self.date,
            "field_id": field_id,
            "status": status == 1,
            "field_name": field_name,
            "field_index": int(field_index) if field_index else None,
            "price": price,
            "field_time": field_time,
            "stock_id": stock_id,
        }

    def save_to_db(self, fields):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS fields_info
                       (
                           schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                           court_id INTEGER NOT NULL,
                           date TEXT NOT NULL,
                           field_id INTEGER NOT NULL,
                           status INTEGER NOT NULL,
                           field_name TEXT,
                           field_index INTEGER,
                           price REAL,
                           field_time TEXT,
                           stock_id INTEGER,
                           FOREIGN KEY (court_id) REFERENCES courts_info (court_id)
                           UNIQUE (court_id, field_id, stock_id, date)
                           )
                       ''')
        cursor.executemany('''
                           INSERT INTO fields_info (court_id, date, field_id, status, field_name, field_index,
                                                      price, field_time, stock_id)
                           VALUES (:court_id, :date, :field_id, :status, :field_name, :field_index, :price,
                                   :field_time, :stock_id)
                           ON CONFLICT(court_id, field_id, stock_id, date) DO UPDATE SET
                                status = excluded.status,
                                field_name = excluded.field_name,
                                field_index = excluded.field_index,
                                price = excluded.price,
                                field_time = excluded.field_time
                           ''', fields)
        conn.commit()
        conn.close()

    def load_all_fields(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 查询所有字段
        cursor.execute("SELECT * FROM fields_info")
        rows = cursor.fetchall()  # 一次性获取所有行

        columns = [col[0] for col in cursor.description]
        result = [dict(zip(columns, row)) for row in rows]

        conn.close()
        return result

    def get_fields_by_date_and_court(self, date, court_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 查询指定 date 和 court_id 的行
        cursor.execute(
            "SELECT * FROM fields_info WHERE date = ? AND court_id = ?",
            (date, court_id)
        )
        rows = cursor.fetchall()

        columns = [col[0] for col in cursor.description]
        result = [dict(zip(columns, row)) for row in rows]

        conn.close()
        return result

    def get_schedule(self, date, court_id):
        fields = self.get_fields_by_date_and_court(date, court_id)
        nested_dict = {}
        for f in fields:
            time = f["field_time"]
            name = f["field_name"]
            # 其他信息去掉 field_time 和 field_name
            info = {k: v for k, v in f.items() if k not in ("field_time", "field_name")}

            if time not in nested_dict:
                nested_dict[time] = {}
            nested_dict[time][name] = info
        return nested_dict


class CourtData(object):
    def __init__(self, places):
        self.db_path = "data/courts.db"
        places = list(map(lambda place: self.parse_data(place), places))
        self.save_to_db(places)   # 将场馆数据保存在sql数据库中

    @staticmethod
    def parse_data(place):
        address = place.get('address')
        image = "http://202.117.17.144:8080/web/upload/image/" + place['image'] if place.get('image') else None
        memo = place.get('memo')
        court_id = place.get('id')
        court_name = place.get('name')
        return {
            'court_id': court_id,
            'court_name': court_name,
            'address': address,
            'image': image,
            'memo': memo
        }

    def save_to_db(self, places):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS courts_info
                       (
                           court_id INTEGER PRIMARY KEY,
                           court_name TEXT NOT NULL,
                           address TEXT,
                           image TEXT,
                           memo TEXT
                       )
                       ''')
        cursor.executemany('''
                       INSERT INTO courts_info (court_id, court_name, address, image, memo)
                       VALUES (:court_id, :court_name, :address, :image, :memo)
                           ON CONFLICT(court_id) DO UPDATE SET
                            court_name = excluded.court_name,
                            address    = excluded.address,
                            image      = excluded.image,
                            memo       = excluded.memo;
                       ''', places)
        conn.commit()
        conn.close()

    def load_all_courts(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # 执行查询
        cursor.execute("SELECT * FROM courts_info")
        rows = cursor.fetchall()

        # 把每行转成字典
        columns = [col[0] for col in cursor.description]  # 获取列名
        result = [dict(zip(columns, row)) for row in rows]

        conn.close()
        return result

    def get_court_by_id(self, court_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 查询指定 court_id 的行
        cursor.execute("SELECT * FROM courts_info WHERE court_id = ?", (court_id,))
        row = cursor.fetchone()  # fetchone() 只返回一行

        if row is None:
            conn.close()
            return None  # 没有找到

        columns = [col[0] for col in cursor.description]
        result = dict(zip(columns, row))

        conn.close()
        return result





