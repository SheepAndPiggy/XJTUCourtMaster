class BaseProperty:
    def __init__(self, name, describe="", *, value_type=None):
        self.name = name

        self.describe = describe
        self._value_type = value_type

    def __get__(self, instance, owner):
        if instance is None:
            return self

        if self.name not in instance.__dict__:
            raise ValueError(f"{instance}中不存在名为{self.name}的属性！")
        value = instance.__dict__.get(self.name, None)
        return value

    def __set__(self, instance, value):
        if self.name in instance.__dict__:
            raise ValueError(f"{instance}中已经存在名为{self.name}的属性，不可重复赋值！")
        if self._value_type is not None and value is not None:
            if not isinstance(value, self._value_type):
                print(f"{self.name}的类型{type(value)}与设定类型{self._value_type}不匹配！")
                try:
                    value = self._value_type(value)
                except:
                    raise TypeError(f"{self.name}的类型{type(value)}无法转换为类型{self._value_type}！")
        instance.__dict__[self.name] = value


class CourtProperties:
    property_names = ["id", "name", "address", "memo", "image", "advanceday", "advancenum", "status", "expirydate"]
    id = BaseProperty("id", "场馆的唯一标识id", value_type=str)
    name = BaseProperty("name", "场馆的名称", value_type=str)
    address = BaseProperty("address", "场馆的地址", value_type=str)
    memo = BaseProperty("memo", "场馆的说明和备注", value_type=str)
    image = BaseProperty("image", "场馆图片的地址", value_type=str)
    advanceday = BaseProperty("advanceday", "可以提前预约的天数（不包含当天）", value_type=int)
    advancenum = BaseProperty("advancenum", "最多可以预约的场地数量", value_type=int)
    status = BaseProperty("status", "场馆的状态，1表示开放，2表示不开放", value_type=int)
    expirydate = BaseProperty("expirydate", "支付时间，单位为分钟", value_type=str)

    def __init__(self, court_data):
        try:
            self._parse_data(court_data)
        except Exception as e:
            print(f"解析数据{court_data}失败！")
            raise e

    @classmethod
    def get_all_properties(cls):
        properties = []
        for name in cls.property_names:
            properties.append(getattr(cls, name))
        return properties

    def _parse_data(self, court_data):
        for p in self.__class__.get_all_properties():
            name = p.name
            if name == "image":
                image_url = court_data.get(name)
                value = ("http://202.117.17.144:8080/web/upload/image/" + image_url) if image_url is not None else None
            else:
                value = court_data.get(name)
            setattr(self, name, value)

    @property
    def properties(self):
        result_dict = {}
        for p in self.__class__.get_all_properties():
            name = p.name
            value = self.__dict__.get(name)
            result_dict[name] = value
        return result_dict


class FieldProperties:
    out_properties = ["id", "name", "sname", "status", "stockid"]
    in_properties = ["s_date", "time_no", "price"]
    tot_properties = out_properties + in_properties

    # 外层属性
    id = BaseProperty("id", "场地的唯一标识id", value_type=int)
    name = BaseProperty("name", "场地的数字名称，例如'1','2'", value_type=str)
    sname = BaseProperty("sname", "场地的名称，例如'场地1','场地2'", value_type=str)
    status = BaseProperty("status", "场次的状态，1表示可预约，2表示不可预约", value_type=int)
    stockid = BaseProperty("stockid", "场次的唯一标识id", value_type=int)

    # stock的内层属性
    s_date = BaseProperty("s_date", "场次对应的日期", value_type=str)
    time_no = BaseProperty("time_no", "场次对应的时间", value_type=str)
    price = BaseProperty("price", "场次的价格", value_type=int)

    def __init__(self, field_data):
        try:
            self._parse_data(field_data)
        except Exception as e:
            print(f"解析数据{field_data}失败！")
            raise e

    @classmethod
    def get_all_properties(cls):
        properties = []
        for name in cls.tot_properties:
            properties.append(getattr(cls, name))
        return properties

    def _parse_data(self, field_data):
        for p in self.__class__.get_all_properties():
            name = p.name
            if name in self.__class__.out_properties:
                setattr(self, name, field_data.get(name))
            elif name in self.__class__.in_properties:
                setattr(self, name, field_data.get("stock", {}).get(name))

    @property
    def properties(self):
        result_dict = {}
        for p in self.__class__.get_all_properties():
            name = p.name
            value = self.__dict__.get(name)
            result_dict[name] = value
        return result_dict


class OrderProperties:
    orderid = BaseProperty("orderid", "", value_type=str)
    userid = BaseProperty("userid", "", value_type=str)
    status = BaseProperty("status", "", value_type=int)

    def __init__(self, order_data):
        try:
            self._parse_data(order_data)
        except Exception as e:
            print(f"解析数据{order_data}失败！")
            raise e

    def _parse_data(self, order_data):
        self.orderid = order_data.get("orderid")
        self.status = order_data.get("status")
        self.userid = order_data.get("userid")

    @property
    def properties(self):
        return {
            "orderid": self.orderid,
            "status": self.status,
            "userid": self.userid
        }


if __name__ == '__main__':
    pass
